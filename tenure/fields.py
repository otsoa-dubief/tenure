# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Field-category vocabulary, key canonicalization and the extraction of the categories a tool call touches (pure).

The shipped vocabulary is ``data/field_categories.json``. ``load`` applies the owner's ``fields:`` setting and never
raises. This module must not import ``classify`` at module level (classify imports it).
"""
from __future__ import annotations

import functools
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

    def note(text: str) -> None:
        if text not in unknown:
            unknown.append(text)

    def strings(value, where: str) -> list[str]:
        """The strings of a list, a bare string as a one-item list; anything else is reported, then ignored."""
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set, frozenset)):
            note(f"{where}: {value!r}")
            return []
        out = []
        for x in value:
            out.append(x) if isinstance(x, str) else note(f"{where}: {x!r}")
        return out

    def block(key: str):
        value = s.get(key)
        if value is not None and not isinstance(value, dict):
            note(f"{key}: {value!r}")
        return ((str(k).strip().lower(), v) for k, v in value.items()) if isinstance(value, dict) else ()

    if setting is not None and not isinstance(setting, dict):
        note(f"fields: {setting!r}")
    s = setting if isinstance(setting, dict) else {}
    for name in (n.strip().lower() for n in strings(s.get("enable"), "enable")):
        active.add(name) if name in CATEGORIES else note(name)
    for name in (n.strip().lower() for n in strings(s.get("disable"), "disable")):
        if name not in CATEGORIES:
            note(name)
        elif name == "unclassified":
            note(name)  # structural: cannot be switched off
        else:
            active.discard(name)
    for key, op in (("add", frozenset.union), ("remove", frozenset.difference)):
        for name, items in block(key):
            if name not in CATEGORIES:
                note(name)
                continue
            canon = set()
            for item in strings(items, f"{key}.{name}"):
                c = canonical(item)     # matched against canonical keys: written as the owner likes
                canon.add(c) if c else note(f"{key}.{name}: {item!r}")
            entries[name] = op(entries[name], frozenset(canon))
    for name, level in block("stakes"):
        if name not in CATEGORIES:
            note(name)
        elif isinstance(level, str) and level.strip().lower() in _STAKES:
            stakes[name] = level.strip().lower()
        else:
            note(f"stakes.{name}: {level!r}")
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

def _split_camel(s: str) -> str:
    out = []

    for i, current in enumerate(s):
        if i > 0:
            previous = s[i - 1]
            next_char = s[i + 1] if i + 1 < len(s) else ""

            boundary_1 = (previous.islower() or previous.isdigit()) and current.isupper()
            boundary_2 = previous.isupper() and current.isupper() and next_char.islower()

            if boundary_1 or boundary_2:
                out.append("_")

        out.append(current)

    return "".join(out)

def canonical(key: str) -> str:
    """Canonical form of a field name (spec 4.4.1); ``""`` when nothing is left."""
    s = unicodedata.normalize("NFKC", str(key))
    s = "".join(c for c in s if unicodedata.category(c) != "Cf")
    s = _split_camel(s)
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
_ID_NAMES_FIELD = frozenset({"custom_fields", "column_values"})
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


_TARGET_WHOLE = frozenset({"id", "to", "cc", "bcc", "from", "path", "url", "email"})
_TARGET_WORDS = ("record contact customer client user account issue ticket recipient channel repo owner project deal "
                 "order invoice file sheet table slug attendee url pull target phone domain branch").split()
_TARGET_TOKENS = frozenset(w + s for w in _TARGET_WORDS for s in ("", "s", "es"))
_NOT_TARGET_LAST = frozenset({"body", "content", "text", "message", "description", "note", "notes", "comment",
                              "size", "limit", "count", "offset", "cursor", "token"})
_SECRET_WORDS = ("secret password passwd pwd passphrase auth authorization bearer cookie credential otp "
                 "signature session privatekey accesskey sessionid motdepasse").split()
_SECRET_PAIRS = ("api_key", "private_key", "access_key")
MASK = "\u2022\u2022\u2022"
_URLISH = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*://)([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$", re.S)


def _shipped_secret() -> frozenset[str]:
    """The entries of the shipped `secret` category, read once (none when the file is unreadable)."""
    key = ("secret", str(DATA_PATH))
    if key not in _cache:
        try:
            raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            _cache[key] = frozenset(canonical(str(e)) for e in raw["categories"]["secret"]["entries"]) - {""}
        except Exception:
            _cache[key] = frozenset()
    return _cache[key]


def _secret_entries(vocab: Vocabulary | None) -> frozenset[str]:
    """The built-in words, the shipped `secret` entries, and the owner's own `secret` entries (on or off)."""
    owner = vocab.entries.get("secret", frozenset()) if vocab is not None else frozenset()
    return frozenset(_SECRET_WORDS) | frozenset(_SECRET_PAIRS) | _shipped_secret() | owner


@functools.lru_cache(maxsize=4096)
def _secret(key: str, entries: frozenset[str]) -> bool:
    canon = canonical(key)
    if not canon:
        return False
    toks = tokens(canon)
    if _token_counts(toks):
        return True
    return any(entry_matches(canon, toks, e) for e in entries if e != "token")   # `token`: minus counters, above


def is_secret(key: str, vocab: Vocabulary | None = None) -> bool:
    """Does this argument name carry a secret? Built-in words plus every entry of the `secret` category, shipped or
    added by the owner, whether the category is on or off (spec 9 C3): switching it off never unmasks."""
    return _secret(key, _secret_entries(vocab))


def is_target(key: str, vocab: Vocabulary | None = None) -> bool:
    """Does this argument name the target of a call (spec 4.1, 9 C2)? A secret never is."""
    canon = canonical(key)
    if not canon or is_secret(key, vocab):
        return False
    toks = tokens(canon)
    if canon in _TARGET_WHOLE or toks[-1] in ("id", "ids"):
        return True
    from .classify import PROSE_KEYS   # lazy: classify imports this module
    if toks[-1] in _NOT_TARGET_LAST or any(toks[-1] == tokens(canonical(p))[-1] for p in PROSE_KEYS):
        return False
    return any(t in _TARGET_TOKENS for t in toks)


def _mask_pairs(part: str) -> str:
    """`a=1&b` -> `a=•••&b`-style: every value is masked, and a bare part (no `=`) is a value itself."""
    return "&".join(p.split("=", 1)[0] + "=" + MASK if "=" in p else (MASK if p else p) for p in part.split("&"))


def _mask_url(s: str) -> str:
    m = _URLISH.match(s.lstrip())
    if not m:
        return s
    scheme, auth, path, query, frag = m.groups()
    if "@" in auth:
        auth = MASK + "@" + auth.rsplit("@", 1)[1]
    if query:
        query = "?" + _mask_pairs(query[1:])
    if frag and "=" in frag:             # `#access_token=...`; a plain anchor (`#top`) stays
        frag = "#" + _mask_pairs(frag[1:])
    return scheme + auth + path + (query or "") + (frag or "")


def mask(value: object, vocab: Vocabulary | None = None, _depth: int = 0) -> object:
    """Deep copy where every value under a secret key is masked, and URLs lose userinfo and query values.

    Known limit: a header list of pairs ``[{"name": "Authorization", "value": ...}]`` is not masked."""
    if _depth > MAX_DEPTH:
        return "\u2026"
    if isinstance(value, dict):
        return {k: MASK if isinstance(k, str) and is_secret(k, vocab) else mask(v, vocab, _depth + 1)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask(v, vocab, _depth + 1) for v in value]
    if isinstance(value, str):
        return _mask_url(value)
    return value


# ------------------------------------------------------------------------------------- secrets in a terminal command
_CMD_SCAN = 4000                                     # characters of a command looked at (a prompt shows 200)
_CMD_SEPS = frozenset(" \t\n\r;|&()<>")
_HEADERISH = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(\S.*)$", re.S)
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.+)$", re.S)
_LONGOPT = re.compile(r"^(--?[A-Za-z][A-Za-z0-9_-]*)=(.+)$", re.S)
_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)([^/?#@\s'\"]+)@")
_SCHEMES = frozenset({"bearer", "basic", "token", "digest"})
_USER_OPTS = frozenset({"-u", "--user", "--proxy-user", "-U"})


def _words(cmd: str) -> list[tuple[int, int]]:
    """Spans of the shell words of `cmd`, quotes included; an unterminated quote runs to the end. Operators split."""
    out, i, n = [], 0, len(cmd)
    while i < n:
        if cmd[i] in _CMD_SEPS:
            i += 1
            continue
        start = i
        while i < n and cmd[i] not in _CMD_SEPS:
            c = cmd[i]
            if c == "\\":
                i += 2
            elif c in "'\"":
                j = i + 1
                while j < n and cmd[j] != c:
                    j += 2 if c == '"' and cmd[j] == "\\" else 1
                i = j + 1
            else:
                i += 1
        out.append((start, min(i, n)))
    return out


def _unquote(raw: str) -> tuple[str, str, str]:
    """(opening quote, inner text, closing quote) of a word quoted as a whole, else ("", raw, "")."""
    if raw[:1] in ("'", '"'):
        q = raw[0]
        end = q if len(raw) > 1 and raw.endswith(q) and raw[-2:] != "\\" + q else ""
        inner = raw[1:len(raw) - len(end)]
        # one quoted segment only: `'a'$(id)` or `"a"x"b"` is several, read as unquoted (so `$` keeps it visible)
        if q not in (inner if q == "'" else inner.replace("\\\\", "").replace("\\" + q, "")):
            return q, inner, end
    return "", raw, ""


def _plain(value: str, quote: str) -> bool:
    """A literal the shell keeps as written: nothing it would run or expand (single quotes keep everything)."""
    return bool(value) and (quote == "'" or not any(c in value for c in "$`") and "<(" not in value)


def _masked(raw: str) -> str | None:
    """`raw` (a whole value, maybe quoted) masked, or None when it is not a plain literal."""
    q, inner, end = _unquote(raw)
    return q + MASK + end if _plain(inner, q) else None


def mask_command(cmd: str, vocab: Vocabulary | None = None) -> str:
    """A terminal command as an approval prompt shows it, with the recognized spellings of a secret masked (#7):
    header values under a secret name (`-H "Authorization: Bearer x"`), the word after Bearer/Basic/Token,
    `--password=x` / `--password x`, `NAME=x` when NAME is a secret name, `-u user:pass`, URL userinfo.

    Display only: classification, written files and proofs keep the raw command. Only plain literals are masked,
    never a value the shell would run or expand (`$(…)`, backticks, `$VAR`, `<(…)`), so the approver still sees any
    code; a mis-parse may only under-mask. URL query values stay visible (often the target). Not a guarantee."""
    head, tail = cmd[:_CMD_SCAN], cmd[_CMD_SCAN:]
    spans = _words(head)
    repl: dict[int, tuple[int, str]] = {}             # start -> (end, new text)

    def put(a: int, b: int, text: str | None) -> None:
        if text is not None and a < b:
            repl[a] = (b, text)

    words = [head[a:b] for a, b in spans]

    def adjacent(i: int) -> bool:
        """Word i+1 is the next argument of word i: only blanks between them, no operator (`;`, `|`, `<(`...)."""
        return i + 1 < len(spans) and head[spans[i][1]:spans[i + 1][0]].strip(" \t") == ""

    for i, ((a, b), raw) in enumerate(zip(spans, words)):
        nxt = spans[i + 1] if adjacent(i) else None
        pre = next((p for p in ("--header=", "-H") if raw.startswith(p) and len(raw) > len(p)), "")
        q, inner, end = _unquote(raw[len(pre):])       # `-H"Authorization: …"`, `--header='…'` glued to the option
        m = _HEADERISH.match(inner)
        if m and is_secret(m.group(1), vocab) and _plain(m.group(2), q):
            put(a, b, pre + q + m.group(1) + ": " + MASK + end)
            continue
        q, inner, end = _unquote(raw)
        if q == "" and raw.endswith(":") and is_secret(raw[:-1], vocab) and nxt:      # -H Authorization: Bearer x
            j = i + 1
            if words[j].lower() in _SCHEMES:
                if not adjacent(j):
                    continue
                j += 1
            put(*spans[j], _masked(words[j]))
            continue
        if inner.lower() in _SCHEMES and nxt:
            put(*nxt, _masked(words[i + 1]))
            continue
        m = _LONGOPT.match(raw)
        if m and is_secret(m.group(1).lstrip("-"), vocab):
            put(a + len(m.group(1)) + 1, b, _masked(m.group(2)))
            continue
        if q == "" and raw.startswith("--") and len(raw) > 2 and "=" not in raw and is_secret(raw[2:], vocab) \
                and nxt and not words[i + 1].startswith("-"):
            put(*nxt, _masked(words[i + 1]))
            continue
        opt, eq, val = raw.partition("=")
        if opt in _USER_OPTS and (eq or nxt):            # `-u user:pass`, `--user=user:pass`
            va, vb, vraw = (a + len(opt) + 1, b, val) if eq else (*nxt, words[i + 1])
            uq, ui, ue = _unquote(vraw)
            if ":" in ui and _plain(ui, uq):
                put(va, vb, uq + ui.split(":", 1)[0] + ":" + MASK + ue)
            continue
        m = _ASSIGN.match(inner)
        if m and is_secret(m.group(1), vocab):
            vq, vi, ve = _unquote(m.group(2))
            if _plain(vi, vq or q):
                put(a, b, q + m.group(1) + "=" + vq + MASK + ve + end)
            continue
        if "://" in inner and "@" in inner and _plain(inner, q):
            put(a, b, _USERINFO.sub(lambda u: u.group(1) + MASK + "@", raw))

    out, pos = [], 0
    for a in sorted(repl):
        if a < pos:
            continue
        b, text = repl[a]
        out.append(head[pos:a] + text)
        pos = b
    return "".join(out) + head[pos:] + tail


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

    def walk(self, value, depth: int, container: str | None, root: bool, decode: bool, level: int,
             in_list: bool = False) -> None:
        if self.stop:
            return
        if isinstance(value, (dict, list, tuple)) and depth > MAX_DEPTH:
            self.flag()
            return
        if isinstance(value, dict):
            self.obj(value, depth, container, root, level, in_list)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.walk(item, depth + 1, container, root, decode, level, True)
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

    def obj(self, d: dict, depth: int, container: str | None, root: bool, level: int, in_list: bool = False) -> None:
        items = [(_key(k), v) for k, v in d.items()]
        canons = [self.canon(k) for k, _ in items]
        by_canon: dict[str, object] = {}
        for c, (_, v) in zip(canons, items):
            by_canon.setdefault(c, v)
        node = not root and bool(items) and set(canons) <= _RICH_KEYS
        if _rest_dict(d):
            self.flag()
        # a list item directly under a container: the fields it names in values are tested as opaque ids there,
        # and under custom_fields / column_values its `id` names a field too (ClickUp, monday)
        fv_container = container if in_list else None
        id_names_field = in_list and container in _ID_NAMES_FIELD
        for ck, (k, v) in zip(canons, items):
            if self.stop:
                return
            if node and ck == "attrs":
                continue                # a rich-text node's attributes are not fields
            self.candidate(k, container, v, root)
            if ck in _FREE_STRING and isinstance(v, str):
                self.flag()
            if isinstance(v, str):
                if ck in _FIELD_VALUE_KEYS or (id_names_field and ck == "id"):
                    self.candidate(v, fv_container, _MISSING, False)
                elif ck == "name" and "value" in by_canon:
                    self.candidate(v, fv_container, by_canon["value"], False)
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


# ------------------------------------------------------------------------------------------------ category types
_RANK = {"free": 0, "low": 1, "medium": 2, "high": 3, "cap": 4}   # same order as classify.RANK (not imported: cycle)


def child_type(parent: str, cats: frozenset[str]) -> str:
    """``<parent>:@<cat1>+<cat2>…``, categories in the fixed order of ``CATEGORIES`` (spec 4.1)."""
    return parent + ":@" + "+".join(c for c in CATEGORIES if c in cats)


def _split(type_: str) -> tuple[str, list[str]] | None:
    if not isinstance(type_, str) or not type_.startswith(("mcp:", "tool:")):
        return None
    parent, sep, last = type_.rpartition(":")
    if not sep or not last.startswith("@") or not parent.startswith(("mcp:", "tool:")) or parent in ("mcp:", "tool:"):
        return None
    names = last[1:].split("+")
    if not all(n in CATEGORIES for n in names):
        return None
    return parent, names


def parent_of(type_: str) -> str | None:
    """The parent of a category type, or None: only an ``mcp:``/``tool:`` type whose last segment is ``@`` followed by
    shipped category names joined by ``+`` (``shell:npx:@angular/cli`` has none)."""
    s = _split(type_)
    return s[0] if s else None


def categories_of(type_: str) -> frozenset[str]:
    s = _split(type_)
    return frozenset(s[1]) if s else frozenset()


def stakes_for(cats: frozenset[str], vocab: Vocabulary) -> str:
    """The highest stakes among the categories touched (unknown level → high)."""
    levels = [vocab.stakes.get(c, "high") for c in cats]
    levels = [lv if lv in _RANK else "high" for lv in levels]
    return max(levels, key=_RANK.__getitem__) if levels else "low"
