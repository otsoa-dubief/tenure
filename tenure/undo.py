"""Snapshots for actions taken at the middle tier ("act then notify").

A snapshot saves each target file's bytes (or the fact that it did not exist)
under ``<root>/undo/<id>/``. The manifest, which holds absolute paths, lives only
there (0600, directory 0700). Paths are never logged.

A restore trusts nothing it finds on disk. The manifest records, per file, its
path, the sha256 of the saved bytes and the resolved folder it sat in; an
HMAC-SHA256 over the snapshot id and the manifest (``manifest.mac``), keyed by a
secret kept in the tenure database, is written at snapshot time and checked
before anything is restored. A restore is refused whole (``Refused``) when the
MAC or a saved file does not match, when a target is now a symlink or sits in a
folder that now resolves elsewhere, or when classify caps the target as a write
(a sensitive file, a Hermes home, tenure's own data).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import tempfile
import time
import uuid

_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAC_FILE = "manifest.mac"


class Refused(Exception):
    """A restore that would write something the snapshot did not record, or somewhere it must not: nothing done."""


def _mac(key: bytes, snap_id: str, manifest: bytes) -> str:
    return hmac.new(key, snap_id.encode("ascii") + b"\0" + manifest, hashlib.sha256).hexdigest()


def _parent(path: str) -> str:
    return os.path.realpath(os.path.dirname(path))


def _undo_dir(root: str) -> str:
    return os.path.join(root, "undo")


def snapshot(paths: list[str], root: str, max_bytes: int = 5_000_000, *, key: bytes | None, cwd: str | None = None,
             home: str | None = None) -> str | None:
    """Save paths; return the snapshot id, or None if it cannot be done safely (no ``key`` included: a snapshot
    without its MAC could never be restored). ``cwd`` and ``home``: the session's working directory and user home,
    signed with the manifest, so a restore judges its targets as classify judged the write."""
    if not key:
        return None
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
                entries.append({"path": ap, "existed": True, "mode": mode, "parent": _parent(ap),
                                "sha256": hashlib.sha256(data).hexdigest()})
                blobs.append(data)
            else:
                entries.append({"path": ap, "existed": False, "parent": _parent(ap)})
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
        manifest = json.dumps({"files": entries, "cwd": cwd, "home": home}).encode("utf-8")
        _write_private(os.path.join(d, "manifest.json"), manifest)
        _write_private(os.path.join(d, MAC_FILE), _mac(key, snap_id, manifest).encode("ascii"))
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
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tenure-")
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


def _checked(d: str, snap_id: str, key: bytes | None) -> tuple[list[dict], list[bytes | None]]:
    """The manifest's entries and saved bytes, once the MAC, every saved file and every target check out; else
    Refused. OSError when the snapshot is gone."""
    with open(os.path.join(d, "manifest.json"), "rb") as fh:
        manifest = fh.read()
    try:
        with open(os.path.join(d, MAC_FILE), "rb") as fh:
            mac = fh.read().decode("ascii", "replace").strip()
    except FileNotFoundError:
        raise Refused("the snapshot has no MAC")
    if not key or not hmac.compare_digest(mac, _mac(key, snap_id, manifest)):
        raise Refused("the snapshot was changed after it was taken")
    try:
        data = json.loads(manifest)
        files, cwd, home = data["files"], data.get("cwd"), data.get("home")
        if not all(v is None or isinstance(v, str) for v in (cwd, home)):
            raise TypeError("cwd")
        blobs = []
        for i, e in enumerate(files):
            path = e["path"]
            if not isinstance(path, str) or not os.path.isabs(path) or "\x00" in path:
                raise Refused("a recorded path is not absolute")
            if e["existed"]:
                with open(os.path.join(d, str(i)), "rb") as fh:
                    data = fh.read()
                if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), e["sha256"]):
                    raise Refused("a saved file was changed after the snapshot")
                blobs.append(data)
            else:
                blobs.append(None)
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused(f"the manifest cannot be read ({type(exc).__name__})")
    from . import classify
    for e in files:
        path = e["path"]
        if os.path.islink(path):
            raise Refused("a target is now a symlink")
        if _parent(path) != e["parent"]:
            raise Refused("a target's folder now resolves elsewhere (a symlink was put on its path)")
        if classify.sensitive_path(path, cwd, home):
            raise Refused("a target is a protected file")
    return files, blobs


def restore(snap_id: str, root: str, keep: bool = False, *, key: bytes | None) -> tuple[int, int]:
    """Put files back (delete those that did not exist). Return (files restored, files that failed). A snapshot that
    cannot be read gives (0, 0); one with failures is kept, so the restore can be retried. With ``keep``, a complete
    restore keeps the snapshot too: the caller discards it once its own transaction has committed. Raises Refused,
    before writing anything, when the snapshot or a target cannot be trusted (see the module's docstring)."""
    if not isinstance(snap_id, str) or not _ID_RE.match(snap_id):
        return 0, 0
    d = os.path.join(_undo_dir(root), snap_id)
    try:
        files, blobs = _checked(d, snap_id, key)
    except OSError:
        return 0, 0
    count = failed = 0
    for i, e in enumerate(files):
        try:
            if e["existed"]:
                data = blobs[i]
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


def describe(snap_id: str | None, root: str) -> dict:
    """What an undo would restore, said for the owner of this machine: the first file, relative to the folder the
    agent worked in, and how many files in all. Read from the snapshot's manifest; {} when it is unreadable."""
    try:
        if not snap_id or not snap_id.isalnum():
            return {}
        with open(os.path.join(_undo_dir(root), snap_id, "manifest.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        files = [f["path"] for f in m.get("files", []) if isinstance(f, dict) and isinstance(f.get("path"), str)]
        if not files:
            return {}
        cwd = m.get("cwd") or ""
        first = (os.path.relpath(files[0], cwd) if cwd and files[0].startswith(cwd.rstrip("/") + "/")
                 else os.path.basename(files[0]))
        return {"file": first, "files": len(files)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


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
