from __future__ import annotations

from .author_summary import AuthorSummary
from .base import ReportContext, ReportRenderer, ReportResult
from .raw_data import RawData

REPORTS: list[type[ReportRenderer]] = [
    AuthorSummary,
    RawData,
]

__all__ = [
    "REPORTS",
    "ReportContext",
    "ReportRenderer",
    "ReportResult",
]
