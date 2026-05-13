from __future__ import annotations

from pathlib import Path

from gitstats.identity import IdentityResolver, normalize_email, normalize_name


def test_normalize_email_lowercases_and_strips_plus() -> None:
    assert normalize_email("Alice+tag@Example.COM") == "alice@example.com"
    assert normalize_email("123+alice@users.noreply.github.com") == (
        "alice@users.noreply.github.com"
    )
    assert normalize_email("alice@users.noreply.github.com") == (
        "alice@users.noreply.github.com"
    )


def test_normalize_name_collapses_whitespace_and_casing() -> None:
    assert normalize_name("  Alice   Smith  ") == "alice smith"


def test_resolver_merges_two_emails_for_same_name() -> None:
    r = IdentityResolver()
    r.observe("Alice Smith", "alice@old.example")
    r.observe("Alice Smith", "asmith@new.example")
    a = r.author_id("Alice Smith", "alice@old.example")
    b = r.author_id("Alice Smith", "asmith@new.example")
    assert a == b


def test_resolver_does_not_merge_unrelated_authors() -> None:
    r = IdentityResolver()
    r.observe("Alice Smith", "alice@old.example")
    r.observe("Bob Jones", "bob@example.com")
    assert r.author_id("Alice Smith", "alice@old.example") != (
        r.author_id("Bob Jones", "bob@example.com")
    )


def test_yaml_override_pins_canonical_name(tmp_path: Path) -> None:
    yml = tmp_path / "map.yaml"
    yml.write_text(
        "Alice Smith:\n  - alice@old.example\n  - asmith@new.example\n"
    )
    r = IdentityResolver.from_yaml(yml)
    # Observe a stray spelling that should still resolve to the canonical name.
    r.observe("alice smith", "alice@old.example")
    assert r.display_name("alice smith", "alice@old.example") == "Alice Smith"


def test_yaml_override_survives_observation_with_different_name(tmp_path: Path) -> None:
    """Regression: observing 'Alice' under an override-mapped email used to
    shift the union-find root and lose the canonical name."""
    yml = tmp_path / "map.yaml"
    yml.write_text(
        "Alice Smith:\n  - alice@example.com\n  - alice@other.com\n"
    )
    r = IdentityResolver.from_yaml(yml)
    r.observe("Alice", "alice@example.com")
    r.observe("Alice", "alice@example.com")
    r.observe("Alice Smith", "alice@other.com")
    assert r.display_name("Alice", "alice@example.com") == "Alice Smith"
    assert r.author_id("Alice", "alice@example.com") == (
        r.author_id("Alice Smith", "alice@other.com")
    )
