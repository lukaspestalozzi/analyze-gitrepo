from __future__ import annotations

import dataclasses
from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.jira_tickets_by_type import (
    JiraTicketsByTypeHTML,
    JiraTicketsByTypeMarkdown,
)
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def _tag_commits(stats, mapping):  # type: ignore[no-untyped-def]
    """Replace each commit with one whose metadata carries the supplied issue type."""
    new = []
    for c in stats.commits:
        first = c.jira_tickets[0] if c.jira_tickets else None
        if first and first in mapping:
            new.append(dataclasses.replace(c, metadata={"jira_first_issuetype": mapping[first]}))
        else:
            new.append(c)
    stats.commits = new
    return stats


def test_jira_markdown_counts_per_author(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    # Tag PROJ-123 as Bug and PROJ-456 as Story (see conftest.py fixture commits).
    stats = _tag_commits(stats, {"PROJ-123": "Bug", "PROJ-456": "Story"})
    resolver = IdentityResolver()
    agg = aggregate([stats], resolver)
    ctx = ReportContext(
        repo_stats=[stats], aggregate=agg, output_dir=tmp_path, resolver=resolver
    )

    path = JiraTicketsByTypeMarkdown().render(ctx)
    text = path.read_text()
    assert "# Jira tickets by type" in text
    assert "Alice Smith" in text  # PROJ-123 (Bug) -> Alice
    assert "Bob Jones" in text  # PROJ-456 (Story) -> Bob


def test_jira_html_writes_stacked_bar(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    stats = _tag_commits(stats, {"PROJ-123": "Bug", "PROJ-456": "Story"})
    resolver = IdentityResolver()
    agg = aggregate([stats], resolver)
    ctx = ReportContext(
        repo_stats=[stats], aggregate=agg, output_dir=tmp_path, resolver=resolver
    )

    path = JiraTicketsByTypeHTML().render(ctx)
    text = path.read_text()
    assert "<html" in text.lower()
    assert "Alice Smith" in text


def test_jira_markdown_handles_no_classified_commits(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)  # no metadata tagging
    resolver = IdentityResolver()
    agg = aggregate([stats], resolver)
    ctx = ReportContext(
        repo_stats=[stats], aggregate=agg, output_dir=tmp_path, resolver=resolver
    )
    path = JiraTicketsByTypeMarkdown().render(ctx)
    assert "(no classified commits)" in path.read_text()
