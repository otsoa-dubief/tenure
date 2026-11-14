# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
import json
import pytest
from tenure import fields as F


@pytest.mark.parametrize("raw,canon", [
    ("accountNumber", "account_number"), ("userIBAN", "user_iban"), ("IBANCode", "iban_code"),
    ("Mot de passe", "mot_de_passe"), ("iban_fr__c", "iban_fr"), ("IBAN__C", "iban"), ("i​ban", "iban"),
    ("ıban", "iban"), ("hasło", "haslo"), ("beløb", "belob"), ("cœur", "coeur"), ("contact[email]", "contact_email"),
    ("user:email", "user_email"), ("E-mail", "e_mail"), ("___", ""), ("​", "")])
def test_canonical(raw, canon):
    assert F.canonical(raw) == canon


@pytest.mark.parametrize("key,entry,hit", [
    ("stripe_api_key", "api_key", True), ("api_keys", "api_key", True), ("private_keys", "private_key", True),
    ("bic_code", "bic", True), ("to", "to", True), ("send_to", "to", False), ("photo", "to", False),
    ("user_password_hash", "password", True), ("mypassword", "password", True), ("statuses", "status", True),
    ("shipping_addresses", "address", True), ("total", "to", False)])
def test_entry_matches(key, entry, hit):
    c = F.canonical(key)
    assert F.entry_matches(c, F.tokens(c), entry) is hit


def test_mixed_script():
    assert F.mixed_script(F.canonical("іban"))           # і cyrillique
    assert not F.mixed_script(F.canonical("телефон_2")) and not F.mixed_script(F.canonical("客户ID"))


def test_load_options():
    v = F.load({"add": {"finance": ["numero_compte"]}, "remove": {"finance": ["bank"]}, "disable": ["secret", "unclassified"],
                "enable": ["identity"], "stakes": {"finance": "medium"}})
    assert "numero_compte" in v.entries["finance"] and "bank" not in v.entries["finance"]
    assert "secret" not in v.active and "unclassified" in v.active and "identity" in v.active
    assert v.stakes["finance"] == "medium" and "unclassified" in v.unknown


def test_owner_entries_are_canonical():
    for written, key in (("numeroCompte", "numero_compte"), ("Numéro Compte", "numero_compte"),
                         ("tva-intra", "tva_intra")):
        v = F.load({"add": {"finance": [written]}})
        assert F.categorize("x", {key: 1}, v, free=False) == {"finance"}, written
    v = F.load({"remove": {"finance": ["Bank"]}})
    assert "bank" not in v.entries["finance"] and F.categorize("x", {"bank": 1}, v, free=False) == frozenset()
    assert F.load({"add": {"finance": ["___"]}}).unknown == ("add.finance: '___'",)


def test_mistyped_setting_values():
    v = F.load({"enable": "identity", "disable": "Secret", "add": {"finance": "tva-intra"},
                "stakes": {"finance": " High ", "amount": "critical", "access": 2, "nope": "low"}})
    assert "identity" in v.active and "secret" not in v.active and "tva_intra" in v.entries["finance"]
    assert v.stakes["finance"] == "high" and v.stakes["amount"] == "medium" and v.stakes["access"] == "medium"
    assert v.unknown == ("stakes.amount: 'critical'", "stakes.access: 2", "nope")
    v = F.load({"enable": [1, None, "nope"], "add": 5, "stakes": [1], "remove": {"finance": 3}})
    assert set(v.unknown) == {"enable: 1", "enable: None", "nope", "add: 5", "stakes: [1]", "remove.finance: 3"}
    assert F.load(["finance"]).unknown == ("fields: ['finance']",)


def test_default_vocabulary():
    v = F.load()
    assert v.active == F.DEFAULT_ON and v.stakes["finance"] == "high" and "iban" in v.entries["finance"]
    assert "amount" not in v.entries["finance"] and v.version


def test_unreadable_vocabulary_file(monkeypatch, tmp_path):
    bad = tmp_path / "v.json"; bad.write_text("{")
    monkeypatch.setattr(F, "DATA_PATH", bad)
    v = F.load()
    assert v.broken and v.active == frozenset({"unclassified"})


def test_load_never_raises_on_bad_setting():
    for s in ("x", 3, ["a"], {"enable": "identity", "add": 5, "stakes": [1], 1: 2}, {"enable": [1, None, "nope"]}):
        v = F.load(s)
        assert isinstance(v, F.Vocabulary)
    assert "nope" in F.load({"enable": ["nope"]}).unknown


V = F.load()


def cat(args, server="x", free=False):
    return F.categorize(server, args, V, free=free)


@pytest.mark.parametrize("args,want", [
    ({"records": [{"id": "rec1", "fields": {"IBAN": "FR76"}}]}, {"finance"}),            # Airtable
    ({"page_id": "p", "properties": {"Mot de passe": {"rich_text": []}}}, {"secret"}),   # Notion
    ({"id": 4, "client_secret": "s"}, {"secret"}),                                          # plat
    ({"issue_fields": [{"field_name": "bank_account", "value": "x"}]}, {"finance"}),       # champ en valeur
    ({"fields": [{"name": "iban", "value": "x"}]}, {"finance"}),
    ([{"op": "replace", "path": "/iban", "value": "x"}], {"finance"}),
    ({"update_mask": "name,iban"}, {"finance"}),
    ({"fields": '{"customfield_10016": 5}'}, {"unclassified"}),                            # Jira en chaîne + opaque
    ({"fields": {"fld0123456789abcd": "x"}}, {"unclassified"}),
    ({"custom_fields": {"1201234567": "x"}}, {"unclassified"}),
    ({"fields": {"іban": "x"}}, {"unclassified"}),
    ({"query": "UPDATE t SET iban=1"}, {"unclassified"}),
    ({"a": json.dumps(json.dumps(json.dumps(json.dumps({"x": 1}))))}, {"unclassified"}),     # 4e niveau de chaîne JSON
    ({"iban": "x", "password": "y"}, {"secret", "finance"}),
])
def test_categorize_shapes(args, want):
    assert cat(args) == frozenset(want)


@pytest.mark.parametrize("args", [
    {"owner": "o", "repo": "r", "title": "[BUG] crash"}, {"cardId": "c", "name": "n"}, {"page_token": "t"},
    {"max_tokens": 5, "token_count": 1}, {"from": "2026-01-01", "to": "2026-02-01"},
    {"messages": [{"role": "user", "content": "hi"}]},
    {"description": {"type": "doc", "content": [{"type": "taskItem", "attrs": {"state": "DONE"}}]}},
    {"телефон_2": "x", "客户ID": "y", "hasło_konta": "z"}, {"record_id": "r", "range": "A1:B2"},
    {"filterByFormula": "x"}, {"content": '{"password": 1}', "path": "x.json"}, {"amount": 5, "status": "won"},
])
def test_categorize_non_regression(args):
    assert cat(args) == frozenset()


def test_rest_generic_even_on_free_tools():
    assert cat({"method": "delete", "url": "/v1/x"}, free=True) == {"unclassified"}
    assert cat({"iban": "x"}, free=True) == frozenset()


def test_rich_text_nodes():
    assert cat({"body": {"type": "doc", "attrs": {"iban": "x"}}}) == frozenset()          # attrs d'un nœud ignorés
    assert cat({"type": "doc", "attrs": {"iban": "x"}}) == {"finance"}                    # jamais à la racine
    assert cat({"body": {"type": "doc", "content": [{"iban": "x"}]}}) == {"finance"}      # on descend dans content
    assert cat({"type": "incident", "content": "x", "iban": "y"}) == {"finance"}


def test_json_strings():
    assert cat({"a": "﻿ " + json.dumps({"iban": 1})}) == {"finance"}               # BOM et espace
    assert cat({"a": json.dumps(json.dumps(json.dumps({"iban": 1})))}) == {"finance"}      # 3 niveaux décodés
    assert cat({"a": "[" * 100_000 + "]" * 100_000}) == {"unclassified"}                   # RecursionError
    assert cat({"a": "[" + " " * 1_000_001 + "]"}) == {"unclassified"}                     # > 1 Mo
    assert cat({"method": "PATCH", "url": "/x", "body": json.dumps({"iban": 1})}) >= {"finance", "unclassified"}


def test_more_unclassified_and_lists():
    assert cat({"fields": {"00N5e00000ABCDE": "x"}}) == {"unclassified"}
    assert cat({"fields": {"123e4567-e89b-12d3-a456-426614174000": "x"}}) == {"unclassified"}
    for k in ("sql", "script", "formula", "jql", "statement"):
        assert cat({k: "x"}) == {"unclassified"}
    assert cat({"fields": ["name", "iban"]}) == {"finance"} and cat({"columns": ["password"]}) == {"secret"}
    assert cat({"ſecret": "x"}) == {"secret"} and cat({"id_token": "t"}) == {"secret"}


def test_page_access_token_counts():
    assert cat({"page_access_token": "t"}) == {"secret"}


def test_bounds():
    assert cat({"records": [{f"k{i}": 1} for i in range(6000)]}) == {"unclassified"}
    deep = {}; d = deep
    for _ in range(12): d["a"] = {}; d = d["a"]
    assert cat(deep) == {"unclassified"}


def test_disabled_categories_and_their_exceptions():
    v = F.load({"enable": ["access", "lifecycle", "recipients"]})
    c = lambda a, s="x": F.categorize(s, a, v, free=False)
    assert c({"owner": "o", "repo": "r"}, "github") == frozenset()
    assert c({"owner": "o", "repo": ""}, "github") == {"access"}
    assert c({"owner": "o", "repo": "r"}, "crm") == {"access"}
    assert c({"role": "admin"}) == {"access"} and c({"role": "user", "content": "x"}) == frozenset()
    assert c({"stateId": "s"}) == {"lifecycle"} and c({"send_to": ["a@b.c"]}) == {"recipients"}
    assert c({"to": "a@b.c"}) == {"recipients"} and c({"to": "2026-02-01"}) == frozenset()


def test_field_named_in_value_under_container():
    assert cat({"custom_fields": [{"field_id": "1201234567", "value": 1}]}) == {"unclassified"}
    assert cat({"custom_fields": [{"id": "123e4567-e89b-12d3-a456-426614174000", "value": 1}]}) == {"unclassified"}
    assert cat({"data": {"id": "1234567", "type": "x"}}) == frozenset()     # JSON:API
    assert cat({"fields": [{"id": "1234567"}]}) == frozenset()
    assert cat({"key": "123456"}) == frozenset()
