from __future__ import annotations

from gitstats.scanner import extract_jira_tickets, scan_repo
from tests.conftest import FixtureRepo


def test_extract_jira_tickets() -> None:
    assert extract_jira_tickets("PROJ-123 ok") == ("PROJ-123",)
    assert extract_jira_tickets("proj-123") == ()
    assert extract_jira_tickets("FOO- BAR-1 BAZ-2") == ("BAR-1", "BAZ-2")
    # Duplicate ticket appearing twice is deduplicated, order preserved.
    assert extract_jira_tickets("AB-1 AB-1 CD-2") == ("AB-1", "CD-2")


def test_scan_repo_counts_commits_and_diff(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    assert len(stats.commits) == 4
    # The walker is GIT_SORT_TIME (newest first) so the last commit is index 0.
    shas = [c.sha for c in stats.commits]
    assert shas[0] == fixture_repo.commits["c4"]
    assert shas[-1] == fixture_repo.commits["c1"]

    # c1 (initial) creates a.txt with 2 lines.
    c1 = next(c for c in stats.commits if c.sha == fixture_repo.commits["c1"])
    assert c1.additions == 2
    assert c1.deletions == 0
    assert c1.files_changed == 1
    assert c1.jira_tickets == ()

    # c2 adds one line to a.txt and a brand new b.txt.
    c2 = next(c for c in stats.commits if c.sha == fixture_repo.commits["c2"])
    assert c2.additions == 2  # "again" line + "b" line
    assert c2.deletions == 0
    assert c2.files_changed == 2
    assert c2.jira_tickets == ("PROJ-123",)


def test_scan_repo_skips_merges_by_default(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    assert all(not c.is_merge for c in stats.commits)
