"""The Python side's catalog (tenure/locales/<lang>/core.json) and its lookup (tenure/i18n.py): every key the code
uses exists in English, placeholders are consistent, plural rules follow CLDR, the fallback chain holds, a catalog for
another language switches the owner's text, Hermes' button labels are used when Hermes has them, and terminal tables
align with double-width characters."""
import json
import re
import shutil
import sys
import types
from pathlib import Path

import pytest

from tenure import i18n
from test_plugin import FAST, climb, plugin  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
EN = ROOT / "tenure" / "locales" / "en" / "core.json"
CODE = [ROOT / "tenure" / f for f in ("__init__.py", "cli.py", "benchmarks.py", "undo.py", "passport.py",
                                      "personal.py", "i18n.py")]
PREFIXES = ("approval", "ask", "benchmarks", "carry", "cli", "notice", "settle", "stakes", "tier", "undo")
KEY = re.compile(r"""["']((?:%s)\.[a-z0-9_.]+)["']""" % "|".join(PREFIXES))
VAR = re.compile(r"\{([^{}]*)\}")
# Keys the code builds from a prefix: (literal prefix in the code, the suffixes it can take).
DYNAMIC = {
    "tier.short.": ("ask", "notify", "alone"),
    "tier.long.": ("ask", "notify", "alone"),
    "stakes.": ("low", "medium", "high"),
    "notice.tier.": ("fault", "settings"),
    "approval.button.": ("run", "reject", "session", "always"),
    "cli.col.": ("type", "stakes", "tier_now", "series", "sessions", "record", "guarantee", "model", "provider",
                 "fault_rate", "note", "number", "restores", "when", "agent"),
}
STRICT_SUFFIXED = ("cli.status.header.profile", "cli.status.header.here")


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.delenv("HERMES_LANGUAGE", raising=False)
    monkeypatch.delitem(sys.modules, "agent", raising=False)
    monkeypatch.delitem(sys.modules, "agent.i18n", raising=False)
    i18n.reset_cache()
    yield
    i18n.reset_cache()


def en():
    return json.loads(EN.read_text(encoding="utf-8"))


def used_keys() -> set[str]:
    keys = set()
    for path in CODE:
        src = path.read_text(encoding="utf-8")
        keys |= {k for k in KEY.findall(src) if not k.endswith((".", ".json", ".py"))}
        for prefix, suffixes in DYNAMIC.items():
            if f'"{prefix}{{' in src or f'f"{prefix}{{' in src:
                keys |= {prefix + s for s in suffixes}
    keys |= {k + "_strict" for k in STRICT_SUFFIXED}
    return keys


def forms(value):
    return list(value.values()) if isinstance(value, dict) else [value]


# ----------------------------------------------------------------------------------------------- catalog
def test_every_key_used_in_code_exists_in_english():
    catalog = en()
    missing = sorted(k for k in used_keys() if k not in catalog)
    assert not missing, missing


def test_every_english_key_is_used():
    unused = sorted(set(en()) - used_keys())
    assert not unused, unused


def test_dynamic_prefixes_are_really_in_the_code():
    src = "".join(p.read_text(encoding="utf-8") for p in CODE)
    for prefix in DYNAMIC:
        assert f'"{prefix}{{' in src, prefix


def test_values_are_strings_or_plural_objects_with_one_and_other():
    for key, value in en().items():
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)+", key), key
        if isinstance(value, dict):
            assert set(value) == {"one", "other"}, key
            assert all("{n}" in v for v in value.values()), key
        else:
            assert isinstance(value, str) and value, key


def test_placeholders_are_well_formed_and_the_same_in_every_form():
    for key, value in en().items():
        names = None
        for text in forms(value):
            found = VAR.findall(text)
            assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in found), (key, found)
            assert text.count("{") == text.count("}") == len(found), key
            if names is None:
                names = set(found)
            assert set(found) == names, key


def test_notes_name_real_keys():
    notes = json.loads((EN.parent / "core.notes.json").read_text(encoding="utf-8"))
    assert set(notes) <= set(en())


# ----------------------------------------------------------------------------------------------- plurals
@pytest.mark.parametrize("n, cat", [(0, "zero"), (1, "one"), (2, "two"), (3, "few"), (10, "few"), (11, "many"),
                                    (99, "many"), (100, "other"), (102, "other"), (103, "few"), (111, "many"),
                                    (1.5, "other")])
def test_arabic_plural_rules(n, cat):
    assert i18n.plural_category("ar", n) == cat


@pytest.mark.parametrize("lang, n, cat", [("fr", 0, "one"), ("fr", 1, "one"), ("fr", 1.5, "one"), ("fr", 2, "other"),
                                          ("fr", 1000000, "many"), ("en", 0, "other"), ("en", 1, "one"),
                                          ("en", 2, "other"), ("es", 1, "one"), ("es", 0, "other"),
                                          ("es", 5, "other"), ("zh", 1, "other"), ("zh-hant", 0, "other"),
                                          ("de", 1, "one")])
def test_plural_rules(lang, n, cat):
    assert i18n.plural_category(lang, n) == cat


# ----------------------------------------------------------------------------------------------- fallback
def fake_locales(tmp_path, monkeypatch, catalogs: dict[str, dict]):
    root = tmp_path / "locales"
    (root / "en").mkdir(parents=True)
    shutil.copy(EN, root / "en" / "core.json")
    for lang, data in catalogs.items():
        (root / lang).mkdir(parents=True, exist_ok=True)
        (root / lang / "core.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALES_DIR", str(root))
    i18n.reset_cache()
    return root


def test_chain_and_normalisation():
    assert i18n.chain("zh-hant") == ["zh-hant", "zh", "en"]
    assert i18n.chain("zh_CN") == ["zh-cn", "zh", "en"]
    assert i18n.chain("fr_FR.UTF-8") == ["fr-fr", "fr", "en"]
    assert i18n.chain("en") == ["en"]
    assert i18n.chain("") == ["en"] and i18n.chain(None) == ["en"] and i18n.chain("../x") == ["en"]


def test_fallback_exact_then_base_then_english(tmp_path, monkeypatch):
    fake_locales(tmp_path, monkeypatch, {"zh": {"cli.revoke.nothing": "没有可撤销的。"},
                                         "zh-hant": {"cli.strict.on": "嚴格模式開啟。"}})
    assert i18n.tr("cli.strict.on", lang="zh-hant") == "嚴格模式開啟。"
    assert i18n.tr("cli.revoke.nothing", lang="zh-hant") == "没有可撤销的。"          # base language
    assert i18n.tr("cli.revoke.nothing", lang="zh-CN") == "没有可撤销的。"
    assert i18n.tr("cli.err.no_agents", lang="zh-hant") == "No agent has a record yet."   # missing key -> en
    assert i18n.tr("cli.err.no_agents", lang="pl") == "No agent has a record yet."        # unknown language -> en
    assert i18n.tr("no.such.key") == "no.such.key"


def test_missing_variable_keeps_its_placeholder_and_never_raises():
    assert i18n.tr("undo.missing") == "No undo entry {id}."
    assert i18n.tr("undo.expired", id=3) == "Undo 3 is older than {n} h: the snapshot is no longer kept."
    assert i18n.tr("undo.missing", id="{n}", n=5) == "No undo entry {n}."         # values are never re-expanded


def test_plural_object_falls_back_to_other(tmp_path, monkeypatch):
    fake_locales(tmp_path, monkeypatch, {"ar": {"cli.count.types": {"zero": "لا أنواع", "one": "نوع واحد",
                                                                    "two": "نوعان", "few": "{n} أنواع",
                                                                    "other": "{n} نوع"}}})
    assert i18n.tr("cli.count.types", lang="ar", n=0) == "لا أنواع"
    assert i18n.tr("cli.count.types", lang="ar", n=2) == "نوعان"
    assert i18n.tr("cli.count.types", lang="ar", n=7) == "7 أنواع"
    assert i18n.tr("cli.count.types", lang="ar", n=12) == "12 نوع"               # no "many": other
    assert i18n.tr("cli.count.types", lang="ar", n=100) == "100 نوع"


def test_language_comes_from_hermes_then_the_environment(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "es")
    assert i18n.language() == "es"
    fake_hermes(monkeypatch, lang="zh-hant")
    assert i18n.language() == "zh-hant"


def test_a_broken_hermes_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("HERMES_LANGUAGE", "fr")
    mod = fake_hermes(monkeypatch, lang="ar")
    mod.get_language = lambda: (_ for _ in ()).throw(RuntimeError("no home"))
    assert i18n.language() == "fr"


# ----------------------------------------------------------------------------------------------- the owner's text
FR = {
    "cli.status.header.here": "tenure : ce profil, préréglage {preset}, 1 contrôle sur {spot}",
    "cli.status.empty": "Aucun type d'action n'a encore d'historique.",
    "cli.col.type": "type", "cli.col.stakes": "enjeu", "cli.col.tier_now": "palier actuel",
    "cli.col.record": "bilan",
    "cli.count.faults": {"one": "{n} faute", "other": "{n} fautes"},
    "cli.count.checks": {"one": "{n} contrôle", "other": "{n} contrôles"},
    "cli.status.chain_ok": {"one": "Preuves : {n} entrée, chaîne intacte.", "other": "Preuves : {n} entrées, chaîne intacte."},
    "stakes.low": "faible",
    "tier.short.ask": "T1 demande d'abord",
    "ask.prompt": "tenure — {summary}\n{why}\n« {run} » si c'est juste ; « {reject} » sinon. {session}/{always} = un « {run} ».",
}


def test_status_output_switches_language(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    english = mod.cli.slash("status")
    assert "No action type has a record yet." in english
    fake_locales(tmp_path, monkeypatch, {"fr": FR})
    monkeypatch.setenv("HERMES_LANGUAGE", "fr")
    text = mod.cli.slash("status")
    assert text.startswith("tenure : ce profil, préréglage")
    assert "Aucun type d'action n'a encore d'historique." in text and "Preuves :" in text
    climb(ctx, 1)
    text = mod.cli.slash("status")
    assert re.search(r"file:write\s+faible\s+T1 demande d'abord\s+1/\d+\s+\d/2\s+0 faute / 1 contrôle", text)
    header = next(ln for ln in text.splitlines() if "palier actuel" in ln)
    assert "enjeu" in header and "bilan" in header and "series" in header          # missing keys stay English
    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    assert mod.cli.slash("status").splitlines()[0].startswith("tenure: this profile, preset")


# ----------------------------------------------------------------------------------------------- Hermes' buttons
def fake_hermes(monkeypatch, *, lang="en", core=None, desktop=None):
    pkg, mod = types.ModuleType("agent"), types.ModuleType("agent.i18n")
    core = core or {}
    mod.get_language = lambda: lang
    mod.t = lambda key, lang=None, **kw: core.get((lang or "en", key), core.get(("en", key), key))
    mod.surface_catalog = lambda l, surface="core": dict(desktop or {}) if surface == "desktop" else {}
    pkg.i18n = mod
    monkeypatch.setitem(sys.modules, "agent", pkg)
    monkeypatch.setitem(sys.modules, "agent.i18n", mod)
    return mod


GATEWAY = {("en", "gateway.exec_approval.action_once"): "Allow Once",
           ("en", "gateway.exec_approval.action_deny"): "Deny",
           ("en", "gateway.exec_approval.action_session"): "Allow Session",
           ("en", "gateway.exec_approval.action_always"): "Always Allow",
           ("fr", "gateway.exec_approval.action_once"): "Autoriser une fois",
           ("fr", "gateway.exec_approval.action_deny"): "Refuser",
           ("fr", "gateway.exec_approval.action_session"): "Autoriser (session)",
           ("fr", "gateway.exec_approval.action_always"): "Toujours autoriser"}


def test_buttons_in_english_keep_our_labels_even_with_hermes(monkeypatch):
    fake_hermes(monkeypatch, lang="en", core=GATEWAY)
    assert i18n.buttons() == {"run": "Run", "reject": "Reject", "session": "Session", "always": "Always"}


def test_buttons_come_from_hermes_when_it_translates_them(monkeypatch):
    fake_hermes(monkeypatch, lang="fr", core=GATEWAY)
    assert i18n.buttons() == {"run": "Autoriser une fois", "reject": "Refuser", "session": "Autoriser (session)",
                              "always": "Toujours autoriser"}


def test_buttons_prefer_a_desktop_pack_then_fall_back_to_ours(tmp_path, monkeypatch):
    fake_hermes(monkeypatch, lang="fr", core=GATEWAY, desktop={"assistant.approval.run": "Exécuter"})
    assert i18n.buttons()["run"] == "Exécuter" and i18n.buttons()["reject"] == "Refuser"
    fake_locales(tmp_path, monkeypatch, {"es": {"approval.button.run": "Ejecutar"}})
    fake_hermes(monkeypatch, lang="es", core=GATEWAY)          # Hermes has no es label: it answers in English
    assert i18n.buttons() == {"run": "Ejecutar", "reject": "Reject", "session": "Session", "always": "Always"}


def test_buttons_without_hermes_use_the_catalog(tmp_path, monkeypatch):
    fake_locales(tmp_path, monkeypatch, {"fr": {"approval.button.reject": "Rejeter"}})
    assert i18n.buttons("fr")["reject"] == "Rejeter" and i18n.buttons("fr")["run"] == "Run"


def test_the_approval_prompt_names_the_localised_buttons(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    fake_locales(tmp_path, monkeypatch, {"fr": FR})
    fake_hermes(monkeypatch, lang="fr", core=GATEWAY)
    s = mod.rule.TypeState(key="file:write", stakes="low", reversible=True)
    act = types.SimpleNamespace(summary="write a.txt", type="file:write", stakes="low", reversible=True)
    text = mod._ask_message(act, s, 4, 0.05, decision=mod.rule.ASK, suspended=False, unsaved=False, earned_at=None)
    assert "« Autoriser une fois » si c'est juste ; « Refuser » sinon." in text
    assert "Autoriser (session)/Toujours autoriser" in text
    assert "(faible stakes)" in text                                    # an untranslated sentence still localises


# ----------------------------------------------------------------------------------------------- terminal width
def test_width_counts_wide_characters_twice():
    assert i18n.width("abc") == 3
    assert i18n.width("类型") == 4
    assert i18n.width("ｆｕｌｌ") == 8
    assert i18n.width("é") == 1 and i18n.width("é") == 1
    assert i18n.width("نوع") == 3


def test_cjk_table_columns_align(plugin):  # noqa: F811
    mod, _ = plugin(FAST)
    rows = mod.cli._table(["类型", "enjeu", "层级"], [["file:write", "低", "T1 先询问"], ["记忆:写入", "medium", "T3"]])
    starts = []
    for line in rows:
        cols = re.split(r"(?<=\S)  +(?=\S)", line)
        assert len(cols) == 3, line
        pos, col_starts = 0, []
        for c in cols:
            pos = line.index(c, pos)
            col_starts.append(i18n.width(line[:pos]))
            pos += len(c)
        starts.append(col_starts)
    assert all(s == starts[0] for s in starts), starts


def test_ascii_table_is_unchanged(plugin):  # noqa: F811
    mod, _ = plugin(FAST)
    header, rows = ["a", "bb"], [["ccc", "d"], ["e", "ffff"]]
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(2)]
    old = ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [header] + rows]
    assert mod.cli._table(header, rows) == old
