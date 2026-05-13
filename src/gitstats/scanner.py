from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pygit2

from .models import Commit, RepoStats

JIRA_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def extract_jira_tickets(message: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for match in JIRA_RE.findall(message):
        seen.setdefault(match, None)
    return tuple(seen)


def _to_datetime(unix_seconds: int, offset_minutes: int) -> datetime:
    tz = timezone(timedelta(minutes=offset_minutes))
    return datetime.fromtimestamp(unix_seconds, tz=tz)


def scan_repo(
    path: Path | str,
    *,
    include_merges: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
) -> RepoStats:
    """Walk a repo's HEAD history and produce a `RepoStats`.

    Diff stats are computed against the first parent (or empty tree for the
    root commit). Merge commits are skipped unless `include_merges=True`.
    """
    path = Path(path)
    repo = pygit2.Repository(str(path))
    commits: list[Commit] = []

    try:
        head_target = repo.head.target
    except (pygit2.GitError, KeyError):
        return RepoStats(path=path, commits=commits)

    walker = repo.walk(head_target, pygit2.GIT_SORT_TIME)

    for commit in walker:
        parents = commit.parents
        is_merge = len(parents) > 1
        if is_merge and not include_merges:
            continue

        ts = _to_datetime(commit.author.time, commit.author.offset)
        if since is not None and ts < since:
            continue
        if until is not None and ts > until:
            continue

        if not parents:
            diff = commit.tree.diff_to_tree(swap=True)
        else:
            diff = parents[0].tree.diff_to_tree(commit.tree)

        stats = diff.stats
        commits.append(
            Commit(
                sha=str(commit.id),
                author_name=commit.author.name,
                author_email=commit.author.email,
                timestamp=ts,
                additions=stats.insertions,
                deletions=stats.deletions,
                files_changed=stats.files_changed,
                jira_tickets=extract_jira_tickets(commit.message),
                is_merge=is_merge,
            )
        )

    return RepoStats(path=path, commits=commits)
