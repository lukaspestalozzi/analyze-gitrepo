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


def test_show_only_mapped_requires_identity_map(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    """Spec §4.1: --show-only-mapped-identities without --identity-map runs nothing."""
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(out), "--show-only-mapped-identities"],
    )
    assert result.exit_code == 2
    assert "--show-only-mapped-identities requires --identity-map" in result.output
    # Nothing ran: the output dir is only created right before reports render.
    assert not out.exists()


def test_show_only_mapped_filters_reports(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    """Spec §4.1: only mapped authors' commits reach the reports. Mapping a single
    email must still keep Alice's other-email commit (name-based union)."""
    import json

    yml = tmp_path / "map.yaml"
    yml.write_text("Alice Smith:\n  - alice@old.example\n")
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(out),
            "-j",
            "1",
            "--identity-map",
            str(yml),
            "--show-only-mapped-identities",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((out / "raw-data.json").read_text())
    assert [a["display_name"] for a in data["authors"]] == ["Alice Smith"]
    # Both of Alice's emails survive: the unlisted one is linked by author name.
    assert set(data["authors"][0]["emails"]) == {
        "alice@old.example",
        "asmith@new.example",
    }
    assert {r["name"]: r["commits"] for r in data["repos"]} == {
        "repo-a": 2,
        "repo-b": 0,
    }
    summary = (out / "author-summary.md").read_text()
    assert "Alice Smith" in summary
    assert "Bob Jones" not in summary
    assert "Carol Wu" not in summary


def test_show_only_mapped_no_matches_warns(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    """Spec §4.1: a map matching no commits warns and renders empty reports."""
    import json

    yml = tmp_path / "map.yaml"
    yml.write_text("Nobody:\n  - nobody@example.com\n")
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(out),
            "-j",
            "1",
            "--identity-map",
            str(yml),
            "--show-only-mapped-identities",
            "--report",
            "raw-data",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "matched no commits" in result.output
    data = json.loads((out / "raw-data.json").read_text())
    assert data["authors"] == []
    assert all(repo["commits"] == 0 for repo in data["repos"])


def test_unknown_report_id(multi_repo_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["scan", str(multi_repo_root), "-o", str(tmp_path), "--report", "no-such"],
    )
    assert result.exit_code == 2
    assert "unknown report" in result.output


def test_timing_emits_per_phase_lines(multi_repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(out),
            "-j",
            "1",
            "--report",
            "raw-data",
            "--timing",
        ],
    )
    assert result.exit_code == 0, result.output
    # Stderr+stdout are merged by CliRunner; look for the phase markers.
    for marker in ("discovery:", "scan:", "aggregate:", "report:raw-data:", "total:"):
        assert marker in result.output, f"missing {marker!r} in:\n{result.output}"


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


def test_unknown_per_report_key_warns(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    cfg = tmp_path / "report-config.yaml"
    cfg.write_text(
        "reports:\n"
        "  commit-wordcloud:\n"
        "    fake_knob: 1\n"
        "  author-summary:\n"
        "    also_fake: true\n"
    )
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(tmp_path / "out"),
            "-j",
            "1",
            "--report-config",
            str(cfg),
            "--report",
            "raw-data",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "reports.commit-wordcloud.fake_knob" in result.output
    assert "reports.author-summary.also_fake" in result.output


def test_dedup_on_by_default_collapses_shared_commit(
    dup_repo_root: Path, tmp_path: Path
) -> None:
    """Two repos share one (message, date)-identical commit; by default it is
    counted once and the earlier-sorted repo path keeps it."""
    import json

    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", str(dup_repo_root), "-o", str(out), "-j", "1"])
    assert result.exit_code == 0, result.output
    assert "Removed 1 duplicate commit" in result.output

    data = json.loads((out / "raw-data.json").read_text())
    # repo-x sorts before repo-y, so it keeps the shared commit.
    assert {r["name"]: r["commits"] for r in data["repos"]} == {
        "repo-x": 2,
        "repo-y": 1,
    }
    dana = next(a for a in data["authors"] if a["display_name"] == "Dana Lee")
    assert dana["commits"] == 3  # 2 unique + 1 shared (not 4)


def test_no_deduplicate_commits_keeps_both(
    dup_repo_root: Path, tmp_path: Path
) -> None:
    import json

    out = tmp_path / "out"
    result = runner.invoke(
        app,
        ["scan", str(dup_repo_root), "-o", str(out), "-j", "1", "--no-deduplicate-commits"],
    )
    assert result.exit_code == 0, result.output
    assert "duplicate commit" not in result.output

    data = json.loads((out / "raw-data.json").read_text())
    assert {r["name"]: r["commits"] for r in data["repos"]} == {
        "repo-x": 2,
        "repo-y": 2,
    }
    dana = next(a for a in data["authors"] if a["display_name"] == "Dana Lee")
    assert dana["commits"] == 4
