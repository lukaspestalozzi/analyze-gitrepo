from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import plotly.graph_objects as go

from ..tz import parse_tz
from .base import ReportContext

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class CommitHeatmap:
    id: ClassVar[str] = "commit-heatmap"
    description: ClassVar[str] = "Plotly heatmap of commit times."
    filename: ClassVar[str] = "commit-heatmap.html"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset({"tz"})

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename

        tz_override = ctx.params.get("tz")
        tz = parse_tz(tz_override) if tz_override else ctx.tz

        # 7 days × 24 hours; rows ordered Mon..Sun.
        grid: list[list[int]] = [[0] * 24 for _ in range(7)]
        for rs in ctx.repo_stats:
            for c in rs.commits:
                local = c.timestamp.astimezone(tz)
                grid[local.weekday()][local.hour] += 1

        fig = go.Figure(
            data=go.Heatmap(
                z=grid,
                x=[f"{h:02d}" for h in range(24)],
                y=_DAYS,
                colorscale="Viridis",
                hovertemplate=(
                    "Day: %{y}<br>Hour: %{x}<br>Commits: %{z}<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            title=f"Commit activity (timezone: {tz})",
            xaxis_title="Hour of day",
            yaxis_title="Day of week",
            yaxis=dict(autorange="reversed"),
        )
        fig.write_html(str(out), include_plotlyjs="inline", full_html=True)
        return out
