"""Timezone resolution with a Windows-safe Pakistan fallback."""

from __future__ import annotations

import logging
from datetime import timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def resolve_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Karachi":
            return timezone(timedelta(hours=5), name="Asia/Karachi")
        logger.warning("Unknown timezone '%s'; using UTC.", name)
        return timezone.utc
