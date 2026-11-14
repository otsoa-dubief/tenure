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
