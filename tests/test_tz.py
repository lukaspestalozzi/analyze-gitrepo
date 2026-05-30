from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from gitstats.tz import parse_tz


def test_parse_tz_utc() -> None:
    assert parse_tz("utc") == ZoneInfo("UTC")
    assert parse_tz("UTC") == ZoneInfo("UTC")


def test_parse_tz_iana() -> None:
    assert parse_tz("Europe/Zurich") == ZoneInfo("Europe/Zurich")


def test_parse_tz_local_and_none_resolve_to_a_tzinfo() -> None:
    assert parse_tz(None) is not None
    assert parse_tz("local") is not None


def test_parse_tz_invalid() -> None:
    with pytest.raises(ValueError, match="unknown timezone"):
        parse_tz("Mars/Olympus")
