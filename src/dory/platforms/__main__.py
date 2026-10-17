from __future__ import annotations

import asyncio
import logging
import sys

from ..config import Settings
from .config import PlatformSettings
from .runtime import run


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    for noisy in ("httpx", "httpcore", "slack_bolt", "slack_sdk", "aiohttp", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # their debug/info lines can echo urls
    s, ps = Settings.from_env(), PlatformSettings()
    if not ps.enabled_platforms():
        sys.exit(
            "No platform configured: set DORY_SLACK_BOT_TOKEN + DORY_SLACK_APP_TOKEN and/or "
            "DORY_LINE_CHANNEL_SECRET + DORY_LINE_CHANNEL_ACCESS_TOKEN and/or "
            "DORY_TELEGRAM_BOT_TOKEN and/or DORY_WHATSAPP_ACCESS_TOKEN + "
            "DORY_WHATSAPP_APP_SECRET + DORY_WHATSAPP_VERIFY_TOKEN + "
            "DORY_WHATSAPP_PHONE_NUMBER_ID (see docs/platforms/)"
        )
    asyncio.run(run(s, ps))


if __name__ == "__main__":
    main()
