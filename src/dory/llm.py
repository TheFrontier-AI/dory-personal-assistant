from __future__ import annotations

import base64
import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from .config import Settings

logger = logging.getLogger(__name__)
TRANSIENT = {408, 429, 500, 502, 503, 504}
RETRY_DELAYS = (2.0, 5.0, 10.0)
# Without a timeout one stuck Vertex call blocks forever (seen live: a voice-meeting
# transcription waited 3+ minutes for headers and froze the meeting's worker).
REQUEST_TIMEOUT_MS = 60_000
# Nemotron 3 reasons by default and spends the whole max_tokens budget on it (probe, 25 Oct 2026: a
# 50-token JSON gate came back empty); this request key is the one switch that turns it off.
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}
# Gemini model ids whose work a Token Factory text model cannot do (speech, images, embeddings, live).
_NOT_TEXT = ("tts", "image", "banana", "embedding", "live", "omni")


def make_client(s: Settings):
    """The Vertex Gemini client. With `DORY_NEBIUS_API_KEY` set it is wrapped in a `RoutedClient`
    so that `generate` sends text-only calls to Nemotron on Nebius Token Factory."""
    client = genai.Client(
        vertexai=True,
        project=s.gcp_project,
        location=s.gemini_location,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )
    if not s.nebius_api_key:
        return client
    route = Nemotron(
        s.nemotron_model, s.nebius_base_url, s.nebius_api_key, vision_model=s.nemotron_vision_model
    )
    return RoutedClient(client, route)


def make_agent_model(s: Settings, *, vision: bool = False):
    """The ADK model for `qa.build_agent`: Nemotron on Token Factory through ADK's LiteLlm adapter
    when the key is set, else None (the caller builds its Gemini model). `vision`: the message
    carries images, so the vision model (same tools, same price) is the brain for this turn.
    Reasoning stays ON here: with the full bot's ~140 tool declarations the model narrated actions
    instead of calling tools when it was off ("I'll set a reminder", no call;
    scripts/dory_tool_calls_probe.py, 25 Oct 2026). The text route below keeps it off (short JSON
    answers, no tools; the vision model returned nothing at all for a JSON schema with it on)."""
    if not s.nebius_api_key:
        return None
    from google.adk.models.lite_llm import LiteLlm  # heavy import, only when used

    return LiteLlm(
        model=f"openai/{s.nemotron_vision_model if vision else s.nemotron_model}",
        api_base=s.nebius_base_url,
        api_key=s.nebius_api_key,
        timeout=REQUEST_TIMEOUT_MS / 1000,
        drop_params=True,
    )


class RoutedClient:
    """A genai client plus the Nemotron route that `generate` consults. Every other attribute
    (`models`, `aio`, `_api_client`...) is the wrapped Vertex client's."""

    def __init__(self, inner, nemotron: Nemotron):
        self._inner = inner
        self.nemotron = nemotron

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TextResponse:
    """What `generate` returns from the Nemotron route: the genai response fields callers read."""

    def __init__(self, text: str, parsed, usage: dict, finish_reason: str | None):
        self.text = text
        self.parsed = parsed
        self.finish_reason = finish_reason
        self.candidates = [
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ]
        self.usage_metadata = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=usage.get("prompt_tokens"),
            candidates_token_count=usage.get("completion_tokens"),
            total_token_count=usage.get("total_tokens"),
        )


def _part_text(p) -> str | None:
    """The text of a str / Part, or None when it carries anything else."""
    if isinstance(p, str):
        return p
    if isinstance(p, types.Part) and p.text is not None:
        extras = (p.inline_data, p.file_data, p.function_call, p.function_response)
        return p.text if all(x is None for x in extras) else None
    return None


def _part_item(p) -> dict | None:
    """One OpenAI content item for a str / Part: text, or an inline image as a data URL. None for
    anything a Token Factory chat model cannot take (audio, video, PDF bytes, file URIs, calls)."""
    text = _part_text(p)
    if text is not None:
        return {"type": "text", "text": text}
    blob = getattr(p, "inline_data", None)
    if (
        isinstance(p, types.Part)
        and blob is not None
        and blob.data
        and (blob.mime_type or "").startswith("image/")
        and p.text is None
        and p.file_data is None
    ):
        b64 = base64.b64encode(blob.data).decode()
        return {"type": "image_url", "image_url": {"url": f"data:{blob.mime_type};base64,{b64}"}}
    return None


def _text_of(x) -> str | None:
    """Joined text of a str / Part / Content / list of those ("" for None), or None when any piece
    is not plain text."""
    if x is None:
        return ""
    if isinstance(x, types.Content):
        x = x.parts or []
    items = x if isinstance(x, list) else [x]
    texts = [_part_text(item) for item in items]
    return None if any(t is None for t in texts) else "\n".join(texts)


def _content(items: list[dict]):
    """Message content: a plain string when every item is text, else the list of items."""
    if all(i["type"] == "text" for i in items):
        return "\n".join(i["text"] for i in items)
    return list(items)  # a copy: the caller clears its buffer afterwards


def _messages(contents) -> list[dict] | None:
    """OpenAI chat messages for genai `contents` (text and inline images), or None when something
    in them is neither."""
    msgs: list[dict] = []
    pending: list[dict] = []

    def flush() -> None:
        if pending:
            msgs.append({"role": "user", "content": _content(pending)})
            pending.clear()

    for item in contents if isinstance(contents, list) else [contents]:
        if isinstance(item, types.Content):
            parts = [_part_item(p) for p in item.parts or []]
            if not parts or any(p is None for p in parts):
                return None
            flush()
            role = "assistant" if item.role == "model" else "user"
            msgs.append({"role": role, "content": _content(parts)})
        else:
            part = _part_item(item)
            if part is None:
                return None
            pending.append(part)
    flush()
    return msgs or None


def _has_image(msgs: list[dict]) -> bool:
    return any(isinstance(m["content"], list) for m in msgs)


def _strict(node):
    """Every object property required, recursively ($defs included). In OpenAI-style JSON-schema
    mode optional properties may be left out, and Nemotron then answered the memory day summary
    with `{}` (live, 25 Oct 2026); with them required it filled every field."""
    if isinstance(node, dict):
        if node.get("type") == "object" and isinstance(node.get("properties"), dict):
            node["required"] = list(node["properties"])
        for value in node.values():
            _strict(value)
    elif isinstance(node, list):
        for value in node:
            _strict(value)
    return node


def _response_format(schema) -> dict:
    if hasattr(schema, "model_json_schema"):  # a pydantic class, what every caller passes today
        name = getattr(schema, "__name__", "out")
        return {
            "type": "json_schema",
            "json_schema": {"name": name, "schema": _strict(schema.model_json_schema())},
        }
    if isinstance(schema, dict):
        strict = _strict(copy.deepcopy(schema))
        return {"type": "json_schema", "json_schema": {"name": "out", "schema": strict}}
    return {"type": "json_object"}


@dataclass
class Nemotron:
    """`generate` calls on NVIDIA Nemotron via Nebius Token Factory (OpenAI-compatible): text on
    `model`, text + images on `vision_model` (empty = images stay on Gemini). `accepts` decides
    per call; `complete` maps GenerateContentConfig to a chat completion; `embeddings` is the
    `/embeddings` endpoint for dory.embed."""

    model: str
    base_url: str
    api_key: str = field(repr=False)
    http: httpx.Client | None = None  # tests pass a client with a MockTransport
    vision_model: str = ""

    def __post_init__(self) -> None:
        if self.http is None:
            self.http = httpx.Client(base_url=self.base_url, timeout=REQUEST_TIMEOUT_MS / 1000)
        logger.info(
            "text calls and the chat agent run on %s via Nebius Token Factory (images: %s)",
            self.model,
            self.vision_model or "Gemini",
        )

    def _post(self, path: str, body: dict) -> dict:
        auth = {"Authorization": f"Bearer {self.api_key}"}
        r = self.http.post(path, json=body, headers=auth)
        if r.status_code != 200:
            detail = {
                "error": {"code": r.status_code, "message": r.text[:300], "status": "TOKEN_FACTORY"}
            }
            raise errors.APIError(r.status_code, detail, r)
        return r.json()

    def accepts(self, model: str, contents, config) -> bool:
        model = model or ""
        if not model.startswith("gemini") or any(x in model for x in _NOT_TEXT):
            return False
        if config is not None and (
            config.tools
            or config.response_modalities
            or config.speech_config
            or config.cached_content
        ):
            return False
        if config is not None and _text_of(config.system_instruction) is None:
            return False
        msgs = _messages(contents)
        return msgs is not None and (bool(self.vision_model) or not _has_image(msgs))

    def embeddings(self, model: str, texts: list[str], dim: int) -> list[list[float]]:
        """One vector per text from `/embeddings` (`dimensions` = Matryoshka truncation)."""
        data = self._post("embeddings", {"model": model, "input": texts, "dimensions": dim})
        rows = sorted(data.get("data") or [], key=lambda e: e.get("index", 0))
        return [e["embedding"] for e in rows]

    def complete(self, contents, config) -> TextResponse:
        msgs = _messages(contents)
        model = self.vision_model if _has_image(msgs) else self.model
        body: dict[str, Any] = {"model": model, "messages": msgs, **NO_THINK}
        schema = None
        if config is not None:
            system = _text_of(config.system_instruction)
            if system:
                body["messages"].insert(0, {"role": "system", "content": system})
            if config.temperature is not None:
                body["temperature"] = config.temperature
            if config.top_p is not None:
                body["top_p"] = config.top_p
            if config.max_output_tokens:
                body["max_tokens"] = config.max_output_tokens
            if config.stop_sequences:
                body["stop"] = list(config.stop_sequences)
            if config.response_mime_type == "application/json":
                schema = config.response_schema
                body["response_format"] = _response_format(schema)
        data = self._post("chat/completions", body)
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        parsed = None
        if schema is not None and hasattr(schema, "model_validate_json"):
            try:
                parsed = schema.model_validate_json(text)
            except Exception:  # noqa: BLE001  callers that need it re-parse resp.text themselves
                parsed = None
        return TextResponse(text, parsed, data.get("usage") or {}, choice.get("finish_reason"))


def media_http_options(**kw) -> types.HttpOptions:
    """HttpOptions for paid media creates (Omni hero clips, Lyria music): the request timeout
    and no SDK retry on 5xx / 408 / 409, because a retry after the service accepted the job would
    start (and bill) a second one. Only 429 (refused before any work) is retried, once:
    `attempts=1` is the fewest the SDK allows (0 is rewritten to 1). The SDK's Interactions
    client still retries a connection error or timeout once; that cannot be switched off here.
    `kw` goes to HttpOptions (tests pass an `httpx_client`)."""
    return types.HttpOptions(
        timeout=REQUEST_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(attempts=1, http_status_codes=[429]),
        **kw,
    )


def make_media_client(s: Settings) -> genai.Client:
    """The client for paid media creates (see `media_http_options`); polls and everything else
    use `make_client`."""
    return genai.Client(
        vertexai=True,
        project=s.gcp_project,
        location=s.gemini_location,
        http_options=media_http_options(),
    )


def with_retry(fn, delays=None):
    """Call `fn()`, retrying transient Vertex errors (429/5xx) after each delay in `delays`
    (None = `RETRY_DELAYS`, read at call time)."""
    delays = RETRY_DELAYS if delays is None else delays
    for attempt, delay in enumerate((*delays, None), start=1):
        try:
            return fn()
        except errors.APIError as e:
            if e.code not in TRANSIENT or delay is None:
                raise
            logger.warning("gemini transient %s, retry %d in %.0fs", e.code, attempt, delay)
            time.sleep(delay)
        except httpx.TimeoutException:
            if delay is None:
                raise
            logger.warning("gemini request timed out, retry %d in %.0fs", attempt, delay)
            time.sleep(delay)


def generate(client, model: str, contents, config, delays=RETRY_DELAYS):
    """generate_content with retry on transient errors (429/5xx). A client from `make_client` that
    carries a Nemotron route sends text and text + image calls there; audio, PDF bytes, tools and
    the speech / image-generation / embedding model ids stay on Gemini."""
    route = getattr(client, "nemotron", None)
    if route is not None and route.accepts(model, contents, config):
        return with_retry(lambda: route.complete(contents, config), delays)
    return with_retry(
        lambda: client.models.generate_content(model=model, contents=contents, config=config),
        delays,
    )


def embed(client, model: str, contents, config, delays=None):
    """embed_content with the same retry policy as `generate`."""
    return with_retry(
        lambda: client.models.embed_content(model=model, contents=contents, config=config), delays
    )
