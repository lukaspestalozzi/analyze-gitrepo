from __future__ import annotations

import json

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.report import render_csv, render_json
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_render_json_is_valid_and_contains_authors(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    report = aggregate([stats], IdentityResolver())
    text = render_json(report)
    data = json.loads(text)
    assert "authors" in data and "repos" in data and "generated_at" in data
    names = {a["display_name"] for a in data["authors"]}
    assert names == {"Alice Smith", "Bob Jones"}


def test_render_csv_has_header_and_rows(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    report = aggregate([stats], IdentityResolver())
    text = render_csv(report)
    lines = text.strip().splitlines()
    assert lines[0].startswith("author_id,display_name,emails,commits,")
    assert len(lines) == 1 + 2  # header + 2 authors
