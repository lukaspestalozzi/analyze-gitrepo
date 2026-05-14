from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

KNOWN_GLOBAL_KEYS = frozenset({"tz"})


@dataclass
class ReportConfig:
    """Resolved view of `--report-config`.

    `global_params` covers the top-level `gitstats:` section. `per_report`
    is keyed by report id with each value the raw mapping from
    `reports.<id>:`. Reports merge global + per-id at lookup time.
    """

    global_params: dict[str, Any] = field(default_factory=dict)
    per_report: dict[str, dict[str, Any]] = field(default_factory=dict)

    def params_for(self, report_id: str) -> dict[str, Any]:
        merged: dict[str, Any] = dict(self.global_params)
        merged.update(self.per_report.get(report_id, {}))
        return merged


def load_report_config(
    path: Path | str | None,
    *,
    known_report_ids: set[str] | None = None,
) -> ReportConfig:
    if path is None:
        return ReportConfig()
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"report-config at {path} must be a mapping")

    global_params: dict[str, Any] = {}
    per_report: dict[str, dict[str, Any]] = {}

    for top_key, value in raw.items():
        if top_key == "gitstats":
            if not isinstance(value, dict):
                _warn(f"`gitstats:` section in {path} must be a mapping; ignoring")
                continue
            for k, v in value.items():
                if k not in KNOWN_GLOBAL_KEYS:
                    _warn(f"unknown key `gitstats.{k}` in {path}; ignoring")
                    continue
                global_params[k] = v
        elif top_key == "reports":
            if not isinstance(value, dict):
                _warn(f"`reports:` section in {path} must be a mapping; ignoring")
                continue
            for rid, params in value.items():
                if known_report_ids is not None and rid not in known_report_ids:
                    _warn(f"unknown report id `reports.{rid}` in {path}; ignoring")
                    continue
                if not isinstance(params, dict):
                    _warn(f"`reports.{rid}` must be a mapping; ignoring")
                    continue
                per_report[rid] = dict(params)
        else:
            _warn(f"unknown top-level section `{top_key}` in {path}; ignoring")

    return ReportConfig(global_params=global_params, per_report=per_report)


def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)
