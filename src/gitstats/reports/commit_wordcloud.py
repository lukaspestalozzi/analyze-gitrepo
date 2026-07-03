from __future__ import annotations

import random
import re
import sys
from pathlib import Path
from typing import ClassVar

from wordcloud import STOPWORDS, WordCloud

from ..scanner import JIRA_RE
from .base import ReportContext

_URL_RE = re.compile(r"https?://\S+")
# Backticked spans and dotted identifiers / paths.
_CODEY_RE = re.compile(r"`[^`]*`|[A-Za-z_][\w.]*\.\w+")

# Token-level junk filtering (see `_keep_word`). `_clean` lowercases the text
# first, so these operate on lowercase input.
_USER_ID_RE = re.compile(r"[ue]\d{6}")  # user IDs: `u`/`e` + exactly 6 digits
# A letter, then a digit, then a letter => a digit sitting between letters.
_INTERIOR_DIGIT_RE = re.compile(r"[^\W\d_].*\d.*[^\W\d_]")
# Mirrors the wordcloud library's own token shape so we filter exactly the
# tokens it would form.
_WORD_RE = re.compile(r"\w[\w']*")
# Common German stopwords / "Bindewörter" (conjunctions, articles,
# pronouns, prepositions, auxiliaries). Commit messages in this corpus mix
# German and English, so these clutter the cloud just like the English
# STOPWORDS the wordcloud library already strips.
_GERMAN_STOPWORDS = {
    "aber", "als", "also", "am", "an", "auch", "auf", "aus",
    "bei", "beim", "bis", "bzw",
    "da", "damit", "dann", "das", "dass", "dem", "den", "denn", "der",
    "des", "diese", "diesem", "diesen", "dieser", "dieses", "doch", "dort",
    "durch",
    "ein", "eine", "einem", "einen", "einer", "eines", "einige", "etwas",
    "für",
    "gegen", "gibt",
    "hab", "habe", "haben", "hat", "hatte", "hatten", "hier",
    "ich", "ihr", "ihre", "im", "immer", "in", "ins", "ist",
    "ja", "jede", "jeden", "jeder", "jetzt",
    "kann", "kein", "keine", "keinen", "können",
    "mal", "man", "mehr", "mit", "muss", "müssen",
    "nach", "nicht", "noch", "nun", "nur",
    "ob", "oder", "ohne",
    "schon", "sehr", "sein", "seine", "sich", "sie", "sind", "so", "soll",
    "sollen", "sondern", "sowie",
    "über", "um", "und", "uns", "unser", "unter",
    "vom", "von", "vor",
    "war", "waren", "warum", "was", "weil", "weiter", "welche", "wenn",
    "werden", "wie", "wieder", "wird", "wir", "wurde", "wurden",
    "zu", "zum", "zur", "zwischen",
}

_EXTRA_STOPWORDS = {
    "merge", "revert", "wip", "tmp", "todo",
    "fix", "fixed", "fixes",
    "add", "added", "adds",
    "update", "updated", "updates",
    "remove", "removed", "bump",
    "review",
    # Ubiquitous, low-signal terms from this corpus (see issue #3).
    "commit", "author", "nicht", "bb43",
} | _GERMAN_STOPWORDS

_DEFAULT_MAX_WORDS = 200

# Wordcloud frequency / layout cost grows with input size but the visual
# output saturates well before a few thousand messages, so cap input length
# by default. Override via `reports.commit-wordcloud.sample_size` (set to
# `null` / 0 / a value greater than the commit count to disable sampling).
_DEFAULT_SAMPLE_SIZE = 5000
_SAMPLE_SEED = 20260514  # fixed so successive runs produce the same artwork


def _clean(message: str) -> str:
    text = JIRA_RE.sub(" ", message)
    text = _URL_RE.sub(" ", text)
    text = _CODEY_RE.sub(" ", text)
    return text.lower()


def _keep_word(word: str) -> bool:
    """Return True if `word` should stay in the wordcloud.

    A *word* cloud has no use for hash-like or number-heavy tokens, so we drop
    them — but keep a couple of meaningful patterns. `word` is expected to be
    lowercase (as produced by `_clean`).
    """
    # Keep-exceptions win over every removal rule below.
    if _USER_ID_RE.fullmatch(word) or word.startswith("rcspf"):
        return True
    if len(word) < 4:  # drop 1-, 2- and 3-character words
        return False
    digits = sum(c.isdigit() for c in word)
    letters = sum(c.isalpha() for c in word)
    if digits > letters:  # more numbers than letters
        return False
    if _INTERIOR_DIGIT_RE.search(word):  # a digit wedged between letters
        return False
    return True


def _filter_tokens(text: str) -> str:
    """Drop junk tokens (see `_keep_word`), replacing them with a space."""
    return _WORD_RE.sub(lambda m: m.group(0) if _keep_word(m.group(0)) else " ", text)


def _resolve_sample_size(raw: object) -> int | None:
    """Return the effective sample cap.

    Accepts the `reports.commit-wordcloud.sample_size` knob from
    `--report-config`. Use `null`, `0`, or a negative value to disable
    sampling entirely; an integer caps the message count. Missing key
    falls back to `_DEFAULT_SAMPLE_SIZE` so large corpora stay fast.
    """
    if raw is None:
        return _DEFAULT_SAMPLE_SIZE
    if isinstance(raw, bool):  # `True`/`False` aren't meaningful here
        return _DEFAULT_SAMPLE_SIZE
    if isinstance(raw, int) and raw > 0:
        return raw
    return None  # 0 or negative = no cap


def _resolve_max_words(raw: object) -> int:
    if raw is None:
        return _DEFAULT_MAX_WORDS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        print(
            f"warning: reports.commit-wordcloud.max_words={raw!r} is not a "
            f"positive integer; falling back to {_DEFAULT_MAX_WORDS}.",
            file=sys.stderr,
        )
        return _DEFAULT_MAX_WORDS
    return raw


def _load_stopwords_file(raw: object) -> set[str]:
    if raw is None:
        return set()
    try:
        path = Path(str(raw))
        text = path.read_text()
    except OSError as e:
        print(
            f"warning: reports.commit-wordcloud.stopwords_file={raw!r} "
            f"could not be read ({e}); ignoring.",
            file=sys.stderr,
        )
        return set()
    extra: set[str] = set()
    for line in text.splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        extra.add(word.lower())
    return extra


class CommitWordcloud:
    id: ClassVar[str] = "commit-wordcloud"
    description: ClassVar[str] = "Wordcloud of commit messages."
    filename: ClassVar[str] = "commit-wordcloud.png"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset(
        {"sample_size", "max_words", "stopwords_file"}
    )

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        sample_size = _resolve_sample_size(ctx.params.get("sample_size"))
        max_words = _resolve_max_words(ctx.params.get("max_words"))
        extra_stopwords = _load_stopwords_file(ctx.params.get("stopwords_file"))

        # Collect every commit message and (optionally) subsample. WordCloud
        # quality saturates well before a few thousand messages but layout
        # cost grows linearly, so capping inputs keeps the report fast on
        # huge corpora without changing small-repo behavior.
        messages: list[str] = [c.message for rs in ctx.repo_stats for c in rs.commits]
        if sample_size is not None and sample_size > 0 and len(messages) > sample_size:
            messages = random.Random(_SAMPLE_SEED).sample(messages, sample_size)

        chunks = [_clean(m) for m in messages]

        text = " ".join(chunks).strip()
        text = _filter_tokens(text).strip()
        if not text:
            # WordCloud raises on empty input; write a tiny placeholder PNG
            # by feeding a known-stable string.
            text = "no commit messages captured"

        stopwords = set(STOPWORDS) | _EXTRA_STOPWORDS | extra_stopwords
        wc = WordCloud(
            width=1600,
            height=900,
            background_color="white",
            max_words=max_words,
            stopwords=stopwords,
            min_word_length=4,
        )
        wc.generate(text)
        wc.to_file(str(out))
        return out
