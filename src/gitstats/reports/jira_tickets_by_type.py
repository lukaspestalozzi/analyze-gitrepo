from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import ClassVar

import plotly.graph_objects as go

from ._markdown import markdown_table
from .base import ReportContext


def _author_to_type_counts(ctx: ReportContext) -> dict[str, Counter[str]]:
    """Count commits per (canonical author, jira_first_issuetype).

    Requires the JiraEnricher to have populated `commit.metadata`. Each
    commit is attributed to its canonical author via the resolver.
    """
    resolver = ctx.resolver
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for rs in ctx.repo_stats:
        for c in rs.commits:
            issuetype = c.metadata.get("jira_first_issuetype")
            if not issuetype:
                continue
            if resolver is None:
                display = c.author_name or c.author_email
            else:
                display = resolver.display_name(c.author_name, c.author_email)
            counts[display][issuetype] += 1
    return counts


def _all_types(counts: dict[str, Counter[str]]) -> list[str]:
    totals: Counter[str] = Counter()
    for c in counts.values():
        totals.update(c)
    # Most-touched issue type first.
    return [t for t, _ in totals.most_common()]


class JiraTicketsByTypeMarkdown:
    id: ClassVar[str] = "jira-tickets-by-type-md"
    description: ClassVar[str] = "Markdown: commits per author per Jira issue type."
    filename: ClassVar[str] = "jira-tickets-by-type.md"
    requires_jira: ClassVar[bool] = True

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        counts = _author_to_type_counts(ctx)
        if not counts:
            out.write_text("# Jira tickets by type\n\n(no classified commits)\n")
            return out

        types = _all_types(counts)
        headers = ["Author", *types, "Total"]
        rows: list[list[str]] = []
        for author in sorted(counts.keys(), key=lambda a: -sum(counts[a].values())):
            row = [author]
            row.extend(str(counts[author].get(t, 0)) for t in types)
            row.append(str(sum(counts[author].values())))
            rows.append(row)

        lines = ["# Jira tickets by type", ""]
        lines.append(
            "Commits per canonical author, classified by the issue type of "
            "the first Jira ticket key in the commit message (see spec §11.1.3)."
        )
        lines.append("")
        lines.append(markdown_table(headers, rows))
        lines.append("")
        out.write_text("\n".join(lines))
        return out


class JiraTicketsByTypeHTML:
    id: ClassVar[str] = "jira-tickets-by-type-html"
    description: ClassVar[str] = "Plotly stacked bar of the same data."
    filename: ClassVar[str] = "jira-tickets-by-type.html"
    requires_jira: ClassVar[bool] = True

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        counts = _author_to_type_counts(ctx)
        types = _all_types(counts)
        # Authors sorted by total descending so the tallest stacks sit on the left.
        authors = sorted(counts.keys(), key=lambda a: -sum(counts[a].values()))

        fig = go.Figure()
        for t in types:
            fig.add_trace(go.Bar(name=t, x=authors, y=[counts[a].get(t, 0) for a in authors]))
        fig.update_layout(
            barmode="stack",
            title="Commits per author by Jira issue type",
            xaxis_title="Author",
            yaxis_title="Commits",
        )
        fig.write_html(str(out), include_plotlyjs="inline", full_html=True)
        return out
