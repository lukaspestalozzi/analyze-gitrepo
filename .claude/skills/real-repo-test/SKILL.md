---
name: real-repo-test
description: Run end-to-end real-repo integration tests for the gitstats CLI. Use this skill whenever the user finishes a CLI-facing change in this repo (new flag, new report, output-format tweak, identity-merging change, error-handling adjustment), before merging or updating a PR that touches src/gitstats/cli.py, src/gitstats/reports/, src/gitstats/tz.py, src/gitstats/config.py, src/gitstats/identity.py, src/gitstats/aggregator.py, or src/gitstats/scanner.py, when validating output shapes or performance claims against realistic data, or when the user says "smoke test", "integration test", "test against real repos", "verify the CLI", or anything similar — even if they don't name this skill. The pytest suite covers Jira via `responses` stubs; this skill clones psf/requests + urllib3/urllib3 and exercises every non-Jira CLI feature, then reports a pass/fail checklist.
---

# real-repo integration test for `gitstats`

This skill verifies the `gitstats` CLI against two large public
repositories. It complements the in-tree pytest suite by exercising
the full CLI surface — flag parsing, exit codes, output filenames,
artifact shapes — on realistic data the unit fixture can't simulate
(thousands of commits, hundreds of authors with overlapping emails,
multiple repos under one root).

## When to invoke

- After landing any change in `src/gitstats/cli.py` or
  `src/gitstats/reports/`.
- Before opening or updating a PR that touches CLI surface, output
  format, identity merging, or error handling.
- When pytest is green but you want one more layer of confidence.
- When validating performance or output-shape claims against
  realistic data.

Why: pytest fixtures are small (~5 commits, 2 authors). Many bugs
only surface on real data — for instance, the `--since 2025-13-99`
bug fixed in commit `520a0fc` was found by this exact procedure.

## How to run

```bash
bash .claude/skills/real-repo-test/scripts/run.sh
```

Exit code 0 = every section passed.
Exit code 1 = at least one section failed; the offending section's
`[fail] <id> - <reason>` line on stderr identifies it.

The runner wipes `/tmp/gs-itest/` at the start, clones the two test
repos, and runs every check sequentially. Total wall-clock is
~2 min on a 4-core machine. Network access is required (git clone
from GitHub).

## What's tested

Each id below maps to one `_test_<id>` function in `scripts/run.sh`.
The *purpose* explains why each one exists so that, on failure, you
can localize the regression by reading just that bullet.

- `catalog-listing` — `gitstats reports` enumerates every registered
  report. Guards the registry-import path.
- `default-scan` — a flag-less scan writes every always-on report.
  Guards the run loop and the Jira-only filter (Jira reports must
  be skipped without `--jira-url`).
- `report-filter` — `--report ID` runs only the named report(s).
- `skip-filter` — `--skip ID` runs everything but the named
  report(s).
- `tz-utc` / `tz-iana` — `--tz` propagates to the heatmap title.
  Without this, heatmap bucketing silently uses UTC even when the
  user requested a local zone.
- `date-range` — `--since/--until` reduces the commit count and
  the scan runtime. Filter is applied during scan, not after.
- `include-merges` — `--include-merges` adds exactly the merge count
  reported by `git log --merges`.
- `identity-map` — a YAML override collapses aliased emails into one
  canonical author whose `source` is `override+observed`.
- `only-mapped` — `--show-only-mapped-identities` drops every commit
  whose author does not resolve to an identity-map group (only the
  mapped author remains, and the per-repo commit counts sum to
  exactly that author's total — no unmapped commits leak through).
- `parallelism` — `-j 4` is at least as fast as `-j 1` on two repos.
- `report-config` — nested YAML (`gitstats.tz` + `reports.<id>.*`)
  applies; per-report keys override global keys.
- `config-warnings` — unknown top-level sections, unknown
  `gitstats.*` keys, and unknown report ids each produce a stderr
  warning.
- `error-mutex` / `error-unknown-id` / `error-bad-tz` /
  `error-missing-root` / `error-no-repos` / `error-bad-date` /
  `error-only-mapped-no-map` — each exit code matches spec §13
  (the last one: `--show-only-mapped-identities` without
  `--identity-map` exits 2).
- `artifact-shapes` — `raw-data.json` has the expected top-level
  keys with `emails` as a list; PNGs have the PNG magic header;
  HTML files start with `<html`.

## How `scripts/run.sh` is structured

One function per test id (`_test_catalog_listing`,
`_test_default_scan`, etc.), each ending in either `log_ok` or
`log_fail`. `main` calls `_setup` (clean + clone) then every test in
catalog order. The exit code is 0 iff every `log_fail` was avoided.

Pass criteria intentionally generalize: e.g. "writes the expected
file count for an always-on default run", not a hard-coded list of
filenames. When you add a new always-on report, you'll only need to
bump that count in one place.

## Extending this skill

When the CLI gains a new feature:

1. Add a bullet to **What's tested** above explaining the *why* in
   one sentence.
2. Add a `_test_<id>` function in `scripts/run.sh` and call it from
   `main`.
3. If the new feature changes existing output (e.g. a new always-on
   report), update the affected `_test_*` function and the relevant
   bullet.

When a feature is removed: delete the catalog bullet, the
`_test_<id>` function, and the `main` call.

## Cleanup

The runner wipes `/tmp/gs-itest/` at the start, so successive runs
are idempotent. Artifacts (HTML, PNG, MD, JSON) stay in place after
the run for inspection. To free disk completely:

```bash
rm -rf /tmp/gs-itest
```

## Jira

Out of scope for this skill. Pytest covers the Jira flows
deterministically using the `responses` library
(`tests/test_jira_enricher.py`, `tests/test_jira_cli.py`,
`tests/reports/test_jira_tickets_by_type.py`). Running the live
Jira path against a real Jira instance is not currently automated.
