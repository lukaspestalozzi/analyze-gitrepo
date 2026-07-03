from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.first_commits import FirstCommits
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_first_commits_has_section_per_author(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = FirstCommits().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    text = path.read_text()
    assert "## Alice Smith" in text
    assert "## Bob Jones" in text
    assert "First commit overall:" in text
    # The overall first commit shows its full hash and message.
    full_sha = agg.authors[0].first_commit_sha
    assert len(full_sha) == 40
    assert full_sha in text
    assert "Initial commit" in text
    assert "Fix typo (no ticket)" in text
