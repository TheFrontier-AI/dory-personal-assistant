"""dory.llm: request timeout and retry behaviour, and the Nemotron route (offline)."""

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types
from pydantic import BaseModel

from dory import llm
from dory.config import Settings


class Models:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def generate_content(self, **kw):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_client_has_a_request_timeout():
    client = llm.make_client(Settings(gcp_project="p", gemini_location="global"))
    assert client._api_client._http_options.timeout == llm.REQUEST_TIMEOUT_MS


def test_chat_agent_model_calls_have_the_request_timeout_and_keep_retries(seeded, settings):
    """The ADK chat agent built its own genai client with no timeout: one stuck Vertex call left
    the answer (and its worker thread) hanging. The timeout rides on every request's config."""
    from conftest import EXEC_ID, GUILD, scripted, text_resp

    from dory.qa import RETRY_OPTIONS, ask, build_agent

    agent = build_agent(settings, [], scoped=False)
    assert agent.model.retry_options is RETRY_OPTIONS  # 429 / 5xx are still retried
    assert agent.generate_content_config.http_options.timeout == llm.REQUEST_TIMEOUT_MS
    model = scripted(text_resp("ok"))
    ask(settings, seeded, "x", guild_id=GUILD, is_exec=True, user_id=EXEC_ID, model=model)
    assert model.requests[0].config.http_options.timeout == llm.REQUEST_TIMEOUT_MS


def test_timeout_is_retried(monkeypatch):
    """A hung call used to block a voice meeting's worker forever; now it times out and retries."""
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    ok = SimpleNamespace(text="hi")
    client = SimpleNamespace(models=Models([httpx.ReadTimeout("slow"), ok]))
    assert llm.generate(client, "m", "x", None) is ok
    assert client.models.calls == 2


def test_timeout_raises_after_all_retries(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    n = len(llm.RETRY_DELAYS) + 1
    client = SimpleNamespace(models=Models([httpx.ReadTimeout("slow")] * n))
    with pytest.raises(httpx.TimeoutException):
        llm.generate(client, "m", "x", None)
    assert client.models.calls == n


def test_meeting_transcription_uses_the_regional_client():
    from dory.meeting import MeetingManager

    s = Settings(gcp_project="p", gemini_location="global", transcribe_location="asia-southeast1")
    shared = object()
    mgr = MeetingManager(SimpleNamespace(s=s, llm=shared))
    stt = mgr.stt_client
    assert stt is not shared and stt is mgr.stt_client  # created once
    assert stt._api_client.location == "asia-southeast1"
    same = MeetingManager(
        SimpleNamespace(s=s.model_copy(update={"transcribe_location": ""}), llm=shared)
    )
    assert same.stt_client is shared


# ---------------------------------------------------------------- Nemotron on Nebius Token Factory
TF = "https://tf.example/v1/"


class _Yes(BaseModel):
    answer: bool


def _nemotron(handler, vision="nvidia/x-vl") -> llm.Nemotron:
    http = httpx.Client(base_url=TF, transport=httpx.MockTransport(handler))
    return llm.Nemotron("nvidia/x", TF, "k", http=http, vision_model=vision)


def _reply(content, status=200):
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }
    return httpx.Response(status, json=body)


def _routed(handler, inner_script=(), vision="nvidia/x-vl"):
    inner = SimpleNamespace(models=Models(inner_script))
    return llm.RoutedClient(inner, _nemotron(handler, vision)), inner


def test_without_a_nebius_key_the_client_is_the_plain_vertex_client():
    client = llm.make_client(Settings(_env_file=None, gcp_project="p", nebius_api_key=""))
    assert not hasattr(client, "nemotron")
    assert client._api_client._http_options.timeout == llm.REQUEST_TIMEOUT_MS


def test_the_routed_client_keeps_the_vertex_client_for_everything_else():
    s = Settings(_env_file=None, gcp_project="p", nebius_api_key="sekret-123")
    client = llm.make_client(s)
    assert client.nemotron.model == "zai-org/GLM-5.3"
    assert client.nemotron.fast_model == "zai-org/GLM-5.3-Flash"
    assert client._api_client._http_options.timeout == llm.REQUEST_TIMEOUT_MS  # delegated
    assert "sekret-123" not in repr(client.nemotron) and "sekret-123" not in repr(s)  # never logged


def test_text_only_calls_go_to_nemotron_with_schema_and_reasoning_off():
    seen = []

    def handler(req):
        seen.append(req)
        return _reply('{"answer": true}')

    client, inner = _routed(handler)
    cfg = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=50,
        response_mime_type="application/json",
        response_schema=_Yes,
        system_instruction="Answer JSON.",
    )
    resp = llm.generate(client, "gemini-3.5-flash-lite", "is this for Dory?", cfg)
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.path == "/v1/chat/completions" and req.headers["authorization"] == "Bearer k"
    assert body["model"] == "nvidia/x" and body["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert body["messages"] == [
        {"role": "system", "content": "Answer JSON."},
        {"role": "user", "content": "is this for Dory?"},
    ]
    assert body["temperature"] == 0 and body["max_tokens"] == 50
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "_Yes"
    assert (
        body["response_format"]["json_schema"]["schema"]["properties"]["answer"]["type"]
        == "boolean"
    )
    assert resp.text == '{"answer": true}' and resp.parsed.answer is True
    assert resp.candidates[0].content.parts[0].text == resp.text
    assert resp.usage_metadata.total_token_count == 10
    assert inner.models.calls == 0


def test_chat_history_contents_become_user_and_assistant_turns():
    seen = []
    client, _ = _routed(lambda r: (seen.append(r), _reply("ok"))[1])
    contents = [
        types.Content(role="user", parts=[types.Part(text="a")]),
        types.Content(role="model", parts=[types.Part(text="b")]),
        "c",
    ]
    assert llm.generate(client, "gemini-3.5-flash", contents, None).text == "ok"
    assert json.loads(seen[0].content)["messages"] == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]


@pytest.mark.parametrize(
    ("model", "contents", "config"),
    [
        ("gemini-2.5-flash-tts", "hi", None),  # speech
        ("gemini-embedding-001", "hi", None),  # embeddings
        ("gemini-nano-banana-2.1", "hi", None),  # image generation
        (
            "gemini-3.5-flash",
            [types.Part.from_bytes(data=b"%PDF", mime_type="application/pdf"), "read"],
            None,
        ),  # PDF bytes
        (
            "gemini-3.5-flash",
            [types.Part.from_bytes(data=b"fLaC", mime_type="audio/flac"), "transcribe"],
            None,
        ),  # audio
        (
            "gemini-3.5-flash",
            "hi",
            types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        ),  # grounded search
    ],
)
def test_non_text_work_stays_on_gemini(model, contents, config):
    ok = SimpleNamespace(text="gemini")
    client, inner = _routed(lambda r: _reply("nemotron"), [ok])
    assert llm.generate(client, model, contents, config) is ok
    assert inner.models.calls == 1


def test_images_go_to_the_vision_model_as_data_urls():
    seen = []
    client, inner = _routed(lambda r: (seen.append(r), _reply('{"total": 246.1}'))[1])
    parts = [types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png"), "read the receipt"]
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Yes)
    resp = llm.generate(client, "gemini-3.5-flash", parts, cfg)
    body = json.loads(seen[0].content)
    assert (
        body["model"] == "nvidia/x-vl"
        and body["chat_template_kwargs"] == llm.NO_THINK["chat_template_kwargs"]
    )
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw=="}},
                {"type": "text", "text": "read the receipt"},
            ],
        }
    ]
    assert body["response_format"]["type"] == "json_schema" and resp.text == '{"total": 246.1}'
    assert inner.models.calls == 0


def test_without_a_vision_model_images_stay_on_gemini():
    ok = SimpleNamespace(text="gemini")
    client, inner = _routed(lambda r: _reply("nemotron"), [ok], vision="")
    parts = [types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png"), "what is this"]
    assert llm.generate(client, "gemini-3.5-flash", parts, None) is ok
    assert inner.models.calls == 1


def test_nemotron_transient_errors_are_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    replies = [httpx.Response(503, text="busy"), _reply("ok")]
    client, _ = _routed(lambda r: replies.pop(0))
    assert llm.generate(client, "gemini-3.5-flash", "hi", None).text == "ok"
    assert not replies


def test_nemotron_client_errors_raise_api_errors_without_retry():
    calls = []
    client, _ = _routed(lambda r: (calls.append(r), httpx.Response(400, text="bad"))[1])
    with pytest.raises(errors.APIError) as e:
        llm.generate(client, "gemini-3.5-flash", "hi", None)
    assert e.value.code == 400 and len(calls) == 1


def test_glm_brains_get_the_fast_tier_low_effort_and_a_token_floor():
    seen = []
    http = httpx.Client(
        base_url=TF, transport=httpx.MockTransport(lambda r: (seen.append(r), _reply("ok"))[1])
    )
    route = llm.Nemotron("zai-org/GLM-5.3", TF, "k", http=http, fast_model="zai-org/GLM-5.3-Flash")
    client = llm.RoutedClient(SimpleNamespace(models=Models([])), route)
    cfg = types.GenerateContentConfig(max_output_tokens=50, system_instruction="yes or no")
    llm.generate(client, "gemini-3.5-flash-lite", "hi", cfg)
    llm.generate(client, "gemini-3.5-flash", "hi", cfg)  # every text call: one tenth of the price
    bodies = [json.loads(r.content) for r in seen]
    assert [b["model"] for b in bodies] == ["zai-org/GLM-5.3-Flash", "zai-org/GLM-5.3-Flash"]
    assert bodies[0]["reasoning_effort"] == "low"  # GLM has no off switch
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert bodies[0]["max_tokens"] == llm.GLM_MIN_TOKENS  # thinking tokens count against it
    route.fast_model = ""
    llm.generate(client, "gemini-3.5-flash", "hi", cfg)
    assert json.loads(seen[-1].content)["model"] == "zai-org/GLM-5.3"  # no fast model: the brain
    assert llm.reasoning("nvidia/nemotron-3-super-120b-a12b", False) == llm.NO_THINK
    assert llm.reasoning("zai-org/GLM-5.3", True) == {"reasoning_effort": "low"}  # the cost default
    assert llm.reasoning("zai-org/GLM-5.3", True, "high") == {"reasoning_effort": "high"}


def test_agent_brain_is_the_token_factory_brain_when_the_key_is_set():
    from dory.qa import build_agent

    agent = build_agent(Settings(_env_file=None, nebius_api_key="k"), [], scoped=False)
    m = agent.model
    assert type(m).__name__ == "LiteLlm"
    assert m.model == "openai/zai-org/GLM-5.3"
    args = m._additional_args
    assert args["api_base"] == "https://api.tokenfactory.nebius.com/v1/" and args["api_key"] == "k"
    assert args["reasoning_effort"] == "low" and args["drop_params"] is True  # on, low
    assert "extra_body" not in args
    assert "Tool rule:" in agent.instruction(None)  # the rule that makes it call tools
    nemotron = build_agent(
        Settings(
            _env_file=None, nebius_api_key="k", brain_model="nvidia/nemotron-3-super-120b-a12b"
        ),
        [],
        scoped=False,
    )
    assert "reasoning_effort" not in nemotron.model._additional_args  # Nemotron: on by default
    gemini_agent = build_agent(Settings(_env_file=None, nebius_api_key=""), [], scoped=False)
    assert type(gemini_agent.model).__name__ == "Gemini"
    assert "Tool rule:" not in gemini_agent.instruction(None)


def test_the_vision_model_is_the_brain_for_a_turn_with_images_and_gemini_for_pdfs():
    from dory.qa import attachment_kind, build_agent

    s = Settings(_env_file=None, nebius_api_key="k")
    assert build_agent(s, [], scoped=False, attachments="images").model.model == (
        "openai/nvidia/Nemotron-3.5-Super-VL"
    )
    assert type(build_agent(s, [], scoped=False, attachments="other").model).__name__ == "Gemini"
    png = types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png")
    pdf = types.Part.from_bytes(data=b"%PDF", mime_type="application/pdf")
    assert attachment_kind([types.Part(text="label"), png]) == "images"
    assert attachment_kind([png, pdf]) == "other"
    assert attachment_kind([types.Part(text="only text")]) == ""


def test_json_schemas_mark_every_property_required_so_nemotron_fills_them():
    """Live, 25 Oct 2026: with pydantic's schema as is (optional fields not required) Nemotron
    answered the memory day summary with `{}`; with every property required it filled it."""

    class Item(BaseModel):
        what: str
        who: str = ""

    class Doc(BaseModel):
        overview: str = ""
        items: list[Item] = []

    sch = llm._response_format(Doc)["json_schema"]["schema"]
    assert sch["required"] == ["overview", "items"]
    assert sch["$defs"]["Item"]["required"] == ["what", "who"]
    raw = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert llm._response_format(raw)["json_schema"]["schema"]["required"] == ["a"]
    assert "required" not in raw  # the caller's dict is not mutated
    assert llm._response_format(list[Item]) == {"type": "json_object"}
