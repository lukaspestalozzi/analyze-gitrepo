from __future__ import annotations

from pathlib import Path

from gitstats.discovery import find_repos


def test_finds_two_repos_and_prunes(multi_repo_root: Path) -> None:
    found = {p.name for p in find_repos(multi_repo_root)}
    assert found == {"repo-a", "repo-b"}


def test_does_not_descend_into_found_repos(multi_repo_root: Path) -> None:
    # repo-a contains files but no sub-repos, repo-b similarly.
    # Just confirm no inner .git scan duplicates results.
    found = list(find_repos(multi_repo_root))
    assert len(found) == 2
