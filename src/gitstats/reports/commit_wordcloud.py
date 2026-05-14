from __future__ import annotations

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


def _clean(message: str) -> str:
    text = JIRA_RE.sub(" ", message)
    text = _URL_RE.sub(" ", text)
    text = _CODEY_RE.sub(" ", text)
    return text.lower()


class CommitWordcloud:
    id: ClassVar[str] = "commit-wordcloud"
    description: ClassVar[str] = "Wordcloud of commit messages."
    filename: ClassVar[str] = "commit-wordcloud.png"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename

        # WordCloud expects a single string and does its own tokenization.
        # We feed in cleaned commit messages joined by spaces.
        chunks: list[str] = []
        for rs in ctx.repo_stats:
            for c in rs.commits:
                chunks.append(_clean(c.message))

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
