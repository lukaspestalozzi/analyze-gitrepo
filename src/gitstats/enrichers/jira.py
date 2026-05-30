from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..models import Commit

# Cap-1 sequential fetcher per spec §11.1; back-off schedule for transient errors.
_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
_HTTP_TIMEOUT = 30.0


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "gitstats" / "jira"


def cache_host(url: str) -> str:
    return urlparse(url).hostname or "unknown"


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    user: str | None
    token: str
    cache_root: Path
    cache_ttl_seconds: float = 86_400.0  # 24h
    no_cache: bool = False


class JiraAuthError(Exception):
    """Raised on 401/403 from Jira — aborts the run per spec §11.1."""


class JiraEnricher:
    """Live-API Jira enricher.

    Per spec §11.1: fetch issue type for the first ticket key on each
    commit; cache results to disk; 404 → silent skip; 401/403 → abort;
    5xx / network → retry with back-off then treat as 404.
    """

    def __init__(self, config: JiraConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        if config.user:
            self.session.auth = (config.user, config.token)
        else:
            self.session.headers["Authorization"] = f"Bearer {config.token}"

    # ------- public API: CommitEnricher -------

    def enrich(self, commits: Iterable[Commit]) -> Iterable[Commit]:
        host = cache_host(self.config.base_url)
        host_dir = self.config.cache_root / host
        if not self.config.no_cache:
            host_dir.mkdir(parents=True, exist_ok=True)

        for c in commits:
            if not c.jira_tickets:
                yield c
                continue
            key = c.jira_tickets[0]
            issuetype = self._lookup(key, host_dir)
            if issuetype is None:
                yield c
            else:
                new_metadata = {**c.metadata, "jira_first_issuetype": issuetype}
                yield dataclasses.replace(c, metadata=new_metadata)

    # ------- internals -------

    def _lookup(self, key: str, host_dir: Path) -> str | None:
        if not self.config.no_cache:
            cached = self._cache_read(host_dir, key)
            if cached is not None:
                return cached.value  # may be None (cached 404)

        issuetype = self._fetch(key)
        if not self.config.no_cache:
            self._cache_write(host_dir, key, issuetype)
        return issuetype

    def _fetch(self, key: str) -> str | None:
        url = f"{self.config.base_url.rstrip('/')}/rest/api/2/issue/{key}"
        last_error: str | None = None
        for attempt, delay in enumerate([0.0, *_RETRY_BACKOFF_SECONDS]):
            if delay > 0:
                time.sleep(delay)
            try:
                resp = self.session.get(
                    url, params={"fields": "issuetype"}, timeout=_HTTP_TIMEOUT
                )
            except requests.RequestException as e:
                last_error = str(e)
                if attempt == len(_RETRY_BACKOFF_SECONDS):
                    print(
                        f"warning: Jira fetch failed for {key} after retries: {last_error}; "
                        f"treating as missing",
                        file=sys.stderr,
                    )
                    return None
                continue

            if resp.status_code in (401, 403):
                raise JiraAuthError(f"Jira auth failed ({resp.status_code}): {resp.text[:200]}")
            if resp.status_code == 404:
                return None
            if 500 <= resp.status_code < 600:
                last_error = f"HTTP {resp.status_code}"
                if attempt == len(_RETRY_BACKOFF_SECONDS):
                    print(
                        f"warning: Jira returned {resp.status_code} for {key} after retries; "
                        f"treating as missing",
                        file=sys.stderr,
                    )
                    return None
                continue
            resp.raise_for_status()
            data = resp.json()
            issuetype = data.get("fields", {}).get("issuetype", {}).get("name")
            return issuetype if isinstance(issuetype, str) else None

        return None

    # ------- cache helpers -------

    def _cache_read(self, host_dir: Path, key: str) -> _CacheHit | None:
        path = host_dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        fetched_at_raw = data.get("fetched_at")
        if not isinstance(fetched_at_raw, str):
            return None
        try:
            fetched_at = datetime.fromisoformat(fetched_at_raw)
        except ValueError:
            return None
        age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
        if age > self.config.cache_ttl_seconds:
            return None
        value = data.get("issuetype")
        if value is not None and not isinstance(value, str):
            return None
        return _CacheHit(value=value)

    def _cache_write(self, host_dir: Path, key: str, issuetype: str | None) -> None:
        path = host_dir / f"{key}.json"
        payload = {
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
            "issuetype": issuetype,
        }
        path.write_text(json.dumps(payload))


@dataclass(frozen=True)
class _CacheHit:
    value: str | None  # None = cached 404


def config_from_env(
    cli_url: str | None,
    cache_root: Path | None = None,
    cache_ttl_seconds: float = 86_400.0,
    no_cache: bool = False,
) -> JiraConfig | None:
    """Build a `JiraConfig` from CLI flag + env vars; return None when inactive.

    Active iff `cli_url` is given or `GITSTATS_JIRA_URL` is set. When
    active, `GITSTATS_JIRA_TOKEN` is required.
    """
    base_url = cli_url or os.environ.get("GITSTATS_JIRA_URL")
    if not base_url:
        return None
    token = os.environ.get("GITSTATS_JIRA_TOKEN")
    if not token:
        raise RuntimeError(
            "Jira is active (--jira-url or GITSTATS_JIRA_URL set) but "
            "GITSTATS_JIRA_TOKEN is missing."
        )
    return JiraConfig(
        base_url=base_url,
        user=os.environ.get("GITSTATS_JIRA_USER"),
        token=token,
        cache_root=cache_root or default_cache_root(),
        cache_ttl_seconds=cache_ttl_seconds,
        no_cache=no_cache,
    )
