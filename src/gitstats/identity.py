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

    def observe_all(self, pairs: Iterable[tuple[str, str]]) -> None:
        for name, email in pairs:
            self.observe(name, email)

    def _root_for(self, name: str, email: str) -> str:
        norm_email = normalize_email(email)
        if norm_email:
            return self._uf.find(f"email::{norm_email}")
        return self._uf.find(f"name::{normalize_name(name)}")

    def author_id(self, name: str, email: str) -> str:
        root = self._root_for(name, email)
        return hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]

    def display_name(self, name: str, email: str) -> str:
        root = self._root_for(name, email)
        # An override may have been registered under a now-merged root; follow find().
        for override_node, canonical in self._override_canonical.items():
            if self._uf.find(override_node) == root:
                return canonical
        # Pick the most common original name observed in this group.
        names_in_group = Counter[str]()
        for obs_name, obs_email in self._observations:
            if self._root_for(obs_name, obs_email) == root and obs_name:
                names_in_group[obs_name] += 1
        if names_in_group:
            return names_in_group.most_common(1)[0][0]
        return name or email

    def group_key(self, name: str, email: str) -> str:
        return self._root_for(name, email)

    def groups(self) -> list[IdentityGroup]:
        """Return one `IdentityGroup` per canonical author for diagnostics.

        Built from the observation log so it reflects exactly what
        `display_name()` and `author_id()` would see right now.
        """
        groups_map: dict[str, dict[str, Any]] = {}
        for obs_name, obs_email in self._observations:
            root = self._root_for(obs_name, obs_email)
            g = groups_map.setdefault(
                root,
                {
                    "author_id": self.author_id(obs_name, obs_email),
                    "display_name": self.display_name(obs_name, obs_email),
                    "emails": set(),
                    "name_observations": Counter[str](),
                    "has_override": False,
                },
            )
            if obs_name:
                g["name_observations"][obs_name] += 1
            if obs_email:
                g["emails"].add(obs_email)

        for override_node in self._override_canonical:
            root = self._uf.find(override_node)
            if root in groups_map:
                groups_map[root]["has_override"] = True

        result: list[IdentityGroup] = []
        for g in groups_map.values():
            if g["has_override"] and g["name_observations"]:
                source = "override+observed"
            elif g["has_override"]:
                source = "override"
            else:
                source = "observed"
            result.append(
                IdentityGroup(
                    author_id=g["author_id"],
                    display_name=g["display_name"],
                    source=source,
                    emails=g["emails"],
                    name_observations=g["name_observations"],
                )
            )
        return result


@dataclass(frozen=True)
class IdentityGroup:
    author_id: str
    display_name: str
    source: str  # "override", "observed", or "override+observed"
    emails: set[str]
    name_observations: Counter[str]


def load_overrides(path: Path | str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return yaml.safe_load(Path(path).read_text())
