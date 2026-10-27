"""Scale-to-zero for the GLM-4-Voice GPU box on Nebius AI Cloud: the START half.

When a voice call arrives and the voice server does not answer, `VmWaker.ensure_running` starts the
VM through the Nebius API (if it is stopped), then polls the server's `/health` until it answers or
`timeout_s` passes; the caller connects afterwards. The STOP half lives on the VM itself
(`deploy/glm_voice/server.py --idle-shutdown-min`, nightly timer) and in the owner's watchdog.

Credentials: a Nebius service account holding `compute.instance-power-operator` on the VM and an
authorized key (`DORY_NEBIUS_VM_ID`, `DORY_NEBIUS_SA_ID`, `DORY_NEBIUS_SA_KEY_ID`,
`DORY_NEBIUS_SA_PRIVATE_KEY` = the PEM, from Secret Manager; `DORY_NEBIUS_PROJECT` optional). The SDK
wants the key as a file, so the PEM is written to a 0600 temp file once per process. Without the
settings `make_waker` returns None and a stopped VM is a plain connection error, as before. The SDK
(`nebius`, gRPC) is imported only when a wake is needed. Never logs keys or tokens.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT_S = 3.0
POLL_S = 5.0
START_COOLDOWN_S = 60.0  # one start request per minute at most, whatever callers do
DEFAULT_TIMEOUT_S = 300.0  # boot (~45 s) + model load (~90 s) + margin, measured 26 Oct 2026


def health_url(voice_url: str) -> str:
    """ws(s)://host:port/voice -> http(s)://host:port/health."""
    u = urlsplit(voice_url)
    scheme = "https" if u.scheme in ("wss", "https") else "http"
    return urlunsplit((scheme, u.netloc, "/health", "", ""))


class VmWaker:
    """Start a stopped Nebius VM and wait for its voice server. One wake at a time per process."""

    def __init__(
        self,
        vm_id: str,
        *,
        health: str,
        sa_id: str = "",
        key_id: str = "",
        private_key_pem: str = "",
        parent_id: str = "",
        sdk: Any = None,  # tests pass a fake with `.get(id) -> state` and `.start(id)`
        http_get: Callable[[str], Awaitable[int]] | None = None,  # tests: url -> status code
    ):
        self.vm_id, self.health = vm_id, health
        self._sa_id, self._key_id, self._pem, self._parent = (
            sa_id,
            key_id,
            private_key_pem,
            parent_id,
        )
        self._sdk = sdk
        self._http_get = http_get or self._get
        self._lock = asyncio.Lock()
        self._last_start = 0.0

    # ---- Nebius
    def _api(self) -> Any:
        """The compute instance client, built on first use (the SDK import is slow and gRPC-heavy)."""
        if self._sdk is None:
            from nebius.api.nebius.compute.v1 import (  # noqa: PLC0415
                GetInstanceRequest,
                InstanceServiceClient,
                StartInstanceRequest,
            )
            from nebius.sdk import SDK  # noqa: PLC0415

            fd, path = tempfile.mkstemp(prefix="dory-nebius-", suffix=".pem")
            with os.fdopen(fd, "w") as f:
                f.write(self._pem)
            os.chmod(path, 0o600)
            sdk = SDK(
                service_account_private_key_file_name=path,
                service_account_public_key_id=self._key_id,
                service_account_id=self._sa_id,
                parent_id=self._parent or None,
                user_agent_prefix="dory-voice/1.0",
            )
            client = InstanceServiceClient(sdk)

            class _Api:
                async def get(self, vm_id: str) -> str:
                    inst = await client.get(GetInstanceRequest(id=vm_id))
                    state = getattr(getattr(inst, "status", None), "state", None)
                    return str(getattr(state, "name", state) or "").upper()

                async def start(self, vm_id: str) -> None:
                    op = await client.start(StartInstanceRequest(id=vm_id))
                    wait = getattr(op, "wait", None)
                    if wait is not None:
                        await wait()

            self._sdk = _Api()
        return self._sdk

    async def state(self) -> str:
        return await self._api().get(self.vm_id)

    # ---- the voice server
    @staticmethod
    async def _get(url: str) -> int:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_S) as c:
            return (await c.get(url)).status_code

    async def healthy(self) -> bool:
        try:
            return await self._http_get(self.health) == 200
        except Exception:
            return False

    async def ensure_running(
        self,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> bool:
        """True once the voice server answers; starts the VM when it is stopped. Callers that arrive
        during a wake wait for the same one. `progress(kind)` gets "starting" / "booting"."""
        async with self._lock:
            if await self.healthy():
                return True
            deadline = time.monotonic() + timeout_s
            try:
                state = await self.state()
            except Exception as e:
                logger.warning("nebius vm: state failed: %s", type(e).__name__)
                state = ""
            if "RUNNING" not in state and time.monotonic() - self._last_start >= START_COOLDOWN_S:
                self._last_start = time.monotonic()
                logger.info("nebius vm: %s is %s, starting", self.vm_id, state or "unknown")
                if progress is not None:
                    await progress("starting")
                try:
                    await self.start()
                except Exception as e:
                    logger.warning("nebius vm: start failed: %s", type(e).__name__)
                    return False
            if progress is not None:
                await progress("booting")
            started = deadline - timeout_s
            while time.monotonic() < deadline:
                await asyncio.sleep(POLL_S)
                if await self.healthy():
                    logger.info(
                        "nebius vm: voice server up after %.0f s", time.monotonic() - started
                    )
                    return True
            logger.warning("nebius vm: voice server not up after %.0f s", timeout_s)
            return False

    async def start(self) -> None:
        await self._api().start(self.vm_id)


def make_waker(settings: Any, voice_url: str) -> VmWaker | None:
    """A waker when the Nebius identity settings are all present, else None."""
    vm = getattr(settings, "nebius_vm_id", "")
    sa = getattr(settings, "nebius_sa_id", "")
    key = getattr(settings, "nebius_sa_key_id", "")
    pem = getattr(settings, "nebius_sa_private_key", "")
    if not (vm and sa and key and pem and voice_url):
        return None
    return VmWaker(
        vm,
        health=health_url(voice_url),
        sa_id=sa,
        key_id=key,
        private_key_pem=pem,
        parent_id=getattr(settings, "nebius_project", ""),
    )
