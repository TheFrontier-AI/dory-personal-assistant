"""Scale-to-zero start side: the waker starts a stopped VM once and waits for the voice server."""

import asyncio
import time
from types import SimpleNamespace

from dory import nebius_vm
from dory.nebius_vm import IdleWatch, VmWaker, error_reason, health_url, make_waker


class FakeApi:
    def __init__(self, state="STOPPED"):
        self.state, self.starts = state, 0

    async def get(self, vm_id):
        return self.state

    async def start(self, vm_id):
        self.starts += 1
        self.state = "RUNNING"

    async def stop(self, vm_id):
        self.stops = getattr(self, "stops", 0) + 1
        self.state = "STOPPED"


def test_health_url_from_the_voice_url():
    assert health_url("ws://204.12.189.216:8765/voice") == "http://204.12.189.216:8765/health"
    assert health_url("wss://voice.example.com/voice") == "https://voice.example.com/health"


def test_make_waker_needs_every_identity_setting():
    s = SimpleNamespace(nebius_vm_id="vm", nebius_sa_id="sa", nebius_sa_key_id="k")
    assert make_waker(s, "ws://x/voice") is None  # no private key
    s.nebius_sa_private_key = "PEM"
    w = make_waker(s, "ws://x/voice")
    assert w is not None and w.vm_id == "vm" and w.health == "http://x/health"
    assert make_waker(s, "ws://x/voice") is w  # one per process: lock + cooldown span every call
    assert make_waker(s, "ws://y/voice") is not w


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


def test_waker_keeps_waiting_when_another_process_started_the_vm(monkeypatch):
    """Two processes wake the box together: Nebius aborts the earlier start (OperationAborted) and
    the VM boots anyway. A VM already STARTING is not started again."""
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)

    class Aborted(FakeApi):
        async def start(self, vm_id):
            self.starts += 1
            self.state = "STARTING"
            raise RuntimeError("OperationAborted")

    def comes_up():
        calls = {"n": 0}

        async def http_get(url):  # down on the first look, up while we poll
            calls["n"] += 1
            return 503 if calls["n"] == 1 else 200

        return http_get

    api = Aborted("STOPPED")
    w = VmWaker("vm-1", health="http://x/health", sdk=api, http_get=comes_up())
    assert asyncio.run(w.ensure_running(timeout_s=1)) is True and api.starts == 1

    api = Aborted("STARTING")
    w = VmWaker("vm-1", health="http://x/health", sdk=api, http_get=comes_up())
    assert asyncio.run(w.ensure_running(timeout_s=1)) is True and api.starts == 0


def test_error_reason_names_the_grpc_code_and_message_but_survives_plain_errors():
    e = RuntimeError("x")
    e.status = SimpleNamespace(
        code=SimpleNamespace(name="FAILED_PRECONDITION"),
        message="instance cannot be started because its preemption policy is closed\nmore",
    )
    assert error_reason(e) == (
        "RuntimeError FAILED_PRECONDITION instance cannot be started because its preemption"
        " policy is closed more"
    )
    assert error_reason(TimeoutError()) == "TimeoutError"


# ----------------------------------------------------------------------------- the cloud idle stop (G4)
class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeWaker:
    def __init__(self, health=None, state="RUNNING"):
        self.health, self.vm_state, self.stops, self.fail = health, state, [], False

    async def health_info(self):
        return self.health

    async def state(self):
        return self.vm_state

    async def stop(self, reason=""):
        if self.fail:
            raise RuntimeError("denied")
        self.stops.append(reason)


def _watch(**health):
    clock, w = Clock(), FakeWaker(health or None)
    return IdleWatch(w, clock=clock), w, clock


def test_an_active_call_is_never_stopped_and_a_silent_one_is_after_the_idle_time():
    watch, w, clock = _watch(calls=1, idle_s=5.0)
    for _ in range(100):  # hours of activity: audio keeps idle_s small
        clock.now += 60
        assert asyncio.run(watch.tick()) == "busy"
    assert w.stops == []
    w.health = {"calls": 1, "idle_s": 1799.0}  # an open call, silent for just under 30 min
    assert asyncio.run(watch.tick()) == "busy" and w.stops == []
    w.health = {"calls": 1, "idle_s": 1801.0}  # an occupied but inactive room
    assert asyncio.run(watch.tick()) == "stopped" and w.stops == ["idle 30 min"]


def test_no_call_open_stops_after_the_idle_time_counted_from_the_last_activity():
    watch, w, clock = _watch(calls=0, idle_s=None)
    clock.now += 1799
    assert asyncio.run(watch.tick()) == "idle" and w.stops == []
    w.health = {"calls": 1, "idle_s": 1.0}
    assert asyncio.run(watch.tick()) == "busy"  # a call came in: the clock restarts
    w.health = {"calls": 0, "idle_s": None}
    clock.now += 1799
    assert asyncio.run(watch.tick()) == "idle" and w.stops == []
    clock.now += 2
    assert asyncio.run(watch.tick()) == "stopped" and len(w.stops) == 1
    clock.now += 60
    assert asyncio.run(watch.tick()) == "idle" and len(w.stops) == 1  # one stop, not a stream


def test_an_old_server_without_idle_s_keeps_an_open_call_busy():
    watch, w, clock = _watch(calls=1, busy=True)
    clock.now += 10_000
    assert asyncio.run(watch.tick()) == "busy" and w.stops == []


def test_a_failed_stop_is_retried_and_reasons_are_logged(caplog):
    watch, w, clock = _watch(calls=0, idle_s=None)
    clock.now += 2000
    w.fail = True
    with caplog.at_level("WARNING", logger="dory.nebius_vm"):
        assert asyncio.run(watch.tick()) == "idle"
    assert "stop failed (reason=idle 33 min)" in caplog.text and w.stops == []
    w.fail = False
    clock.now += 60
    assert asyncio.run(watch.tick()) == "stopped"


def test_a_vm_that_runs_without_a_voice_server_is_stopped_only_after_the_grace_time():
    watch, w, clock = _watch()  # nothing answers /health
    for _ in range(80):  # 80 minutes booting or crashed: grace is 90
        clock.now += 60
        assert asyncio.run(watch.tick()) == "down"
    assert w.stops == []
    clock.now += 12 * 60  # past 90 minutes of a RUNNING vm with no server
    assert asyncio.run(watch.tick()) == "stopped" and "no voice server" in w.stops[0]
    stopped, ws, clk = _watch()  # a STOPPED VM is never stopped again, however long it sleeps
    ws.vm_state = "STOPPED"
    for _ in range(300):
        clk.now += 60
        assert asyncio.run(stopped.tick()) == "down"
    assert ws.stops == []


def test_stop_calls_the_api_and_logs_why_and_a_wake_logs_who_asked(monkeypatch, caplog):
    monkeypatch.setattr(nebius_vm, "POLL_S", 0.01)
    api = FakeApi("STOPPED")

    async def http_get(url):
        return 200 if api.state == "RUNNING" else 503

    w = VmWaker("vm-1", health="http://x/health", sdk=api, http_get=http_get)
    with caplog.at_level("INFO", logger="dory.nebius_vm"):
        assert asyncio.run(w.ensure_running(timeout_s=5, reason="typed command by user 7"))
        asyncio.run(w.stop(reason="idle 31 min"))
    assert api.stops == 1 and api.state == "STOPPED"
    assert "starting (reason=typed command by user 7)" in caplog.text
    assert "stopping (reason=idle 31 min)" in caplog.text
