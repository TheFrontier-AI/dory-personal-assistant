"""Embeddings for memory search: Vertex embedder (batching, task types, retry), the kill switch,
vector packing and cosine. Offline: a fake genai client."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from dory import llm
from dory.config import Settings
from dory.embed import (
    QUERY_INSTRUCT,
    NullEmbedder,
    TokenFactoryEmbedder,
    VertexEmbedder,
    cosine,
    make_embedder,
    normalize,
    pack,
    unpack,
)


class FakeEmbedClient:
    def __init__(self, *script):
        self.script, self.calls = list(script), []
        self.models = self

    def embed_content(self, model, contents, config):
        self.calls.append((model, list(contents), config))
        item = self.script.pop(0) if self.script else None
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0]) for _ in contents])


def test_vertex_embedder_batches_and_sets_task_and_dim():
    c = FakeEmbedClient()
    vecs = VertexEmbedder(c, "m", 2, batch=2).embed(["a", "b", "c", "d", "e"], "document")
    assert [len(x[1]) for x in c.calls] == [2, 2, 1] and len(vecs) == 5
    cfg = c.calls[0][2]
    assert cfg.task_type == "RETRIEVAL_DOCUMENT" and cfg.output_dimensionality == 2
    assert vecs[0].typecode == "f" and abs(cosine(vecs[0], vecs[0]) - 1.0) < 1e-6  # normalised


def test_query_task_and_model_id():
    c = FakeEmbedClient()
    e = VertexEmbedder(c, "gemini-embedding-001", 2)
    e.embed(["q"], "query")
    assert c.calls[0][2].task_type == "RETRIEVAL_QUERY" and e.model_id == "gemini-embedding-001@2"


def test_transient_errors_are_retried(monkeypatch):
    monkeypatch.setattr("dory.llm.RETRY_DELAYS", (0.0,))
    c = FakeEmbedClient(errors.ClientError(429, {"error": {"message": "quota"}}))
    assert len(VertexEmbedder(c, "m", 2).embed(["a"], "document")) == 1 and len(c.calls) == 2


def test_vertex_embedder_rejects_a_short_response():
    c = FakeEmbedClient()
    c.embed_content = lambda model, contents, config: SimpleNamespace(embeddings=[])
    with pytest.raises(ValueError):
        VertexEmbedder(c, "m", 2).embed(["a"], "document")


def test_kill_switch_and_missing_client_give_the_null_embedder():
    assert isinstance(make_embedder(Settings(embed_model=""), object()), NullEmbedder)
    assert isinstance(make_embedder(Settings(), None), NullEmbedder)
    assert NullEmbedder().embed(["a"], "query") == [] and NullEmbedder().model_id == ""


def test_pack_roundtrip():
    vs = [normalize([1.0, 2.0]), normalize([0.0, 1.0])]
    back = unpack(pack(vs), 2)
    assert len(pack(vs)) == 16 and [list(v) for v in back] == [list(v) for v in vs]


def test_query_embeddings_fail_fast_without_retry(monkeypatch):
    monkeypatch.setattr("dory.llm.RETRY_DELAYS", (0.0,))
    c = FakeEmbedClient(errors.ClientError(429, {"error": {"message": "quota"}}))
    with pytest.raises(errors.ClientError):
        VertexEmbedder(c, "m", 2).embed(["q"], "query")
    assert len(c.calls) == 1  # an answer is waiting: no retry, the caller falls back to keywords


# ---------------------------------------------------------------- Token Factory embeddings
def _route(handler):
    import httpx

    http = httpx.Client(base_url="https://tf.example/v1/", transport=httpx.MockTransport(handler))
    return llm.Nemotron("nvidia/x", "https://tf.example/v1/", "k", http=http)


def _embeddings_reply(request):
    import json

    import httpx

    body = json.loads(request.content)
    rows = [{"index": i, "embedding": [3.0, 4.0]} for i, _ in enumerate(body["input"])]
    return httpx.Response(200, json={"data": list(reversed(rows)), "usage": {"prompt_tokens": 1}})


def test_token_factory_embedder_sends_dimensions_and_normalises():
    import json

    seen = []
    e = TokenFactoryEmbedder(
        _route(lambda r: (seen.append(r), _embeddings_reply(r))[1]), "Qwen/q", 2, batch=2
    )
    vecs = e.embed(["a", "b", "c"], "document")
    assert e.model_id == "Qwen/q@2" and len(seen) == 2  # two batches
    body = json.loads(seen[0].content)
    assert body == {"model": "Qwen/q", "input": ["a", "b"], "dimensions": 2}
    assert seen[0].url.path == "/v1/embeddings" and seen[0].headers["authorization"] == "Bearer k"
    assert len(vecs) == 3 and all(list(v) == pytest.approx([0.6, 0.8]) for v in vecs)  # unit length


def test_token_factory_queries_get_the_instruction_and_fail_fast(monkeypatch):
    import json

    import httpx

    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    seen = []
    e = TokenFactoryEmbedder(
        _route(lambda r: (seen.append(r), _embeddings_reply(r))[1]), "Qwen/q", 2
    )
    e.embed(["what did we decide"], "query")
    assert json.loads(seen[0].content)["input"] == [QUERY_INSTRUCT + "what did we decide"]
    busy = _route(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(errors.APIError):
        TokenFactoryEmbedder(busy, "Qwen/q", 2).embed(["q"], "query")  # no retry for a query


def test_make_embedder_prefers_token_factory_when_the_client_carries_the_route():
    s = Settings(_env_file=None, gcp_project="p", nebius_api_key="k", embed_dim=256)
    client = llm.make_client(s)
    e = make_embedder(s, client)
    assert isinstance(e, TokenFactoryEmbedder) and e.model_id == "Qwen/Qwen3-Embedding-8B@256"
    plain = make_embedder(
        Settings(_env_file=None, gcp_project="p", nebius_api_key=""), FakeEmbedClient()
    )
    assert isinstance(plain, VertexEmbedder)
    off = make_embedder(s.model_copy(update={"nebius_embed_model": ""}), client)
    assert isinstance(
        off, VertexEmbedder
    )  # Token Factory embeddings switched off: Vertex as before
