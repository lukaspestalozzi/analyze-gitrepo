from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import plotly.graph_objects as go

from .base import ReportContext


class AuthorLeaderboard:
    id: ClassVar[str] = "author-leaderboard"
    description: ClassVar[str] = "Plotly bar chart, top-N authors."
    filename: ClassVar[str] = "author-leaderboard.html"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        top_n = int(ctx.params.get("top_n", 20))
        authors = ctx.aggregate.authors[:top_n]
        names = [a.display_name for a in authors]

        fig = go.Figure()
        fig.add_trace(go.Bar(name="Commits", x=names, y=[a.commits for a in authors]))
        fig.add_trace(
            go.Bar(name="Lines added", x=names, y=[a.additions for a in authors], visible=False)
        )
        fig.add_trace(
            go.Bar(name="Lines deleted", x=names, y=[a.deletions for a in authors], visible=False)
        )
        fig.update_layout(
            title=f"Top {len(authors)} authors",
            xaxis_title="Author",
            yaxis_title="Count",
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=0.5,
                    xanchor="center",
                    y=1.15,
                    showactive=True,
                    buttons=[
                        dict(
                            label="Commits",
                            method="update",
                            args=[{"visible": [True, False, False]}],
                        ),
                        dict(
                            label="Lines added",
                            method="update",
                            args=[{"visible": [False, True, False]}],
                        ),
                        dict(
                            label="Lines deleted",
                            method="update",
                            args=[{"visible": [False, False, True]}],
                        ),
                    ],
                )
            ],
        )
        fig.write_html(str(out), include_plotlyjs="inline", full_html=True)
        return out
