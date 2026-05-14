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
| **Aggregate** | The in-memory cross-repo data structure produced by aggregation; the input to every report (see §8). |
| **Report** | A user-facing artifact (markdown, HTML, PNG, JSON) written to the output directory by a `ReportRenderer` (see §9). |

## 4. CLI surface

The console script is `gitstats`. Three subcommands today:

- `gitstats scan ROOT` — discover repos, scan, generate reports.
- `gitstats reports` (alias `gitstats reports list`) — print the
  available-report catalog and exit.
- `gitstats jira <subcommand>` — Jira-workflow utilities (see §4.4).

### 4.1 `gitstats scan ROOT [OPTIONS]`

| Flag | Type | Default | Behavior |
|---|---|---|---|
| `ROOT` (positional) | dir | required | Directory to recursively search for repos. |
| `--report ID` | str (repeatable) | — | Run only the listed reports. Mutually exclusive with `--skip`. |
| `--skip ID` | str (repeatable) | — | Run all reports **except** the listed ones. Mutually exclusive with `--report`. |
| `--output-dir / -o` | path | `./gitstats-reports/` | Directory where report files are written. Created if missing. Existing same-named files are overwritten. |
| `--report-config` | path | — | YAML file with per-report parameters (see §10.2). |
| `--tz` | str | local system tz | Timezone for date filters and time-bucketed reports. Accepts `utc`, `local`, or an IANA name (e.g. `Europe/Zurich`). |
| `--jobs / -j` | int | `os.cpu_count()` | Worker processes for parallel repo scanning. |
| `--since` | `YYYY-MM-DD` | — | Drop commits older than this date, interpreted in `--tz`, inclusive. |
| `--until` | `YYYY-MM-DD` | — | Drop commits newer than this date, interpreted in `--tz`, inclusive. |
| `--identity-map` | path | — | YAML file pinning canonical identities (see §10.1). |
| `--include-merges` | flag | off | Include merge commits (counted with first-parent diff). |
| `--jira-url URL` | url | — | If set, enables the Jira enricher (§11.1). Can also come from `GITSTATS_JIRA_URL`. |

Auth env vars (no CLI flag — secrets never appear in shell history):

| Variable | Purpose |
|---|---|
| `GITSTATS_JIRA_URL` | Jira base URL. Equivalent to `--jira-url`. |
| `GITSTATS_JIRA_USER` | Account email or username for basic-auth Jira deployments. |
| `GITSTATS_JIRA_TOKEN` | Personal Access Token / API token. **Required** whenever Jira is active. |

Selection rules:

- With **neither** `--report` nor `--skip`: every registered report
  whose preconditions are satisfied runs. (Jira-only reports are
  skipped silently when Jira isn't active.)
- With one or more `--report ID`: only those reports run; unknown IDs
  cause exit 2.
- With one or more `--skip ID`: every registered report runs except
  those; unknown IDs cause exit 2.
- Passing both `--report` and `--skip` in the same invocation is an
  error (exit 2).

**Examples**

```bash
gitstats scan ~/code                                # all default reports
gitstats scan ~/code -o /tmp/report                 # custom output dir
gitstats scan ~/code --report author-summary        # just one report
gitstats scan ~/code --skip commit-wordcloud --skip commit-heatmap
gitstats scan ~/code --identity-map identities.yaml --since 2025-01-01
gitstats scan ~/code -j 8 --include-merges
gitstats scan ~/code --tz America/New_York
gitstats scan ~/code --jira-url https://jira.example.com  # +2 jira reports
gitstats scan ~/code --report-config reports.yaml         # tuning per-report
```

### 4.2 `gitstats reports [list]`

Prints the registered-report catalog as a small table to stdout:

```
ID                       Output file                    Jira  Description
author-summary           author-summary.md                    Markdown table of authors with totals.
first-commits            first-commits.md                     Per-author first/last commit per repo.
commit-heatmap           commit-heatmap.html                  Plotly heatmap of commit times.
raw-data                 raw-data.json                        Full aggregate as JSON.
commit-wordcloud         commit-wordcloud.png                 Wordcloud of commit messages.
repo-summary             repo-summary.md                      Markdown: per-repo totals and top contributors.
author-leaderboard       author-leaderboard.html              Plotly bar chart, top-N authors.
identity-debug           identity-debug.md                    Markdown: which identities merged into each author.
jira-tickets-by-type     jira-tickets-by-type.md           ✓  Markdown: commits per author per Jira issue type.
jira-tickets-by-type     jira-tickets-by-type.html         ✓  Plotly stacked bar of the same data.
```

The `Jira` column marks reports that only run when Jira is active.
With no argument or `list` the same table is printed. Reserved for
future siblings (e.g. `gitstats reports info <id>`).

### 4.3 Exit codes

| Code | Meaning |
|---|---|
| 0 | All requested reports rendered successfully. |
| 1 | No git repositories found under `ROOT`. |
| 2 | Bad CLI arguments — invalid path, unknown report ID, mutex violation, malformed date, invalid `--tz`, missing `GITSTATS_JIRA_TOKEN` when Jira is active, etc. |
| 3 | At least one report failed to render. Other reports may still have written files. |

### 4.4 `gitstats jira <subcommand>`

Auxiliary commands for the Jira workflow (§11.1). Each requires
`--jira-url` (or `GITSTATS_JIRA_URL`) and `GITSTATS_JIRA_TOKEN`.

- `gitstats jira test-connection` — issues a single Jira API call
  (`/rest/api/2/myself`) to validate the URL and credentials. Prints
  the resolved account on success; non-zero exit on failure.
- `gitstats jira clear-cache` — removes the per-host filesystem cache
  directory at `~/.cache/gitstats/jira/<host>/`. Prints how many
  cached entries were deleted.

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
  - `--since YYYY-MM-DD` and `--until YYYY-MM-DD` are interpreted as
    midnight in the timezone supplied by `--tz` (default: local
    system tz), then applied inclusively against each commit's
    **author** time (which carries its own offset; the comparison is
    on absolute instants).
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

### `Aggregate`
The in-memory cross-repo aggregation produced by
`aggregator.aggregate(...)`. Consumed by every report.

- `authors: list[AuthorStats]` — sorted by `commits` desc.
- `repos: list[RepoSummary]` — sorted by `name`.
- `generated_at: datetime` — UTC.

> The class was originally named `Report`; it was renamed to free up
> the name **Report** for the user-facing artifact concept (see §9).

## 9. Reports

A **report** is a self-contained artifact written to a file in the
output directory. Each report focuses on one aspect of the data and
declares its own filename and output kind (markdown, HTML, JSON, PNG).
A single `gitstats scan` run can produce many reports.

### 9.1 Architecture

Reports are pluggable. The protocol lives in
`src/gitstats/reports/base.py`:

```python
@dataclass(frozen=True)
class ReportContext:
    repo_stats: list[RepoStats]   # raw scanned commits, in case the report needs them
    aggregate: Aggregate          # the cross-repo aggregation
    output_dir: Path

@dataclass(frozen=True)
class ReportResult:
    report_id: str
    output_path: Path
    ok: bool
    error: str | None = None

class ReportRenderer(Protocol):
    id: ClassVar[str]             # kebab-case, e.g. "author-summary"
    description: ClassVar[str]    # one-line, used by `gitstats reports`
    filename: ClassVar[str]       # e.g. "author-summary.md"

    def render(self, ctx: ReportContext) -> Path: ...
```

Rules:

- `id` matches `^[a-z][a-z0-9-]*$`. Used by `--report` / `--skip`.
- `filename` is the basename inside `--output-dir`; reports never
  write outside that directory.
- `render` may raise; the caller catches and records a `ReportResult`
  with `ok=False`. One failing report does not stop the others (§13).
- `ReportContext` is read-only — reports must not mutate the input
  collections.
- Reports may read all of `repo_stats[i].commits` (raw `Commit` list)
  if they need timestamps or messages; in-memory cost is the
  already-scanned data, no extra git work.

A module-level `REPORTS: list[type[ReportRenderer]]` in
`src/gitstats/reports/__init__.py` is the registry consumed by both
`gitstats reports` and `gitstats scan`.

### 9.2 MVP report catalog

Ten reports are registered. **Eight** run by default; the two Jira
reports (§9.2.9, §9.2.10) only run when Jira is active (§11.1).

#### 9.2.1 `author-summary` → `author-summary.md`

A markdown document with two GitHub-flavored tables:

1. **Repositories** — same columns as today's terminal table
   (name, commits, authors, first/last commit).
2. **Authors** — `Author | Commits | + | - | Files | First | Last | Repos`.

Datetimes are rendered as ISO-8601 (UTC). Numbers are integers, no
thousands-separator. Sort: authors by `commits` desc, repos by name.

#### 9.2.2 `first-commits` → `first-commits.md`

For each canonical author, one section:

```
## Alice Smith (alice@example.com, alice@other.com)

- First commit overall: 2024-01-15T10:00:00+00:00 in repo-a (sha abc1234)
- Last commit overall: 2026-05-12T18:30:00+00:00 in repo-b (sha def5678)

| Repo    | First commit       | Last commit        | Commits |
|---------|--------------------|--------------------|---------|
| repo-a  | 2024-01-15T10:…    | 2025-09-04T11:…    |       9 |
| repo-b  | 2024-08-20T09:…    | 2026-05-12T18:…    |       8 |
```

Sections are ordered by overall first-commit ascending (the earliest
contributor first).

#### 9.2.3 `commit-heatmap` → `commit-heatmap.html`

A self-contained Plotly HTML file showing a 7 × 24 heatmap of commit
counts: y-axis = day of week (Mon → Sun), x-axis = hour of day (0–23),
cell value = number of commits at that slot, summed across all repos
and authors. Colorscale: Viridis. Hover shows day/hour/count.

Time conversion: timestamps are converted to the timezone given by
`--tz` (default: local system tz) for bucketing.

The HTML is fully offline-capable (Plotly bundle embedded).

#### 9.2.4 `raw-data` → `raw-data.json`

A JSON dump of the `Aggregate`. Identical to the file that the
old `--format json` produced. Pretty-printed, sorted keys, 2-space
indent. Shape:

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

- All datetimes ISO-8601 with tz offset.
- `emails` is a sorted list (sets aren't valid JSON).
- Null `first_commit`/`last_commit` appear as `null`.
- This file's shape is the JSON schema referred to by §16
  (versioning).

#### 9.2.5 `commit-wordcloud` → `commit-wordcloud.png`

A PNG wordcloud (default 1600×900, white background) of all commit
messages across all repos.

Preprocessing pipeline applied to every message before tokenization:

1. Strip Jira-ticket keys (the `JIRA_RE` from §6) so the cloud
   doesn't fill with `PROJ-123`.
2. Strip URLs (`https?://\S+`).
3. Strip surrounded code/identifiers — backticked spans and tokens
   matching `[A-Za-z_][\w.]*\.\w+` (paths and method-like names).
4. Lowercase.
5. Drop tokens shorter than 3 characters.
6. Drop the default English stopword list from the `wordcloud`
   library plus a small gitstats-specific list: `merge`, `revert`,
   `wip`, `tmp`, `todo`, `fix`, `fixed`, `fixes`, `add`, `added`,
   `adds`, `update`, `updated`, `updates`, `remove`, `removed`,
   `bump`.

Max 200 words rendered. Stopword list and image dimensions are
hardcoded; future tuning lands in `--report-config` (§10.2).

To keep the report fast on large corpora the commit-message input
is **subsampled to 5 000 messages** by default (random sample with a
fixed seed, so successive runs produce the same artwork). Override
in `--report-config`:

```yaml
reports:
  commit-wordcloud:
    sample_size: 10000   # cap input at 10k messages
    # sample_size: 0     # disable sampling (use every message)
```

Layout cost grows linearly with input length; wordcloud quality
saturates well below 5 000 messages, so the default cap is a
near-free speedup on big repos.

#### 9.2.6 `repo-summary` → `repo-summary.md`

One markdown section per repo, ordered by name. Each section
contains:

- A heading `## <repo-name>` and the absolute repo path.
- Totals line: `Commits: N · Authors: N · First: <iso> · Last: <iso>`.
- Total distinct Jira ticket keys referenced (regex matches; not
  filtered by enrichment).
- Top 5 authors table: `Author | Commits | + | - | Files`.

#### 9.2.7 `author-leaderboard` → `author-leaderboard.html`

Self-contained Plotly HTML. A bar chart of the top **20** authors
(by `commits` descending). Three traces are bound to a button:
`Commits` (default), `Lines added`, `Lines deleted`. X-axis labels
are author display names. The 20-cap is fixed for MVP and will
become a `--report-config` knob (§10.2).

#### 9.2.8 `identity-debug` → `identity-debug.md`

Diagnostic markdown intended for tuning `identity-map.yaml`. For
each canonical author group, in the order they appear in
`author-summary.md`:

```
## Alice Smith   (id: 086f06e0f825)

source: identity-map.yaml
emails: alice@example.com, alice@other.com
observed name spellings: Alice Smith (12), alice smith (3), Alice (1)
```

`source` is one of `identity-map.yaml`, `observed`, or
`override+observed` (when the override seeded the group and
observations later joined it). Useful for spotting unintended merges
or splits.

#### 9.2.9 `jira-tickets-by-type` (markdown) → `jira-tickets-by-type.md`

**Only runs when Jira is active (§11.1).** Markdown table with one
row per canonical author and one column per Jira issue type that
appears in the dataset. Cells hold the **count of that author's
commits classified by issue type**, where each commit is classified
by the issue type of its **first** Jira ticket key in the commit
message (see §11.1.3 for the rule). Commits whose first ticket is
absent from Jira are silently excluded; commits with no ticket are
excluded.

```
| Author      | Bug | Story | Task | Sub-task |
|-------------|-----|-------|------|----------|
| Alice Smith |  17 |     8 |    3 |        2 |
| Bob Jones   |   4 |    11 |    1 |        0 |
```

Authors with zero classified commits are omitted. Columns are sorted
by total commits across the column (most-touched issue type first).

#### 9.2.10 `jira-tickets-by-type` (HTML) → `jira-tickets-by-type.html`

**Only runs when Jira is active.** Same data as §9.2.9 rendered as a
self-contained Plotly stacked bar chart: x-axis = authors (sorted by
total bar height), y-axis = commit count, each issue type a stacked
segment with hover details.

### 9.3 Run flow

```
1. discover repos under ROOT
2. scan in parallel  -> list[RepoStats]
3. if Jira is active (§11.1):
     fetch / cache issue types for every Commit.jira_tickets[0]
     attach to Commit.metadata["jira_first_issuetype"] (or skip if missing)
4. resolve identities -> Aggregate
5. select reports from REPORTS based on --report / --skip
   (Jira-only reports are filtered out when Jira is inactive)
6. for each selected report:
     try render(ctx) -> Path
     except Exception as exc: record ok=False, error=str(exc)
7. print per-report status to stderr
8. exit 0 if all ok, else exit 3
```

Step 6 prints one line per report, e.g.:

```
[ok]   author-summary    -> ./gitstats-reports/author-summary.md
[ok]   first-commits     -> ./gitstats-reports/first-commits.md
[fail] commit-wordcloud  -> wordcloud library not installed
```

## 10. Configuration

### 10.1 `--identity-map` YAML

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

### 10.2 `--report-config` YAML

A nested mapping with two top-level sections: `gitstats` for
cross-cutting parameters and `reports` keyed by report id for
per-report tuning.

```yaml
gitstats:
  # Optional. Overrides --tz if both are given on the CLI.
  tz: Europe/Zurich

reports:
  commit-heatmap:
    tz: utc                          # overrides gitstats.tz for this report

  commit-wordcloud:
    max_words: 300
    stopwords_file: ./stopwords.txt  # path; one extra stopword per line

  author-leaderboard:
    top_n: 30
    default_metric: additions        # one of: commits, additions, deletions
```

Rules:

- The file is loaded once. Unknown top-level sections produce a
  warning to stderr and are otherwise ignored.
- Unknown keys inside a known report's section produce a warning to
  stderr and are ignored (so the file survives spec changes).
- CLI flags override `gitstats.*` keys; `reports.<id>.<key>`
  overrides `gitstats.<key>` for that report only.
- MVP reports that accept parameters: **none ship configurable**.
  The schema and resolver exist so future reports (and §14.11
  wordcloud tuning) can read params with no further plumbing.

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

The MVP ships **one** concrete enricher: the Jira enricher (§11.1).

### 11.1 JiraEnricher

**Activation.** The Jira enricher runs whenever `--jira-url` is
given or `GITSTATS_JIRA_URL` is set. There is no separate
`--with-jira` toggle. When inactive, no API call is made and the two
Jira-only reports (§9.2.9, §9.2.10) are filtered out of the run.

**Configuration sources (precedence high → low):**

1. `--jira-url URL` CLI flag.
2. `GITSTATS_JIRA_URL` environment variable.
3. (User) `GITSTATS_JIRA_USER` — account email/username for basic
   auth or `email:token` cloud Jira.
4. (Token) `GITSTATS_JIRA_TOKEN` — Personal Access Token. **Always
   required when Jira is active.** Never accepted as a CLI flag.

If activation is on but `GITSTATS_JIRA_TOKEN` is missing, exit 2
with a clear error before any scanning starts.

**Fetch pattern.** For each unique first-ticket key across all
commits (see §11.1.3), look up the issue via Jira's
`/rest/api/2/issue/{key}?fields=issuetype`. We never bulk-search;
one issue at a time, sequentially (cap on parallelism: 1, because
Jira rate limits are nasty and this keeps the cache layer simple).

**Behavior on lookup failures:**

| Situation | Behavior |
|---|---|
| 404 (ticket not in Jira) | Skip silently. Commit gets no metadata; it's excluded from Jira-based classification. |
| 401 / 403 (auth) | Abort the entire run, exit 2 with the Jira error message. |
| 5xx / network error | Retry up to 3 times with exponential back-off (1s, 2s, 4s). After that, treat as 404 — skip silently and continue. |
| Timeout (> 30 s per request) | Same as 5xx after retries. |

#### 11.1.1 Cache

Filesystem-backed, persistent. One file per ticket, JSON-encoded.

- Default location: `~/.cache/gitstats/jira/<host>/<KEY>.json`.
  `<host>` is the URL host (port and path stripped). `<KEY>` is the
  Jira issue key.
- Cache entry shape:
  ```json
  {"fetched_at": "2026-05-13T20:00:00+00:00", "issuetype": "Bug"}
  ```
- Default TTL **24 hours** (`--jira-cache-ttl` to override in
  seconds; `--jira-no-cache` to disable both read and write).
- A 404 is also cached (as `{"fetched_at": "...", "issuetype": null}`)
  so we don't re-pummel Jira on every run for missing tickets.

`gitstats jira clear-cache` (§4.4) deletes the
`~/.cache/gitstats/jira/<host>/` directory for the configured host.

#### 11.1.2 What lands on `Commit.metadata`

Only one key is set:

```python
commit.metadata["jira_first_issuetype"] = "Bug"   # or "Story", "Task", ...
```

When the first ticket is missing from Jira (404 or skipped after
errors), the key is **not** set — downstream reports treat missing
keys as "unclassified".

#### 11.1.3 Multi-ticket commit rule

A commit message may contain several ticket keys. **First match
wins**: the issue type used for classification is that of the
**first** key in iteration order of `Commit.jira_tickets` (which
preserves first-occurrence order from the regex scan, §6).
Other tickets remain on the commit (in `jira_tickets`) but are not
classified.

This is a deliberate simplification — see §14.2 for the alternative
designs (set-based and fractional attribution) that we deferred for
MVP.

#### 11.1.4 Ordering in the pipeline

Per §9.3 step 3, the Jira enricher runs **after** scanning and
**before** identity resolution / aggregation. The enrichment step
itself does no parallelism (cap-1 is documented above).

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
| `--report` and `--skip` both given | Print red error to stderr, exit 2. |
| Unknown report ID in `--report` or `--skip` | Print red error listing valid IDs, exit 2. |
| `--output-dir` exists but is not writable | Print red error to stderr, exit 2. |
| `--output-dir` does not exist | Created (with parents) silently. |
| A single report's `render()` raises | Caught; logged to stderr as `[fail]`; other reports still run; final exit code is 3 if any failed. |
| Invalid date in `--since` / `--until` | Typer/strptime raises → exit 2. |
| Invalid `--tz` value (not `utc`, `local`, or an IANA name) | Print red error to stderr, exit 2. |
| Jira active but `GITSTATS_JIRA_TOKEN` missing | Print red error to stderr, exit 2. |
| Jira 401 / 403 during fetch | Abort, print Jira message to stderr, exit 2. |
| Jira 404 for a referenced ticket | Skip silently; the commit is not classified. |
| Jira 5xx / network / timeout | Retry 3× with backoff; if still failing, treat as 404. |
| Unknown key in `--report-config` | Warn to stderr, continue. |

## 14. Roadmap

Most original §14 items are now resolved (their decisions live in
the relevant section above). What remains here is the genuinely
open future work plus design alternatives that we deliberately
deferred.

### 14.1 Jira integration **[resolved]**

Specified in §11.1. Activation via `--jira-url` /
`GITSTATS_JIRA_URL` + `GITSTATS_JIRA_TOKEN`; live REST API only
(no CSV export path); filesystem cache with 24h TTL; only the
`issuetype` field is surfaced; missing tickets are skipped
silently; the two `jira-tickets-by-type` reports (§9.2.9, §9.2.10)
are the headline output.

Open follow-ups (not in MVP):

- Additional Jira fields (`status`, `resolution`, `components`,
  `priority`) — once a real use case appears.
- Bulk-search via `/rest/api/2/search?jql=key in (...)` to reduce
  request count.
- Distinguishing "tickets touched" (set-based) from "commits
  classified" (current) as separate metrics in `raw-data.json`.

### 14.2 Multi-ticket counting alternatives **[deferred]**

Today: **first ticket wins** (§11.1.3). If feedback shows it
loses too much signal, alternatives to evaluate are:

- Count each linked ticket independently (set-of-tickets-per-type).
- Fractional attribution (1/N to each linked ticket's type).
- Tracking both in `raw-data.json`, presenting one in reports.

### 14.3 Time-series / activity heatmap **[resolved]**

Implemented as `commit-heatmap` (§9.2.3). Time-series breakdowns
beyond the day-of-week × hour grid remain candidates for additional
reports — see §14.7.

### 14.4 Unique-files counter **[resolved → no]**

Decision: stick with the summed `files_touched` (per-commit
`files_changed` totaled). The unique-set variant was rejected for
MVP — it doubles the memory of the aggregation step for marginal
gain. Revisit if a real user use case appears.

### 14.5 Bot/automated-author handling **[resolved → no]**

Decision: bots (`dependabot[bot]`, `github-actions[bot]`, etc.)
are treated as ordinary authors. Users who want to fold them into
a single synthetic identity can do so via `--identity-map`.

### 14.6 Date filter / heatmap timezone **[resolved]**

Decision: a single global `--tz` flag controls both. Default is
the local system timezone. Per-report overrides go through
`--report-config` (§10.2).

### 14.7 Additional reports **[ongoing]**

The MVP catalog (§9.2) lists ten reports. Further candidates that
are **not** in MVP:

- `commit-timeline.html` — weekly per-author commit lines.
- `jira-tickets-touched.md` — set-based counterpart to §14.2.
- `pair-matrix.md` — co-authorship from `Co-authored-by:` trailers.

Adding a report is a non-breaking change; pick them up as need
arises.

### 14.8 JSON schema versioning **[resolved → no]**

Decision: no `schema_version` field in `raw-data.json`. The
`gitstats` package's semver covers the public surface (§16). Adding
a field later is non-breaking; consumers should tolerate unknown
keys.

### 14.9 Per-report parameters **[resolved]**

Mechanism shipped as `--report-config` (§10.2). MVP reports don't
read any params yet; the schema and resolver exist so future
reports can.

### 14.10 Optional-dependency split **[resolved → no]**

Decision: `plotly` and `wordcloud` are required runtime deps. A
single `pip install gitstats` gets everything. Revisit if install
size becomes a complaint.

### 14.11 Wordcloud customization **[deferred]**

The wordcloud's stopwords, max-words, dimensions, and colormap are
hardcoded in §9.2.5. When tuning becomes necessary, the knobs will
live under `reports.commit-wordcloud:` in `--report-config` — no
new CLI flags.

## 15. Testing strategy

- `tests/conftest.py` builds a fixture repo via `pygit2.init_repository`
  with two authors (one with two emails) and a Jira ticket in a
  commit message — exercises identity merging, first/last commit, and
  the Jira regex.
- One test module per source module:
  `test_discovery.py`, `test_scanner.py`, `test_identity.py`,
  `test_aggregator.py`, plus `tests/reports/test_<id>.py` for each
  registered report.
- `tests/test_cli.py` covers report selection (`--report` / `--skip`
  mutex, unknown-ID error, default-runs-all behavior), `--tz`
  validation, `--report-config` loading and unknown-key warnings,
  output-dir creation, and exit-code semantics (0 / 1 / 2 / 3).
- `tests/test_jira.py` covers the `JiraEnricher` against a stubbed
  Jira HTTP server: cache hit/miss, 404 silent skip, 401 abort,
  retry-on-5xx, and first-ticket-wins classification.
- A `slow`-marked test for scanning a real large repo (e.g. CPython)
  is allowed but not required for green CI.
- New features in this spec must be accompanied by tests that
  reference the relevant section number in a comment or docstring
  where the link helps reviewers.

## 16. Versioning

`gitstats` follows semver:

- **Public surface** = the `scan`, `reports`, and `jira` CLI flag
  sets, exit codes, the set of registered report IDs and their
  filenames, the `--identity-map` and `--report-config` YAML schemas,
  and the `raw-data.json` shape.
- **Breaking** = removing or renaming a CLI flag, an exit-code
  meaning change, removing or renaming a report ID, removing a field
  from `raw-data.json`, or changing identity-merging rules in a way
  that re-buckets authors.
- **Non-breaking** = adding new flags with defaults, adding new
  reports, adding new fields to `raw-data.json`, new subcommands,
  performance improvements, internal refactors.

CI must pass on all currently-supported Python versions before
release.

## 17. Workflow

1. New feature → update this spec **first** (open PR with just the
   spec change if non-trivial).
2. Spec change is reviewed/approved.
3. Implementation PR references the spec section it implements.
4. Tests reference the spec section they cover when not obvious.
