#!/usr/bin/env bash
# Real-repo integration tests for the gitstats CLI.
# See SKILL.md (../SKILL.md) for the *why* behind each test.
#
# Exit 0 = every section passed.
# Exit 1 = at least one section failed; check stderr for [fail] lines.

set -uo pipefail

WORKDIR=/tmp/gs-itest
REQUESTS_URL=https://github.com/psf/requests.git
URLLIB3_URL=https://github.com/urllib3/urllib3.git
EXPECTED_DEFAULT_REPORT_COUNT=10   # always-on (Jira-only reports skipped without --jira-url)
EXPECTED_CATALOG_COUNT=10
FAILED=0

log_ok()   { echo "[ok]   $1"; }
log_fail() { echo "[fail] $1 - $2" >&2; FAILED=1; }

_setup() {
  rm -rf "$WORKDIR"
  mkdir -p "$WORKDIR"
  ( cd "$WORKDIR" && git clone --quiet "$REQUESTS_URL" requests \
                   && git clone --quiet "$URLLIB3_URL" urllib3 ) || return 1
}

_test_catalog_listing() {
  local id=catalog-listing
  local out
  # COLUMNS=200 keeps Rich from truncating long report ids with an ellipsis.
  out=$(COLUMNS=200 gitstats reports 2>&1) || { log_fail $id "command exited non-zero"; return; }
  # Count rows by counting unique IDs we know must exist.
  for must in author-summary first-commits commit-heatmap raw-data \
              commit-wordcloud repo-summary author-leaderboard identity-debug \
              jira-tickets-by-type-md jira-tickets-by-type-html; do
    grep -q "$must" <<<"$out" || { log_fail $id "missing report id: $must"; return; }
  done
  log_ok $id
}

_test_default_scan() {
  local id=default-scan
  local out="$WORKDIR/out-default"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  local count
  count=$(find "$out" -maxdepth 1 -type f | wc -l)
  [ "$count" -eq "$EXPECTED_DEFAULT_REPORT_COUNT" ] \
    || { log_fail $id "expected $EXPECTED_DEFAULT_REPORT_COUNT files, got $count"; return; }
  log_ok $id
}

_test_report_filter() {
  local id=report-filter
  local out="$WORKDIR/out-rep"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 \
    --report author-summary --report raw-data >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  [ -f "$out/author-summary.md" ] || { log_fail $id "missing author-summary.md"; return; }
  [ -f "$out/raw-data.json"   ] || { log_fail $id "missing raw-data.json"; return; }
  local extras
  extras=$(find "$out" -maxdepth 1 -type f ! -name author-summary.md ! -name raw-data.json | wc -l)
  [ "$extras" -eq 0 ] || { log_fail $id "$extras unexpected extra file(s)"; return; }
  log_ok $id
}

_test_skip_filter() {
  local id=skip-filter
  local out="$WORKDIR/out-skip"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 \
    --skip commit-wordcloud --skip commit-heatmap --skip author-leaderboard \
    >/dev/null 2>&1 || { log_fail $id "exit $?"; return; }
  [ ! -f "$out/commit-wordcloud.png" ]    || { log_fail $id "wordcloud not skipped"; return; }
  [ ! -f "$out/commit-heatmap.html" ]     || { log_fail $id "heatmap not skipped"; return; }
  [ ! -f "$out/author-leaderboard.html" ] || { log_fail $id "leaderboard not skipped"; return; }
  [ -f "$out/author-summary.md" ]         || { log_fail $id "expected report missing"; return; }
  log_ok $id
}

_test_tz_utc() {
  local id=tz-utc
  local out="$WORKDIR/out-tz-utc"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 --tz utc --report commit-heatmap >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  grep -q "timezone: UTC" "$out/commit-heatmap.html" \
    || { log_fail $id "heatmap title missing 'timezone: UTC'"; return; }
  log_ok $id
}

_test_tz_iana() {
  local id=tz-iana
  local out="$WORKDIR/out-tz-zrh"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 --tz Europe/Zurich --report commit-heatmap >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  # Plotly JSON-escapes the forward slash; accept both forms.
  grep -qE "Europe/Zurich|Europe\\\\u002fZurich" "$out/commit-heatmap.html" \
    || { log_fail $id "heatmap title missing Europe/Zurich"; return; }
  log_ok $id
}

_test_date_range() {
  local id=date-range
  local out="$WORKDIR/out-date"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 \
    --since 2025-01-01 --until 2025-12-31 \
    --report raw-data >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  local total
  total=$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(sum(r['commits'] for r in d['repos']))" "$out/raw-data.json")
  # 2025-only window should massively shrink the commit count.
  [ "$total" -gt 0 ] && [ "$total" -lt 1000 ] \
    || { log_fail $id "unexpected total in 2025 window: $total"; return; }
  log_ok $id
}

_test_include_merges() {
  local id=include-merges
  local out1="$WORKDIR/out-m1" out2="$WORKDIR/out-m2"
  rm -rf "$out1" "$out2"
  gitstats scan "$WORKDIR" -o "$out1" -j 4 --since 2024-01-01 --report raw-data >/dev/null 2>&1 \
    || { log_fail $id "exit (no-merges) $?"; return; }
  gitstats scan "$WORKDIR" -o "$out2" -j 4 --since 2024-01-01 --include-merges \
    --report raw-data >/dev/null 2>&1 \
    || { log_fail $id "exit (with-merges) $?"; return; }
  local n1 n2
  n1=$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(sum(r['commits'] for r in d['repos']))" "$out1/raw-data.json")
  n2=$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(sum(r['commits'] for r in d['repos']))" "$out2/raw-data.json")
  local delta=$((n2 - n1))
  local merges_a merges_b expected
  merges_a=$(git -C "$WORKDIR/requests" log --since=2024-01-01 --merges --oneline | wc -l)
  merges_b=$(git -C "$WORKDIR/urllib3"  log --since=2024-01-01 --merges --oneline | wc -l)
  expected=$((merges_a + merges_b))
  [ "$delta" -eq "$expected" ] \
    || { log_fail $id "delta=$delta expected=$expected (m1=$n1 m2=$n2)"; return; }
  log_ok $id
}

_test_identity_map() {
  local id=identity-map
  local map="$WORKDIR/identity-map.yaml"
  local out="$WORKDIR/out-id"
  cat > "$map" <<'EOF'
The Reitz Mononym:
  - _@kennethreitz.com
  - me@kennethreitz.com
  - me@kennethreitz.org
  - kreitz@Kenneths-MacBook-Pro.local
EOF
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 --identity-map "$map" \
    --report identity-debug --report author-summary >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  grep -q "The Reitz Mononym" "$out/identity-debug.md" \
    || { log_fail $id "canonical name not in identity-debug"; return; }
  grep -A 3 "The Reitz Mononym" "$out/identity-debug.md" | grep -q "source: override+observed" \
    || { log_fail $id "source not override+observed"; return; }
  grep -q "The Reitz Mononym" "$out/author-summary.md" \
    || { log_fail $id "canonical name not in author-summary"; return; }
  log_ok $id
}

_test_only_mapped() {
  local id=only-mapped
  local map="$WORKDIR/identity-map.yaml"   # written by _test_identity_map
  local out="$WORKDIR/out-only-mapped"
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 --identity-map "$map" \
    --show-only-mapped-identities --report raw-data --report author-summary \
    >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  python <<PY || { log_fail $id "python checks failed"; return; }
import json
d = json.load(open("$out/raw-data.json"))
names = [a["display_name"] for a in d["authors"]]
assert names == ["The Reitz Mononym"], f"expected only the mapped author, got {names}"
total = d["authors"][0]["commits"]
assert total > 0, "mapped author has no commits"
by_repo = {r["name"]: r["commits"] for r in d["repos"]}
# Every surviving commit belongs to the one mapped author.
assert sum(by_repo.values()) == total, f"unmapped commits leaked: {by_repo} vs author total {total}"
assert by_repo.get("requests", 0) > 0, f"requests should keep mapped commits, got {by_repo}"
PY
  log_ok $id
}

_test_parallelism() {
  local id=parallelism
  local out="$WORKDIR/out-par"
  rm -rf "$out"
  local t1 t4
  t1=$( { time gitstats scan "$WORKDIR" -o "$out" -j 1 --report raw-data >/dev/null 2>&1; } 2>&1 \
        | awk '/^real/{print $2}')
  rm -rf "$out"
  t4=$( { time gitstats scan "$WORKDIR" -o "$out" -j 4 --report raw-data >/dev/null 2>&1; } 2>&1 \
        | awk '/^real/{print $2}')
  # Convert MmS.SSSs to seconds for comparison via python.
  if ! python -c "
import re, sys
def s(t):
    m = re.match(r'(\d+)m([\d.]+)s', t)
    return int(m.group(1))*60 + float(m.group(2)) if m else None
t1, t4 = s('$t1'), s('$t4')
if t1 is None or t4 is None:
    sys.exit('parse')
# -j 4 should be no worse than -j 1 plus a small overhead margin.
if t4 > t1 * 1.5:
    sys.exit(f'-j 4 ({t4:.1f}s) much slower than -j 1 ({t1:.1f}s)')
" ; then
    log_fail $id "perf check failed (j1=$t1, j4=$t4)"
    return
  fi
  log_ok $id
}

_test_report_config() {
  local id=report-config
  local cfg="$WORKDIR/report-config.yaml"
  local out="$WORKDIR/out-cfg"
  cat > "$cfg" <<'EOF'
gitstats:
  tz: utc
reports:
  commit-heatmap:
    tz: Europe/Zurich
  author-leaderboard:
    top_n: 5
EOF
  rm -rf "$out"
  gitstats scan "$WORKDIR" -o "$out" -j 4 --report-config "$cfg" \
    --report commit-heatmap --report author-leaderboard >/dev/null 2>&1 \
    || { log_fail $id "exit $?"; return; }
  grep -qE "Europe/Zurich|Europe\\\\u002fZurich" "$out/commit-heatmap.html" \
    || { log_fail $id "heatmap tz override not applied"; return; }
  grep -q "Top 5 authors" "$out/author-leaderboard.html" \
    || { log_fail $id "leaderboard top_n=5 not applied"; return; }
  log_ok $id
}

_test_config_warnings() {
  local id=config-warnings
  local cfg="$WORKDIR/bad-config.yaml"
  local out="$WORKDIR/out-bad"
  cat > "$cfg" <<'EOF'
gitstats:
  unknown_global: ignore-me
typo-section:
  whatever: x
reports:
  no-such-report:
    foo: bar
EOF
  rm -rf "$out"
  local err
  err=$(gitstats scan "$WORKDIR" -o "$out" -j 4 --report-config "$cfg" --report raw-data 2>&1 1>/dev/null) \
    || { log_fail $id "exit $?"; return; }
  grep -q "unknown key .*unknown_global" <<<"$err" \
    || { log_fail $id "missing unknown-global warning"; return; }
  grep -q "unknown top-level section .*typo-section" <<<"$err" \
    || { log_fail $id "missing typo-section warning"; return; }
  grep -q "unknown report id .*no-such-report" <<<"$err" \
    || { log_fail $id "missing unknown-report-id warning"; return; }
  log_ok $id
}

_expect_exit() {
  # _expect_exit <id> <expected-code> -- gitstats <args...>
  local id=$1 expected=$2; shift 2
  local code=0
  "$@" >/dev/null 2>&1 || code=$?
  [ "$code" -eq "$expected" ] \
    && log_ok "$id" \
    || log_fail "$id" "expected exit $expected, got $code"
}

_test_error_mutex()        { _expect_exit error-mutex        2 gitstats scan "$WORKDIR" -o "$WORKDIR/x" --report author-summary --skip raw-data; }
_test_error_unknown_id()   { _expect_exit error-unknown-id   2 gitstats scan "$WORKDIR" -o "$WORKDIR/x" --report no-such; }
_test_error_bad_tz()       { _expect_exit error-bad-tz       2 gitstats scan "$WORKDIR" -o "$WORKDIR/x" --tz Mars/Olympus; }
_test_error_missing_root() { _expect_exit error-missing-root 2 gitstats scan /tmp/gs-itest-does-not-exist -o "$WORKDIR/x"; }
_test_error_no_repos()     {
  local empty="$WORKDIR/empty-root"
  mkdir -p "$empty"
  _expect_exit error-no-repos 1 gitstats scan "$empty" -o "$WORKDIR/x"
}
_test_error_bad_date()     { _expect_exit error-bad-date     2 gitstats scan "$WORKDIR" -o "$WORKDIR/x" --since 2025-13-99; }
_test_error_only_mapped_no_map() { _expect_exit error-only-mapped-no-map 2 gitstats scan "$WORKDIR" -o "$WORKDIR/x" --show-only-mapped-identities; }

_test_artifact_shapes() {
  local id=artifact-shapes
  local out="$WORKDIR/out-default"
  python <<PY || { log_fail $id "python checks failed"; return; }
import json, sys
d = json.load(open("$out/raw-data.json"))
assert {"authors", "repos", "generated_at"} <= d.keys(), "raw-data top-level keys missing"
assert isinstance(d["authors"][0]["emails"], list), "emails is not a list"
head = open("$out/commit-wordcloud.png", "rb").read(8)
assert head == b"\x89PNG\r\n\x1a\n", "PNG magic mismatch"
html = open("$out/commit-heatmap.html").read(64)
assert "<html" in html.lower(), "heatmap html missing <html"
PY
  log_ok $id
}

main() {
  echo "real-repo-test: setting up /tmp/gs-itest (cloning repos)..."
  _setup || { log_fail setup "clone failed"; exit 1; }

  _test_catalog_listing
  _test_default_scan
  _test_report_filter
  _test_skip_filter
  _test_tz_utc
  _test_tz_iana
  _test_date_range
  _test_include_merges
  _test_identity_map
  _test_only_mapped
  _test_parallelism
  _test_report_config
  _test_config_warnings
  _test_error_mutex
  _test_error_unknown_id
  _test_error_bad_tz
  _test_error_missing_root
  _test_error_no_repos
  _test_error_bad_date
  _test_error_only_mapped_no_map
  _test_artifact_shapes

  echo
  if [ "$FAILED" -eq 0 ]; then
    echo "All sections passed."
    exit 0
  else
    echo "FAIL: at least one section failed (see [fail] lines above)."
    exit 1
  fi
}

main "$@"
