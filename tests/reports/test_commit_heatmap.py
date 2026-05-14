from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.commit_heatmap import CommitHeatmap
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_commit_heatmap_writes_html(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = CommitHeatmap().render(
        ReportContext(
            repo_stats=[stats], aggregate=agg, output_dir=tmp_path, tz=ZoneInfo("UTC")
        )
    )
    assert path == tmp_path / "commit-heatmap.html"
    text = path.read_text()
    # Plotly bundle is inlined and the layout title mentions the timezone.
    assert "<html" in text.lower()
    assert "UTC" in text
