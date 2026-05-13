from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console

from .aggregator import aggregate
from .discovery import find_repos
from .identity import IdentityResolver
from .models import RepoStats
from .report import render
from .scanner import scan_repo

app = typer.Typer(
    add_completion=False,
    help="Analyze git repositories under a directory and produce author/commit stats.",
)
err = Console(stderr=True)


@app.callback()
def _root() -> None:
    """gitstats — multi-repo git history analyzer."""


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _scan_one(args: tuple[str, bool, str | None, str | None]) -> RepoStats:
    path, include_merges, since_iso, until_iso = args
    since = datetime.fromisoformat(since_iso) if since_iso else None
    until = datetime.fromisoformat(until_iso) if until_iso else None
    return scan_repo(path, include_merges=include_merges, since=since, until=until)


@app.command()
def scan(
    root: Path = typer.Argument(..., exists=True, file_okay=False, help="Directory to search."),
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, or csv."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to file instead of stdout."
    ),
    jobs: int = typer.Option(
        os.cpu_count() or 1, "--jobs", "-j", help="Parallel worker processes."
    ),
    since: str | None = typer.Option(
        None, "--since", help="Only include commits on/after YYYY-MM-DD."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Only include commits on/before YYYY-MM-DD."
    ),
    identity_map: Path | None = typer.Option(
        None,
        "--identity-map",
        exists=True,
        dir_okay=False,
        help="YAML file mapping canonical names to email lists.",
    ),
    include_merges: bool = typer.Option(
        False, "--include-merges", help="Include merge commits (default: skip)."
    ),
) -> None:
    """Discover git repositories under ROOT and report author statistics."""
    if fmt not in {"table", "json", "csv"}:
        err.print(f"[red]unknown --format: {fmt}[/red]")
        raise typer.Exit(2)

    since_dt = _parse_date(since)
    until_dt = _parse_date(until)

    repos = list(find_repos(root))
    if not repos:
        err.print(f"[yellow]no git repositories found under {root}[/yellow]")
        raise typer.Exit(1)

    err.print(f"Scanning {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}...")

    work = [
        (str(p), include_merges, since_dt.isoformat() if since_dt else None,
         until_dt.isoformat() if until_dt else None)
        for p in repos
    ]

    repo_stats: list[RepoStats]
    if jobs > 1 and len(repos) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            repo_stats = list(pool.map(_scan_one, work))
    else:
        repo_stats = [_scan_one(w) for w in work]

    resolver = IdentityResolver.from_yaml(identity_map)
    report = aggregate(repo_stats, resolver)
    render(report, fmt, output)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app() or 0)
