# analyze-gitrepo / `gitstats`

A Python CLI that auto-discovers git repositories under a directory and
produces per-author commit statistics across all of them.

## Features (MVP)

- **Auto-discovery** of git repos under a root directory (skips `.venv`,
  `node_modules`, etc., and does not recurse into found repos).
- **Per-author statistics**: total commits, lines added/removed, files
  changed, first commit, last commit — per repo and aggregated across
  all repos.
- **Cross-repo identity merging**: the same person under different emails
  is counted as one author. Union-find on normalized email/name, with
  optional YAML overrides for manual mapping.
- **Fast**: uses [pygit2](https://www.pygit2.org/) (libgit2 C bindings)
  and parallelizes across repos with `ProcessPoolExecutor`. Scans a
  large repo in seconds.
- **Output formats**: Rich table (default), JSON, CSV.
- **Jira-ready**: extracts ticket keys (`PROJ-123`) from commit messages
  at scan time. A future `CommitEnricher` plugin will join these against
  Jira ticket data to enrich stats (e.g. "bugfixes per author").

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
gitstats scan <root-dir>
gitstats scan ~/code --format json --output stats.json
gitstats scan ~/code --identity-map identities.yaml
gitstats scan ~/code --since 2025-01-01 --jobs 8
```

### `identities.yaml` example

```yaml
Alice Smith:
  - alice@old.example
  - asmith@new.example
  - 12345+alicesmith@users.noreply.github.com
```

## Project layout

```
src/gitstats/
├── cli.py          # Typer entry point
├── discovery.py    # find_repos(root)
├── scanner.py      # scan_repo(path) using pygit2
├── identity.py     # IdentityResolver (union-find + YAML overrides)
├── aggregator.py   # repo stats -> Report
├── enrichment.py   # CommitEnricher Protocol (Jira hook)
├── report.py       # render table / json / csv
└── models.py       # dataclasses
tests/              # pytest with pygit2-built fixture repo
```

## Development

```bash
python -m pytest          # run tests
ruff check .              # lint
mypy src                  # type-check
```
