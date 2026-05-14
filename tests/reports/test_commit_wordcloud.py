from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.commit_wordcloud import CommitWordcloud, _clean
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_clean_strips_jira_keys_and_urls() -> None:
    s = _clean("PROJ-123 fix bug see https://example.com")
    assert "proj-123" not in s
    assert "https" not in s


def test_resolve_sample_size_defaults_and_overrides() -> None:
    from gitstats.reports.commit_wordcloud import _DEFAULT_SAMPLE_SIZE, _resolve_sample_size

    assert _resolve_sample_size(None) == _DEFAULT_SAMPLE_SIZE
    assert _resolve_sample_size(123) == 123
    # 0 / negative / non-int means "no cap"
    assert _resolve_sample_size(0) is None
    assert _resolve_sample_size(-1) is None
    assert _resolve_sample_size("ten") is None


def test_clean_strips_example_com_from_url() -> None:
    s = _clean("see https://example.com")
    assert "example.com" not in s


def test_commit_wordcloud_writes_png(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = CommitWordcloud().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    assert path == tmp_path / "commit-wordcloud.png"
    # PNG magic header.
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
