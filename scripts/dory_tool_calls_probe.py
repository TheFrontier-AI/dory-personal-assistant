"""Live probe (billed): does the Nemotron brain CALL tools with the full bot assembly? Builds the
agent exactly like the web chat (headless bot, `SecretaryBot._agent_kwargs`), asks a few questions and
prints, per variant, the tool declarations sent, the first response's function calls and the final
text. Point DORY_DB_PATH at a COPY of a live ledger.db so the guild's feature flags (and so the full
tool list) apply; the default is an empty temp DB. DORY_PROBE_GUILD / DORY_PROBE_USER pick the guild
and asker; REPRO_QUESTIONS="q1|q2" the questions; the arguments select variants (A B C D E F).

    cp data/ledger.db /tmp/live-copy.db
    DORY_DB_PATH=/tmp/live-copy.db DORY_STORE=sqlite uv run python -I scripts/dory_tool_calls_probe.py A F

Finding, 25 Oct 2026: reasoning off = no tool calls with 141 declarations; reasoning on + the tool
rule (now `qa.NEMOTRON_TOOL_RULE`) = every tool called, greetings still tool-free."""

import logging
import os
import sys
import tempfile
import time

os.environ.setdefault(
    "DORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="dory-repro-"), "ledger.db")
)
os.environ["DORY_STORE"] = "sqlite"
logging.basicConfig(level=logging.ERROR)
for n in ("LiteLLM", "litellm", "httpx", "google_adk", "google.adk", "dory"):
    logging.getLogger(n).setLevel(logging.CRITICAL)

from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.genai import types  # noqa: E402

from dory import llm, qa  # noqa: E402
from dory.headless import agent_kwargs_in_thread, get_headless_bot, web_context  # noqa: E402

GID = int(os.environ.get("DORY_PROBE_GUILD", "1561374853263663175"))
UID = int(os.environ.get("DORY_PROBE_USER", "965514580585484348"))
DIRECTIVE = (
    "Tool rule: when the person asks you to DO something (remind, schedule, record, assign, "
    "search) or asks for a NUMBER or a FACT that a tool can fetch (spending, receipts, memory of "
    "past chat, tasks, files), you MUST call the matching tool in this turn and answer from its "
    "result. Never say you did, will do, or found something unless a tool call returned it. If no "
    "tool fits, say plainly that you cannot."
)
TRACE: list = []
MODE = {"directive": False, "force_first": False}


class Spy(LiteLlm):
    async def generate_content_async(self, llm_request, stream=False):
        decls = sum(
            len(getattr(t, "function_declarations", None) or [])
            for t in llm_request.config.tools or []
        )
        first = not any(e.get("req") for e in TRACE if e.get("run") == MODE.get("run"))
        if MODE["directive"]:
            llm_request.append_instructions([DIRECTIVE])
        if MODE["force_first"] and first and decls:
            llm_request.config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="ANY")
            )
        TRACE.append({"run": MODE.get("run"), "req": True, "decls": decls})
        async for resp in super().generate_content_async(llm_request, stream):
            parts = (resp.content.parts if resp.content else None) or []
            fcs = [p.function_call.name for p in parts if p.function_call]
            text = "".join(p.text or "" for p in parts if p.text)
            TRACE.append({"run": MODE.get("run"), "fcs": fcs, "text": text[:160]})
            yield resp


def model(think: bool) -> Spy:
    s = get_headless_bot().s
    kw = dict(api_base=s.nebius_base_url, api_key=s.nebius_api_key, timeout=120, drop_params=True)
    if not think:
        kw["extra_body"] = llm.NO_THINK
    return Spy(model=f"openai/{s.nemotron_model}", **kw)


def ask(question: str, m: Spy, keep_tools=None):
    bot = get_headless_bot()
    guild, member, channel = web_context(
        GID, "The Frontier Company Limited", uid=UID, name="hari", admin=False
    )
    message = bot.room_message(guild, member, channel)
    kw = agent_kwargs_in_thread(
        bot,
        message=message,
        guild=guild,
        asker=member,
        is_exec=False,
        setting="en",
        lang="en",
        question=question,
        memory=qa.MemoryTools(bot.memory_store, GID, {}, bot.s),
        profile=None,
    )
    kw.pop("chat_actions", None)
    kw.pop("user_id", None)
    if keep_tools is not None:
        kw["extra_tools"] = [
            f for f in kw.get("extra_tools") or [] if getattr(f, "__name__", "") in keep_tools
        ]
    t = time.monotonic()
    ans = qa.ask(
        bot.s, bot.store, question, guild_id=GID, is_exec=False, user_id=UID, model=m, **kw
    )
    return ans, time.monotonic() - t, len(kw.get("extra_tools") or [])


QUESTIONS = os.environ.get(
    "REPRO_QUESTIONS",
    "Dory, remind me tomorrow at 9 to send the invoice|how much did we spend this week",
).split("|")
VARIANTS = [
    ("A baseline (think off)", dict(think=False), {}),
    ("B think on", dict(think=True), {}),
    ("C think off + directive", dict(think=False), {"directive": True}),
    ("D think off + force tool on 1st call", dict(think=False), {"force_first": True}),
    ("F think on + directive", dict(think=True), {"directive": True}),
    (
        "E think off, 12 tools only",
        dict(think=False),
        {
            "keep": {
                "set_reminder",
                "list_reminders",
                "cancel_reminder",
                "my_day",
                "list_tasks",
                "update_task",
                "catch_up",
                "chat_search",
                "chat_days",
                "search_everything",
                "spending_summary",
                "list_receipts",
            }
        },
    ),
]
only = set(sys.argv[1:])
for label, mk, mode in VARIANTS:
    if only and label[0] not in only:
        continue
    print(f"\n=== {label}")
    for q in QUESTIONS:
        MODE.update({"directive": False, "force_first": False, "run": f"{label}|{q}"})
        MODE.update({k: v for k, v in mode.items() if k != "keep"})
        try:
            ans, dt, ntools = ask(q, model(**mk), keep_tools=mode.get("keep"))
            reqs = [e for e in TRACE if e["run"] == MODE["run"] and e.get("req")]
            resps = [e for e in TRACE if e["run"] == MODE["run"] and "fcs" in e]
            print(
                f"  [{q[:38]}] {dt:.1f}s extra_tools={ntools} decls={reqs[0]['decls'] if reqs else '?'} "
                f"rounds={ans.rounds} tools={[n for n, _ in ans.tool_calls]} tok={ans.tokens_in}/{ans.tokens_out}"
            )
            print(
                f"     1st response fcs={resps[0]['fcs'] if resps else '?'} | final: {(ans.text or '')[:150]!r}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"  [{q[:38]}] FAILED {type(e).__name__}: {str(e)[:200]}")
