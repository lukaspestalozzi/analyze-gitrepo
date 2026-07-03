from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.models import Commit, RepoStats
from gitstats.reports import ReportContext
from gitstats.reports.commit_word_frequencies import CommitWordFrequencies, _word_counts
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def _ctx(messages: list[str], output_dir: Path) -> ReportContext:
    commits = [
        Commit(
            sha=f"{i:040x}",
            author_name="A",
            author_email="a@example.com",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            additions=0,
            deletions=0,
            files_changed=0,
            message=m,
        )
        for i, m in enumerate(messages)
    ]
    rs = RepoStats(path=Path("/r"), commits=commits)
    agg = aggregate([rs], IdentityResolver())
    return ReportContext(repo_stats=[rs], aggregate=agg, output_dir=output_dir)


def test_word_counts_ranks_and_filters(tmp_path: Path) -> None:
    counts = _word_counts(
        _ctx(
            [
                "refactor scanner refactor refactor",
                "refactor scanner cae29ce2 abc",  # junk + 3-letter dropped
                "fix the parser",  # `fix` is a stopword, `the` a stopword, `parser` kept
            ],
            tmp_path,
        )
    )
    assert counts["refactor"] == 4
    assert counts["scanner"] == 2
    assert counts["parser"] == 1
    # Filtered out by _keep_word / stopwords.
    assert "cae29ce2" not in counts
    assert "abc" not in counts
    assert "fix" not in counts
    assert "the" not in counts


def test_render_writes_sorted_markdown(tmp_path: Path) -> None:
    ctx = _ctx(["alpha alpha alpha beta beta gamma"], tmp_path)
    path = CommitWordFrequencies().render(ctx)
    assert path == tmp_path / "commit-word-frequencies.md"
    body = path.read_text()
    assert "# Commit word frequencies" in body
    # Descending order with counts in brackets.
    assert "- alpha [3]" in body
    assert "- beta [2]" in body
    assert "- gamma [1]" in body
    assert body.index("- alpha [3]") < body.index("- beta [2]") < body.index("- gamma [1]")


def test_render_empty_corpus(tmp_path: Path) -> None:
    ctx = _ctx([], tmp_path)
    body = CommitWordFrequencies().render(ctx).read_text()
    assert "(no words captured)" in body


def test_render_against_fixture_repo(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = CommitWordFrequencies().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    assert path.is_file()
    assert path.read_text().startswith("# Commit word frequencies")
