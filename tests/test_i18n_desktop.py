# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The desktop plugin's strings: catalog in tenure/locales/en/desktop.json, embedded copy in plugin.js, keys used."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "tenure" / "desktop" / "plugin.js"
LOCALES = ROOT / "tenure" / "locales"
CATALOG = LOCALES / "en" / "desktop.json"
NOTES = LOCALES / "en" / "desktop.notes.json"
BEGIN, END = "/* TENURE_LOCALES_BEGIN */", "/* TENURE_LOCALES_END */"
HBEGIN, HEND = "/* TENURE_I18N_BEGIN */", "/* TENURE_I18N_END */"
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
KEY = re.compile(r"[a-z0-9_]+(\.[a-z0-9_]+)+\Z")
PLURAL_CATS = {"zero", "one", "two", "few", "many", "other"}

SRC = PLUGIN.read_text(encoding="utf-8")


def _block(text: str, begin: str, end: str) -> str:
    i, j = text.find(begin), text.find(end)
    assert 0 <= i < j, f"markers {begin} / {end} not found"
    return text[i + len(begin):j]


def embedded() -> dict:
    body = _block(SRC, BEGIN, END).strip()
    assert body.startswith("const TENURE_LOCALES = ") and body.endswith(";")
    return json.loads(body[len("const TENURE_LOCALES = "):-1])


def catalogs() -> dict:
    return {d.name: json.loads((d / "desktop.json").read_text(encoding="utf-8"))
            for d in sorted(LOCALES.iterdir()) if (d / "desktop.json").exists()}


def placeholders(value) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return {m for t in texts for m in PLACEHOLDER.findall(t)}


EN = json.loads(CATALOG.read_text(encoding="utf-8"))


def test_embedded_block_matches_json_files():
    emb = embedded()
    assert emb == catalogs()
    assert emb["en"] == EN


def test_embedded_block_is_what_the_build_script_writes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_locales", ROOT / "scripts" / "build_locales.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert BEGIN + _block(SRC, BEGIN, END) + END == mod.block("desktop")


def test_keys_are_dotted_ids_and_no_key_is_a_prefix_of_another():
    # The host resolves `a.b.c` as a path into a nested bundle, so `a.b` cannot be both a leaf and a branch.
    for key in EN:
        assert KEY.match(key), key
    for key in EN:
        for other in EN:
            assert not other.startswith(key + "."), (key, other)


def test_values_are_strings_or_plural_objects_with_wellformed_placeholders():
    for key, value in EN.items():
        if isinstance(value, dict):
            assert set(value) <= PLURAL_CATS and {"one", "other"} <= set(value), key
            assert all(isinstance(v, str) for v in value.values()), key
            assert "n" in placeholders(value), f"{key}: a plural object is chosen by {{n}}"
            # A category may leave out {n} ("{type} changed" for one), never another placeholder.
            assert len({frozenset(set(PLACEHOLDER.findall(v)) - {"n"}) for v in value.values()}) == 1, f"{key}: categories differ"
        else:
            assert isinstance(value, str), key
        for name in placeholders(value):
            assert IDENT.match(name), f"{key}: bad placeholder {{{name}}}"


def test_other_locales_use_the_same_placeholders_as_en():
    for lang, cat in catalogs().items():
        for key, value in cat.items():
            assert key in EN, f"{lang}: unknown key {key}"
            assert placeholders(value) == placeholders(EN[key]), f"{lang}: {key}"


def _code() -> str:
    # The code outside the embedded catalog.
    i, j = SRC.find(BEGIN), SRC.find(END)
    return SRC[:i] + SRC[j:]


def test_every_key_used_in_plugin_js_exists_and_every_key_is_used():
    code = _code()
    used = {k for k in re.findall(r"\btr?\(\s*'([^']+)'", code) if not k.endswith("_")}
    used |= set(re.findall(r"withNode\(t, '([^']+)'", code))
    for a, b in re.findall(r"\btr?\(\s*[\w.]+ \? '([^']+)' : '([^']+)'", code):   # t(cond ? 'k1' : 'k2', …)
        used |= {a, b}
    # Keys built by prefix: 'type.stakes_' + level.
    for prefix in re.findall(r"\btr?\(\s*'([a-z0-9_.]+_)'\s*\+", code):
        used |= {k for k in EN if k.startswith(prefix)}
    missing = sorted(used - set(EN))
    assert not missing, missing
    unused = sorted(set(EN) - used)
    assert not unused, unused


def test_vars_passed_match_placeholders():
    # t('key', { a, b: x }) passes exactly the names the English value uses.
    code = _code()
    for key, args in re.findall(r"\btr?\(\s*'([a-z0-9_.]+)',\s*\{([^{}]*)\}\s*\)", code):
        names = set(re.findall(r"(?:^|,)\s*(\w+)\s*(?=:|,|$)", args.strip()))
        assert names == placeholders(EN[key]), (key, names)


def test_no_old_style_function_values_or_inline_en_dictionary():
    assert "const EN = {" not in SRC
    assert "ctx.i18n.register(hostBundles(TENURE_LOCALES))" in SRC


def test_no_physical_direction_in_styles_or_classes():
    code = _code()
    for pat in (r"\b(?:ml|mr|pl|pr|left|right)-[\w\[]", r"\btext-(?:left|right)\b", r"\b(?:marginLeft|marginRight|paddingLeft|paddingRight)\b",
                r"\b(?:left|right)\s*:", r"textAlign:\s*'(?:left|right)'"):
        hits = [m.group(0) for m in re.finditer(pat, code)]
        assert not hits, (pat, hits)


def test_notes_only_describe_existing_keys():
    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    assert set(notes) <= set(EN)


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_node_check_and_lookup_fallbacks(tmp_path):
    subprocess.run([NODE, "--check", str(PLUGIN)], check=True)
    helper = _block(SRC, HBEGIN, HEND)
    script = tmp_path / "t.mjs"
    script.write_text(helper + r"""
const L = {
  en: { 'a.hello': 'Hello {name}', 'a.only_en': 'English only',
        'a.items': { one: '{n} item', other: '{n} items' } },
  zh: { 'a.hello': '你好 {name}', 'a.items': { other: '{n} 项' } },
  ar: { 'a.items': { zero: 'لا عناصر', one: 'عنصر واحد', two: 'عنصران', few: '{n} عناصر', many: '{n} عنصرًا', other: '{n} عنصر' } },
}
const out = {
  unknown: translate(L, 'xx', 'a.hello', { name: 'Bo' }),
  missing: translate(L, 'zh', 'a.only_en'),
  hant: translate(L, 'zh-hant', 'a.hello', { name: 'Bo' }),
  nokey: translate(L, 'en', 'a.nope'),
  one: translate(L, 'en', 'a.items', { n: 1 }),
  other: translate(L, 'en', 'a.items', { n: 3 }),
  zh: translate(L, 'zh', 'a.items', { n: 1 }),
  ar0: translate(L, 'ar', 'a.items', { n: 0 }),
  ar2: translate(L, 'ar', 'a.items', { n: 2 }),
  ar5: translate(L, 'ar', 'a.items', { n: 5 }),
  keep: translate(L, 'en', 'a.hello'),
}
const b = hostBundles(L)
out.bundles = Object.keys(b).sort()
out.host_hant = b['zh-hant'].a.hello({ name: 'Bo' })
out.host_items = b.en.a.items({ n: 2 })
console.log(JSON.stringify(out))
""", encoding="utf-8")
    res = json.loads(subprocess.run([NODE, str(script)], check=True, capture_output=True, text=True,
                                    encoding="utf-8").stdout)
    assert res["unknown"] == "Hello Bo"
    assert res["missing"] == "English only"
    assert res["hant"] == "你好 Bo"
    assert res["nokey"] == "a.nope"
    assert (res["one"], res["other"], res["zh"]) == ("1 item", "3 items", "1 项")
    assert (res["ar0"], res["ar2"], res["ar5"]) == ("لا عناصر", "عنصران", "5 عناصر")
    assert res["keep"] == "Hello {name}"
    assert res["bundles"] == ["ar", "en", "zh", "zh-hant"]
    assert res["host_hant"] == "你好 Bo" and res["host_items"] == "2 items"


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_english_output_of_real_catalog(tmp_path):
    script = tmp_path / "e.mjs"
    script.write_text(_block(SRC, BEGIN, END) + _block(SRC, HBEGIN, HEND) + r"""
const T = (k, v) => translate(TENURE_LOCALES, 'en', k, v)
console.log(JSON.stringify([
  T('type.sessions', { n: 1 }), T('type.sessions', { n: 0 }),
  T('toast.acted', { type: 'file:write', n: 1, name: 'm' }), T('toast.acted', { type: 'file:write', n: 3, name: 'm' }),
  T('benchmark.faults', { n: 1, total: 4 }), T('preset.value_pending', { preset: 'balanced', k: 10 }),
  T('revoke.desc', { name: 'NAME' }),
]))
""", encoding="utf-8")
    res = json.loads(subprocess.run([NODE, str(script)], check=True, capture_output=True, text=True,
                                    encoding="utf-8").stdout)
    assert res == ["1 session", "0 sessions", "file:write changed, then told you (m).", "file:write: 3 changes, then told you (m).",
                   "1 fault / 4", "balanced · 1 in 10 spot-checked · applies from the next action",
                   "Every action type of NAME asks first again and its series restarts from zero. Its record stays in the ledger. Not a fault."]
