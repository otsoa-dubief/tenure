import os
import stat
import time

from clearance import undo


def test_snapshot_then_restore_puts_content_back(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"before")
    root = str(tmp_path / "data")
    sid = undo.snapshot([str(f)], root)
    assert sid
    f.write_bytes(b"after")
    assert undo.restore(sid, root) == 1
    assert f.read_bytes() == b"before"
    d = os.path.join(root, "undo", sid)
    assert not os.path.exists(d) or stat.S_IMODE(os.stat(d).st_mode) == 0o700


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
    assert undo.restore(sid, root) == 1
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
            return  # running as root: cannot simulate
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
    assert undo.restore("nope", root) == 0
    assert undo.restore("../../etc", root) == 0
