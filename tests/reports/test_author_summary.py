from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.author_summary import AuthorSummary
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_author_summary_writes_markdown_with_tables(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    ctx = ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)

    path = AuthorSummary().render(ctx)
    assert path == tmp_path / "author-summary.md"

    text = path.read_text()
    assert "# Author summary" in text
    assert "## Repositories (1)" in text
    assert "## Authors (2)" in text
    assert "Alice Smith" in text
    assert "Bob Jones" in text
