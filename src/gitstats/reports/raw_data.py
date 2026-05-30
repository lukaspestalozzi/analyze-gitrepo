from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from ..models import Aggregate
from .base import ReportContext


def aggregate_to_dict(agg: Aggregate) -> dict[str, Any]:
    def normalize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [normalize(v) for v in obj]
        return obj

    return {
        "generated_at": agg.generated_at.isoformat(),
        "repos": [normalize(asdict(r)) for r in agg.repos],
        "authors": [normalize(asdict(a)) for a in agg.authors],
    }


class RawData:
    id: ClassVar[str] = "raw-data"
    description: ClassVar[str] = "Full aggregate as JSON."
    filename: ClassVar[str] = "raw-data.json"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset()

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        out.write_text(json.dumps(aggregate_to_dict(ctx.aggregate), indent=2, sort_keys=True))
        return out
