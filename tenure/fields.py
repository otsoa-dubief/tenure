# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Field-category vocabulary and key canonicalization (pure; no argument extraction here).

The shipped vocabulary is ``data/field_categories.json``. ``load`` applies the owner's ``fields:`` setting and never
raises. This module must not import ``classify`` at module level (classify imports it).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "field_categories.json"

CATEGORIES: tuple[str, ...] = ("secret", "finance", "unclassified", "amount", "access", "recipients", "identity",
                               "lifecycle")
DEFAULT_ON = frozenset({"secret", "finance", "unclassified"})
_STAKES = ("low", "medium", "high")
_FOLD = {"ı": "i", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "æ": "ae", "œ": "oe", "þ": "th", "ß": "ss"}
_SUBSTRING = frozenset({"password", "passwd", "iban", "secret"})
_WHOLE_KEY = frozenset({"to", "cc"})
_HOMOGLYPH_SCRIPTS = ("CYRILLIC", "GREEK", "ARMENIAN")


@dataclass(frozen=True)
class Vocabulary:
    entries: dict[str, frozenset[str]]
    active: frozenset[str]
    stakes: dict[str, str]
    version: str
    unknown: tuple[str, ...]
    broken: bool


_cache: dict = {}


def _names(value) -> list[str]:
    return [str(x) for x in value] if isinstance(value, (list, tuple, set, frozenset)) else []


def _build(setting) -> Vocabulary:
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cats = raw["categories"]
        entries = {n: frozenset(str(e) for e in cats[n]["entries"]) for n in CATEGORIES}
        stakes = {n: str(cats[n]["stakes"]) for n in CATEGORIES}
        active = {n for n in CATEGORIES if cats[n].get("on")}
        version = str(raw.get("version", ""))
        broken = False
    except Exception:  # unreadable or malformed file: only the structural category stays, stakes high
        entries = {n: frozenset() for n in CATEGORIES}
        stakes = {n: "high" for n in CATEGORIES}
        active, version, broken = {"unclassified"}, "", True
    unknown: list[str] = []

    def note(name: str) -> None:
        if name not in unknown:
            unknown.append(name)

    s = setting if isinstance(setting, dict) else {}
    for name in _names(s.get("enable")):
        active.add(name) if name in CATEGORIES else note(name)
    for name in _names(s.get("disable")):
        if name not in CATEGORIES:
            note(name)
        elif name == "unclassified":
            note(name)  # structural: cannot be switched off
        else:
            active.discard(name)
    for key, op in (("add", frozenset.union), ("remove", frozenset.difference)):
        block = s.get(key)
        for name, items in (block.items() if isinstance(block, dict) else ()):
            name = str(name)
            if name not in CATEGORIES:
                note(name)
                continue
            entries[name] = op(entries[name], frozenset(_names(items)))
    block = s.get("stakes")
    for name, level in (block.items() if isinstance(block, dict) else ()):
        name = str(name)
        if name not in CATEGORIES:
            note(name)
        elif level in _STAKES:
            stakes[name] = level
    return Vocabulary(entries, frozenset(active), stakes, version, tuple(unknown), broken)


def load(setting: object = None) -> Vocabulary:
    """The vocabulary with the owner's ``fields:`` setting applied. Never raises."""
    try:
        norm = json.dumps(setting, sort_keys=True, default=str) if not isinstance(setting, dict) else json.dumps(
            {str(k): v for k, v in setting.items()}, sort_keys=True, default=str)
    except Exception:
        norm = repr(type(setting))
    key = (str(DATA_PATH), norm)
    if key not in _cache:
        try:
            _cache[key] = _build(setting)
        except Exception:
            _cache[key] = Vocabulary({n: frozenset() for n in CATEGORIES}, frozenset({"unclassified"}),
                                     {n: "high" for n in CATEGORIES}, "", (), True)
    return _cache[key]


def canonical(key: str) -> str:
    """Canonical form of a field name (spec 4.4.1); ``""`` when nothing is left."""
    s = unicodedata.normalize("NFKC", str(key))
    s = "".join(c for c in s if unicodedata.category(c) != "Cf")
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = s.casefold()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")
    s = "".join(_FOLD.get(c, c) for c in s)
    s = unicodedata.normalize("NFKC", s)
    if s.endswith("__c"):
        s = s[:-3]
    s = re.sub(r"[\W_]+", "_", s)
    return s.strip("_")


def tokens(canon: str) -> list[str]:
    return [t for t in canon.split("_") if t]


def entry_matches(canon: str, toks: list[str], entry: str) -> bool:
    """Does a vocabulary entry match a canonical key (spec 4.4.2-3)?"""
    if not canon or not entry:
        return False
    if entry in _WHOLE_KEY:
        return canon == entry
    if entry in _SUBSTRING and entry in canon:
        return True
    words = entry.split("_")
    n = len(words)
    last = words[-1]
    ends = {last, last + "s", last + "es"}
    for i in range(len(toks) - n + 1):
        if toks[i:i + n - 1] == words[:-1] and toks[i + n - 1] in ends:
            return True
    return False


def mixed_script(canon: str) -> bool:
    """A token mixing [a-z] with Cyrillic, Greek or Armenian letters (homoglyph risk, spec 4.4.5)."""
    for tok in tokens(canon):
        latin = foreign = False
        for c in tok:
            if "a" <= c <= "z":
                latin = True
            elif c.isalpha():
                try:
                    if unicodedata.name(c).startswith(_HOMOGLYPH_SCRIPTS):
                        foreign = True
                except ValueError:
                    pass
        if latin and foreign:
            return True
    return False
