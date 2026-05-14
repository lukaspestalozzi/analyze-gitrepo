from __future__ import annotations

import random
import re
from pathlib import Path
from typing import ClassVar

from wordcloud import STOPWORDS, WordCloud

from ..scanner import JIRA_RE
from .base import ReportContext

_URL_RE = re.compile(r"https?://\S+")
# Backticked spans and dotted identifiers / paths.
_CODEY_RE = re.compile(r"`[^`]*`|[A-Za-z_][\w.]*\.\w+")
_EXTRA_STOPWORDS = {
    "merge", "revert", "wip", "tmp", "todo",
    "fix", "fixed", "fixes",
    "add", "added", "adds",
    "update", "updated", "updates",
    "remove", "removed", "bump",
}

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


class CommitWordcloud:
    id: ClassVar[str] = "commit-wordcloud"
    description: ClassVar[str] = "Wordcloud of commit messages."
    filename: ClassVar[str] = "commit-wordcloud.png"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        sample_size = _resolve_sample_size(ctx.params.get("sample_size"))

        # Collect every commit message and (optionally) subsample. WordCloud
        # quality saturates well before a few thousand messages but layout
        # cost grows linearly, so capping inputs keeps the report fast on
        # huge corpora without changing small-repo behavior.
        messages: list[str] = [c.message for rs in ctx.repo_stats for c in rs.commits]
        if sample_size is not None and sample_size > 0 and len(messages) > sample_size:
            messages = random.Random(_SAMPLE_SEED).sample(messages, sample_size)

        chunks = [_clean(m) for m in messages]

        text = " ".join(chunks).strip()
        if not text:
            # WordCloud raises on empty input; write a tiny placeholder PNG
            # by feeding a known-stable string.
            text = "no commit messages captured"

        stopwords = set(STOPWORDS) | _EXTRA_STOPWORDS
        wc = WordCloud(
            width=1600,
            height=900,
            background_color="white",
            max_words=200,
            stopwords=stopwords,
            min_word_length=3,
        )
        wc.generate(text)
        wc.to_file(str(out))
        return out
