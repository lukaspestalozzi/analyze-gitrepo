from __future__ import annotations

from datetime import datetime

from .models import RepoStats


def deduplicate_commits(repo_stats: list[RepoStats]) -> int:
    """Drop commits sharing an (message, author-date) key with an already-seen
    commit, across all repos. Mutates each ``rs.commits`` in place. Returns the
    number of commits removed.

    Repos are visited in sorted path order so that, for a cross-repo duplicate,
    the lexicographically-first repo path deterministically keeps the commit
    regardless of filesystem/scan ordering. The ``repo_stats`` list order itself
    is left unchanged.
    """
    seen: set[tuple[str, datetime]] = set()
    removed = 0
    for rs in sorted(repo_stats, key=lambda rs: str(rs.path)):
        kept = []
        for c in rs.commits:
            key = (c.message, c.timestamp)
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(c)
        rs.commits = kept
    return removed
