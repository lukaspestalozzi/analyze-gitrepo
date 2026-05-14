from __future__ import annotations

from .author_leaderboard import AuthorLeaderboard
from .author_summary import AuthorSummary
from .base import ReportContext, ReportRenderer, ReportResult
from .commit_heatmap import CommitHeatmap
from .commit_wordcloud import CommitWordcloud
from .first_commits import FirstCommits
from .identity_debug import IdentityDebug
from .jira_tickets_by_type import JiraTicketsByTypeHTML, JiraTicketsByTypeMarkdown
from .raw_data import RawData
from .repo_summary import RepoSummary

REPORTS: list[type[ReportRenderer]] = [
    AuthorSummary,
    FirstCommits,
    CommitHeatmap,
    RawData,
    CommitWordcloud,
    RepoSummary,
    AuthorLeaderboard,
    IdentityDebug,
    JiraTicketsByTypeMarkdown,
    JiraTicketsByTypeHTML,
]

__all__ = [
    "REPORTS",
    "ReportContext",
    "ReportRenderer",
    "ReportResult",
]
