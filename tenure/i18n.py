# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""Owner-facing text of the Python side (chat notices, approval prompt text, ``hermes tenure`` and ``/tenure``).

Catalogs: ``tenure/locales/<lang>/core.json``, flat dotted keys; a value is a string or an object of CLDR plural
categories selected by the variable ``n``. The language is resolved at every call, in Hermes' own order:
``HERMES_LANGUAGE``, else ``display.language`` from the profile's config (public ``hermes_cli.config.load_config``,
re-read every few seconds), else en. Fallback chain: exact id, base language (``zh-hant`` -> ``zh``), en; a
missing key gives the en value, then the key itself; a missing variable leaves its ``{placeholder}``. Never raises.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
SURFACE = "core"
DEFAULT = "en"

_cache: dict[tuple[str, str], dict] = {}
_config_lang: dict[str, tuple[str, float]] = {}
CONFIG_TTL = 5.0
_lock = threading.Lock()
_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# ----------------------------------------------------------------------------------------------- language
def normalize(lang) -> str:
    """``zh_CN`` / ``ZH-Hant`` -> ``zh-cn`` / ``zh-hant``; empty or unusable -> en."""
    s = str(lang or "").strip().lower().replace("_", "-")
    s = s.split(".", 1)[0]                     # POSIX ``fr_FR.UTF-8``
    return s if re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{1,8})*", s) else DEFAULT


def _config_language() -> str:
    """``display.language`` of this profile's config, through Hermes' public reader; "" when unset or unreadable.
    Read again at most every CONFIG_TTL seconds (a change in Settings shows within that time)."""
    now = time.monotonic()
    with _lock:
        hit = _config_lang.get("value")
        if hit is not None and now - hit[1] < CONFIG_TTL:
            return hit[0]
    lang = ""
    try:
        from hermes_cli.config import load_config
        display = (load_config() or {}).get("display") or {}
        value = display.get("language") if isinstance(display, dict) else None
        lang = value.strip() if isinstance(value, str) else ""
    except Exception:
        lang = ""
    with _lock:
        _config_lang["value"] = (lang, now)
    return lang


def language() -> str:
    """The owner's language now, in Hermes' own order: ``HERMES_LANGUAGE``, else ``display.language``, else en."""
    env = os.environ.get("HERMES_LANGUAGE") or ""
    if env.strip():
        return normalize(env)
    return normalize(_config_language() or DEFAULT)


def chain(lang) -> list[str]:
    """exact -> base language -> en, without repeats."""
    lang = normalize(lang)
    out = [lang]
    base = lang.split("-", 1)[0]
    for x in (base, DEFAULT):
        if x not in out:
            out.append(x)
    return out


def catalog(lang: str) -> dict:
    """``locales/<lang>/core.json``, read once; {} when missing or unreadable."""
    key = (LOCALES_DIR, lang)
    with _lock:
        if key in _cache:
            return _cache[key]
    try:
        with open(os.path.join(LOCALES_DIR, lang, f"{SURFACE}.json"), encoding="utf-8") as f:
            data = json.load(f)
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    with _lock:
        _cache[key] = data
    return data


def reset_cache() -> None:
    with _lock:
        _cache.clear()
        _config_lang.clear()


# ----------------------------------------------------------------------------------------------- plurals
def _int_parts(n) -> tuple[float, int, bool]:
    """(absolute value, integer part, is an integer)."""
    try:
        x = abs(float(n))
    except (TypeError, ValueError):
        return 0.0, 0, False
    return x, int(x), x == int(x)


def plural_category(lang: str, n) -> str:
    """CLDR cardinal category of ``n`` for ``lang`` (en, fr, es, zh, ar; any other language follows en)."""
    base = normalize(lang).split("-", 1)[0]
    x, i, whole = _int_parts(n)
    if base == "zh":
        return "other"
    if base == "ar":
        if not whole:
            return "other"
        if i == 0:
            return "zero"
        if i == 1:
            return "one"
        if i == 2:
            return "two"
        if 3 <= i % 100 <= 10:
            return "few"
        if 11 <= i % 100 <= 99:
            return "many"
        return "other"
    if base == "fr":
        if i in (0, 1):
            return "one"
        if whole and i % 1000000 == 0:
            return "many"
        return "other"
    if base == "es":
        if whole and i == 1:
            return "one"
        if whole and i % 1000000 == 0 and i:
            return "many"
        return "other"
    return "one" if whole and i == 1 else "other"


# ----------------------------------------------------------------------------------------------- lookup
def _fill(text: str, values: dict) -> str:
    return _VAR.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def _pick(value, lang: str, values: dict):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        cat = plural_category(lang, values.get("n", 0))
        got = value.get(cat)
        if not isinstance(got, str):
            got = value.get("other")
        return got if isinstance(got, str) else None
    return None


def tr(key: str, lang: str | None = None, **values) -> str:
    """The text of ``key`` in the owner's language (or ``lang``), with ``{name}`` filled from ``values``."""
    try:
        for code in chain(lang if lang else language()):
            text = _pick(catalog(code).get(key), code, values)
            if text is not None:
                return _fill(text, values)
    except Exception:
        pass
    return key


# -------------------------------------------------------------------------------------------------- percentages
_DECIMAL_COMMA = {"fr", "es"}          # "2,08 %" (non-breaking space before %, as Hermes' fr and es catalogs write it)


def pct(x: float, digits: int = 1, lang: str | None = None) -> str:
    """A rate as a percentage in the owner's language: 2.08% in English, Chinese and Arabic (Western digits), 2,08 %
    in French and Spanish."""
    base = chain(lang or language())[0].split("-")[0]
    text = f"{x * 100:.{digits}f}"
    return text.replace(".", ",") + "\u00a0%" if base in _DECIMAL_COMMA else text + "%"


# ------------------------------------------------------------------------------------------------- terminal width
def width(text: str) -> int:
    """Columns ``text`` takes in a terminal: East Asian wide and fullwidth characters take two, combining marks none.
    Arabic keeps its logical order and one column per character."""
    w = 0
    for ch in str(text):
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def ljust(text: str, columns: int) -> str:
    return text + " " * max(0, columns - width(text))


__all__ = ["tr", "language", "chain", "catalog", "plural_category", "pct", "width", "ljust", "reset_cache"]
