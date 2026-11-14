# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Field-category vocabulary, key canonicalization and the extraction of the categories a tool call touches (pure).

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


# ---- extraction (spec 4.3) and structural @unclassified rules (spec 4.5) ----

MAX_DEPTH = 8              # as classify._strings
MAX_KEYS = 5000            # distinct candidate keys, after canonicalization
MAX_JSON = 1_000_000       # bytes of one JSON string
JSON_LEVELS = 3            # JSON strings decoded inside JSON strings; a 4th level is unclassified

_CONTENT_KEYS = frozenset({"content", "body", "text", "description", "message"})
_FIELD_VALUE_KEYS = frozenset({"field_name", "field", "field_id", "key", "property", "property_name", "property_id",
                               "attribute", "column", "column_name"})
_FIELD_LIST_KEYS = frozenset({"fields", "columns", "properties"})
_RICH_KEYS = frozenset({"type", "content", "attrs", "text", "marks", "version", "annotations", "plain_text", "href"})
_CONTAINERS = frozenset({"fields", "properties", "custom_fields", "column_values", "data", "values"})
_FREE_STRING = frozenset({"sql", "query", "statement", "formula", "jql", "script"})
_REST_METHOD_KEYS = frozenset({"method", "http_method", "verb"})
_REST_WRITE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REST_TARGET_KEYS = frozenset({"path", "endpoint", "url"})
_OPAQUE = re.compile(r"customfield_\d+|fld[A-Za-z0-9]{14}|00N[A-Za-z0-9]{12,15}")
_OPAQUE_IN_CONTAINER = re.compile(r"\d{6,}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
_TOKEN_NOT_BEFORE = frozenset({"id", "ids", "count", "limit", "budget", "usage"})
_TOKEN_NOT_AFTER = frozenset({"page", "next", "cursor", "continuation", "sync", "idempotency", "pagination", "max",
                              "min", "num", "count", "total", "input", "output", "prompt", "completion"})
_CHAT_ROLES = frozenset({"system", "user", "assistant", "tool", "developer"})
_MISSING = object()        # a field named in a value: its own value is unknown


def _token_counts(toks: list[str]) -> bool:
    """The `token` entry, minus pagination and usage counters (spec 4.4.4)."""
    for i, t in enumerate(toks):
        if t not in ("token", "tokens"):
            continue
        if (i + 1 < len(toks) and toks[i + 1] in _TOKEN_NOT_BEFORE) or (i > 0 and toks[i - 1] in _TOKEN_NOT_AFTER):
            continue
        return True
    return False


def _key(k) -> str:
    return k if isinstance(k, str) else str(k)


def _rest_dict(d: dict) -> bool:
    """One object holding a writing HTTP method and a target (spec 4.5, generic REST)."""
    method = target = False
    for k, v in d.items():
        c = canonical(_key(k))
        if c in _REST_METHOD_KEYS and isinstance(v, str) and v.strip().upper() in _REST_WRITE:
            method = True
        elif c in _REST_TARGET_KEYS:
            target = True
    return method and target


def _has_rest(value, depth: int = 0) -> bool:
    if depth > MAX_DEPTH:
        return False
    if isinstance(value, dict):
        return _rest_dict(value) or any(_has_rest(v, depth + 1) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_rest(v, depth + 1) for v in value)
    return False


def _pointer_segments(path: str) -> list[tuple[str, str | None]]:
    """JSON Pointer segments of a JSON Patch `path`, each with the canonical previous segment as its container."""
    out, prev = [], None
    for seg in path.split("/"):
        seg = seg.replace("~1", "/").replace("~0", "~")
        if seg:
            out.append((seg, prev if prev in _CONTAINERS else None))
            prev = canonical(seg)
    return out


class _Reader:
    def __init__(self, server, args, vocab: Vocabulary, rest_call: bool):
        self.vocab = vocab
        self.rest_call = rest_call
        repo = args.get("repo") if isinstance(args, dict) else None
        self.repo_exempt = ((server or "").casefold() in self._repository_servers()
                            and isinstance(repo, str) and bool(repo.strip()))
        self.hits: set[str] = set()
        self.unclassified = False
        self.stop = False
        self.seen: set[str] = set()
        self._canon: dict[str, str] = {}
        self._matches: dict[str, tuple] = {}
        self._entries = [(c, e) for c in CATEGORIES if c != "unclassified" and c in vocab.active
                         for e in sorted(vocab.entries.get(c, ()))]

    @staticmethod
    def _repository_servers():
        from .classify import REPOSITORY_SERVERS   # lazy: classify imports this module
        return REPOSITORY_SERVERS

    def canon(self, raw: str) -> str:
        c = self._canon.get(raw)
        if c is None:
            c = self._canon[raw] = canonical(raw)
        return c

    def flag(self) -> None:
        self.unclassified = True

    def matches(self, canon: str) -> tuple:
        m = self._matches.get(canon)
        if m is None:
            toks = tokens(canon)
            m = self._matches[canon] = tuple(
                (c, e) for c, e in self._entries
                if (_token_counts(toks) if e == "token" else entry_matches(canon, toks, e)))
        return m

    def exempt(self, cat: str, entry: str, canon: str, value, root: bool) -> bool:
        if cat == "access" and entry == "owner":
            return canon == "owner" and root and self.repo_exempt
        if cat == "access" and entry == "role":
            return canon == "role" and isinstance(value, str) and value.strip().casefold() in _CHAT_ROLES
        if cat == "recipients" and entry == "to":
            return not (value is _MISSING or isinstance(value, (list, tuple))
                        or (isinstance(value, str) and "@" in value))
        return False

    def candidate(self, raw: str, container: str | None, value, root: bool) -> None:
        """One field name: opaque ids on the raw form, then canonical form, mixed script and the vocabulary."""
        if self.stop:
            return
        if _OPAQUE.fullmatch(raw) or (container is not None and _OPAQUE_IN_CONTAINER.fullmatch(raw)):
            self.flag()
        canon = self.canon(raw)
        if canon not in self.seen:
            self.seen.add(canon)
            if len(self.seen) > MAX_KEYS:
                self.flag()
                self.stop = True
                return
            if mixed_script(canon):
                self.flag()
        for cat, entry in self.matches(canon):
            if cat not in self.hits and not self.exempt(cat, entry, canon, value, root):
                self.hits.add(cat)

    def walk(self, value, depth: int, container: str | None, root: bool, decode: bool, level: int) -> None:
        if self.stop:
            return
        if isinstance(value, (dict, list, tuple)) and depth > MAX_DEPTH:
            self.flag()
            return
        if isinstance(value, dict):
            self.obj(value, depth, container, root, level)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.walk(item, depth + 1, container, root, decode, level)
                if self.stop:
                    return
        elif isinstance(value, str) and decode:
            self.string(value, depth, container, root, level)

    def string(self, s: str, depth: int, container: str | None, root: bool, level: int) -> None:
        t = s.strip().lstrip("\ufeff").strip()
        if not t or t[0] not in '{["':
            return
        if len(t) > MAX_JSON or (len(t) > MAX_JSON // 4 and len(t.encode("utf-8", "surrogatepass")) > MAX_JSON):
            self.flag()
            return
        try:
            obj = json.loads(t)
        except RecursionError:
            self.flag()
            return
        except ValueError:
            return                      # an ordinary string ("[BUG] crash")
        if level >= JSON_LEVELS:
            self.flag()                 # a 4th level of JSON in a string
            return
        self.walk(obj, depth + 1, container, root, True, level + 1)

    def obj(self, d: dict, depth: int, container: str | None, root: bool, level: int) -> None:
        items = [(_key(k), v) for k, v in d.items()]
        canons = [self.canon(k) for k, _ in items]
        by_canon: dict[str, object] = {}
        for c, (_, v) in zip(canons, items):
            by_canon.setdefault(c, v)
        node = not root and bool(items) and set(canons) <= _RICH_KEYS
        if _rest_dict(d):
            self.flag()
        for ck, (k, v) in zip(canons, items):
            if self.stop:
                return
            if node and ck == "attrs":
                continue                # a rich-text node's attributes are not fields
            self.candidate(k, container, v, root)
            if ck in _FREE_STRING and isinstance(v, str):
                self.flag()
            if isinstance(v, str):
                if ck in _FIELD_VALUE_KEYS:
                    self.candidate(v, None, _MISSING, False)
                elif ck == "name" and "value" in by_canon:
                    self.candidate(v, None, by_canon["value"], False)
                elif ck == "path" and "op" in by_canon:
                    for seg, cont in _pointer_segments(v):
                        self.candidate(seg, cont, by_canon.get("value", _MISSING), False)
                elif ck == "update_mask":
                    for part in v.split(","):
                        part = part.strip()
                        if part:
                            self.candidate(part, None, _MISSING, False)
                            if "." in part:
                                for seg in part.split("."):
                                    if seg:
                                        self.candidate(seg, None, _MISSING, False)
            elif isinstance(v, (list, tuple)) and ck in _FIELD_LIST_KEYS:
                for item in v:
                    if isinstance(item, str):
                        self.candidate(item, ck, _MISSING, False)
            self.walk(v, depth + 1, ck if ck in _CONTAINERS else None, False,
                      self.rest_call or ck not in _CONTENT_KEYS, level)


def categorize(server: str | None, args: object, vocab: Vocabulary, *, free: bool) -> frozenset[str]:
    """The active categories a tool call's arguments touch (spec 4.3-4.5). ``server`` is None for a ``tool:`` type.

    On a ``FREE`` tool only the generic REST rule applies. May raise: ``classify`` catches."""
    rest_call = _has_rest(args)
    if free:
        return frozenset({"unclassified"} & vocab.active) if rest_call else frozenset()
    reader = _Reader(server, args, vocab, rest_call)
    reader.walk(args, 0, None, True, True, 0)
    if rest_call:
        reader.flag()
    hits = set(reader.hits)
    if reader.unclassified:
        hits.add("unclassified")
    return frozenset(hits & vocab.active)
