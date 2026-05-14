from __future__ import annotations

from datetime import datetime, timezone

from .identity import IdentityResolver
from .models import Aggregate, AuthorStats, RepoAuthorStats, RepoStats, RepoSummary


def aggregate(repo_stats: list[RepoStats], resolver: IdentityResolver) -> Aggregate:
    """Reduce per-repo commits into an `Aggregate` keyed by canonical author id."""
    # First pass: feed all (name, email) pairs to the resolver so the
    # union-find converges before we look anything up.
    for rs in repo_stats:
        for c in rs.commits:
            resolver.observe(c.author_name, c.author_email)

    authors: dict[str, AuthorStats] = {}
    repos: list[RepoSummary] = []

    for rs in repo_stats:
        repo_name = rs.name
        repo_first: datetime | None = None
        repo_last: datetime | None = None
        repo_authors: set[str] = set()

        for c in rs.commits:
            author_id = resolver.author_id(c.author_name, c.author_email)
            repo_authors.add(author_id)

            if author_id not in authors:
                authors[author_id] = AuthorStats(
                    author_id=author_id,
                    display_name=resolver.display_name(c.author_name, c.author_email),
                )
            a = authors[author_id]
            a.emails.add(c.author_email)
            a.commits += 1
            a.additions += c.additions
            a.deletions += c.deletions
            a.files_touched += c.files_changed
            a.first_commit = _min_ts(a.first_commit, c.timestamp)
            a.last_commit = _max_ts(a.last_commit, c.timestamp)

            per = a.per_repo.setdefault(repo_name, RepoAuthorStats(repo=repo_name))
            per.commits += 1
            per.additions += c.additions
            per.deletions += c.deletions
            per.files_touched += c.files_changed
            per.first_commit = _min_ts(per.first_commit, c.timestamp)
            per.last_commit = _max_ts(per.last_commit, c.timestamp)

            repo_first = _min_ts(repo_first, c.timestamp)
            repo_last = _max_ts(repo_last, c.timestamp)

        repos.append(
            RepoSummary(
                path=str(rs.path),
                name=repo_name,
                commits=len(rs.commits),
                authors=len(repo_authors),
                first_commit=repo_first,
                last_commit=repo_last,
            )
        )

    # Refresh display names (most-common may have shifted as we observed more).
    for a in authors.values():
        any_email = next(iter(a.emails), "")
        a.display_name = resolver.display_name(a.display_name, any_email)

    sorted_authors = sorted(authors.values(), key=lambda x: x.commits, reverse=True)
    return Aggregate(
        authors=sorted_authors,
        repos=sorted(repos, key=lambda r: r.name),
        generated_at=datetime.now(tz=timezone.utc),
    )


def _min_ts(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a <= b else b


def _max_ts(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b
