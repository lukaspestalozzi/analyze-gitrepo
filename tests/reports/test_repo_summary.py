from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.repo_summary import RepoSummary
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_repo_summary_includes_repo_and_top_authors(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = RepoSummary().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    text = path.read_text()
    assert f"## {stats.name}" in text
    assert "Top contributors" in text
    assert "Alice Smith" in text
    # The fixture has PROJ-123 and PROJ-456 in commit messages.
    assert "Jira ticket keys referenced (distinct): 2" in text
