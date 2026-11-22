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
import subprocess
import tempfile
import time
import uuid

from .i18n import tr

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


# git, run by an undo or a snapshot: no hook, no file-system monitor, names taken as written, and a minimal
# environment built from scratch: nothing else from the agent's process reaches it (its API keys, GIT_DIR or
# GIT_INDEX_FILE, which would point git elsewhere).
GIT = ("git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "--literal-pathspecs")
GIT_TIMEOUT = 10
GIT_ENV_KEPT = ("PATH", "HOME") + (("SYSTEMROOT",) if os.name == "nt" else ())


def git_env() -> dict[str, str]:
    """The whole environment of the git child: PATH, HOME (SYSTEMROOT on Windows), the C locale, no prompt."""
    env = {k: os.environ[k] for k in GIT_ENV_KEPT if os.environ.get(k)}
    env.update(LANG="C", LC_ALL="C", GIT_TERMINAL_PROMPT="0")
    return env


def _git(top: str, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([*GIT, "-C", top, *args], input=data, capture_output=True, env=git_env(),
                          timeout=GIT_TIMEOUT, check=False)


def git_top(cwd: str | None) -> str | None:
    """The repository holding ``cwd`` when git keeps it plainly there (a ``.git`` folder, not a link or a file)."""
    d = os.path.realpath(cwd or ".")
    while True:
        git = os.path.join(d, ".git")
        if os.path.lexists(git):
            return d if os.path.isdir(git) and not os.path.islink(git) else None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


LS_BATCH = 400                    # paths per `git ls-files` call: never a command line too long for the system
_ITA, _SKIP, _VALID = 0x20000000, 0x40000000, 0x8000     # intent-to-add, skip-worktree, assume-unchanged


def _ls_records(out: bytes) -> list[str] | None:
    """The ``mode object stage<TAB>path`` records of ``git ls-files -s -t -v -z --debug``, or None when one cannot be
    put back as it was: skip-worktree, assume-unchanged, intent-to-add, a conflict, a name with a new line."""
    chunks = out.decode("utf-8", "surrogateescape").split("\0")
    records, cur = [], None
    for i, chunk in enumerate(chunks):
        if i == 0:
            debug, head = [], chunk
            if "\n" in head:
                return None
        else:                                        # the previous record's debug lines, then the next record
            lines = chunk.split("\n")
            debug, head = lines[:-1], lines[-1]
            flags = [ln.rsplit("flags:", 1)[1].strip() for ln in debug if "flags:" in ln]
            if cur is None or len(flags) != 1:
                return None
            try:
                if int(flags[0], 16) & (_ITA | _SKIP | _VALID):
                    return None
            except ValueError:
                return None
            records.append(cur)
            cur = None
        if head:
            tag, sp, rest = head.partition(" ")
            meta, tab, _path = rest.partition("\t")
            if tag != "H" or not sp or not tab or meta.split(" ")[-1] != "0":
                return None
            cur = rest
    return records if cur is None else None


def _git_index(paths: list[str], specs: list[str], cwd: str | None) -> dict | None:
    """The index entries a ``git rm`` or ``git mv`` changes, read before it runs: those of its files and of the paths
    it gives git (a folder's entries without a file on disk included): {"top", "paths" (from the top), "index"}.
    None when they cannot be read or put back as they are (a worktree or a submodule, a flag, an intent-to-add)."""
    top = git_top(cwd)
    if not top:
        return None

    def rel(p: str) -> str | None:
        r = os.path.relpath(os.path.realpath(p), top)
        if r == ".." or r.startswith(".." + os.sep) or os.path.isabs(r) or any(ord(c) < 32 for c in r):
            return None
        return r.replace(os.sep, "/")

    rels, asked = [rel(p) for p in paths], [rel(p) for p in specs]
    if None in rels or None in asked:
        return None
    asked = list(dict.fromkeys(asked + rels))
    records: list[str] = []
    try:
        for i in range(0, len(asked), LS_BATCH):
            r = _git(top, "--no-optional-locks", "ls-files", "-s", "-t", "-v", "-z", "--debug", "--",
                     *asked[i:i + LS_BATCH])
            got = _ls_records(r.stdout) if r.returncode == 0 else None
            if got is None:
                return None
            records += got
    except (OSError, subprocess.SubprocessError):
        return None
    return {"top": top, "paths": rels, "index": list(dict.fromkeys(records))}


def snapshot(paths: list[str], root: str, max_bytes: int = 5_000_000, *, key: bytes | None, cwd: str | None = None,
             home: str | None = None, git: list[str] | None = None, git_specs: list[str] | None = None) -> str | None:
    """Save paths; return the snapshot id, or None if it cannot be done safely (no ``key`` included: a snapshot
    without its MAC could never be restored). ``cwd`` and ``home``: the session's working directory and user home,
    signed with the manifest, so a restore judges its targets as classify judged the write. ``git``: the paths a
    ``git rm`` or ``git mv`` of the call changes in git's index (``git_specs``: the paths it gives git); their entries
    are signed with the manifest too, so ``restore_index`` can put them back. No snapshot when they cannot be read:
    an undo that would leave the index changed is never promised."""
    if not key:
        return None
    index = _git_index(git, list(git_specs or []), cwd) if git else None
    if git and index is None:
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
        extra = {"git": index} if index else {}
        manifest = json.dumps({"files": entries, "cwd": cwd, "home": home, **extra}).encode("utf-8")
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
        raise Refused(tr("undo.refused.no_mac"))
    if not key or not hmac.compare_digest(mac, _mac(key, snap_id, manifest)):
        raise Refused(tr("undo.refused.changed"))
    try:
        data = json.loads(manifest)
        files, cwd, home = data["files"], data.get("cwd"), data.get("home")
        if not all(v is None or isinstance(v, str) for v in (cwd, home)):
            raise TypeError("cwd")
        blobs = []
        for i, e in enumerate(files):
            path = e["path"]
            if not isinstance(path, str) or not os.path.isabs(path) or "\x00" in path:
                raise Refused(tr("undo.refused.not_absolute"))
            if e["existed"]:
                with open(os.path.join(d, str(i)), "rb") as fh:
                    data = fh.read()
                if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), e["sha256"]):
                    raise Refused(tr("undo.refused.file_changed"))
                blobs.append(data)
            else:
                blobs.append(None)
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused(tr("undo.refused.manifest", error=type(exc).__name__))
    from . import classify
    for e in files:
        path = e["path"]
        if os.path.islink(path):
            raise Refused(tr("undo.refused.symlink"))
        if _parent(path) != e["parent"]:
            raise Refused(tr("undo.refused.folder"))
        if classify.sensitive_path(path, cwd, home):
            raise Refused(tr("undo.refused.protected"))
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


def restore_index(snap_id: str, root: str, *, key: bytes | None) -> str | None:
    """After ``restore``: put git's index entries of the snapshot's ``git rm`` and ``git mv`` paths back as they were
    (an entry that was there comes back, one that was not is taken out), so ``git status`` shows the state before the
    call. None when done or when the snapshot holds no git entries; else why it failed, in a few words (the files
    stay restored)."""
    if not isinstance(snap_id, str) or not _ID_RE.match(snap_id):
        return None
    d = os.path.join(_undo_dir(root), snap_id)
    try:
        with open(os.path.join(d, "manifest.json"), "rb") as fh:
            manifest = fh.read()
        with open(os.path.join(d, MAC_FILE), "rb") as fh:
            mac = fh.read().decode("ascii", "replace").strip()
    except OSError:
        return "snapshot gone"
    if not key or not hmac.compare_digest(mac, _mac(key, snap_id, manifest)):
        return "snapshot changed"
    try:
        rec = json.loads(manifest).get("git")
        if not rec:
            return None
        top, rels, records = rec.get("top"), list(rec.get("paths") or []), list(rec.get("index") or [])
    except (ValueError, TypeError, AttributeError):
        return "unreadable"
    if not top or git_top(top) != top:
        return "not a plain git repository"
    known, lines = set(), []
    for r in records:
        if not isinstance(r, str) or "\t" not in r:
            return "unreadable"
        known.add(r.split("\t", 1)[1])
        lines.append(r)
    try:
        if any(p not in known for p in rels):          # a path git did not hold: taken out, with a zero object id
            size = len(records[0].split(" ")[1]) if records else (
                64 if _git(top, "rev-parse", "--show-object-format").stdout.strip() == b"sha256" else 40)
            lines += [f"0 {'0' * size}\t{p}" for p in rels if p not in known]
        r = _git(top, "update-index", "-z", "--index-info",
                 data=b"".join(x.encode("utf-8", "surrogateescape") + b"\0" for x in lines))
    except (OSError, subprocess.SubprocessError) as exc:
        return type(exc).__name__
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").replace(top.rstrip("/") + "/", "").strip().splitlines()
        first = err[0] if err else f"exit {r.returncode}"
        return (first[len("fatal: "):] if first.startswith("fatal: ") else first)[:160]
    return None


def exists(snap_id: str | None, root: str) -> bool:
    """The snapshot is still there (not purged, not discarded)."""
    return (isinstance(snap_id, str) and bool(_ID_RE.match(snap_id))
            and os.path.isfile(os.path.join(_undo_dir(root), snap_id, "manifest.json")))


def unchanged(snap_id: str, root: str, *, key: bytes | None) -> bool:
    """Every file of the snapshot is still as it was saved (a saved file with the same bytes, a new one still
    absent): the call changed nothing. False when the snapshot cannot be read. Raises Refused like ``restore``."""
    if not isinstance(snap_id, str) or not _ID_RE.match(snap_id):
        return False
    try:
        files, _ = _checked(os.path.join(_undo_dir(root), snap_id), snap_id, key)
    except OSError:
        return False
    for e in files:
        path = e["path"]
        if not e["existed"]:
            if os.path.lexists(path):
                return False
            continue
        try:
            with open(path, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != e["sha256"]:
                    return False
        except OSError:
            return False
    return True


def describe(snap_id: str | None, root: str) -> dict:
    """What an undo would restore, said for the owner of this machine: the first file, relative to the folder the
    agent worked in, how many files in all, and how many of them existed before the call. Read from the snapshot's
    manifest; {} when it is unreadable."""
    try:
        if not snap_id or not snap_id.isalnum():
            return {}
        with open(os.path.join(_undo_dir(root), snap_id, "manifest.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        files = [f["path"] for f in m.get("files", []) if isinstance(f, dict) and isinstance(f.get("path"), str)]
        existed = sum(1 for f in m.get("files", []) if isinstance(f, dict) and f.get("existed"))
        if not files:
            return {}
        cwd = m.get("cwd") or ""
        f0, base = files[0].replace("\\", "/"), cwd.replace("\\", "/").rstrip("/")
        first = (f0[len(base) + 1:] if base and f0.startswith(base + "/") else f0.rsplit("/", 1)[-1])
        return {"file": first, "files": len(files), "existed": existed}
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
