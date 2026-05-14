from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import responses
from responses import matchers

from gitstats.enrichers.jira import JiraAuthError, JiraConfig, JiraEnricher
from gitstats.models import Commit

JIRA_URL = "https://jira.example.com"
ISSUE_URL = f"{JIRA_URL}/rest/api/2/issue/PROJ-1"


def _commit(*tickets: str) -> Commit:
    return Commit(
        sha="abc",
        author_name="Alice",
        author_email="a@x",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        additions=0,
        deletions=0,
        files_changed=0,
        jira_tickets=tickets,
    )


def _cfg(tmp_path: Path, **overrides) -> JiraConfig:
    defaults = dict(
        base_url=JIRA_URL,
        user=None,
        token="t",
        cache_root=tmp_path / "cache",
        cache_ttl_seconds=86_400.0,
        no_cache=False,
    )
    defaults.update(overrides)
    return JiraConfig(**defaults)


@responses.activate
def test_fetches_issuetype_and_caches(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        ISSUE_URL,
        json={"fields": {"issuetype": {"name": "Bug"}}},
        status=200,
        match=[matchers.query_param_matcher({"fields": "issuetype"})],
    )

    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1")]))
    assert out[0].metadata["jira_first_issuetype"] == "Bug"

    # Cache file written.
    cache_file = tmp_path / "cache" / "jira.example.com" / "PROJ-1.json"
    assert cache_file.is_file()
    payload = json.loads(cache_file.read_text())
    assert payload["issuetype"] == "Bug"


@responses.activate
def test_cached_response_skips_http(tmp_path: Path) -> None:
    host_dir = tmp_path / "cache" / "jira.example.com"
    host_dir.mkdir(parents=True)
    (host_dir / "PROJ-1.json").write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                "issuetype": "Story",
            }
        )
    )

    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1")]))
    assert out[0].metadata["jira_first_issuetype"] == "Story"
    # No HTTP call should have been made.
    assert len(responses.calls) == 0


@responses.activate
def test_404_silent_skip_and_cached(tmp_path: Path) -> None:
    responses.add(responses.GET, ISSUE_URL, status=404)

    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1")]))
    assert "jira_first_issuetype" not in out[0].metadata

    cache_file = tmp_path / "cache" / "jira.example.com" / "PROJ-1.json"
    assert cache_file.is_file()
    payload = json.loads(cache_file.read_text())
    assert payload["issuetype"] is None


@responses.activate
def test_401_aborts(tmp_path: Path) -> None:
    responses.add(responses.GET, ISSUE_URL, status=401, body="forbidden")
    enricher = JiraEnricher(_cfg(tmp_path))
    with pytest.raises(JiraAuthError, match="401"):
        list(enricher.enrich([_commit("PROJ-1")]))


@responses.activate
def test_5xx_retried_then_treated_as_missing(tmp_path: Path, monkeypatch) -> None:
    # Skip the back-off sleeps to keep the test fast.
    monkeypatch.setattr("gitstats.enrichers.jira.time.sleep", lambda *_: None)
    for _ in range(4):
        responses.add(responses.GET, ISSUE_URL, status=503)
    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1")]))
    assert "jira_first_issuetype" not in out[0].metadata
    assert len(responses.calls) == 4  # initial + 3 retries


@responses.activate
def test_only_first_ticket_is_classified(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        ISSUE_URL,
        json={"fields": {"issuetype": {"name": "Bug"}}},
        status=200,
    )
    # If the enricher tried to fetch PROJ-2 we'd get a connection error from `responses`.
    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1", "PROJ-2")]))
    assert out[0].metadata["jira_first_issuetype"] == "Bug"
    assert len(responses.calls) == 1


@responses.activate
def test_no_cache_skips_filesystem(tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        ISSUE_URL,
        json={"fields": {"issuetype": {"name": "Bug"}}},
        status=200,
    )
    enricher = JiraEnricher(_cfg(tmp_path, no_cache=True))
    list(enricher.enrich([_commit("PROJ-1")]))
    # Cache dir should not have been created.
    assert not (tmp_path / "cache").exists()


@responses.activate
def test_expired_cache_refetches(tmp_path: Path) -> None:
    host_dir = tmp_path / "cache" / "jira.example.com"
    host_dir.mkdir(parents=True)
    old = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
    (host_dir / "PROJ-1.json").write_text(
        json.dumps({"fetched_at": old, "issuetype": "Stale"})
    )

    responses.add(
        responses.GET,
        ISSUE_URL,
        json={"fields": {"issuetype": {"name": "Fresh"}}},
        status=200,
    )
    enricher = JiraEnricher(_cfg(tmp_path))
    out = list(enricher.enrich([_commit("PROJ-1")]))
    assert out[0].metadata["jira_first_issuetype"] == "Fresh"


def test_commit_without_tickets_passes_through(tmp_path: Path) -> None:
    enricher = JiraEnricher(_cfg(tmp_path))
    c = _commit()  # no tickets
    out = list(enricher.enrich([c]))
    assert out == [c]
