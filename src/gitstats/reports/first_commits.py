from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from ._markdown import markdown_table
from .base import ReportContext


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt is not None else "-"


class FirstCommits:
    id: ClassVar[str] = "first-commits"
    description: ClassVar[str] = "Per-author first/last commit per repo."
    filename: ClassVar[str] = "first-commits.md"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        agg = ctx.aggregate

        authors_by_first = sorted(
            agg.authors,
            key=lambda a: (a.first_commit or datetime.max.replace(tzinfo=None)),
        )

        lines: list[str] = ["# First commits", ""]
        lines.append(f"Generated at {agg.generated_at.isoformat()}.")
        lines.append("")

        for a in authors_by_first:
            emails = ", ".join(sorted(a.emails))
            lines.append(f"## {a.display_name} ({emails})")
            lines.append("")
            lines.append(f"- First commit overall: {_iso(a.first_commit)}")
            lines.append(f"- Last commit overall: {_iso(a.last_commit)}")
            lines.append(f"- Total commits: {a.commits}")
            lines.append("")
            rows = [
                [r, p.commits, _iso(p.first_commit), _iso(p.last_commit)]
                for r, p in sorted(a.per_repo.items())
            ]
            lines.append(markdown_table(["Repo", "Commits", "First commit", "Last commit"], rows))
            lines.append("")

        out.write_text("\n".join(lines))
        return out
