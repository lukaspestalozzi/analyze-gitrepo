from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_GITHUB_NOREPLY_RE = re.compile(
    r"^(?:\d+\+)?(?P<user>[^@]+)@users\.noreply\.github\.com$", re.IGNORECASE
)


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return email
    m = _GITHUB_NOREPLY_RE.match(email)
    if m:
        return f"{m.group('user')}@users.noreply.github.com"
    local, _, domain = email.partition("@")
    local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def normalize_name(name: str) -> str:
    return " ".join((name or "").lower().split())


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        if key not in self.parent:
            self.parent[key] = key

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression
        cur = key
        while self.parent[cur] != root:
            nxt = self.parent[cur]
            self.parent[cur] = root
            cur = nxt
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class IdentityResolver:
    """Maps `(name, email)` pairs to canonical author identities.

    Algorithm:
      - Normalize email (lowercase, strip `+tag`, collapse GitHub no-reply form).
      - Normalize name (lowercase, collapsed whitespace).
      - Union-find merge over a graph where each `(name, email)` pair adds
        an edge between its normalized name node and normalized email node.
      - Optional YAML override file seeds groups before observation.
    """

    def __init__(self, overrides: dict[str, list[str]] | None = None) -> None:
        self._uf = _UnionFind()
        self._pair_to_root: dict[tuple[str, str], str] = {}
        self._observations: list[tuple[str, str]] = []
        self._override_canonical: dict[str, str] = {}
        # Lazily built on first lookup; invalidated by each observe().
        # Reads (display_name / author_id / groups) are O(1) lookups once built.
        self._group_cache: dict[str, _GroupInfo] | None = None
        if overrides:
            self._apply_overrides(overrides)

    @classmethod
    def from_yaml(cls, path: Path | str | None) -> IdentityResolver:
        if path is None:
            return cls()
        data = yaml.safe_load(Path(path).read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError(f"identity map at {path} must be a mapping")
        return cls(overrides=data)

    def _apply_overrides(self, overrides: dict[str, list[str]]) -> None:
        for canonical_name, emails in overrides.items():
            norm_name = normalize_name(canonical_name)
            name_node = f"name::{norm_name}"
            self._uf.add(name_node)
            self._override_canonical[self._uf.find(name_node)] = canonical_name
            for email in emails:
                email_node = f"email::{normalize_email(email)}"
                self._uf.union(name_node, email_node)
                self._override_canonical[self._uf.find(name_node)] = canonical_name
        self._group_cache = None

    def observe(self, name: str, email: str) -> None:
        norm_name = normalize_name(name)
        norm_email = normalize_email(email)
        name_node = f"name::{norm_name}" if norm_name else None
        email_node = f"email::{norm_email}" if norm_email else None
        if name_node and email_node:
            self._uf.union(name_node, email_node)
        elif name_node:
            self._uf.add(name_node)
        elif email_node:
            self._uf.add(email_node)
        self._observations.append((name, email))
        self._group_cache = None

    def observe_all(self, pairs: Iterable[tuple[str, str]]) -> None:
        for name, email in pairs:
            self.observe(name, email)

    def _root_for(self, name: str, email: str) -> str:
        norm_email = normalize_email(email)
        if norm_email:
            return self._uf.find(f"email::{norm_email}")
        return self._uf.find(f"name::{normalize_name(name)}")

    def author_id(self, name: str, email: str) -> str:
        cache = self._ensure_group_cache()
        root = self._root_for(name, email)
        info = cache.get(root)
        if info is not None:
            return info.author_id
        # Fallback for the never-observed case (kept for API completeness).
        return hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]

    def display_name(self, name: str, email: str) -> str:
        cache = self._ensure_group_cache()
        root = self._root_for(name, email)
        info = cache.get(root)
        if info is not None and info.display_name:
            return info.display_name
        return name or email

    def group_key(self, name: str, email: str) -> str:
        return self._root_for(name, email)

    def groups(self) -> list[IdentityGroup]:
        """Return one `IdentityGroup` per canonical author for diagnostics."""
        cache = self._ensure_group_cache()
        result: list[IdentityGroup] = []
        for root, g in cache.items():
            has_override = self._override_for_root(root) is not None
            if has_override and g.name_counter:
                source = "override+observed"
            elif has_override:
                source = "override"
            else:
                source = "observed"
            result.append(
                IdentityGroup(
                    author_id=g.author_id,
                    display_name=g.display_name,
                    source=source,
                    emails=g.emails,
                    name_observations=g.name_counter,
                )
            )
        return result

    # ------- cache internals -------

    def _ensure_group_cache(self) -> dict[str, _GroupInfo]:
        if self._group_cache is None:
            self._group_cache = self._build_group_cache()
        return self._group_cache

    def _build_group_cache(self) -> dict[str, _GroupInfo]:
        """One linear pass over observations + overrides.

        Both `display_name` and `author_id` used to walk the full
        observation list per call, giving O(G·N) in the aggregator's
        inner loop and O(N²) in `groups()` (because of an eager
        setdefault default). This precomputes everything once after
        all observations are recorded.
        """
        cache: dict[str, _GroupInfo] = {}
        for obs_name, obs_email in self._observations:
            root = self._root_for(obs_name, obs_email)
            g = cache.get(root)
            if g is None:
                g = _GroupInfo(
                    author_id=hashlib.sha1(root.encode("utf-8")).hexdigest()[:12],
                    display_name="",
                    emails=set(),
                    name_counter=Counter[str](),
                )
                cache[root] = g
            if obs_name:
                g.name_counter[obs_name] += 1
            if obs_email:
                g.emails.add(obs_email)

        # Seed groups for overrides that never received an observation, so
        # `display_name("Alice", "a@x")` works even if Alice has never been
        # observed (the overrides-only edge case).
        for override_node in self._override_canonical:
            root = self._uf.find(override_node)
            if root not in cache:
                cache[root] = _GroupInfo(
                    author_id=hashlib.sha1(root.encode("utf-8")).hexdigest()[:12],
                    display_name="",
                    emails=set(),
                    name_counter=Counter[str](),
                )

        # Resolve display names: override wins, else most-common observed name.
        for root, g in cache.items():
            override = self._override_for_root(root)
            if override is not None:
                g.display_name = override
            elif g.name_counter:
                g.display_name = g.name_counter.most_common(1)[0][0]
        return cache

    def _override_for_root(self, root: str) -> str | None:
        for override_node, canonical in self._override_canonical.items():
            if self._uf.find(override_node) == root:
                return canonical
        return None


@dataclass(frozen=True)
class IdentityGroup:
    author_id: str
    display_name: str
    source: str  # "override", "observed", or "override+observed"
    emails: set[str]
    name_observations: Counter[str]


@dataclass
class _GroupInfo:
    """Precomputed per-root state used by `IdentityResolver` lookups."""

    author_id: str
    display_name: str
    emails: set[str]
    name_counter: Counter[str]


def load_overrides(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return yaml.safe_load(Path(path).read_text())
