"""A hard spending cap for the live (billed) probes: every Token Factory call goes through `Meter`.

Both paths are wrapped: the agent's (ADK `LiteLLMClient.acompletion`) and the text / gate /
embedding calls (`dory.llm.Nemotron._post`). Before a call the meter adds a WORST-CASE estimate
(prompt characters / 2.5 tokens, plus `max_tokens`, forced to at most MAX_OUT) to what was already
spent and refuses the call (`BudgetExceeded`) when that could pass the cap. After the call it adds
the real usage. Prices are the GLM-5.3 list prices with NO cache discount, applied to every model
(the cheaper Flash and embedding calls are over-counted), so the real bill is at most the meter's.
LiteLLM's own retries are switched off; `retries` transient errors per call are retried here and
counted. `dry=True` sends nothing: it records the request sizes and answers "ok" with no tool call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

IN_PER_M, OUT_PER_M = 1.40, 4.40  # USD per million tokens (GLM-5.3, Token Factory, 29 Oct 2026)
MAX_OUT = 4096  # output tokens allowed per call (GLM thinking tokens count here too)
CHARS_PER_TOKEN = 2.5  # pessimistic: Thai prompt parts and JSON pack fewer characters per token


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Meter:
    cap_usd: float = 2.0
    max_calls: int = 40
    retries: int = 1
    dry: bool = False
    spent: float = 0.0
    calls: list[dict] = field(default_factory=list)  # one row per attempt: kind, tokens, usd, ms

    @staticmethod
    def cost(prompt_tokens: int, out_tokens: int) -> float:
        return (prompt_tokens * IN_PER_M + out_tokens * OUT_PER_M) / 1_000_000

    def _admit(self, kind: str, prompt_chars: int) -> float:
        if len(self.calls) >= self.max_calls:
            raise BudgetExceeded(f"call cap {self.max_calls} reached")
        worst = self.cost(int(prompt_chars / CHARS_PER_TOKEN) + 1, MAX_OUT)
        if self.spent + worst > self.cap_usd:
            raise BudgetExceeded(f"{kind}: ${self.spent:.4f} spent + ${worst:.4f} worst case > cap")
        return worst

    def _book(self, kind: str, usage: dict | None, prompt_chars: int, t0: float, error="") -> None:
        p = int((usage or {}).get("prompt_tokens") or 0)
        o = int((usage or {}).get("completion_tokens") or 0)
        if usage is None:  # no usage reported (an error after sending): count the worst case
            p, o = int(prompt_chars / CHARS_PER_TOKEN) + 1, MAX_OUT if not error else 0
        usd = self.cost(p, o)
        self.spent += usd
        self.calls.append({"kind": kind, "prompt_tokens": p, "out_tokens": o, "usd": usd,
                           "prompt_chars": prompt_chars, "ms": int((time.monotonic() - t0) * 1000),
                           "error": error})  # fmt: skip

    def install(self, monkeypatch) -> Meter:
        from google.adk.models import lite_llm

        from dory import llm

        meter = self
        real_acompletion = lite_llm.LiteLLMClient.acompletion
        real_post = llm.Nemotron._post

        async def acompletion(client, model, messages, tools=None, **kwargs):
            chars = len(json.dumps(messages, default=str)) + len(
                json.dumps(tools or [], default=str)
            )
            kwargs["max_tokens"] = min(int(kwargs.get("max_tokens") or MAX_OUT), MAX_OUT)
            kwargs["num_retries"] = 0
            for attempt in range(meter.retries + 1):
                meter._admit("agent", chars)
                t0 = time.monotonic()
                if meter.dry:
                    meter._book(
                        "agent(dry)", {"prompt_tokens": 0, "completion_tokens": 0}, chars, t0
                    )
                    return _dry_response()
                try:
                    res = await real_acompletion(client, model, messages, tools=tools, **kwargs)
                except Exception as e:  # noqa: BLE001 - counted, then retried or raised
                    meter._book("agent", None, chars, t0, error=type(e).__name__)
                    if attempt == meter.retries or not _transient(e):
                        raise
                    continue
                usage = getattr(res, "usage", None)  # a stream has none: the worst case is booked
                meter._book("agent", (usage.model_dump() if hasattr(usage, "model_dump") else
                                      dict(usage)) if usage else None, chars, t0)  # fmt: skip
                return res
            raise AssertionError("unreachable")

        def post(nemo, path, body):
            chars = len(json.dumps(body, default=str))
            if "max_tokens" in body:
                body["max_tokens"] = min(int(body["max_tokens"]), MAX_OUT)
            kind = "embed" if path.startswith("embeddings") else "text"
            for attempt in range(meter.retries + 1):
                meter._admit(kind, chars)
                t0 = time.monotonic()
                if meter.dry:
                    meter._book(
                        kind + "(dry)", {"prompt_tokens": 0, "completion_tokens": 0}, chars, t0
                    )
                    raise BudgetExceeded("dry run: text calls are not answered")
                try:
                    data = real_post(nemo, path, body)
                except Exception as e:  # noqa: BLE001
                    meter._book(kind, None, chars, t0, error=type(e).__name__)
                    if attempt == meter.retries or not _transient(e):
                        raise
                    continue
                meter._book(kind, data.get("usage") or None, chars, t0)
                return data
            raise AssertionError("unreachable")

        monkeypatch.setattr(lite_llm.LiteLLMClient, "acompletion", acompletion)
        monkeypatch.setattr(llm.Nemotron, "_post", post)
        return meter

    def report(self) -> str:
        rows = [f"{c['kind']:<11} in={c['prompt_tokens']:>7} out={c['out_tokens']:>5} "
                f"${c['usd']:.4f} {c['ms']:>6} ms {c['error']}" for c in self.calls]  # fmt: skip
        return "\n".join([*rows, f"TOTAL ${self.spent:.4f} of ${self.cap_usd:.2f} cap, "
                                 f"{len(self.calls)} calls"])  # fmt: skip


def _transient(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(e, "code", None)
    return status in (408, 409, 429, 500, 502, 503, 504) or "Timeout" in type(e).__name__


def _dry_response():
    from litellm import ModelResponse

    return ModelResponse(
        choices=[
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}
        ],  # fmt: skip
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )
