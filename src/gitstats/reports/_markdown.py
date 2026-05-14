from __future__ import annotations

from collections.abc import Iterable


def markdown_table(headers: list[str], rows: Iterable[list[str]]) -> str:
    """Render a GitHub-flavored markdown table.

    Cells are not escaped — callers are expected to substitute pipe
    characters themselves if needed (they don't occur in our data).
    """
    materialized = [list(map(str, r)) for r in rows]
    widths = [len(h) for h in headers]
    for r in materialized:
        for i, cell in enumerate(r):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    lines = [fmt_row(headers), sep]
    lines.extend(fmt_row(r) for r in materialized)
    return "\n".join(lines)
