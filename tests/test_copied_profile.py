"""A tenure record copied into another profile (Hermes `profile create --clone-all`, the desktop's Duplicate Bot)
does not carry earned autonomy over silently: the copy starts provisional, with its own keys. A record that only
moved (the original profile is gone) keeps everything."""
import os
import shutil

from test_plugin import A, FAST, climb, ledger, plugin, state, to_t3  # noqa: F401


def clone(original, name="bot-copy"):
    """What `hermes profile create NAME --clone-all` does to the plugin's files: the profile copied under
    ``<root>/profiles/NAME``."""
    staging = original.parent / f"staging-{name}"
    shutil.copytree(original, staging, ignore=shutil.ignore_patterns("profiles"))
    target = original / "profiles" / name
    target.parent.mkdir(exist_ok=True)
    shutil.move(str(staging), str(target))
    return target


def reopen(mod, monkeypatch, home):
    """Point the plugin at another Hermes home, as a process started in that profile would be."""
    if mod.ST.store is not None:
        mod.ST.store.db.close()
    mod.ST.store, mod.ST.store_path = None, None
    monkeypatch.setenv("HERMES_HOME", str(home))


def test_a_copied_profile_starts_provisional_and_the_original_keeps_its_tiers(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    assert state(mod, "file:write").tier == mod.rule.T3
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)

    reopen(mod, monkeypatch, copy)
    s = state(mod, "file:write")
    assert s.tier == mod.rule.T1 and s.provisional > 0
    copies = ledger(mod, "copy")
    assert len(copies) == 1 and copies[0]["mode"] == "carry"
    replayed = mod.passport.replay(mod.store_().ledger())[A]["file:write"]
    assert (replayed.tier, replayed.series, replayed.provisional) == (s.tier, s.series, s.provisional)
    assert "copied from another profile" in mod.cli.slash("status")
    reopen(mod, monkeypatch, copy)
    assert len(ledger(mod, "copy")) == 1                                   # detected once, not at every start

    reopen(mod, monkeypatch, original)
    assert state(mod, "file:write").tier == mod.rule.T3 and not ledger(mod, "copy")
    assert "copied from another profile" not in mod.cli.slash("status")


def test_a_copy_in_strict_mode_starts_empty(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin({**FAST, "strict": True})
    to_t3(ctx)
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    s = state(mod, "file:write")
    assert (s.tier, s.series, s.provisional) == (mod.rule.T1, 0, 0)
    assert ledger(mod, "copy")[0]["mode"] == "strict"


def test_a_moved_profile_keeps_everything(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    original, moved = tmp_path / "hermes", tmp_path / "restored"
    reopen(mod, monkeypatch, original)
    shutil.move(str(original), str(moved))
    reopen(mod, monkeypatch, moved)
    assert state(mod, "file:write").tier == mod.rule.T3 and not ledger(mod, "copy")
    reopen(mod, monkeypatch, moved)
    assert not ledger(mod, "copy")


def test_a_copy_gets_its_own_keys_and_none_of_the_originals_undos(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    climb(ctx, 12)
    with open(os.path.join(ctx.cwd, "src", "u.py"), "w") as f:
        f.write("before = 1\n")
    assert ctx.call("write_file", {"path": "src/u.py", "content": "after = 2\n"}) == "ran"
    mod.cli.slash("passport")
    undo_key = mod.undo_key()
    original = tmp_path / "hermes"
    pem = os.path.join("plugin-data", "tenure", mod.passport.KEY_FILE)
    reopen(mod, monkeypatch, original)
    assert os.path.exists(original / pem)
    copy = clone(original)

    reopen(mod, monkeypatch, copy)
    mod.store_()
    assert not os.path.exists(copy / pem)                                  # a new key is made at the next passport
    assert mod.undo_key() != undo_key
    assert mod.cli.slash("undo").startswith("Nothing to undo")

    reopen(mod, monkeypatch, original)
    assert mod.undo_key() == undo_key and os.path.exists(original / pem)
    assert not mod.cli.slash("undo").startswith("Nothing to undo")
