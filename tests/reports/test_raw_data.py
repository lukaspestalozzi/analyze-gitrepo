from __future__ import annotations

import json
from pathlib import Path

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.reports import ReportContext
from gitstats.reports.raw_data import RawData
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_raw_data_writes_valid_json_with_authors(
    fixture_repo: FixtureRepo, tmp_path: Path
) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    ctx = ReportContext(repo_stats=[stats], aggregate=agg, output_dir=tmp_path)

    path = RawData().render(ctx)
    assert path == tmp_path / "raw-data.json"

    data = json.loads(path.read_text())
    assert {"authors", "repos", "generated_at"} <= data.keys()
    names = {a["display_name"] for a in data["authors"]}
    assert names == {"Alice Smith", "Bob Jones"}
    # `emails` must be a sorted list, not a set (JSON-incompatible).
    for a in data["authors"]:
        assert isinstance(a["emails"], list)
        assert a["emails"] == sorted(a["emails"])
