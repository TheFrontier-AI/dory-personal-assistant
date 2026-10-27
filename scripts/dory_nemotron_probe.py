"""Live probe: Dory's real agent on NVIDIA Nemotron via Nebius Token Factory. Billed; run by hand.

Nothing here touches the project environment: litellm (ADK's OpenAI-compatible adapter) and its
`mcp` import come from `uv run --with`.

    uv run --with litellm --with mcp python scripts/dory_nemotron_probe.py --offline       # wiring only
    uv run --with litellm --with mcp python scripts/dory_nemotron_probe.py --stage 0        # Nemotron catalogue
    uv run --with litellm --with mcp python scripts/dory_nemotron_probe.py --stage 1 [--models a,b]
    uv run --with litellm --with mcp python scripts/dory_nemotron_probe.py --stage 2 [--models a,b] [--no-think]

Stage 1 = raw API: tool call, JSON-schema gate, Thai reply, and which knob switches reasoning off.
Stage 2 = the real `qa.ask` agent (ADK) on a throwaway seeded SQLite ledger, six questions.
The key comes from DORY_NEBIUS_API_KEY (env, else a line in .env) and is never printed.
Results: stdout + data/nemotron_probe.json (data/ is gitignored for .db only: delete the json after).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

BASE = "https://api.tokenfactory.nebius.com/v1/"
OUT = REPO / "data" / "nemotron_probe.json"
ALICE, BOB = 100, 200  # dory_seed_demo's two staff ids (guild 0)
NO_THINK = {
    "chat_template_kwargs": {"enable_thinking": False}
}  # vLLM-style knob, verified in stage 1


def api_key() -> str:
    names = ("DORY_NEBIUS_API_KEY",)
    k = next((os.environ[n].strip() for n in names if os.environ.get(n, "").strip()), "")
    if not k and (REPO / ".env").exists():
        for line in (REPO / ".env").read_text().splitlines():
            key, _, value = line.partition("=")
            if key in names and value.strip():
                k = value.strip().strip('"').strip("'")
                break
    if not k:
        sys.exit(
            "DORY_NEBIUS_API_KEY missing: export it, or add a DORY_NEBIUS_API_KEY=... line to .env"
        )
    return k


def short(e: BaseException) -> str:
    return f"{type(e).__name__}: {str(e)[:300]}"


def thai(s: str | None) -> bool:
    return any("฀" <= ch <= "๿" for ch in (s or ""))


# ---------------------------------------------------------------- stage 0: catalogue
def stage0(key: str) -> list[dict]:
    with httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {key}"}, timeout=30) as c:
        r = c.get("models", params={"verbose": "true"})
        r.raise_for_status()
        rows = r.json().get("data", [])
    nem = [m for m in rows if "nemotron" in m.get("id", "").lower()]
    print(f"{len(rows)} models on Token Factory, {len(nem)} Nemotron:")
    for m in nem:
        p = m.get("pricing") or {}
        lim = m.get("per_request_limits") or {}
        print(
            f"  {m['id']}: ctx={m.get('context_length')} ${float(p.get('prompt', 0)) * 1e6:.2f}/M in "
            f"${float(p.get('completion', 0)) * 1e6:.2f}/M out rpm={lim.get('requests_per_minute')} "
            f"features={m.get('supported_features')} modality={(m.get('architecture') or {}).get('modality')}"
        )
    return nem


# ---------------------------------------------------------------- stage 1: raw API
TOOL = {
    "type": "function",
    "function": {
        "name": "spending_summary",
        "description": "Total spending of the team between two dates, optionally grouped.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "group_by": {"type": "string", "enum": ["none", "category", "person"]},
            },
            "required": ["start_date", "end_date"],
        },
    },
}
GATE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "yes",
        "schema": {
            "type": "object",
            "properties": {"answer": {"type": "boolean"}},
            "required": ["answer"],
        },
    },
}
GATE_MSGS = [
    {"role": "system", "content": "Answer only with JSON matching the schema."},
    {
        "role": "user",
        "content": "Is this message addressed to Dory? Message: 'ดอรี่ ช่วยสรุปค่าใช้จ่ายเดือนนี้หน่อย'",
    },
]


def chat(c: httpx.Client, **body) -> tuple[dict, float]:
    t = time.monotonic()
    r = c.post("chat/completions", json=body)
    dt = time.monotonic() - t
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json(), dt


def summarize(j: dict, dt: float) -> dict:
    ch = j["choices"][0]
    msg = ch["message"]
    u = j.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    return {
        "s": round(dt, 2),
        "finish": ch.get("finish_reason"),
        "content": (msg.get("content") or "")[:400],
        "reasoning_chars": len(msg.get("reasoning_content") or msg.get("reasoning") or ""),
        "reasoning_tokens": det.get("reasoning_tokens"),
        "tokens": (u.get("prompt_tokens"), u.get("completion_tokens")),
        "tool_calls": [
            (x["function"]["name"], x["function"]["arguments"]) for x in msg.get("tool_calls") or []
        ],
    }


def stage1(key: str, models: list[str]) -> dict:
    out: dict = {}
    with httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {key}"}, timeout=120) as c:
        for mid in models:
            res: dict = {}
            print(f"\n== stage 1: {mid}")

            def probe(name: str, ok, *, mid=mid, res=res, **body):
                try:
                    j, dt = chat(c, model=mid, **body)
                    s = summarize(j, dt)
                    s["ok"] = bool(ok(s))
                except Exception as e:
                    s = {"ok": False, "error": short(e)}
                res[name] = s
                shown = {k: v for k, v in s.items() if k != "content"}
                print(f"  {name}: {shown}")
                if s.get("content"):
                    print("     content:", s["content"][:200].replace("\n", " | "))

            sysmsg = {
                "role": "system",
                "content": "You are Dory, a company assistant. Today is 2026-10-25. Use tools for numbers.",
            }
            ask = {"role": "user", "content": "How much did we spend this week, by category?"}
            probe(
                "tool_call",
                lambda s: s["tool_calls"],
                messages=[sysmsg, ask],
                tools=[TOOL],
                tool_choice="auto",
                temperature=0.2,
                max_tokens=600,
            )
            probe(
                "json_gate",
                lambda s: (
                    '"answer": true'
                    in s["content"].replace(" ", "").replace('"answer":true', '"answer": true')
                ),
                messages=GATE_MSGS,
                response_format=GATE_SCHEMA,
                temperature=0,
                max_tokens=400,
            )
            # reasoning off, two candidate knobs; "ok" = answered with no reasoning tokens
            probe(
                "json_gate_nothink_kwarg",
                lambda s: s["content"] and not s["reasoning_tokens"],
                messages=GATE_MSGS,
                response_format=GATE_SCHEMA,
                temperature=0,
                max_tokens=100,
                **NO_THINK,
            )
            probe(
                "json_gate_nothink_prompt",
                lambda s: s["content"] and not s["reasoning_tokens"],
                messages=[
                    {"role": "system", "content": "/no_think\n" + GATE_MSGS[0]["content"]},
                    GATE_MSGS[1],
                ],
                response_format=GATE_SCHEMA,
                temperature=0,
                max_tokens=100,
            )
            probe(
                "thai",
                lambda s: thai(s["content"]) and "thinking" not in s["content"].lower(),
                messages=[
                    {
                        "role": "system",
                        "content": "คุณชื่อดอรี่ เป็นผู้ช่วยในบริษัท ตอบสั้นๆ ภาษาไทย ลงท้ายด้วย ค่ะ",
                    },
                    {"role": "user", "content": "ดอรี่ แนะนำตัวสั้นๆ แล้วบอกว่าช่วยอะไรได้บ้าง 2 ข้อ"},
                ],
                temperature=0.6,
                max_tokens=600,
            )
            out[mid] = res
    return out


# ---------------------------------------------------------------- stage 2: the real agent
QUESTIONS = [  # (label, question, is_exec, user_id, language)
    ("en exec summary", "How much did we spend this week, by category?", True, 1, "en"),
    ("th exec who+dupes", "เดือนนี้ใครใช้จ่ายเยอะที่สุด และมีใบเสร็จที่น่าสงสัยหรือซ้ำไหม", True, 1, "th"),
    ("en staff scoped", "What did I spend this week?", False, ALICE, "en"),
    ("th compare", "เทียบค่าใช้จ่ายสัปดาห์นี้กับสัปดาห์ก่อนให้หน่อย", True, 1, "th"),
    ("en small talk", "Hi Dory, how is it going today?", True, 1, "en"),
    ("en staff forbidden", "Void receipt 1, it was a mistake.", False, BOB, "en"),
]


def build(models: list[str], key: str, no_think: bool):
    import dory_seed_demo  # scripts/
    from google.adk.models.lite_llm import LiteLlm

    from dory.config import Settings
    from dory.store import SQLiteStore

    db = Path(tempfile.mkdtemp(prefix="dory-probe-")) / "ledger.db"
    dory_seed_demo.main(str(db))
    settings = Settings(_env_file=None, store="sqlite", db_path=str(db))
    store = SQLiteStore(str(db))
    extra = {"extra_body": NO_THINK} if no_think else {}
    llms = {
        mid: LiteLlm(
            model=f"openai/{mid}",
            api_base=BASE,
            api_key=key,
            timeout=120,
            drop_params=True,
            **extra,
        )
        for mid in (models or ["nvidia/placeholder"])
    }
    return settings, store, llms


def offline_check(settings, store, llms) -> None:
    from dory import qa

    ledger = qa.LedgerTools(store, 0)
    agent = qa.build_agent(
        settings, qa.build_tools(ledger), scoped=False, model=next(iter(llms.values()))
    )
    prompt = agent.instruction(None) if callable(agent.instruction) else agent.instruction
    print(
        f"offline: {len(agent.tools)} tools, model={agent.model.model}, prompt={len(prompt)} chars, "
        f"rows={ledger.spending_summary('2020-01-01', '2030-01-01').get('count')}"
    )


def stage2(settings, store, llms: dict) -> dict:
    from dory import qa

    out: dict = {}
    for mid, llm in llms.items():
        print(f"\n== stage 2: {mid}")
        rows = []
        for label, q, is_exec, uid, lang in QUESTIONS:
            t = time.monotonic()
            try:
                ans = qa.ask(
                    settings,
                    store,
                    q,
                    guild_id=0,
                    is_exec=is_exec,
                    user_id=uid,
                    model=llm,
                    language=lang,
                )
                row = {
                    "label": label,
                    "ok": True,
                    "s": round(time.monotonic() - t, 1),
                    "rounds": ans.rounds,
                    "tools": [n for n, _ in ans.tool_calls],
                    "tokens": (ans.tokens_in, ans.tokens_out),
                    "answer": (ans.text or "")[:600],
                }
            except Exception as e:
                row = {
                    "label": label,
                    "ok": False,
                    "s": round(time.monotonic() - t, 1),
                    "error": short(e),
                    "trace": traceback.format_exc()[-1200:],
                }
            rows.append(row)
            print(
                f"  [{label}] ok={row['ok']} {row['s']}s rounds={row.get('rounds')} tools={row.get('tools')} tokens={row.get('tokens')}"
            )
            print("    " + (row.get("answer") or row.get("error", "")).replace("\n", "\n    "))
        out[mid] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="0,1,2")
    ap.add_argument(
        "--models",
        default="",
        help="comma list of Token Factory ids; default = Nemotron text models from stage 0",
    )
    ap.add_argument("--no-think", action="store_true", help="stage 2 with reasoning switched off")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    for name in ("LiteLLM", "google_adk", "google.adk", "httpx", "litellm"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    models = [m.strip() for m in a.models.split(",") if m.strip()]
    if a.offline:
        offline_check(*build(models, "offline-no-key", a.no_think))
        return
    key = api_key()
    stages = {int(s) for s in a.stage.split(",") if s.strip()}
    results: dict = {}
    if 0 in stages:
        nem = stage0(key)
        results["models"] = nem
        if not models:
            models = [
                m["id"]
                for m in nem
                if "nemotron-3" in m["id"].lower()
                and not any(x in m["id"].lower() for x in ("base", "vl", "omni", "ultra"))
            ]
            print("default --models:", models)
    if not models and stages & {1, 2}:
        sys.exit("no models: run --stage 0 first or pass --models")
    if 1 in stages:
        results["stage1"] = stage1(key, models)
    if 2 in stages:
        results["stage2"] = stage2(*build(models, key, a.no_think))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    print(f"\nresults -> {OUT}")


if __name__ == "__main__":
    main()
