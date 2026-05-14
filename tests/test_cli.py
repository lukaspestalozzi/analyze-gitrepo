from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from gitstats.cli import app
from tests.conftest import FixtureRepo

runner = CliRunner()


def test_reports_subcommand_lists_catalog() -> None:
    result = runner.invoke(app, ["reports"])
    assert result.exit_code == 0, result.output
    assert "author-summary" in result.output
    assert "raw-data" in result.output


def test_reports_list_alias() -> None:
    result = runner.invoke(app, ["reports", "list"])
    assert result.exit_code == 0
    assert "author-summary" in result.output


def test_scan_default_runs_all_reports(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", str(multi_repo_root), "-o", str(out), "-j", "1"])
    assert result.exit_code == 0, result.output
    assert (out / "author-summary.md").is_file()
    assert (out / "raw-data.json").is_file()


def test_scan_with_report_filter(multi_repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(out), "-j", "1", "--report", "raw-data"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "raw-data.json").is_file()
    assert not (out / "author-summary.md").exists()


def test_scan_with_skip(multi_repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(out), "-j", "1", "--skip", "raw-data"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "author-summary.md").is_file()
    assert not (out / "raw-data.json").exists()


def test_report_and_skip_are_mutex(multi_repo_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(tmp_path),
            "--report",
            "raw-data",
            "--skip",
            "author-summary",
        ],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_unknown_report_id(multi_repo_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(tmp_path), "--report", "no-such"],
    )
    assert result.exit_code == 2
    assert "unknown report" in result.output


def test_invalid_date_exits_2(multi_repo_root: Path, tmp_path: Path) -> None:
    """Regression: invalid `--since` used to bubble a Python traceback (exit 1)."""
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(tmp_path), "--since", "2025-13-99"],
    )
    assert result.exit_code == 2, result.output
    assert "invalid date" in result.output


def test_invalid_tz(multi_repo_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(tmp_path), "--tz", "Mars/Olympus"],
    )
    assert result.exit_code == 2
    assert "unknown timezone" in result.output


def test_no_repos_under_root(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(app, ["scan", str(empty), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "no git repositories" in result.output


def test_root_does_not_exist(tmp_path: Path) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path / "nope"), "-o", str(tmp_path / "out")])
    assert result.exit_code == 2


def test_failing_report_yields_exit_3(
    fixture_repo: FixtureRepo, tmp_path: Path, monkeypatch
) -> None:
    """If a report raises, the run continues but exits 3."""
    from gitstats.reports import author_summary as mod

    original = mod.AuthorSummary.render

    def boom(self, ctx):  # type: ignore[no-untyped-def]
        raise RuntimeError("intentional")

    monkeypatch.setattr(mod.AuthorSummary, "render", boom)
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["scan", str(fixture_repo.path.parent), "-o", str(out), "-j", "1"]
    )
    assert result.exit_code == 3, result.output
    # raw-data should still have been written
    assert (out / "raw-data.json").is_file()
    # restore (pytest will restore the monkeypatch too)
    mod.AuthorSummary.render = original  # type: ignore[method-assign]
