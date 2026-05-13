# `gitstats` — Specification

> **Status:** living document. Sections marked **TBD** are open for
> discussion; everything else describes the current behavior of the
> code on `main`. This is the single source of truth: features get
> specified here **before** they are implemented.

## 1. Overview & goals

`gitstats` is a Python CLI that auto-discovers git repositories under a
directory and produces author-centric statistics across all of them
combined. It is designed to answer questions like:

- "Across all our repos, how many commits has each person made?"
- "When did Alice make her first commit anywhere?"
- "How many lines did Bob add to repo-X last quarter?"
- *(planned)* "How many bugfix tickets did each engineer ship across
  all our services last quarter?"

**Primary use cases**

1. Onboarding/team retrospectives — who has worked where, since when.
2. Engineering-effectiveness reports — commit/line throughput per
   author per repo, cross-repo aggregated.
3. *(planned)* Jira-enriched analytics — joining commits to tickets to
   slice stats by issue type (bug, feature, etc.).

## 2. Non-goals

- Not a replacement for `git blame` or code-review tooling.
- Not a productivity-measurement tool — line counts and commit counts
  are weak proxies for impact and are documented as such.
- No GUI; CLI only.
- No remote git access — operates on local working copies only.
- Bare repositories are out of scope (the discovery step requires a
  `.git` entry inside a working directory).

## 3. Glossary

| Term | Meaning |
|---|---|
| **Repo** | A directory containing a `.git` entry, discovered via filesystem walk. |
| **Commit** | A non-merge commit on the discovered HEAD by default; merge commits included only with `--include-merges`. |
| **Author** | A canonical identity produced by `IdentityResolver`. One author may have multiple `(name, email)` pairs. |
| **Identity** | A `(name, email)` pair as recorded in the git commit's author header. |
| **Ticket** | A Jira-style key matching `[A-Z][A-Z0-9]+-\d+` found in a commit message. |
| **Enricher** | A pluggable post-scan step that attaches metadata to commits (see §11). |

## 4. CLI surface

The console script is `gitstats`. There is currently one subcommand,
`scan`. Future commands (§14) will be siblings.

```
gitstats scan ROOT [OPTIONS]
```

| Flag | Type | Default | Behavior |
|---|---|---|---|
| `ROOT` (positional) | dir | required | Directory to recursively search for repos. |
| `--format / -f` | `table\|json\|csv` | `table` | Output format. |
| `--output / -o` | path | stdout | Write to file instead of stdout. |
| `--jobs / -j` | int | `os.cpu_count()` | Worker processes for parallel repo scanning. |
| `--since` | `YYYY-MM-DD` | — | Drop commits older than this date (UTC, inclusive). |
| `--until` | `YYYY-MM-DD` | — | Drop commits newer than this date (UTC, inclusive). |
| `--identity-map` | path | — | YAML file pinning canonical identities (see §10). |
| `--include-merges` | flag | off | Include merge commits (counted with first-parent diff). |

**Examples**

```bash
gitstats scan ~/code
gitstats scan ~/code -f json -o stats.json
gitstats scan ~/code --identity-map identities.yaml --since 2025-01-01
gitstats scan ~/code -j 8 --include-merges
```

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | No git repositories found under `ROOT`. |
| 2 | Bad CLI arguments (invalid `--format`, malformed date, missing path). |

## 5. Discovery rules

Implemented in `src/gitstats/discovery.py::find_repos`.

- Walks the filesystem from `ROOT` using `os.walk`.
- A directory is treated as a repo if it contains a `.git` entry
  (file or directory). The repo path is yielded **and** descent into
  the repo is stopped (no submodule traversal).
- These directories are pruned from the walk (case-sensitive exact
  match): `.venv`, `venv`, `env`, `node_modules`, `__pycache__`,
  `.tox`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `target`,
  `build`, `dist`.
- Any directory whose name starts with `.` is also pruned (so
  `.cache`, `.gradle`, etc., are skipped without an explicit entry).
- **Bare repos are out of scope.** A directory ending in `.git` that
  is itself the bare repo (rather than containing a `.git`) is not
  yielded by the current implementation.

## 6. Commit scanning

Implemented in `src/gitstats/scanner.py::scan_repo`.

- Opens the repo with `pygit2.Repository`.
- Walks `repo.walk(repo.head.target, GIT_SORT_TIME)` — newest commit
  first. If the repo has no HEAD (unborn branch), an empty
  `RepoStats` is returned without error.
- **Merge handling**: a commit with >1 parents is a merge.
  - By default merges are **skipped** (no `Commit` emitted).
  - With `--include-merges`, the merge is included and its diff is
    computed against the **first parent only**.
- **Root commit**: diffed against the empty tree
  (`commit.tree.diff_to_tree(swap=True)`), so all lines count as
  additions.
- **Diff stats**: `(insertions, deletions, files_changed)` come from
  `diff.stats` (libgit2-computed; `files_changed` is the number of
  files in the patch).
- **Filters**:
  - `--since YYYY-MM-DD` and `--until YYYY-MM-DD` are converted to
    UTC midnight and applied inclusively against the **author** time
    of each commit.
- **Jira ticket extraction**: every commit message is scanned with
  the regex `\b[A-Z][A-Z0-9]+-\d+\b`. Matches are deduplicated
  preserving first-occurrence order and stored on `Commit.jira_tickets`.
  This runs at scan time even before any enrichers are configured.

## 7. Identity merging

Implemented in `src/gitstats/identity.py::IdentityResolver`.

### 7.1 Email normalization

1. Lowercase and strip whitespace.
2. If the email matches `(\d+\+)?(?P<user>[^@]+)@users\.noreply\.github\.com`,
   collapse to `{user}@users.noreply.github.com` (so
   `12345+alice@users.noreply.github.com` and `alice@users.noreply.github.com`
   become the same).
3. Otherwise, drop everything from `+` to `@` in the local part
   (`alice+work@example.com` → `alice@example.com`).
4. An empty or `@`-less string is returned unchanged.

### 7.2 Name normalization

`" ".join(name.lower().split())` — lowercase and collapse whitespace.

### 7.3 Union-find merge

Each observed `(name, email)` pair contributes two graph nodes
(`name::<normalized-name>` and `email::<normalized-email>`) and a union
edge between them. Two identities end up in the same group if they
share **either** a normalized email or a normalized name (transitively).

Practical effects:

- The same person under two emails but the same name → merged.
- The same email but slightly different names → merged.
- Two different people with the same name and no overlapping email →
  **merged** (false-positive risk; the YAML override is the escape hatch).

### 7.4 Canonical identity

- `author_id` = first 12 hex chars of `sha1(group_root_key)`. Stable
  for a given resolver state but may change if observation order
  shifts the union-find root; treat as opaque within a single run.
- `display_name` selection order:
  1. If any node in the group came from the YAML override, use the
     override's canonical name verbatim.
  2. Otherwise, the most frequently observed original name in the
     group.

### 7.5 YAML override file

See §10.

## 8. Data model

Defined in `src/gitstats/models.py`. All datetimes are timezone-aware.

### `Commit` (frozen)
| Field | Type | Notes |
|---|---|---|
| `sha` | `str` | Full git OID. |
| `author_name` | `str` | Verbatim from commit header. |
| `author_email` | `str` | Verbatim from commit header. |
| `timestamp` | `datetime` | Author time, with the commit's tz offset. |
| `additions` | `int` | Lines added per `diff.stats`. |
| `deletions` | `int` | Lines deleted per `diff.stats`. |
| `files_changed` | `int` | Number of files in the commit's diff. |
| `jira_tickets` | `tuple[str, ...]` | Dedup'd, first-occurrence order. |
| `is_merge` | `bool` | `True` only when `--include-merges` is on. |
| `metadata` | `dict[str, Any]` | Reserved for enrichers (§11). Empty in MVP. |

### `RepoStats`
| Field | Type |
|---|---|
| `path` | `Path` |
| `commits` | `list[Commit]` |
| `name` | property → `path.name` |

### `RepoAuthorStats`
Per-author stats scoped to one repo: `repo`, `commits`, `additions`,
`deletions`, `files_touched`, `first_commit`, `last_commit`.

### `AuthorStats`
Cross-repo aggregation per canonical author: `author_id`,
`display_name`, `emails: set[str]`, `commits`, `additions`,
`deletions`, `files_touched`, `first_commit`, `last_commit`,
`per_repo: dict[str, RepoAuthorStats]`.

> **Unit note**: `files_touched` is a **sum across commits** of
> per-commit `files_changed`, not a count of unique files. A file
> touched in 5 commits contributes 5. This is intentional for MVP;
> see §14 for the planned `unique_files` variant.

### `RepoSummary`
`path`, `name`, `commits`, `authors` (distinct in this repo),
`first_commit`, `last_commit`.

### `Report`
`authors: list[AuthorStats]` (sorted by `commits` desc),
`repos: list[RepoSummary]` (sorted by `name`),
`generated_at: datetime` (UTC).

## 9. Output formats

### 9.1 Table (default)

Rich tables, one for repos and one for authors. Truncated to the
terminal width by Rich. No top-N limit currently (see §14 TBD).

### 9.2 JSON

Pretty-printed with sorted keys, 2-space indent. Top-level shape:

```json
{
  "generated_at": "2026-05-13T20:17:00+00:00",
  "repos": [
    {
      "path": "/home/user/code/repo-a",
      "name": "repo-a",
      "commits": 42,
      "authors": 5,
      "first_commit": "2024-01-15T10:00:00+00:00",
      "last_commit": "2026-05-12T18:30:00+00:00"
    }
  ],
  "authors": [
    {
      "author_id": "086f06e0f825",
      "display_name": "Alice Smith",
      "emails": ["alice@example.com", "alice@other.com"],
      "commits": 17,
      "additions": 5234,
      "deletions": 1102,
      "files_touched": 89,
      "first_commit": "2024-01-15T10:00:00+00:00",
      "last_commit": "2026-05-12T18:30:00+00:00",
      "per_repo": {
        "repo-a": {
          "repo": "repo-a",
          "commits": 9,
          "additions": 3120,
          "deletions": 605,
          "files_touched": 41,
          "first_commit": "...",
          "last_commit": "..."
        }
      }
    }
  ]
}
```

- All `datetime` fields are ISO-8601 strings with tz offset.
- `emails` is serialized as a sorted list (sets aren't valid JSON).
- Null `first_commit`/`last_commit` appear as `null`.

### 9.3 CSV

Author-table only (no repo summary, no per-repo breakdown — use JSON
for those).

Columns (header row required):

```
author_id,display_name,emails,commits,additions,deletions,files_touched,first_commit,last_commit
```

- `emails` is `;`-joined sorted list (semicolon, not comma).
- Empty datetimes are empty strings.

## 10. Configuration: `--identity-map` YAML

A mapping from canonical display name to a list of emails:

```yaml
Alice Smith:
  - alice@old.example
  - asmith@new.example
  - 12345+alicesmith@users.noreply.github.com

Bob Jones:
  - bob@example.com
  - bjones@personal.example
```

Rules:

- Keys are canonical display names — used verbatim in output.
- Values are emails (un-normalized; the resolver normalizes them).
- Override groups are seeded **before** scanning, so they take
  precedence over observed identities.
- An email may only appear in one group (no validation yet — last
  write wins).

## 11. Extension point: `CommitEnricher`

Defined in `src/gitstats/enrichment.py`:

```python
class CommitEnricher(Protocol):
    def enrich(self, commits: Iterable[Commit]) -> Iterable[Commit]: ...
```

Contract:

- Enrichers receive an iterable of `Commit` and yield (potentially
  modified) `Commit`s.
- `Commit` is frozen — yield replacements via `dataclasses.replace`,
  do **not** mutate.
- Enrichers should populate `Commit.metadata` (a free-form `dict`)
  rather than adding new dataclass fields, so that downstream
  aggregation can introspect generically.
- Enrichers run **after** scanning and **before** aggregation.
- Order is significant — `apply_enrichers` chains them left to right.
- Enrichers may perform I/O but should cache it themselves; the
  pipeline does not memoize.

The MVP ships zero enrichers. The Jira integration (§14.1) will be
the first.

## 12. Performance contract

- Scanning a 100k-commit repo (e.g. CPython) on a 4-core laptop must
  complete in **single-digit seconds** with default `--jobs`.
- Cross-repo parallelism is via `ProcessPoolExecutor` over repos.
  Within a single repo the scan is single-threaded — `pygit2.Repository`
  is not thread-safe.
- pygit2 releases the GIL during diff computation, but we use
  processes (not threads) to also isolate aggregation state and
  protect against libgit2 surprises.
- Memory: all commits live in memory during aggregation. For very
  large monorepos this is acceptable for MVP; revisit if it bites.

## 13. Error handling

| Situation | Behavior |
|---|---|
| `ROOT` does not exist | Typer raises argument error → exit 2. |
| No repos found under `ROOT` | Print yellow warning to stderr, exit 1. |
| Repo has no HEAD (unborn branch) | Empty `RepoStats`, no error. |
| Repo is corrupted / pygit2 can't open it | Worker raises; the process pool re-raises in the parent. (Future: collect and continue — TBD.) |
| Shallow clone | Treated as a full repo; only the available history is scanned. |
| Detached HEAD | `repo.head.target` resolves; scan proceeds normally. |
| Invalid `--format` | Print red error to stderr, exit 2. |
| Invalid date in `--since` / `--until` | Typer/strptime raises → exit 2. |

## 14. Roadmap (planned, not implemented)

### 14.1 Jira integration **[TBD]**

The first enricher. Will join `Commit.jira_tickets` against a Jira
ticket dataset and attach issue metadata to `Commit.metadata` for
downstream aggregation.

**Open questions to resolve:**

- Data source: live Jira REST API, CSV export, both?
- Auth model if API: PAT in env var? OAuth?
- Cache location and TTL?
- Which Jira fields to surface: `issuetype`, `status`, `resolution`,
  `priority`, `components`?
- New aggregator output: `bugfixes`, `features`, `chores` per author
  per repo and overall — what's the JSON shape?
- New CLI flags: `--jira-export PATH`, `--jira-url URL`, …?
- Behavior when a commit references multiple tickets (counted once
  for each? deduped by issue type?).
- Behavior when a referenced ticket is missing from the dataset
  (skip silently? warn? fail?).

### 14.2 Future subcommands **[TBD]**

- `gitstats author <name|email>` — detail view for one author.
- `gitstats repo <path>` — detail view for one repo.
- `gitstats jira <…>` — Jira-specific queries (once §14.1 lands).
- Output contracts to be defined.

### 14.3 Time-series / activity heatmap **[TBD]**

Was a deferred MVP option. Commits-per-week, day-of-week patterns.
Need to decide: another subcommand, or a flag on `scan`?

### 14.4 Unique-files counter **[TBD]**

Today `files_touched` is the sum of per-commit `files_changed`.
A `unique_files` field (set of distinct paths per author) would be
more meaningful for some questions but increases memory. Worth it?

### 14.5 Bot/automated-author handling **[TBD]**

Should we treat `dependabot[bot]`, `github-actions[bot]`, web-edit
commits (`noreply@github.com`), etc. as a separate class? Options:
exclude, group under a synthetic "bots" identity, tag with metadata?

### 14.6 Date filter timezone **[TBD]**

Currently `--since`/`--until` are coerced to UTC midnight. Should
we accept explicit timezones (`2025-01-01T00:00:00+02:00`), local
time, or stay UTC-only?

### 14.7 JSON schema versioning **[TBD]**

Once enrichers add `metadata`, the JSON shape grows. Do we add a
top-level `schema_version: int` for downstream consumers?

### 14.8 Output limits / sorting **[TBD]**

Should the table truncate to top-N authors by commits? Should
sorting be configurable (`--sort commits|additions|recency`)?

## 15. Testing strategy

- `tests/conftest.py` builds a fixture repo via `pygit2.init_repository`
  with two authors (one with two emails) and a Jira ticket in a
  commit message — exercises identity merging, first/last commit, and
  the Jira regex.
- One test module per source module (`test_discovery.py`,
  `test_scanner.py`, `test_identity.py`, `test_aggregator.py`,
  `test_report.py`).
- A `slow`-marked test for scanning a real large repo (e.g. CPython)
  is allowed but not required for green CI.
- New features in this spec must be accompanied by tests that
  reference the relevant section number in a comment or docstring
  where the link helps reviewers.

## 16. Versioning

`gitstats` follows semver:

- **Public surface** = the `scan` CLI flag set, exit codes, and the
  JSON output schema.
- **Breaking** = removing/renaming a flag or JSON field, changing
  exit-code semantics, or changing identity-merging rules in a way
  that re-buckets authors.
- **Non-breaking** = adding new flags with defaults, adding new
  JSON fields, new subcommands, performance improvements, internal
  refactors.

CI must pass on all currently-supported Python versions before
release.

## 17. Workflow

1. New feature → update this spec **first** (open PR with just the
   spec change if non-trivial).
2. Spec change is reviewed/approved.
3. Implementation PR references the spec section it implements.
4. Tests reference the spec section they cover when not obvious.
