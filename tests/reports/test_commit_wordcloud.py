from __future__ import annotations

from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.commit_wordcloud import (
    CommitWordcloud,
    _clean,
    _filter_tokens,
    _keep_word,
)
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_clean_strips_jira_keys_and_urls() -> None:
    s = _clean("PROJ-123 fix bug see https://example.com")
    assert "proj-123" not in s
    assert "https" not in s


def test_keep_word_keeps_real_words_and_exceptions() -> None:
    for word in ("refactor", "python3", "utf8", "sha256"):
        assert _keep_word(word), word
    # User-ID exceptions: `u`/`e` + exactly 6 digits.
    assert _keep_word("u123456")
    assert _keep_word("e123456")
    # `rcspf`-prefixed words are kept regardless of digits (case-insensitive
    # because `_clean` lowercases first).
    assert _keep_word("rcspf12345")
    assert _keep_word("rcspfabc")
    assert _keep_word(_clean("RCSPF99"))


def test_keep_word_drops_numeric_junk() -> None:
    assert not _keep_word("cae29ce2")  # interior digit
    assert not _keep_word("abc123def")  # interior digit
    assert not _keep_word("123456")  # more numbers than letters
    assert not _keep_word("1a2b3")  # more numbers than letters
    assert not _keep_word("abc")  # 3-letter word
    # Wrong digit count for a user ID => no exception, dropped as number-heavy.
    assert not _keep_word("u12345")
    assert not _keep_word("u1234567")


def test_filter_tokens_keeps_good_drops_junk() -> None:
    out = _filter_tokens("refactor cae29ce2 u123456 abc")
    assert "refactor" in out
    assert "u123456" in out
    assert "cae29ce2" not in out
    # `abc` dropped (3-letter); check it's gone as a standalone token.
    assert "abc" not in out.split()


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


def test_resolve_max_words_default_and_overrides(capsys) -> None:
    from gitstats.reports.commit_wordcloud import _DEFAULT_MAX_WORDS, _resolve_max_words

    assert _resolve_max_words(None) == _DEFAULT_MAX_WORDS
    assert _resolve_max_words(50) == 50
    # bad inputs warn and fall back
    assert _resolve_max_words(0) == _DEFAULT_MAX_WORDS
    assert _resolve_max_words(-3) == _DEFAULT_MAX_WORDS
    assert _resolve_max_words("plenty") == _DEFAULT_MAX_WORDS
    err = capsys.readouterr().err
    assert err.count("warning:") == 3


def test_load_stopwords_file_reads_words(tmp_path: Path) -> None:
    from gitstats.reports.commit_wordcloud import _load_stopwords_file

    f = tmp_path / "stopwords.txt"
    f.write_text("Foo\n# comment\n\nbar\nBAZ\n")
    extra = _load_stopwords_file(str(f))
    assert extra == {"foo", "bar", "baz"}


def test_load_stopwords_file_missing_warns(tmp_path: Path, capsys) -> None:
    from gitstats.reports.commit_wordcloud import _load_stopwords_file

    extra = _load_stopwords_file(str(tmp_path / "nope.txt"))
    assert extra == set()
    assert "warning:" in capsys.readouterr().err


def test_commit_wordcloud_writes_png(fixture_repo: FixtureRepo, tmp_path: Path) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    path = CommitWordcloud().render(
        ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)
    )
    assert path == tmp_path / "commit-wordcloud.png"
    # PNG magic header.
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
