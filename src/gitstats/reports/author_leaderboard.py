from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar

import plotly.graph_objects as go

from .base import ReportContext

_METRIC_INDEX = {"commits": 0, "additions": 1, "deletions": 2}


def _resolve_default_metric(raw: object) -> int:
    if raw is None:
        return 0
    if not isinstance(raw, str) or raw not in _METRIC_INDEX:
        print(
            f"warning: reports.author-leaderboard.default_metric={raw!r} is "
            f"not one of {sorted(_METRIC_INDEX)}; falling back to 'commits'.",
            file=sys.stderr,
        )
        return 0
    return _METRIC_INDEX[raw]


class AuthorLeaderboard:
    id: ClassVar[str] = "author-leaderboard"
    description: ClassVar[str] = "Plotly bar chart, top-N authors."
    filename: ClassVar[str] = "author-leaderboard.html"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset({"top_n", "default_metric"})

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        top_n = int(ctx.params.get("top_n", 20))
        default_idx = _resolve_default_metric(ctx.params.get("default_metric"))
        authors = ctx.aggregate.authors[:top_n]
        names = [a.display_name for a in authors]

        visible = [i == default_idx for i in range(3)]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(name="Commits", x=names, y=[a.commits for a in authors], visible=visible[0])
        )
        fig.add_trace(
            go.Bar(
                name="Lines added",
                x=names,
                y=[a.additions for a in authors],
                visible=visible[1],
            )
        )
        fig.add_trace(
            go.Bar(
                name="Lines deleted",
                x=names,
                y=[a.deletions for a in authors],
                visible=visible[2],
            )
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
