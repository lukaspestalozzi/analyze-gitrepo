from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from gitstats.dedup import deduplicate_commits
from gitstats.models import Commit, RepoStats

UTC = timezone.utc


def _commit(sha: str, message: str, ts: datetime) -> Commit:
    return Commit(
        sha=sha,
        author_name="Alice",
        author_email="alice@example.com",
        timestamp=ts,
        additions=1,
        deletions=0,
        files_changed=1,
        message=message,
    )


def _repo(path: str, commits: list[Commit]) -> RepoStats:
    return RepoStats(path=Path(path), commits=commits)


def test_cross_repo_duplicate_removed_and_first_path_kept() -> None:
    ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    repo_b = _repo("/b", [_commit("bbb", "Fix bug", ts)])
    repo_a = _repo("/a", [_commit("aaa", "Fix bug", ts)])

    # Pass in reverse-sorted order to prove the sorted-path tie-break, not list
    # order, decides which repo keeps the commit.
    removed = deduplicate_commits([repo_b, repo_a])

    assert removed == 1
    assert [c.sha for c in repo_a.commits] == ["aaa"]  # "/a" sorts first, keeps it
    assert repo_b.commits == []


def test_distinct_message_or_timestamp_not_removed() -> None:
    ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    other = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    repo_a = _repo("/a", [_commit("a1", "Fix bug", ts)])
    repo_b = _repo("/b", [_commit("b1", "Fix typo", ts)])  # same date, diff msg
    repo_c = _repo("/c", [_commit("c1", "Fix bug", other)])  # same msg, diff date

    removed = deduplicate_commits([repo_a, repo_b, repo_c])

    assert removed == 0
    assert len(repo_a.commits) == 1
    assert len(repo_b.commits) == 1
    assert len(repo_c.commits) == 1


def test_same_instant_across_offsets_is_duplicate() -> None:
    # 10:00+00:00 and 11:00+01:00 are the same absolute instant.
    ts_utc = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    ts_plus1 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone(timedelta(hours=1)))
    repo_a = _repo("/a", [_commit("a1", "Ship it", ts_utc)])
    repo_b = _repo("/b", [_commit("b1", "Ship it", ts_plus1)])

    removed = deduplicate_commits([repo_a, repo_b])

    assert removed == 1
    assert len(repo_a.commits) == 1
    assert repo_b.commits == []


def test_duplicate_within_single_repo_removed() -> None:
    ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    repo = _repo("/a", [_commit("a1", "dup", ts), _commit("a2", "dup", ts)])

    removed = deduplicate_commits([repo])

    assert removed == 1
    assert [c.sha for c in repo.commits] == ["a1"]
