from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from .base import ReportContext


class IdentityDebug:
    id: ClassVar[str] = "identity-debug"
    description: ClassVar[str] = "Markdown: which identities merged into each author."
    filename: ClassVar[str] = "identity-debug.md"
    requires_jira: ClassVar[bool] = False

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        lines: list[str] = ["# Identity debug", ""]
        if ctx.resolver is None:
            lines.append("(no IdentityResolver available)")
            out.write_text("\n".join(lines))
            return out

        # Sort groups by author_id for stable output.
        groups = sorted(ctx.resolver.groups(), key=lambda g: g.author_id)
        for g in groups:
            lines.append(f"## {g.display_name}   (id: {g.author_id})")
            lines.append("")
            lines.append(f"source: {g.source}")
            emails = ", ".join(sorted(g.emails)) or "-"
            lines.append(f"emails: {emails}")
            spellings = ", ".join(
                f"{name} ({n})" for name, n in g.name_observations.most_common()
            ) or "-"
            lines.append(f"observed name spellings: {spellings}")
            lines.append("")

        out.write_text("\n".join(lines))
        return out
