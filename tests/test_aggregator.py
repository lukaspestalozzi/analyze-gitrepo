from __future__ import annotations

from gitstats.aggregator import aggregate
from gitstats.identity import IdentityResolver
from gitstats.scanner import scan_repo
from tests.conftest import FixtureRepo


def test_aggregator_merges_alice_emails_and_counts(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    resolver = IdentityResolver()
    agg = aggregate([stats], resolver)

    # Two distinct authors after identity merging: Alice (2 emails) + Bob.
    assert len(agg.authors) == 2

    by_name = {a.display_name: a for a in agg.authors}
    alice = by_name["Alice Smith"]
    bob = by_name["Bob Jones"]

    assert alice.commits == 2
    assert bob.commits == 2
    assert alice.emails == {"alice@old.example", "asmith@new.example"}
    assert bob.emails == {"bob@example.com"}

    # First commit of Alice is c1 (initial), of Bob is c3.
    assert alice.first_commit is not None
    assert alice.last_commit is not None
    assert alice.first_commit < alice.last_commit
    assert bob.first_commit is not None
    assert bob.first_commit > alice.first_commit


def test_aggregator_per_repo_breakdown(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    alice = next(a for a in agg.authors if a.display_name == "Alice Smith")
    assert list(alice.per_repo.keys()) == [stats.name]
    assert alice.per_repo[stats.name].commits == 2


def test_repo_summary_counts(fixture_repo: FixtureRepo) -> None:
    stats = scan_repo(fixture_repo.path)
    agg = aggregate([stats], IdentityResolver())
    assert len(agg.repos) == 1
    repo = agg.repos[0]
    assert repo.commits == 4
    assert repo.authors == 2
