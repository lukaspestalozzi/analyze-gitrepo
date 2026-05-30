from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .models import Commit


class CommitEnricher(Protocol):
    """Extension point for attaching metadata to commits between scan and aggregate.

    A future `JiraEnricher` will join `commit.jira_tickets` against a Jira
    export and populate `commit.metadata` with fields like `is_bugfix` or
    `ticket_type`. The aggregator can then group/filter by metadata.

    Implementations should be pure functions over the stream — no I/O during
    iteration if possible, and no mutation of inputs (since `Commit` is frozen,
    yield replacements via `dataclasses.replace`).
    """

    def enrich(self, commits: Iterable[Commit]) -> Iterable[Commit]: ...


def apply_enrichers(
    commits: Iterable[Commit], enrichers: list[CommitEnricher]
) -> Iterable[Commit]:
    for enricher in enrichers:
        commits = enricher.enrich(commits)
    return commits
