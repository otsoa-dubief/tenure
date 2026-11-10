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


# ------------------------------------------------------------------------------------- adversarial cases (review)
from test_plugin import pre, write  # noqa: E402


def test_renaming_the_original_before_the_copy_starts_does_not_invert(plugin, tmp_path, monkeypatch):  # noqa: F811
    """A rename keeps the database file; a copy is a new file: the file identity decides, not who starts first."""
    mod, ctx = plugin(FAST)
    root = tmp_path / "hermes"
    a = root / "profiles" / "a"
    reopen(mod, monkeypatch, a)
    to_t3(ctx)
    reopen(mod, monkeypatch, a)
    b = root / "profiles" / "b"
    shutil.copytree(a, b)
    c = root / "profiles" / "c"
    shutil.move(str(a), str(c))                                     # hermes profile rename a c
    reopen(mod, monkeypatch, c)
    assert state(mod, "file:write").tier == mod.rule.T3 and not ledger(mod, "copy")
    reopen(mod, monkeypatch, b)
    assert state(mod, "file:write").tier != mod.rule.T3 and len(ledger(mod, "copy")) == 1


def test_two_processes_opening_the_copy_demote_it_once(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    db = os.path.join(copy, "plugin-data", "tenure", "tenure.db")
    st1, st2 = mod.store.Store(db), mod.store.Store(db)
    real, done = mod._store_id_at, []

    def racing(h):
        r = real(h)
        if not done:
            done.append(1)
            mod._check_copied(st2)                 # the other process settles it while this one is deciding
        return r
    monkeypatch.setattr(mod, "_store_id_at", racing)
    mod._check_copied(st1)
    assert len([r for r in st1.ledger() if r["event"]["event"] == "copy"]) == 1


def test_an_unreadable_original_is_retried_and_asks_meanwhile(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    real = mod._store_id_at

    def locked(h):
        raise mod.CopyCheckFailed("database is locked")
    monkeypatch.setattr(mod, "_store_id_at", locked)
    mod.store_()
    assert mod.ST.copy_unchecked
    assert pre(mod, "write_file", write("z"), "c1") is not None            # asks while the check is pending
    monkeypatch.setattr(mod, "_store_id_at", real)
    reopen(mod, monkeypatch, copy)
    assert state(mod, "file:write").tier != mod.rule.T3 and len(ledger(mod, "copy")) == 1
    assert not mod.ST.copy_unchecked


def test_an_error_during_the_check_makes_every_action_ask(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    real = mod.sync_settings

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(mod, "sync_settings", boom)
    mod.store_()
    assert pre(mod, "write_file", write("z"), "c1") is not None
    monkeypatch.setattr(mod, "sync_settings", real)
    mod.ST.copy_retry_at = 0
    mod.store_()                                                            # retried in the same process
    assert state(mod, "file:write").tier != mod.rule.T3 and not mod.ST.copy_unchecked


def test_a_failed_key_removal_rolls_back_and_is_retried(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    mod.cli.slash("passport")
    original = tmp_path / "hermes"
    pem = os.path.join("plugin-data", "tenure", mod.passport.KEY_FILE)
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    real = os.remove

    def boom(p, *a, **k):
        if str(p).endswith(mod.passport.KEY_FILE):
            raise PermissionError(p)
        return real(p, *a, **k)
    monkeypatch.setattr(os, "remove", boom)
    mod.store_()
    assert mod.ST.copy_unchecked and not ledger(mod, "copy")               # rolled back: nothing half-done
    monkeypatch.setattr(os, "remove", real)
    reopen(mod, monkeypatch, copy)
    mod.store_()                                                           # the next start retries
    assert not os.path.exists(copy / pem) and len(ledger(mod, "copy")) == 1


def test_the_copy_passport_replays_to_the_live_states_and_verifies(plugin, tmp_path, monkeypatch):  # noqa: F811
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    climb(ctx, 3, "s3", tool="memory")
    original = tmp_path / "hermes"
    reopen(mod, monkeypatch, original)
    copy = clone(original)
    reopen(mod, monkeypatch, copy)
    st = mod.store_()
    live = {(a, s.key): (s.tier, s.series, s.provisional, s.wald, s.trial_left) for a, s in st.states()}
    rep = mod.passport.replay(st.ledger())
    assert live == {(a, k): (s.tier, s.series, s.provisional, s.wald, s.trial_left)
                    for a, d in rep.items() for k, s in d.items()}
    assert "Passport written" in mod.cli.slash("passport")


def test_the_home_mark_is_salted(plugin, tmp_path, monkeypatch):  # noqa: F811
    """No path, and no unsalted hash of one, in the database: a dictionary of usual paths must not reveal the user."""
    import hashlib
    mod, ctx = plugin(FAST)
    to_t3(ctx)
    home = os.path.realpath(str(tmp_path / "hermes"))
    mark = mod.store_().get_meta(mod.HOME_META)
    assert mark and home not in mark and hashlib.sha256(home.encode()).hexdigest()[:32] != mark
