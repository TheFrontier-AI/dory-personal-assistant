"""Scale-to-zero start side: the waker starts a stopped VM once and waits for the voice server."""

import asyncio
import time
from types import SimpleNamespace

from dory import nebius_vm
from dory.nebius_vm import VmWaker, health_url, make_waker


class FakeApi:
    def __init__(self, state="STOPPED"):
        self.state, self.starts = state, 0

    async def get(self, vm_id):
        return self.state

    async def start(self, vm_id):
        self.starts += 1
        self.state = "RUNNING"


def test_health_url_from_the_voice_url():
    assert health_url("ws://204.12.189.216:8765/voice") == "http://204.12.189.216:8765/health"
    assert health_url("wss://voice.example.com/voice") == "https://voice.example.com/health"


def test_make_waker_needs_every_identity_setting():
    s = SimpleNamespace(nebius_vm_id="vm", nebius_sa_id="sa", nebius_sa_key_id="k")
    assert make_waker(s, "ws://x/voice") is None  # no private key
    s.nebius_sa_private_key = "PEM"
    w = make_waker(s, "ws://x/voice")
    assert w is not None and w.vm_id == "vm" and w.health == "http://x/health"


def test_waker_starts_a_stopped_vm_once_and_waits_for_health(monkeypatch):
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)
    api = FakeApi("STOPPED")
    probes = {"n": 0}

    async def http_get(url):
        probes["n"] += 1
        return 200 if probes["n"] >= 4 else 503  # down, down, down, then the server answers

    events = []

    async def progress(kind):
        events.append(kind)

    w = VmWaker("vm-1", health="http://x/health", sdk=api, http_get=http_get)

    async def main():
        # three callers arrive together: one start, everyone waits for the same wake
        results = await asyncio.gather(
            w.ensure_running(timeout_s=5, progress=progress),
            w.ensure_running(timeout_s=5),
            w.ensure_running(timeout_s=5),
        )
        return results

    assert asyncio.run(main()) == [True, True, True]
    assert api.starts == 1 and api.state == "RUNNING"
    assert events == ["starting", "booting"]


def test_waker_gives_up_after_the_timeout_and_never_starts_a_running_vm(monkeypatch):
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)
    api = FakeApi("RUNNING")  # running but the server never answers (model still loading)

    async def http_get(url):
        return 503

    w = VmWaker("vm-1", health="http://x/health", sdk=api, http_get=http_get)
    assert asyncio.run(w.ensure_running(timeout_s=0.05)) is False
    assert api.starts == 0


def test_waker_start_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)

    class Broken(FakeApi):
        async def start(self, vm_id):
            raise RuntimeError("no permission")

    async def http_get(url):
        return 503

    w = VmWaker("vm-1", health="http://x/health", sdk=Broken("STOPPED"), http_get=http_get)
    assert asyncio.run(w.ensure_running(timeout_s=1)) is False


def test_waker_gives_up_when_the_api_hangs(monkeypatch):
    """A wrong key id makes the SDK retry its token refresh for ever; the waker must not wait."""
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)
    monkeypatch.setattr(nebius_vm, "API_TIMEOUT_S", 0.02)

    class Hanging(FakeApi):
        async def get(self, vm_id):
            await asyncio.Event().wait()

        async def start(self, vm_id):
            await asyncio.Event().wait()

    async def http_get(url):
        return 503

    w = VmWaker("vm-1", health="http://x/health", sdk=Hanging(), http_get=http_get)
    t0 = time.monotonic()
    assert asyncio.run(w.ensure_running(timeout_s=5)) is False
    assert time.monotonic() - t0 < 1
