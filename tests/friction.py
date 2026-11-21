"""The friction bench: one ordinary coding session (about thirty calls), replayed through the plugin in a throwaway
HERMES_HOME with a scripted owner who allows everything once. It counts the questions tenure adds, apart from the ones
Hermes asks by itself (its own dangerous-command check, when Hermes' source is importable)."""
import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from test_plugin import PKG, FakeCtx, Picks  # noqa: E402

# The in-place edit as each system's sed spells it (BSD sed on macOS takes the suffix as the next word).
SED_I = "sed -i '' " if sys.platform == "darwin" else "sed -i "
SED = SED_I + "'s/old/new/' src/app.py"

SESSION = [
    ("write_file", {"path": "src/app.py", "content": "old = 1\n"}),
    ("write_file", {"path": "src/util.py", "content": "def f():\n    return 1\n"}),
    ("write_file", {"path": "tests/test_app.py", "content": "def test_x():\n    assert True\n"}),
    ("terminal", {"command": "npm install"}),
    ("terminal", {"command": "npm test"}),
    ("write_file", {"path": "src/app.py", "content": "old = 2\n"}),
    ("terminal", {"command": "pytest -q"}),
    ("terminal", {"command": "git status"}),
    ("terminal", {"command": "git add -A"}),
    ("terminal", {"command": 'git commit -m "first version"'}),
    ("write_file", {"path": "notes.txt", "content": "todo\n"}),
    ("terminal", {"command": "rm notes.txt"}),
    ("terminal", {"command": "mv src/util.py src/helpers.py"}),
    ("terminal", {"command": SED}),
    ("terminal", {"command": "echo 'node_modules/' >> .gitignore"}),
    ("terminal", {"command": "cp src/app.py src/app_backup.py"}),
    ("terminal", {"command": "touch src/__init__.py"}),
    ("terminal", {"command": "python -c 'import sys; print(sys.version)'"}),
    ("terminal", {"command": "rm -rf build"}),
    ("terminal", {"command": "ls -la"}),
    ("terminal", {"command": "cat src/app.py"}),
    ("terminal", {"command": "mkdir -p docs"}),
    ("write_file", {"path": "docs/usage.md", "content": "# Usage\n"}),
    ("terminal", {"command": "npm run build"}),
    ("terminal", {"command": "python -m pytest tests"}),
    ("terminal", {"command": "rm *.log"}),
    ("terminal", {"command": "git diff"}),
    ("terminal", {"command": "git push origin main"}),
    ("terminal", {"command": "curl https://example.com/docs"}),
    ("terminal", {"command": "npm test"}),
]


# Chained lines as a real agent (Sonnet in Hermes) wrote them, on a project whose files exist, so each undo really
# saves what the line deletes or moves (the bench runs no command: the files stay for the next line).
CHAIN_FILES = {"build/out.txt": "built\n", "build/sub/more.txt": "more\n", "app.log": "app\n", "debug.log": "debug\n",
               "tmp/scratch.txt": "scratch\n", "notes.bak": "notes\n", "inventory/__init__.py": "",
               "inventory/textutil.py": "def shout(s):\n    return s.upper()\n",
               "inventory/report.py": "from inventory.textutil import shout\n",
               "tests/test_inventory.py": "def test_ok():\n    assert True\n", "cache.pyc": "x\n",
               "dist/bundle.js": "x\n", "package.json": '{"scripts": {"build": "true"}}\n'}
CHAINS = [
    ("terminal", {"command": "git status && git diff --stat"}),
    ("terminal", {"command": "git rm -rq build app.log debug.log && rm -rf build && git mv inventory/textutil.py "
                             "inventory/text.py && " + SED_I + "'s/textutil/text/g' inventory/report.py"}),
    ("terminal", {"command": "rm -rf tmp notes.bak && python3 -m unittest discover -s tests -v 2>&1 | tail -40"}),
    ("terminal", {"command": "rm -f *.pyc && python -m pytest -q"}),
    ("terminal", {"command": "rm -rf dist && npm run build"}),
    ("terminal", {"command": 'git add -A && git commit -m "rename textutil to text"'}),
    ("terminal", {"command": "rm notes.bak && git push origin main"}),
    ("terminal", {"command": "rm -rf tmp && curl -s https://example.com/api"}),
]


def _hermes_detect():
    """Hermes' own dangerous-command check (installed Hermes, or its source in HERMES_AGENT_DIR); None if missing."""
    src = os.environ.get("HERMES_AGENT_DIR")
    if src and src not in sys.path:
        sys.path.append(src)
    try:
        from tools.approval_detection import detect_dangerous_command
    except Exception:
        return None
    return lambda cmd: bool(detect_dangerous_command(cmd)[0])


def session(early_web: bool = False, chains: bool = False) -> list:
    """The session; early_web moves the web page from the end to the fourth call (chains: a web page second)."""
    if chains:
        web = [("terminal", {"command": "curl https://example.com/docs"})] if early_web else []
        return CHAINS[:1] + web + CHAINS[1:]
    if not early_web:
        return list(SESSION)
    web = [c for c in SESSION if c[1].get("command", "").startswith("curl")]
    rest = [c for c in SESSION if c not in web]
    return rest[:3] + web + rest[3:]


def replay(start: str, early_web: bool = False, answer: str = "once", after_fault: str = "",
           mode: str = "study", chains: bool = False) -> list[dict]:
    """One row per call: the call, whether tenure asked, whether Hermes alone would ask (None: unknown), whether it
    was a watched action listed at the end of its turn (simple mode). answer: what the owner picks when tenure asks
    ("once", or "session" for "Allow for this session"). after_fault: before the session, one file write is undone
    ("undone": a fault on file:write), then excused ("excused"). mode: "study" (the start applies) or "simple" (every
    call is its own turn). chains: the chained lines of a real run (``CHAINS``), on a project holding their files."""
    detect = _hermes_detect()
    old = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HERMES_HOME"] = os.path.join(tmp, "hermes")
        os.environ.pop("HERMES_YOLO_MODE", None)
        try:
            mod = importlib.reload(importlib.import_module(PKG))
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            for name, text in (CHAIN_FILES.items() if chains else ()):
                path = os.path.join(project, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            if chains:                                   # a repository: git rm and git mv save its index too
                import subprocess
                for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "start"]):
                    subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@example.com", *cmd],
                                   cwd=project, check=True, capture_output=True)
            ctx = FakeCtx({"start": start, "mode": mode}, cwd=project)
            mod.register(ctx)
            mod.ST.rng = Picks()
            mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
            if after_fault:
                ctx.call("write_file", {"path": "src/draft.py", "content": "x = 0\n"}, session="s0")
                last = mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]   # the write's undo
                out = mod.cli.slash(f"undo {last}")
                if after_fault == "excused":
                    import re
                    mod.cli.slash("excuse " + re.search(r"excuse (\d+)", out).group(1))
            rows, last_undo = [], None
            for tool, args in session(early_web, chains):
                before, said = len(ctx.prompts), len(ctx.posted)
                ctx.call(tool, args, answer=answer)
                mod.post_llm_call(session_id="s1")             # the turn ends: simple mode lists what it watched
                cmd = args.get("command") if tool == "terminal" else None
                undo = mod.store_().db.execute("SELECT MAX(id) FROM undo").fetchone()[0]
                rows.append({"tool": tool, "what": cmd or args.get("path"), "tenure": len(ctx.prompts) > before,
                             "undo": undo is not None and undo != last_undo,
                             "hermes": (detect(cmd) if cmd and detect else False if not cmd else None),
                             "watched": any("watched action" in str(x) for x in ctx.posted[said:])})
                last_undo = undo
            return rows
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


def count_asks(start: str, mode: str = "study") -> tuple[int, int | None]:
    """(questions tenure adds on calls Hermes alone would not ask about, questions Hermes asks by itself)."""
    rows = replay(start, mode=mode)
    hermes = None if any(r["hermes"] is None for r in rows) else sum(bool(r["hermes"]) for r in rows)
    return sum(r["tenure"] and not r["hermes"] for r in rows), hermes
