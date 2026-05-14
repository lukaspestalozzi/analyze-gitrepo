from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from ._markdown import markdown_table
from .base import ReportContext


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt is not None else "-"


class RepoSummary:
    id: ClassVar[str] = "repo-summary"
    description: ClassVar[str] = "Markdown: per-repo totals and top contributors."
    filename: ClassVar[str] = "repo-summary.md"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        agg = ctx.aggregate

        # Pre-compute per-repo author rankings from agg.authors.
        per_repo_authors: dict[str, list[tuple[str, int, int, int, int]]] = {}
        for a in agg.authors:
            for repo_name, p in a.per_repo.items():
                per_repo_authors.setdefault(repo_name, []).append(
                    (a.display_name, p.commits, p.additions, p.deletions, p.files_touched)
                )

        # Ticket counts per repo (distinct keys observed at scan time).
        tickets_per_repo: dict[str, set[str]] = {}
        for rs in ctx.repo_stats:
            ts = tickets_per_repo.setdefault(rs.name, set())
            for c in rs.commits:
                ts.update(c.jira_tickets)

        lines: list[str] = ["# Repository summary", ""]
        lines.append(f"Generated at {agg.generated_at.isoformat()}.")
        lines.append("")

        for r in agg.repos:
            lines.append(f"## {r.name}")
            lines.append("")
            lines.append(f"Path: `{r.path}`")
            lines.append("")
            lines.append(
                f"Commits: {r.commits} · Authors: {r.authors} · "
                f"First: {_iso(r.first_commit)} · Last: {_iso(r.last_commit)}"
            )
            lines.append("")
            tickets = tickets_per_repo.get(r.name, set())
            lines.append(f"Jira ticket keys referenced (distinct): {len(tickets)}")
            lines.append("")

            ranked = sorted(per_repo_authors.get(r.name, []), key=lambda x: x[1], reverse=True)[:5]
            rows = [list(x) for x in ranked]
            lines.append("**Top contributors**")
            lines.append("")
            lines.append(markdown_table(["Author", "Commits", "+", "-", "Files"], rows))
            lines.append("")

        out.write_text("\n".join(lines))
        return out
