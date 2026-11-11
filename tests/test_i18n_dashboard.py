# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""The dashboard tab reads every visible string from its catalog (tenure/locales/<lang>/dashboard.json)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "tenure" / "dashboard" / "dist" / "index.js"
EN = ROOT / "tenure" / "locales" / "en" / "dashboard.json"
NOTES = ROOT / "tenure" / "locales" / "en" / "dashboard.notes.json"
BEGIN, END = "/* TENURE_LOCALES_BEGIN */", "/* TENURE_LOCALES_END */"
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KEY = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
CALL = re.compile(r"(?<![\w.$])t\(\s*\"([^\"]+)\"\s*([+,)])")
TERNARY = re.compile(r"(?<![\w.$])t\(\s*[\w.!]+\s*\?\s*\"([^\"]+)\"\s*:\s*\"([^\"]+)\"\s*[,)]")

# Keys built from a prefix and a data id: the code only ever completes them with these ids.
DYNAMIC = {
    "tier.name.": ["ask", "notify", "alone"],
    "stakes.": ["low", "medium", "high"],
    "stakes.group.": ["low", "medium", "high"],
    "preset.": ["careful", "balanced", "fast", "custom"],
    "view.": ["map", "models", "switch", "passport", "undo", "settings", "help"],
    "help.asks_": ["leaves", "irreversible", "unknown", "outside", "files"],
    "event.fault.": ["refusal", "spot", "check", "undo", "flag"],
    "event.neutral.": ["alone", "error", "blocked", "timeout", "nobody", "expired", "ambiguous"],
    "event.why.": ["wald", "fault", "settings", "stakes"],
    "passport.field.": ["protocol", "agent", "profile", "rule", "settings", "ledger", "public_key", "signature",
                        "generated", "type_names"],
    "switch.count.": ["carried", "reset", "vetoed", "kept"],
    "switch.status.": [f"{s}.{p}" for s in ("carried", "reset", "vetoed", "kept") for p in ("label", "text")],
    "transitions.why.": ["trial_open", "after_fault", "on_evidence"],
}


def _js() -> str:
    return JS.read_text(encoding="utf-8")


def _en() -> dict:
    return json.loads(EN.read_text(encoding="utf-8"))


def _embedded() -> dict:
    text = _js()
    i, j = text.find(BEGIN), text.find(END)
    assert 0 <= i < j, "locale markers missing"
    body = text[i + len(BEGIN):j].strip()
    m = re.fullmatch(r"const TENURE_LOCALES = (\{.*\});", body, re.S)
    assert m, "the block must be a single `const TENURE_LOCALES = {...};`"
    return json.loads(m.group(1))


def _calls() -> list[tuple[str, str]]:
    text = _js()
    out = CALL.findall(text)
    for a, b in TERNARY.findall(text):       # t(cond ? "key.a" : "key.b", vars)
        out += [(a, ","), (b, ",")]
    return out


def _texts(value) -> list[str]:
    return list(value.values()) if isinstance(value, dict) else [value]


def test_embedded_block_equals_the_json_files():
    emb = _embedded()
    assert list(emb)[0] == "en"
    assert emb["en"] == _en()
    for lang, cat in emb.items():
        path = ROOT / "tenure" / "locales" / lang / "dashboard.json"
        assert json.loads(path.read_text(encoding="utf-8")) == cat, lang


def test_embedded_block_is_what_the_build_script_writes():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_locales
    finally:
        sys.path.pop(0)
    old, new = build_locales.rebuilt("dashboard")
    assert old == new, "run python3 scripts/build_locales.py"


def test_every_key_used_in_code_exists_in_english():
    en = _en()
    calls = _calls()
    assert len(calls) > 200
    for key, after in calls:
        if after == "+":
            assert key in DYNAMIC, f"dynamic key prefix {key!r} not declared in the test"
        else:
            assert key in en, key
    for prefix, ids in DYNAMIC.items():
        assert any(k == prefix and a == "+" for k, a in calls), f"{prefix} no longer used"
        for i in ids:
            assert prefix + i in en, prefix + i


def test_no_unused_english_key():
    en = _en()
    used = {k for k, a in _calls() if a != "+"}
    used |= {p + i for p, ids in DYNAMIC.items() for i in ids}
    assert set(en) - used == set()


def test_keys_and_values_are_well_formed():
    en = _en()
    assert list(en) == sorted(en)
    for key, value in en.items():
        assert KEY.match(key), key
        if isinstance(value, dict):
            assert set(value) >= {"one", "other"} and set(value) <= {"zero", "one", "two", "few", "many", "other"}, key
            assert all(isinstance(v, str) for v in value.values()), key
            names = [set(PLACEHOLDER.findall(v)) for v in value.values()]
            assert all(n == names[0] for n in names), f"{key}: plural forms disagree on placeholders"
            assert "n" in names[0] or any("{count}" in v or "{wait}" in v or "{left}" in v for v in value.values()) \
                or key in {"counters.actions.label"}, key
        else:
            assert isinstance(value, str), key
        for text in _texts(value):
            for name in PLACEHOLDER.findall(text):
                assert IDENT.match(name), f"{key}: bad placeholder {{{name}}}"
            assert text.count("{") == text.count("}"), key


def test_placeholders_match_the_code():
    """Each call passes at least the placeholders its English text needs."""
    en = _en()
    text = _js()
    pairs = [(m.group(1), m.group(2)) for m in re.finditer(r"(?<![\w.$])t\(\s*\"([^\"]+)\"\s*,\s*\{([^{}]*)\}", text)]
    for m in re.finditer(r"(?<![\w.$])t\(\s*[\w.!]+\s*\?\s*\"([^\"]+)\"\s*:\s*\"([^\"]+)\"\s*,\s*\{([^{}]*)\}", text):
        pairs += [(m.group(1), m.group(3)), (m.group(2), m.group(3))]
    assert len(pairs) > 90
    for key, args in pairs:
        if key not in en:
            continue
        given = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", args))
        needed = set().union(*(set(PLACEHOLDER.findall(s)) for s in _texts(en[key])))
        if isinstance(en[key], dict):
            needed.add("n")
        assert needed <= given, f"{key}: needs {sorted(needed)}, given {sorted(given)}"


def test_other_languages_keep_english_placeholders():
    en = _en()
    for lang, cat in _embedded().items():
        for key, value in cat.items():
            assert key in en, f"{lang}: unknown key {key}"
            want = set().union(*(set(PLACEHOLDER.findall(s)) for s in _texts(en[key])))
            got = set().union(*(set(PLACEHOLDER.findall(s)) for s in _texts(value)))
            assert got == want, f"{lang}/{key}"


def test_notes_point_at_real_keys():
    en = _en()
    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    assert set(notes) <= set(en)


def test_keyboard_letters_stay_and_smoke_texts_are_in_english():
    text, en = _js(), _en()
    for letter in "mbwpus":
        assert f'key: "{letter}"' in text
    assert en["page.title"] == "Tenure"
    assert en["view.models"] == "Your benchmark"
    assert "public capability on their tasks, not reliability on yours" in en["models.lede_bold"]
    assert en["preset.careful"] == "careful" and en["settings.save"] == "Save"
    assert en["settings.in_force"] == "In force"


def test_locale_comes_from_the_dashboard_sdk():
    text = _js()
    assert "SDK.useI18n()" in text and "i18n.locale" in text


RUNNER = r"""
const fs = require("fs");
let src = fs.readFileSync(process.argv[2], "utf8");
const block = fs.readFileSync(process.argv[3], "utf8");
const i = src.indexOf("/* TENURE_LOCALES_BEGIN */"), j = src.indexOf("/* TENURE_LOCALES_END */");
src = src.slice(0, i) + "/* TENURE_LOCALES_BEGIN */\nconst TENURE_LOCALES = " + block + ";\n" + src.slice(j);
src = src.replace('REG.register("tenure", TenurePage);', "global.__T = { t: t, setLocale: setLocale, ago: ago };");
global.document = { documentElement: { getAttribute: () => null } };
global.window = { __HERMES_PLUGINS__: { register() {} }, __HERMES_PLUGIN_SDK__: { React: { createElement() {} },
  hooks: {}, components: {} } };
eval(src);
const T = global.__T, out = {};
for (const loc of ["en", "fr", "fr-CA", "zh-hant", "zh", "ar", "xx", undefined]) {
  T.setLocale(loc);
  out[String(loc)] = [T.t("view.map"), T.t("view.undo"), T.t("count.faults", { n: 1 }), T.t("count.faults", { n: 2 }),
    T.t("count.faults", { n: 1234 }), T.t("no.such.key"), T.t("totals.checked", { n: null }), T.ago(3725)];
}
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_lookup_falls_back_and_selects_plurals(tmp_path):
    en = _en()
    fake = {"en": en,
            "fr": {"view.map": "Carte", "count.faults": {"one": "{n} faute", "other": "{n} fautes"}},
            "zh": {"view.map": "地图", "count.faults": {"other": "{n} 个错误"}},
            "ar": {"view.map": "خريطة", "count.faults": {"zero": "لا أخطاء", "one": "خطأ واحد", "two": "خطآن",
                                                        "few": "{n} أخطاء", "many": "{n} خطأ", "other": "{n} خطأ"}}}
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    data = tmp_path / "locales.json"                    # a file: the catalog is longer than a Windows command line
    data.write_text(json.dumps(fake, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run(["node", str(runner), str(JS), str(data)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["en"] == ["Map", "Undo", "1 fault", "2 faults", "1,234 faults", "no.such.key", "— verified by you", "1h 02m ago"]
    assert out["undefined"] == out["en"] and out["xx"] == out["en"]
    assert out["fr"][:4] == ["Carte", "Undo", "1 faute", "2 fautes"]          # missing key -> English
    assert out["fr-CA"][:4] == out["fr"][:4]                                     # base language
    assert out["zh-hant"][0] == "地图" and out["zh-hant"][2] == "1 个错误"       # zh-hant -> zh, only "other"
    assert out["ar"][2] == "خطأ واحد" and out["ar"][1] == "Undo"
