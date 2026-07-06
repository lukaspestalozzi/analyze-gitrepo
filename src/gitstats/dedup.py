from __future__ import annotations

from datetime import datetime

from .models import Commit, RepoStats

# Repo whose copy of a duplicate is preferred when the original cannot be
# determined by committer date (i.e. the committer dates tie).
_PREFERRED_REPO_NAME = "rcs"


def _winner_key(rs: RepoStats, c: Commit) -> tuple[datetime, int, str]:
    """Sort key selecting which copy of a duplicate group to keep (min wins).

    1. Earliest committer date — the original / older commit. A cherry-pick
       preserves the author date but gets a fresh, later committer date, so the
       original sorts first. Falls back to the author ``timestamp`` when no
       committer date was captured.
    2. Prefer the ``rcs`` repo — only breaks a genuine committer-date tie.
    3. Sorted repo path — final deterministic tie-break.
    """
    committer = c.committer_timestamp if c.committer_timestamp is not None else c.timestamp
    return (committer, 0 if rs.name == _PREFERRED_REPO_NAME else 1, str(rs.path))


def deduplicate_commits(repo_stats: list[RepoStats]) -> int:
    """Collapse commits sharing an (message, author-date) key across all repos,
    keeping the original (oldest) copy. Mutates each ``rs.commits`` in place and
    returns the number of commits removed.

    Within each duplicate group the surviving copy is chosen by the earliest
    committer date (the true original — see :func:`_winner_key`), falling back to
    the ``rcs`` repo and then sorted repo path. The winner is decided by an
    explicit key, so the result is independent of ``repo_stats`` list order.
    """
    groups: dict[tuple[str, datetime], list[tuple[RepoStats, Commit]]] = {}
    for rs in repo_stats:
        for c in rs.commits:
            groups.setdefault((c.message, c.timestamp), []).append((rs, c))

    keep_ids: set[int] = set()
    removed = 0
    for candidates in groups.values():
        _, winner_c = min(candidates, key=lambda pair: _winner_key(*pair))
        keep_ids.add(id(winner_c))
        removed += len(candidates) - 1

    for rs in repo_stats:
        rs.commits = [c for c in rs.commits if id(c) in keep_ids]
    return removed
