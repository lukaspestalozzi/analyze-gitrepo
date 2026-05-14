from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from ..models import Aggregate, RepoStats

if TYPE_CHECKING:
    from ..identity import IdentityResolver


@dataclass(frozen=True)
class ReportContext:
    """Inputs passed to every report's `render` call.

    Reports may read freely from `aggregate` and `repo_stats` but must
    not mutate them. `params` carries the per-report mapping from the
    optional `--report-config` file (empty dict if none). `tz` is the
    CLI-resolved default timezone (`--tz`); a per-report override of
    `tz` may live in `params`.
    """

    repo_stats: list[RepoStats]
    aggregate: Aggregate
    output_dir: Path
    tz: tzinfo = timezone.utc
    params: dict[str, Any] = field(default_factory=dict)
    resolver: IdentityResolver | None = None


@dataclass(frozen=True)
class ReportResult:
    report_id: str
    output_path: Path
    ok: bool
    error: str | None = None


@runtime_checkable
class ReportRenderer(Protocol):
    """Plugin interface for report renderers.

    Concrete classes are instantiated with no arguments; per-run inputs
    come through `ReportContext`. Class-level constants describe the
    catalog entry shown by `gitstats reports`.
    """

    id: ClassVar[str]
    description: ClassVar[str]
    filename: ClassVar[str]
    requires_jira: ClassVar[bool]

    def render(self, ctx: ReportContext) -> Path: ...
