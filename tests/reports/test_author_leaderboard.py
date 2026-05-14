from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.author_leaderboard import AuthorLeaderboard
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_author_leaderboard_writes_html(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = AuthorLeaderboard().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    assert path == tmp_path / "author-leaderboard.html"
    text = path.read_text()
    assert "<html" in text.lower()
    assert "Alice Smith" in text
