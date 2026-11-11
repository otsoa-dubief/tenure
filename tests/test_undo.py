import sys
import os
import stat
import time

import pytest

from tenure import undo

KEY = b"k" * 32


def test_snapshot_then_restore_puts_content_back(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"before")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    assert sid
    f.write_bytes(b"after")
    assert undo.restore(sid, root, key=KEY) == (1, 0)
    assert f.read_bytes() == b"before"
    d = os.path.join(root, "undo", sid)
    assert not os.path.exists(d)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_snapshot_dir_and_manifest_modes(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    d = os.path.join(root, "undo", sid)
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(os.path.join(d, "manifest.json")).st_mode) == 0o600


def test_restore_deletes_a_file_that_did_not_exist(tmp_path):
    f = tmp_path / "new.txt"
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    assert sid
    f.write_bytes(b"created by agent")
    assert undo.restore(sid, root, key=KEY) == (1, 0)
    assert not f.exists()


def test_snapshot_over_cap_returns_none(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 100)
    root = str(tmp_path / "data")
    assert undo.snapshot([str(f)], root, max_bytes=50, key=KEY) is None
    assert not os.path.isdir(os.path.join(root, "undo")) or not os.listdir(os.path.join(root, "undo"))


def test_unreadable_file_returns_none(tmp_path):
    f = tmp_path / "secret.txt"
    f.write_bytes(b"x")
    os.chmod(f, 0)
    try:
        if os.access(f, os.R_OK):
            pytest.skip("running as root: cannot simulate")
        root = str(tmp_path / "data")
        assert undo.snapshot([str(f)], root, key=KEY) is None
    finally:
        os.chmod(f, 0o600)


def test_directory_target_returns_none(tmp_path):
    assert undo.snapshot([str(tmp_path)], str(tmp_path / "data"), key=KEY) is None


def test_purge_removes_old_snapshots(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    root = str(tmp_path / "data")
    old = undo.snapshot([str(f)], root, key=KEY)
    new = undo.snapshot([str(f)], root, key=KEY)
    past = time.time() - 90000
    os.utime(os.path.join(root, "undo", old), (past, past))
    assert undo.purge(root) == 1
    assert not os.path.exists(os.path.join(root, "undo", old))
    assert os.path.exists(os.path.join(root, "undo", new))


def test_restore_unknown_or_malicious_id_returns_zero(tmp_path):
    root = str(tmp_path / "data")
    assert undo.restore("nope", root, key=KEY) == (0, 0)
    assert undo.restore("../../etc", root, key=KEY) == (0, 0)


def test_binary_file_returns_none(tmp_path):
    f = tmp_path / "b.bin"
    f.write_bytes(b"abc\x00def")
    assert undo.snapshot([str(f)], str(tmp_path / "data"), key=KEY) is None


def test_nul_in_path_returns_none(tmp_path):
    assert undo.snapshot(["bad\x00path"], str(tmp_path / "data"), key=KEY) is None


def test_symlink_target_returns_none(tmp_path):
    real = tmp_path / "real.txt"
    real.write_bytes(b"x")
    link = tmp_path / "link.txt"
    os.symlink(real, link)
    assert undo.snapshot([str(link)], str(tmp_path / "data"), key=KEY) is None
    dangling = tmp_path / "dangling"
    os.symlink(tmp_path / "missing", dangling)
    assert undo.snapshot([str(dangling)], str(tmp_path / "data"), key=KEY) is None


def test_discard_deletes_an_unneeded_snapshot(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"before")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    assert undo.discard(sid, root) is True
    assert not os.path.exists(os.path.join(root, "undo", sid))
    assert undo.discard(sid, root) is False
    assert undo.discard("../../etc", root) is False and undo.discard(None, root) is False
    assert f.read_bytes() == b"before"                     # the file itself is never touched


def test_partial_restore_reports_failures_and_keeps_the_snapshot(tmp_path, monkeypatch):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_bytes(b"a0")
    b.write_bytes(b"b0")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(a), str(b)], root, key=KEY)
    a.write_bytes(b"a1")
    b.write_bytes(b"b1")
    real = undo._atomic_write

    def flaky(target, data, mode):
        if target.endswith("b.txt"):
            raise OSError("read-only")
        real(target, data, mode)
    monkeypatch.setattr(undo, "_atomic_write", flaky)
    assert undo.restore(sid, root, key=KEY) == (1, 1)
    assert a.read_bytes() == b"a0" and os.path.isdir(os.path.join(root, "undo", sid))
    monkeypatch.setattr(undo, "_atomic_write", real)
    assert undo.restore(sid, root, key=KEY) == (2, 0) and b.read_bytes() == b"b0"


def test_restore_can_keep_the_snapshot_for_the_caller_to_discard(tmp_path):
    f = tmp_path / "k.txt"
    f.write_bytes(b"v1")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    f.write_bytes(b"v2")
    assert undo.restore(sid, root, keep=True, key=KEY) == (1, 0) and f.read_bytes() == b"v1"
    assert os.path.isdir(os.path.join(root, "undo", sid))
    assert undo.discard(sid, root) is True


# ---------------------------------------------------------------------------------- trust in the snapshot (C2)
def _snap(tmp_path, name="a.txt", content=b"before"):
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    f = proj / name
    f.write_bytes(content)
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)
    assert sid
    f.write_bytes(b"after")
    return f, root, os.path.join(root, "undo", sid), sid


def _manifest(d):
    import json
    with open(os.path.join(d, "manifest.json"), "rb") as fh:
        return json.loads(fh.read())


def _rewrite(d, data):
    import json
    p = os.path.join(d, "manifest.json")
    os.chmod(p, 0o600)
    with open(p, "w") as fh:
        json.dump(data, fh)


def test_a_snapshot_carries_a_mac_over_its_manifest(tmp_path):
    f, root, d, sid = _snap(tmp_path)
    assert os.path.exists(os.path.join(d, "manifest.mac"))
    m = _manifest(d)
    assert m["files"][0]["path"] == str(f) and len(m["files"][0]["sha256"]) == 64


def test_a_tampered_manifest_path_is_refused(tmp_path):
    f, root, d, sid = _snap(tmp_path)
    victim = tmp_path / "elsewhere.txt"
    victim.write_bytes(b"keep me")
    m = _manifest(d)
    m["files"][0]["path"] = str(victim)
    _rewrite(d, m)
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    assert victim.read_bytes() == b"keep me" and f.read_bytes() == b"after"


def test_an_added_manifest_entry_is_refused(tmp_path):
    f, root, d, sid = _snap(tmp_path)
    victim = tmp_path / "elsewhere.txt"
    victim.write_bytes(b"keep me")
    m = _manifest(d)
    m["files"].append({"path": str(victim), "existed": False})
    _rewrite(d, m)
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    assert victim.exists()


def test_a_tampered_blob_or_a_missing_mac_or_another_key_is_refused(tmp_path):
    f, root, d, sid = _snap(tmp_path)
    os.chmod(os.path.join(d, "0"), 0o600)
    with open(os.path.join(d, "0"), "wb") as fh:
        fh.write(b"evil")
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    f2, root2, d2, sid2 = _snap(tmp_path, name="b.txt")
    with pytest.raises(undo.Refused):
        undo.restore(sid2, root2, key=b"another key, not the one in the DB")
    os.unlink(os.path.join(d2, "manifest.mac"))
    with pytest.raises(undo.Refused):
        undo.restore(sid2, root2, key=KEY)
    with pytest.raises(undo.Refused):
        undo.restore(sid2, root2, key=None)
    assert f.read_bytes() == b"after" and f2.read_bytes() == b"after"


def test_a_target_now_a_symlink_is_refused(tmp_path):
    f, root, d, sid = _snap(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"secret")
    f.unlink()
    os.symlink(secret, f)
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    assert secret.read_bytes() == b"secret"


def test_a_parent_replaced_by_a_symlink_after_the_snapshot_is_refused(tmp_path):
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    f = proj / "sub" / "a.txt"
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root, key=KEY)            # a file the action creates
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "a.txt").write_bytes(b"not yours")
    os.rmdir(proj / "sub")
    os.symlink(elsewhere, proj / "sub")
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    assert (elsewhere / "a.txt").read_bytes() == b"not yours"


def test_a_sensitive_target_is_refused(tmp_path, monkeypatch):
    import sys
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delitem(sys.modules, "hermes_constants", raising=False)
    cfg = home / "config.yaml"
    cfg.write_bytes(b"plugins: {}\n")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(cfg)], root, key=KEY)
    cfg.write_bytes(b"changed\n")
    with pytest.raises(undo.Refused):
        undo.restore(sid, root, key=KEY)
    assert cfg.read_bytes() == b"changed\n"
