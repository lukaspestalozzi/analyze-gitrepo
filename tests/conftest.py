from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygit2
import pytest


@dataclass
class FixtureRepo:
    path: Path
    head_oid: str
    # Mapping commit-label -> oid for assertions
    commits: dict[str, str]


def _signature(name: str, email: str, t: int) -> pygit2.Signature:
    return pygit2.Signature(name, email, t, 0)


def _commit(
    repo: pygit2.Repository,
    *,
    parents: list[str],
    files: dict[str, str],
    author: pygit2.Signature,
    message: str,
) -> str:
    index = repo.index
    if parents:
        parent_commit = repo.get(parents[0])
        index.read_tree(parent_commit.tree)
    for relpath, content in files.items():
        full = Path(repo.workdir) / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        index.add(relpath)
    index.write()
    tree = index.write_tree()
    oid = repo.create_commit("HEAD", author, author, message, tree, parents)
    return str(oid)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> FixtureRepo:
    """A tiny repo with two authors (one with two emails) and one Jira ticket."""
    path = tmp_path / "sample"
    path.mkdir()
    repo = pygit2.init_repository(str(path), bare=False)

    alice_old = _signature("Alice Smith", "alice@old.example", 1_700_000_000)
    alice_new = _signature("Alice Smith", "asmith@new.example", 1_700_001_000)
    bob = _signature("Bob Jones", "bob@example.com", 1_700_002_000)

    commits: dict[str, str] = {}

    commits["c1"] = _commit(
        repo,
        parents=[],
        files={"a.txt": "hello\nworld\n"},
        author=alice_old,
        message="Initial commit",
    )
    commits["c2"] = _commit(
        repo,
        parents=[commits["c1"]],
        files={"a.txt": "hello\nworld\nagain\n", "b.txt": "b\n"},
        author=alice_new,
        message="PROJ-123 add another file",
    )
    commits["c3"] = _commit(
        repo,
        parents=[commits["c2"]],
        files={"a.txt": "hello\nworld\nagain\nplus\n"},
        author=bob,
        message="Fix typo (no ticket)",
    )
    commits["c4"] = _commit(
        repo,
        parents=[commits["c3"]],
        files={"c.txt": "c\n"},
        author=bob,
        message="PROJ-456 PROJ-456 unrelated change",
    )

    return FixtureRepo(path=path, head_oid=commits["c4"], commits=commits)


@pytest.fixture
def multi_repo_root(tmp_path: Path, fixture_repo: FixtureRepo) -> Path:
    """A directory containing two repos (fixture_repo + a copy) to exercise discovery."""
    root = tmp_path / "workspace"
    root.mkdir()

    # Move the fixture repo under the workspace.
    target_a = root / "repo-a"
    fixture_repo.path.rename(target_a)

    # Build a second tiny repo with one author.
    target_b = root / "nested" / "repo-b"
    target_b.mkdir(parents=True)
    repo_b = pygit2.init_repository(str(target_b), bare=False)
    sig = _signature("Carol Wu", "carol@example.com", 1_700_010_000)
    index = repo_b.index
    (Path(repo_b.workdir) / "readme.md").write_text("hi\n")
    index.add("readme.md")
    index.write()
    tree = index.write_tree()
    repo_b.create_commit("HEAD", sig, sig, "PROJ-789 first", tree, [])

    # Add a non-repo dir to verify it is skipped.
    (root / "not-a-repo").mkdir()
    (root / "not-a-repo" / "file.txt").write_text("nope\n")

    # Add a pruned dir to verify it is skipped.
    pruned = root / "node_modules" / "fake"
    pruned.mkdir(parents=True)
    pygit2.init_repository(str(pruned), bare=False)

    return root


@pytest.fixture
def dup_repo_root(tmp_path: Path) -> Path:
    """Two repos sharing one commit with identical message AND author time.

    Each repo has a unique commit plus a common commit (same author signature
    and message but a different tree, so the git SHAs differ). A (message,
    author-date) dedup should collapse the shared commit to a single count.
    """
    root = tmp_path / "dupspace"
    root.mkdir()

    dana = _signature("Dana Lee", "dana@example.com", 1_700_020_000)
    shared = _signature("Dana Lee", "dana@example.com", 1_700_030_000)

    for name, unique_file in (("repo-x", "x.txt"), ("repo-y", "y.txt")):
        target = root / name
        target.mkdir()
        repo = pygit2.init_repository(str(target), bare=False)
        c1 = _commit(
            repo,
            parents=[],
            files={unique_file: f"{name}\n"},
            author=dana,
            message=f"Unique to {name}",
        )
        _commit(
            repo,
            parents=[c1],
            files={"shared.txt": f"shared via {name}\n"},
            author=shared,
            message="Shared change across repos",
        )

    return root
