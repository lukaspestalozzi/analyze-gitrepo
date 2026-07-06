from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.models import Commit, RepoStats
from gitstats.reports import ReportContext
from gitstats.reports.commit_wordcloud_interactive import CommitWordcloudInteractive


def _ctx(messages: list[str], output_dir: Path, **params) -> ReportContext:
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
    return ReportContext(
        repo_stats=[rs], aggregate=agg, output_dir=output_dir, params=params
    )


def _embedded_words(html: str) -> list[list]:
    """Extract the JSON payload from the report's <script id="data"> tag."""
    m = re.search(
        r'<script id="data"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    assert m, "data script tag not found"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_render_writes_self_contained_html_with_word_data(tmp_path: Path) -> None:
    ctx = _ctx(["refactor scanner refactor refactor", "refactor parser"], tmp_path)
    path = CommitWordcloudInteractive().render(ctx)
    assert path == tmp_path / "commit-wordcloud-interactive.html"

    text = path.read_text()
    assert "<html" in text.lower()
    # Self-contained: no external CDN references — opens offline like the PNG.
    assert 'src="http' not in text
    assert 'href="http' not in text

    words = dict((w, n) for w, n in _embedded_words(text))
    assert words["refactor"] == 4
    assert words["scanner"] == 1
    assert words["parser"] == 1


def test_max_words_caps_embedded_data(tmp_path: Path) -> None:
    messages = [" ".join([f"word{i}"] * (30 - i)) for i in range(10)]
    ctx = _ctx(messages, tmp_path, max_words=3)
    words = _embedded_words(CommitWordcloudInteractive().render(ctx).read_text())
    assert len(words) == 3
    # most_common keeps the highest-frequency words.
    assert [w for w, _ in words] == ["word0", "word1", "word2"]


def test_stopwords_file_removes_word(tmp_path: Path) -> None:
    stop = tmp_path / "stop.txt"
    stop.write_text("scanner\n")
    ctx = _ctx(
        ["refactor scanner refactor", "scanner scanner"],
        tmp_path,
        stopwords_file=str(stop),
    )
    words = dict((w, n) for w, n in _embedded_words(
        CommitWordcloudInteractive().render(ctx).read_text()
    ))
    assert "refactor" in words
    assert "scanner" not in words


def test_render_empty_corpus(tmp_path: Path) -> None:
    ctx = _ctx([], tmp_path)
    text = CommitWordcloudInteractive().render(ctx).read_text()
    assert "<html" in text.lower()
    assert _embedded_words(text) == []


def test_max_words_invalid_warns_and_falls_back(tmp_path: Path, capsys) -> None:
    ctx = _ctx(["alpha beta gamma"], tmp_path, max_words=0)
    CommitWordcloudInteractive().render(ctx)
    assert "max_words" in capsys.readouterr().err
