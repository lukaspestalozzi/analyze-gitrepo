from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .aggregator import aggregate
from .config import load_report_config
from .discovery import find_repos
from .enrichers.jira import JiraAuthError, JiraEnricher, cache_host, config_from_env
from .identity import IdentityResolver
from .models import RepoStats
from .reports import REPORTS, ReportContext, ReportResult
from .scanner import scan_repo
from .tz import parse_tz

app = typer.Typer(
    add_completion=False,
    help="Analyze git repositories under a directory and produce report files.",
)
reports_app = typer.Typer(help="List available reports.", invoke_without_command=True)
app.add_typer(reports_app, name="reports")
jira_app = typer.Typer(help="Jira-workflow utilities.")
app.add_typer(jira_app, name="jira")
err = Console(stderr=True)


@app.callback()
def _root() -> None:
    """gitstats — multi-repo git history analyzer."""


def _parse_date(value: str | None, tz) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError as e:
        err.print(f"[red]invalid date {value!r}: expected YYYY-MM-DD ({e})[/red]")
        raise typer.Exit(2) from e


def _scan_one(args: tuple[str, bool, str | None, str | None]) -> RepoStats:
    path, include_merges, since_iso, until_iso = args
    since = datetime.fromisoformat(since_iso) if since_iso else None
    until = datetime.fromisoformat(until_iso) if until_iso else None
    return scan_repo(path, include_merges=include_merges, since=since, until=until)


def _resolve_selection(
    report_flags: list[str], skip_flags: list[str], jira_active: bool
) -> list[type]:
    known = {cls.id: cls for cls in REPORTS}

    if report_flags and skip_flags:
        err.print("[red]--report and --skip are mutually exclusive[/red]")
        raise typer.Exit(2)

    if report_flags:
        unknown = [r for r in report_flags if r not in known]
        if unknown:
            err.print(
                f"[red]unknown report id(s): {', '.join(unknown)}[/red]\n"
                f"available: {', '.join(known)}"
            )
            raise typer.Exit(2)
        return [known[r] for r in report_flags]

    if skip_flags:
        unknown = [r for r in skip_flags if r not in known]
        if unknown:
            err.print(
                f"[red]unknown report id(s): {', '.join(unknown)}[/red]\n"
                f"available: {', '.join(known)}"
            )
            raise typer.Exit(2)
        candidates = [cls for cls in REPORTS if cls.id not in set(skip_flags)]
    else:
        candidates = list(REPORTS)

    if not jira_active:
        candidates = [cls for cls in candidates if not getattr(cls, "requires_jira", False)]
    return candidates


@app.command()
def scan(
    root: Path = typer.Argument(..., exists=True, file_okay=False, help="Directory to search."),
    report: list[str] = typer.Option(
        None, "--report", help="Run only these reports. Repeatable. Mutex with --skip."
    ),
    skip: list[str] = typer.Option(
        None, "--skip", help="Run all reports except these. Repeatable. Mutex with --report."
    ),
    output_dir: Path = typer.Option(
        Path("./gitstats-reports"),
        "--output-dir",
        "-o",
        help="Directory where report files are written.",
    ),
    report_config: Path | None = typer.Option(
        None,
        "--report-config",
        exists=True,
        dir_okay=False,
        help="YAML file with per-report parameters.",
    ),
    tz_arg: str | None = typer.Option(
        None, "--tz", help="Timezone: utc, local, or IANA name (e.g. Europe/Zurich)."
    ),
    jobs: int = typer.Option(
        os.cpu_count() or 1, "--jobs", "-j", help="Parallel worker processes."
    ),
    since: str | None = typer.Option(
        None, "--since", help="Only include commits on/after YYYY-MM-DD (in --tz)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Only include commits on/before YYYY-MM-DD (in --tz)."
    ),
    identity_map: Path | None = typer.Option(
        None,
        "--identity-map",
        exists=True,
        dir_okay=False,
        help="YAML file pinning canonical identities.",
    ),
    include_merges: bool = typer.Option(
        False, "--include-merges", help="Include merge commits (default: skip)."
    ),
    jira_url: str | None = typer.Option(
        None,
        "--jira-url",
        help="Jira base URL. Enables the Jira enricher. Also via GITSTATS_JIRA_URL.",
    ),
) -> None:
    """Discover git repositories under ROOT and write report files."""
    try:
        tz = parse_tz(tz_arg)
    except ValueError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from e

    cfg = load_report_config(report_config, known_report_ids={cls.id for cls in REPORTS})

    try:
        jira_config = config_from_env(jira_url)
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from e

    since_dt = _parse_date(since, tz)
    until_dt = _parse_date(until, tz)

    selected = _resolve_selection(report or [], skip or [], jira_active=jira_config is not None)

    repos = list(find_repos(root))
    if not repos:
        err.print(f"[yellow]no git repositories found under {root}[/yellow]")
        raise typer.Exit(1)

    err.print(f"Scanning {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'}...")

    work = [
        (
            str(p),
            include_merges,
            since_dt.isoformat() if since_dt else None,
            until_dt.isoformat() if until_dt else None,
        )
        for p in repos
    ]

    repo_stats: list[RepoStats]
    if jobs > 1 and len(repos) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            repo_stats = list(pool.map(_scan_one, work))
    else:
        repo_stats = [_scan_one(w) for w in work]

    if jira_config is not None:
        err.print(f"Fetching Jira issue types from {jira_config.base_url}...")
        enricher = JiraEnricher(jira_config)
        try:
            for rs in repo_stats:
                rs.commits = list(enricher.enrich(rs.commits))
        except JiraAuthError as e:
            err.print(f"[red]{e}[/red]")
            raise typer.Exit(2) from e

    resolver = IdentityResolver.from_yaml(identity_map)
    agg = aggregate(repo_stats, resolver)

    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[ReportResult] = []
    for cls in selected:
        params = cfg.params_for(cls.id)
        ctx = ReportContext(
            repo_stats=repo_stats,
            aggregate=agg,
            output_dir=output_dir,
            tz=tz,
            params=params,
            resolver=resolver,
        )
        try:
            path = cls().render(ctx)
            results.append(ReportResult(report_id=cls.id, output_path=path, ok=True))
        except Exception as e:  # noqa: BLE001 - record and continue per spec §9.3
            results.append(
                ReportResult(
                    report_id=cls.id,
                    output_path=output_dir / cls.filename,
                    ok=False,
                    error=str(e),
                )
            )

    for r in results:
        if r.ok:
            err.print(f"[green][ok][/green]   {r.report_id:24} -> {r.output_path}")
        else:
            err.print(f"[red][fail][/red] {r.report_id:24} {r.error}")

    if any(not r.ok for r in results):
        raise typer.Exit(3)


@reports_app.callback(invoke_without_command=True)
def reports_default(ctx: typer.Context) -> None:
    """Print the registered-report catalog."""
    if ctx.invoked_subcommand is not None:
        return
    _print_catalog()


@reports_app.command("list")
def reports_list() -> None:
    """Print the registered-report catalog (alias)."""
    _print_catalog()


def _print_catalog() -> None:
    table = Table(title=f"Available reports ({len(REPORTS)})")
    table.add_column("ID")
    table.add_column("Output file")
    table.add_column("Jira", justify="center")
    table.add_column("Description")
    for cls in REPORTS:
        jira_mark = "✓" if getattr(cls, "requires_jira", False) else ""
        table.add_row(cls.id, cls.filename, jira_mark, cls.description)
    Console().print(table)


@jira_app.command("test-connection")
def jira_test_connection(
    jira_url: str | None = typer.Option(
        None, "--jira-url", help="Jira base URL. Also via GITSTATS_JIRA_URL."
    ),
) -> None:
    """Validate Jira URL/credentials by calling /rest/api/2/myself."""
    import requests

    try:
        cfg = config_from_env(jira_url)
    except RuntimeError as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(2) from e
    if cfg is None:
        err.print("[red]Jira inactive: pass --jira-url or set GITSTATS_JIRA_URL.[/red]")
        raise typer.Exit(2)

    session = requests.Session()
    if cfg.user:
        session.auth = (cfg.user, cfg.token)
    else:
        session.headers["Authorization"] = f"Bearer {cfg.token}"
    url = f"{cfg.base_url.rstrip('/')}/rest/api/2/myself"
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        err.print(f"[red]network error: {e}[/red]")
        raise typer.Exit(2) from e
    if resp.status_code >= 400:
        err.print(f"[red]Jira returned {resp.status_code}: {resp.text[:300]}[/red]")
        raise typer.Exit(2)
    data = resp.json()
    print(
        f"OK: {data.get('displayName', '?')} <{data.get('emailAddress', '?')}>"
    )


@jira_app.command("clear-cache")
def jira_clear_cache(
    jira_url: str | None = typer.Option(
        None, "--jira-url", help="Jira base URL. Also via GITSTATS_JIRA_URL."
    ),
) -> None:
    """Remove the per-host Jira cache directory."""
    try:
        cfg = config_from_env(jira_url)
    except RuntimeError:
        # Token isn't actually needed to clear the cache, but the URL is.
        cfg = None
    base_url = (
        cfg.base_url if cfg is not None else (jira_url or os.environ.get("GITSTATS_JIRA_URL"))
    )
    if not base_url:
        err.print("[red]Jira inactive: pass --jira-url or set GITSTATS_JIRA_URL.[/red]")
        raise typer.Exit(2)
    from .enrichers.jira import default_cache_root

    host_dir = default_cache_root() / cache_host(base_url)
    if not host_dir.is_dir():
        print(f"No cache directory at {host_dir}.")
        return
    removed = 0
    for entry in host_dir.iterdir():
        if entry.is_file():
            entry.unlink()
            removed += 1
    host_dir.rmdir()
    print(f"Removed {removed} cached entr{'y' if removed == 1 else 'ies'} from {host_dir}.")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    app()
