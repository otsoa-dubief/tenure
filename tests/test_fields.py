# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
import json
import pytest
from tenure import fields as F


@pytest.mark.parametrize("raw,canon", [
    ("accountNumber", "account_number"), ("userIBAN", "user_iban"), ("IBANCode", "iban_code"),
    ("Mot de passe", "mot_de_passe"), ("iban_fr__c", "iban_fr"), ("IBAN__C", "iban"), ("i​ban", "iban"),
    ("ıban", "iban"), ("hasło", "haslo"), ("beløb", "belob"), ("cœur", "coeur"), ("contact[email]", "contact_email"),
    ("userÉmail", "user_email"), ("cléApi", "cle_api"), ("ÉtatCompte", "etat_compte"),
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
    assert F.mixed_script(F.canonical("іban"))           # Cyrillic і
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


def test_swift_needs_its_qualifier():
    assert cat({"swift_version": "5.9"}) == frozenset() and cat({"swift": "x"}) == frozenset()
    assert cat({"swift_code": "x"}) == {"finance"} and cat({"swiftBic": "x"}) == {"finance"}


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
    assert cat({"body": {"type": "doc", "attrs": {"iban": "x"}}}) == frozenset()          # a node's attrs are ignored
    assert cat({"type": "doc", "attrs": {"iban": "x"}}) == {"finance"}                    # never at the root
    assert cat({"body": {"type": "doc", "content": [{"iban": "x"}]}}) == {"finance"}      # content is walked into
    assert cat({"type": "incident", "content": "x", "iban": "y"}) == {"finance"}


def test_json_strings():
    assert cat({"a": "﻿ " + json.dumps({"iban": 1})}) == {"finance"}               # BOM and a space
    assert cat({"a": json.dumps(json.dumps(json.dumps({"iban": 1})))}) == {"finance"}      # 3 levels decoded
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


@pytest.mark.parametrize("key,hit", [
    ("contact_id", True), ("recordId", True), ("to", True), ("cc", True), ("bcc", True), ("from", True),
    ("issue_number", True), ("message_id", True), ("comment_id", True), ("webhook_url", True),
    ("attendees", True), ("token_id", True), ("pull_number", True), ("phone", True), ("domain", True), ("branch", True),
    ("api_key", False), ("client_secret", False), ("user_password", False), ("file_content", False),
    ("email_body", False), ("ticket_description", False), ("page_size", False), ("token", False),
    ("photo", False), ("session_id", False), ("auth_id", False), ("", False)])
def test_is_target(key, hit):
    assert F.is_target(key) is hit


@pytest.mark.parametrize("key,hit", [
    ("api_key", True), ("Authorization", True), ("client_secret", True), ("cookie", True), ("pwd", True),
    ("access_key", True), ("credentials", True), ("cookies", True), ("X-Api-Key", True), ("accessKey", True),
    ("auth_token", True), ("session_id", True), ("password", True),
    ("max_tokens", False), ("page_token", False), ("token_count", False), ("contact_id", False),
    ("next_page_token", False), ("author", False), ("token_id", False),
    ("secretary", True), ("motdepasse", True)])   # `secret` is a substring entry in entry_matches: secretary follows it
def test_is_secret(key, hit):
    assert F.is_secret(key) is hit


def test_mask_nested_and_url():
    v = F.mask({"headers": {"Authorization": "Bearer x"}, "records": [{"fields": {"Password": "p"}}],
                "url": "https://u:p@h.io/a?api_key=k&page=2"})
    assert v["headers"]["Authorization"] == "•••" and v["records"][0]["fields"]["Password"] == "•••"
    assert "u:p@" not in v["url"] and "api_key=•••" in v["url"] and "page=•••" in v["url"]
    assert "%" not in v["url"] and v["url"].startswith("https://•••@h.io/a?")


def test_mask_shapes_and_depth():
    src = {1: "a", "t": ("x", {"token": "k"}), "n": 3, "secret": {"a": 1}}
    v = F.mask(src)
    assert v == {1: "a", "t": ["x", {"token": "•••"}], "n": 3, "secret": "•••"} and src["t"][1]["token"] == "k"
    deep = cur = {}
    for _ in range(F.MAX_DEPTH + 2):
        cur["a"] = {}
        cur = cur["a"]
    out = F.mask(deep)
    for _ in range(F.MAX_DEPTH + 1):    # depth > MAX_DEPTH is replaced
        out = out["a"]
    assert out == "…"
    assert F.mask("plain text") == "plain text"


def test_mask_url_leading_whitespace():
    v = F.mask("  \n https://u:p@h.io/a?k=v")
    assert "u:p@" not in v and "k=•••" in v and v.startswith("https://•••@h.io")


def test_mask_url_fragment_pairs():
    v = F.mask("https://h.io/cb#access_token=abc&state=xyz")
    assert v == "https://h.io/cb#access_token=•••&state=•••"
    assert F.mask("https://h.io/doc#top") == "https://h.io/doc#top"


def test_mask_url_bare_query_parts():
    v = F.mask("https://h.io/a?abc123")
    assert v == "https://h.io/a?•••" and "%" not in v
    assert F.mask("https://h.io/a?abc123&p=2") == "https://h.io/a?•••&p=•••"
