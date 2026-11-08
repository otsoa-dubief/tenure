import os
import stat
import time

import pytest

from clearance import undo


def test_snapshot_then_restore_puts_content_back(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"before")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
    assert sid
    f.write_bytes(b"after")
    assert undo.restore(sid, root) == (1, 0)
    assert f.read_bytes() == b"before"
    d = os.path.join(root, "undo", sid)
    assert not os.path.exists(d)


def test_snapshot_dir_and_manifest_modes(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
    d = os.path.join(root, "undo", sid)
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(os.path.join(d, "manifest.json")).st_mode) == 0o600


def test_restore_deletes_a_file_that_did_not_exist(tmp_path):
    f = tmp_path / "new.txt"
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
    assert sid
    f.write_bytes(b"created by agent")
    assert undo.restore(sid, root) == (1, 0)
    assert not f.exists()


def test_snapshot_over_cap_returns_none(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 100)
    root = str(tmp_path / "data")
    assert undo.snapshot([str(f)], root, max_bytes=50) is None
    assert not os.path.isdir(os.path.join(root, "undo")) or not os.listdir(os.path.join(root, "undo"))


def test_unreadable_file_returns_none(tmp_path):
    f = tmp_path / "secret.txt"
    f.write_bytes(b"x")
    os.chmod(f, 0)
    try:
        if os.access(f, os.R_OK):
            pytest.skip("running as root: cannot simulate")
        root = str(tmp_path / "data")
        assert undo.snapshot([str(f)], root) is None
    finally:
        os.chmod(f, 0o600)


def test_directory_target_returns_none(tmp_path):
    assert undo.snapshot([str(tmp_path)], str(tmp_path / "data")) is None


def test_purge_removes_old_snapshots(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    root = str(tmp_path / "data")
    old = undo.snapshot([str(f)], root)
    new = undo.snapshot([str(f)], root)
    past = time.time() - 90000
    os.utime(os.path.join(root, "undo", old), (past, past))
    assert undo.purge(root) == 1
    assert not os.path.exists(os.path.join(root, "undo", old))
    assert os.path.exists(os.path.join(root, "undo", new))


def test_restore_unknown_or_malicious_id_returns_zero(tmp_path):
    root = str(tmp_path / "data")
    assert undo.restore("nope", root) == (0, 0)
    assert undo.restore("../../etc", root) == (0, 0)


def test_binary_file_returns_none(tmp_path):
    f = tmp_path / "b.bin"
    f.write_bytes(b"abc\x00def")
    assert undo.snapshot([str(f)], str(tmp_path / "data")) is None


def test_nul_in_path_returns_none(tmp_path):
    assert undo.snapshot(["bad\x00path"], str(tmp_path / "data")) is None


def test_symlink_target_returns_none(tmp_path):
    real = tmp_path / "real.txt"
    real.write_bytes(b"x")
    link = tmp_path / "link.txt"
    os.symlink(real, link)
    assert undo.snapshot([str(link)], str(tmp_path / "data")) is None
    dangling = tmp_path / "dangling"
    os.symlink(tmp_path / "missing", dangling)
    assert undo.snapshot([str(dangling)], str(tmp_path / "data")) is None


def test_discard_deletes_an_unneeded_snapshot(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"before")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
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
    sid = undo.snapshot([str(a), str(b)], root)
    a.write_bytes(b"a1")
    b.write_bytes(b"b1")
    real = undo._atomic_write

    def flaky(target, data, mode):
        if target.endswith("b.txt"):
            raise OSError("read-only")
        real(target, data, mode)
    monkeypatch.setattr(undo, "_atomic_write", flaky)
    assert undo.restore(sid, root) == (1, 1)
    assert a.read_bytes() == b"a0" and os.path.isdir(os.path.join(root, "undo", sid))
    monkeypatch.setattr(undo, "_atomic_write", real)
    assert undo.restore(sid, root) == (2, 0) and b.read_bytes() == b"b0"


def test_restore_can_keep_the_snapshot_for_the_caller_to_discard(tmp_path):
    f = tmp_path / "k.txt"
    f.write_bytes(b"v1")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
    f.write_bytes(b"v2")
    assert undo.restore(sid, root, keep=True) == (1, 0) and f.read_bytes() == b"v1"
    assert os.path.isdir(os.path.join(root, "undo", sid))
    assert undo.discard(sid, root) is True
