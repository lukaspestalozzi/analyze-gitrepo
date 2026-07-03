from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import ClassVar

from wordcloud import STOPWORDS

from .base import ReportContext
from .commit_wordcloud import _EXTRA_STOPWORDS, _WORD_RE, _clean, _keep_word


def _word_counts(ctx: ReportContext) -> Counter[str]:
    """Count word occurrences across every commit message.

    Uses the exact same cleaning (`_clean`), token filtering (`_keep_word`)
    and stopword set as the commit wordcloud, so this list is the readable,
    count-annotated companion to `commit-wordcloud.png`. Unlike the wordcloud
    it counts every commit (no subsampling) and keeps every surviving word
    (no `max_words` cap).
    """
    stopwords = {w.lower() for w in STOPWORDS} | _EXTRA_STOPWORDS
    counts: Counter[str] = Counter()
    for rs in ctx.repo_stats:
        for c in rs.commits:
            for tok in _WORD_RE.findall(_clean(c.message)):
                if _keep_word(tok) and tok not in stopwords:
                    counts[tok] += 1
    return counts


class CommitWordFrequencies:
    id: ClassVar[str] = "commit-word-frequencies"
    description: ClassVar[str] = "Markdown: commit-message words ranked by frequency."
    filename: ClassVar[str] = "commit-word-frequencies.md"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset()

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        counts = _word_counts(ctx)

        lines = ["# Commit word frequencies", ""]
        if not counts:
            lines.append("(no words captured)")
            out.write_text("\n".join(lines) + "\n")
            return out

        lines.append(
            f"{len(counts)} distinct words from commit messages, most frequent "
            "first. Same cleaning and stopwords as `commit-wordcloud.png`."
        )
        lines.append("")
        # Sort by descending count, then alphabetically so ties are stable.
        for word, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {word} [{count}]")
        out.write_text("\n".join(lines) + "\n")
        return out
