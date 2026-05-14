from __future__ import annotations

from pathlib import Path

import responses
from typer.testing import CliRunner

from gitstats.cli import app

runner = CliRunner()


def test_scan_without_jira_url_skips_jira_reports(
    multi_repo_root: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", str(multi_repo_root), "-o", str(out), "-j", "1"])
    assert result.exit_code == 0, result.output
    assert not (out / "jira-tickets-by-type.md").exists()
    assert not (out / "jira-tickets-by-type.html").exists()


def test_scan_with_jira_url_missing_token_exits_2(
    multi_repo_root: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("GITSTATS_JIRA_TOKEN", raising=False)
    result = runner.invoke(
        app,
        [
            "scan",
            str(multi_repo_root),
            "-o",
            str(tmp_path / "out"),
            "--jira-url",
            "https://jira.example.com",
        ],
    )
    assert result.exit_code == 2
    assert "GITSTATS_JIRA_TOKEN" in result.output


@responses.activate
def test_scan_with_jira_active_produces_jira_reports(
    multi_repo_root: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GITSTATS_JIRA_TOKEN", "tok")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    # Fixture commits reference PROJ-123, PROJ-456, OTHER-1.
    for key, kind in [("PROJ-123", "Bug"), ("PROJ-456", "Story"), ("OTHER-1", "Task")]:
        responses.add(
            responses.GET,
            f"https://jira.example.com/rest/api/2/issue/{key}",
            json={"fields": {"issuetype": {"name": kind}}},
            status=200,
        )

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
            "--jira-url",
            "https://jira.example.com",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out / "jira-tickets-by-type.md").is_file()
    assert (out / "jira-tickets-by-type.html").is_file()


@responses.activate
def test_scan_with_jira_no_cache_writes_no_cache_files(
    multi_repo_root: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GITSTATS_JIRA_TOKEN", "tok")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    for key, kind in [("PROJ-123", "Bug"), ("PROJ-456", "Story"), ("OTHER-1", "Task")]:
        responses.add(
            responses.GET,
            f"https://jira.example.com/rest/api/2/issue/{key}",
            json={"fields": {"issuetype": {"name": kind}}},
            status=200,
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
            "--jira-url",
            "https://jira.example.com",
            "--jira-no-cache",
        ],
    )
    assert result.exit_code == 0, result.output
    cache_host_dir = tmp_path / "home" / ".cache" / "gitstats" / "jira" / "jira.example.com"
    assert not cache_host_dir.exists() or not any(cache_host_dir.iterdir())


@responses.activate
def test_jira_test_connection_ok(monkeypatch) -> None:
    monkeypatch.setenv("GITSTATS_JIRA_TOKEN", "tok")
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/myself",
        json={"displayName": "Alice", "emailAddress": "a@x"},
        status=200,
    )
    result = runner.invoke(
        app, ["jira", "test-connection", "--jira-url", "https://jira.example.com"]
    )
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output


@responses.activate
def test_jira_test_connection_fails_on_401(monkeypatch) -> None:
    monkeypatch.setenv("GITSTATS_JIRA_TOKEN", "tok")
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/myself",
        status=401,
        body="nope",
    )
    result = runner.invoke(
        app, ["jira", "test-connection", "--jira-url", "https://jira.example.com"]
    )
    assert result.exit_code == 2


def test_jira_clear_cache_no_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(
        app, ["jira", "clear-cache", "--jira-url", "https://jira.example.com"]
    )
    assert result.exit_code == 0
    assert "No cache directory" in result.output


def test_jira_clear_cache_removes_entries(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    host_dir = tmp_path / ".cache" / "gitstats" / "jira" / "jira.example.com"
    host_dir.mkdir(parents=True)
    (host_dir / "PROJ-1.json").write_text("{}")
    (host_dir / "PROJ-2.json").write_text("{}")
    result = runner.invoke(
        app, ["jira", "clear-cache", "--jira-url", "https://jira.example.com"]
    )
    assert result.exit_code == 0, result.output
    assert "Removed 2" in result.output
    assert not host_dir.exists()
