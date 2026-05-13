from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

PRUNE_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "build",
        "dist",
    }
)


def find_repos(root: Path) -> Iterator[Path]:
    """Yield directories that contain a `.git` entry (file or dir).

    Prunes descent into found repos and common junk directories.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(root)

    for dirpath, dirnames, _filenames in os.walk(root):
        current = Path(dirpath)
        if (current / ".git").exists():
            yield current
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS and not d.startswith(".")]
