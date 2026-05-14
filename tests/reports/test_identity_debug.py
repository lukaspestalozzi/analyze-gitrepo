from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.identity_debug import IdentityDebug
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_identity_debug_lists_groups(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    resolver = IdentityResolver()
    agg = aggregate([stats], resolver)
    path = IdentityDebug().render(
        ReportContext(
            repo_stats=[stats], aggregate=agg, output_dir=tmp_path, resolver=resolver
        )
    )
    text = path.read_text()
    assert "## Alice Smith" in text
    assert "## Bob Jones" in text
    # Alice has two emails; both should appear.
    assert "alice@old.example" in text
    assert "asmith@new.example" in text
    # Source should be "observed" since no override was provided.
    assert "source: observed" in text
