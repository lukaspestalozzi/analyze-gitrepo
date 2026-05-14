from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from ._markdown import markdown_table
from .base import ReportContext


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt is not None else "-"


class AuthorSummary:
    id: ClassVar[str] = "author-summary"
    description: ClassVar[str] = "Markdown table of authors with totals."
    filename: ClassVar[str] = "author-summary.md"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset()

    def render(self, ctx: ReportContext) -> Path:
        agg = ctx.aggregate
        out = ctx.output_dir / self.filename

        lines: list[str] = ["# Author summary", ""]
        lines.append(f"Generated at {agg.generated_at.isoformat()}.")
        lines.append("")
        lines.append(f"## Repositories ({len(agg.repos)})")
        lines.append("")
        repo_rows = [
            [r.name, r.commits, r.authors, _iso(r.first_commit), _iso(r.last_commit)]
            for r in agg.repos
        ]
        lines.append(
            markdown_table(
                ["Name", "Commits", "Authors", "First commit", "Last commit"],
                repo_rows,
            )
        )
        lines.append("")
        lines.append(f"## Authors ({len(agg.authors)})")
        lines.append("")
        author_rows = [
            [
                a.display_name,
                a.commits,
                a.additions,
                a.deletions,
                a.files_touched,
                _iso(a.first_commit),
                _iso(a.last_commit),
                len(a.per_repo),
            ]
            for a in agg.authors
        ]
        lines.append(
            markdown_table(
                ["Author", "Commits", "+", "-", "Files", "First commit", "Last commit", "Repos"],
                author_rows,
            )
        )
        lines.append("")

        out.write_text("\n".join(lines))
        return out
