"""Snapshots for actions taken at the middle tier ("act then notify").

A snapshot saves each target file's bytes (or the fact that it did not exist)
under ``<root>/undo/<id>/``. The manifest, which holds absolute paths, lives only
there (0600, directory 0700). Paths are never logged.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _undo_dir(root: str) -> str:
    return os.path.join(root, "undo")


def snapshot(paths: list[str], root: str, max_bytes: int = 5_000_000) -> str | None:
    """Save paths; return the snapshot id, or None if it cannot be done safely."""
    entries = []
    blobs: list[bytes | None] = []
    total = 0
    try:
        for p in paths:
            ap = os.path.abspath(p)
            if "\x00" in ap:
                return None
            if os.path.islink(ap):
                return None
            if os.path.lexists(ap):
                if not os.path.isfile(ap):
                    return None
                size = os.stat(ap).st_size
                total += size
                if total > max_bytes:
                    return None
                with open(ap, "rb") as fh:
                    data = fh.read(max_bytes + 1)
                if len(data) != size and len(data) > max_bytes:
                    return None
                if b"\x00" in data[:8192]:
                    return None
                mode = os.stat(ap).st_mode & 0o777
                entries.append({"path": ap, "existed": True, "mode": mode})
                blobs.append(data)
            else:
                entries.append({"path": ap, "existed": False})
                blobs.append(None)
    except (OSError, ValueError, TypeError, MemoryError):
        return None

    snap_id = uuid.uuid4().hex
    base = _undo_dir(root)
    d = os.path.join(base, snap_id)
    try:
        os.makedirs(base, mode=0o700, exist_ok=True)
        os.mkdir(d, 0o700)
        os.chmod(d, 0o700)
        for i, data in enumerate(blobs):
            if data is not None:
                _write_private(os.path.join(d, str(i)), data)
        _write_private(
            os.path.join(d, "manifest.json"),
            json.dumps({"files": entries}).encode("utf-8"),
        )
    except OSError:
        shutil.rmtree(d, ignore_errors=True)
        return None
    return snap_id


def _write_private(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _atomic_write(target: str, data: bytes, mode: int) -> None:
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".clearance-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def restore(snap_id: str, root: str, keep: bool = False) -> tuple[int, int]:
    """Put files back (delete those that did not exist). Return (files restored, files that failed). A snapshot that
    cannot be read gives (0, 0); one with failures is kept, so the restore can be retried. With ``keep``, a complete
    restore keeps the snapshot too: the caller discards it once its own transaction has committed."""
    if not isinstance(snap_id, str) or not _ID_RE.match(snap_id):
        return 0, 0
    d = os.path.join(_undo_dir(root), snap_id)
    try:
        with open(os.path.join(d, "manifest.json"), "rb") as fh:
            files = json.loads(fh.read())["files"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0, 0
    count = failed = 0
    for i, e in enumerate(files):
        try:
            if e["existed"]:
                with open(os.path.join(d, str(i)), "rb") as fh:
                    data = fh.read()
                _atomic_write(e["path"], data, e.get("mode", 0o600))
            else:
                try:
                    os.unlink(e["path"])
                except FileNotFoundError:
                    pass
            count += 1
        except (OSError, KeyError, TypeError):
            failed += 1
    if not failed and not keep:
        shutil.rmtree(d, ignore_errors=True)
    return count, failed


def discard(snap_id: str, root: str) -> bool:
    """Delete a snapshot that will not be used (the action asked instead). The saved files are not touched. Return
    True when there was one."""
    if not isinstance(snap_id, str) or not _ID_RE.match(snap_id):
        return False
    d = os.path.join(_undo_dir(root), snap_id)
    if os.path.islink(d) or not os.path.isdir(d):
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


def purge(root: str, older_than: float = 86400) -> int:
    """Delete snapshots older than ``older_than`` seconds. Return how many."""
    base = _undo_dir(root)
    try:
        names = os.listdir(base)
    except OSError:
        return 0
    cutoff = time.time() - older_than
    n = 0
    for name in names:
        d = os.path.join(base, name)
        try:
            if os.path.isdir(d) and os.stat(d).st_mtime < cutoff:
                shutil.rmtree(d)
                n += 1
        except OSError:
            continue
    return n
