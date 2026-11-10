"""Every shipped language has every key of every surface, the same placeholders, and its plural categories; the
JavaScript surfaces embed the current catalogs."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "tenure" / "locales"
LANGS = ["fr", "es", "zh", "ar"]
SURFACES = ["desktop", "dashboard", "core"]
PLURALS = {"en": {"one", "other"}, "fr": {"one", "many", "other"}, "es": {"one", "many", "other"},
           "zh": {"other"}, "ar": {"zero", "one", "two", "few", "many", "other"}}
REQUIRED = {"en": {"one", "other"}, "fr": {"one", "other"}, "es": {"one", "other"}, "zh": {"other"},
            "ar": {"zero", "one", "two", "few", "many", "other"}}
PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load(lang, surface):
    return json.loads((LOCALES / lang / f"{surface}.json").read_text(encoding="utf-8"))


def holders(v):
    vals = v.values() if isinstance(v, dict) else [v]
    return set().union(*(set(PH.findall(x)) for x in vals))


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("lang", LANGS)
def test_language_is_complete_and_consistent(lang, surface):
    en, tr = load("en", surface), load(lang, surface)
    assert set(tr) == set(en), f"missing {sorted(set(en) - set(tr))[:10]}, extra {sorted(set(tr) - set(en))[:10]}"
    for k, v in en.items():
        t = tr[k]
        assert isinstance(t, (str, dict)), k
        if isinstance(v, dict):
            assert isinstance(t, dict), f"{k}: plural in English, plain in {lang}"
            assert REQUIRED[lang] <= set(t) <= PLURALS[lang], f"{k}: categories {sorted(t)}"
        else:
            assert isinstance(t, str), f"{k}: plural in {lang}, plain in English"
        assert holders(t) == holders(v), f"{k}: placeholders {holders(t)} != {holders(v)}"
        forms = t.values() if isinstance(t, dict) else [t]
        for f in forms:
            assert f.strip() or not (v if isinstance(v, str) else v.get("other", "")).strip(), f"{k}: empty"
            assert set(PH.findall(f)) == holders(v) or isinstance(t, dict), k


@pytest.mark.parametrize("lang", LANGS)
def test_untranslatable_tokens_are_kept(lang):
    """Commands, tier codes and type names travel unchanged."""
    for surface in SURFACES:
        en, tr = load("en", surface), load(lang, surface)
        for k, v in en.items():
            for token in re.findall(r"hermes tenure [a-z]+|/tenure [a-z]+|\bT[123]\b|file:write", json.dumps(v)):
                assert token in json.dumps(tr[k], ensure_ascii=False), f"{surface} {k}: {token!r} lost in {lang}"


def test_embedded_blocks_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_locales.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
