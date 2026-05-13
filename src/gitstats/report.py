from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .models import Report


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _report_to_dict(report: Report) -> dict[str, Any]:
    def normalize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [normalize(v) for v in obj]
        return obj

    return {
        "generated_at": report.generated_at.isoformat(),
        "repos": [normalize(asdict(r)) for r in report.repos],
        "authors": [normalize(asdict(a)) for a in report.authors],
    }


def render_json(report: Report) -> str:
    return json.dumps(_report_to_dict(report), indent=2, sort_keys=True)


def render_csv(report: Report) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "author_id",
            "display_name",
            "emails",
            "commits",
            "additions",
            "deletions",
            "files_touched",
            "first_commit",
            "last_commit",
        ]
    )
    for a in report.authors:
        writer.writerow(
            [
                a.author_id,
                a.display_name,
                ";".join(sorted(a.emails)),
                a.commits,
                a.additions,
                a.deletions,
                a.files_touched,
                _iso(a.first_commit) or "",
                _iso(a.last_commit) or "",
            ]
        )
    return buf.getvalue()


def render_table(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    repo_table = Table(title=f"Repositories ({len(report.repos)})")
    repo_table.add_column("Name")
    repo_table.add_column("Commits", justify="right")
    repo_table.add_column("Authors", justify="right")
    repo_table.add_column("First commit")
    repo_table.add_column("Last commit")
    for r in report.repos:
        repo_table.add_row(
            r.name,
            str(r.commits),
            str(r.authors),
            _iso(r.first_commit) or "-",
            _iso(r.last_commit) or "-",
        )
    console.print(repo_table)

    author_table = Table(title=f"Authors ({len(report.authors)})")
    author_table.add_column("Author")
    author_table.add_column("Commits", justify="right")
    author_table.add_column("+", justify="right")
    author_table.add_column("-", justify="right")
    author_table.add_column("Files", justify="right")
    author_table.add_column("First commit")
    author_table.add_column("Last commit")
    author_table.add_column("Repos", justify="right")
    for a in report.authors:
        author_table.add_row(
            a.display_name,
            str(a.commits),
            str(a.additions),
            str(a.deletions),
            str(a.files_touched),
            _iso(a.first_commit) or "-",
            _iso(a.last_commit) or "-",
            str(len(a.per_repo)),
        )
    console.print(author_table)


def render(report: Report, fmt: str, output: Path | None = None) -> None:
    fmt = fmt.lower()
    if fmt == "table":
        if output is None:
            render_table(report)
        else:
            with output.open("w") as fh:
                render_table(report, Console(file=fh, force_terminal=False))
        return
    if fmt == "json":
        text = render_json(report)
    elif fmt == "csv":
        text = render_csv(report)
    else:
        raise ValueError(f"unknown format: {fmt}")
    if output is None:
        print(text)
    else:
        output.write_text(text)
