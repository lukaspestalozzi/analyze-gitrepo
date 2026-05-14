from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_tz(value: str | None) -> tzinfo:
    """Resolve a `--tz` argument to a `tzinfo`.

    `None` and `local` both resolve to the system local timezone via
    `datetime.now().astimezone()`. `utc` is a fast path. Anything else
    is treated as an IANA zone name; invalid names raise `ValueError`.
    """
    if value is None or value.lower() == "local":
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]
    if value.lower() == "utc":
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"unknown timezone: {value!r}") from e
