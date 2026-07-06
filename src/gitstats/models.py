from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    timestamp: datetime
    additions: int
    deletions: int
    files_changed: int
    committer_timestamp: datetime | None = None
    message: str = ""
    jira_tickets: tuple[str, ...] = ()
    is_merge: bool = False
    metadata: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


@dataclass
class RepoStats:
    path: Path
    commits: list[Commit]

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class RepoAuthorStats:
    repo: str
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    files_touched: int = 0
    first_commit: datetime | None = None
    last_commit: datetime | None = None


@dataclass
class AuthorStats:
    author_id: str
    display_name: str
    emails: set[str] = field(default_factory=set)
    commits: int = 0
    additions: int = 0
    deletions: int = 0
    files_touched: int = 0
    first_commit: datetime | None = None
    last_commit: datetime | None = None
    # SHA and message of the author's overall first commit (by timestamp).
    first_commit_sha: str | None = None
    first_commit_message: str = ""
    per_repo: dict[str, RepoAuthorStats] = field(default_factory=dict)


@dataclass
class RepoSummary:
    path: str
    name: str
    commits: int
    authors: int
    first_commit: datetime | None
    last_commit: datetime | None
    # SHA and message of the repo's first commit (by timestamp).
    first_commit_sha: str | None = None
    first_commit_message: str = ""


@dataclass
class Aggregate:
    authors: list[AuthorStats]
    repos: list[RepoSummary]
    generated_at: datetime
