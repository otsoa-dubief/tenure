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
SED = ("sed -i '' " if sys.platform == "darwin" else "sed -i ") + "'s/old/new/' src/app.py"

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


def session(early_web: bool = False) -> list:
    """The session; early_web moves the web page from the end to the fourth call."""
    if not early_web:
        return list(SESSION)
    web = [c for c in SESSION if c[1].get("command", "").startswith("curl")]
    rest = [c for c in SESSION if c not in web]
    return rest[:3] + web + rest[3:]


def replay(start: str, early_web: bool = False, answer: str = "once") -> list[dict]:
    """One row per call: the call, whether tenure asked, whether Hermes alone would ask (None: unknown). answer: what
    the owner picks when tenure asks ("once", or "session" for "Allow for this session")."""
    detect = _hermes_detect()
    old = os.environ.get("HERMES_HOME")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HERMES_HOME"] = os.path.join(tmp, "hermes")
        os.environ.pop("HERMES_YOLO_MODE", None)
        try:
            mod = importlib.reload(importlib.import_module(PKG))
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            ctx = FakeCtx({"start": start}, cwd=project)
            mod.register(ctx)
            mod.ST.rng = Picks()
            mod.pre_api_request(model="model-a", provider="nous", session_id="s1")
            rows = []
            for tool, args in session(early_web):
                before = len(ctx.prompts)
                ctx.call(tool, args, answer=answer)
                cmd = args.get("command") if tool == "terminal" else None
                rows.append({"tool": tool, "what": cmd or args.get("path"), "tenure": len(ctx.prompts) > before,
                             "hermes": (detect(cmd) if cmd and detect else False if not cmd else None)})
            return rows
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


def count_asks(start: str) -> tuple[int, int | None]:
    """(questions tenure adds on calls Hermes alone would not ask about, questions Hermes asks by itself)."""
    rows = replay(start)
    hermes = None if any(r["hermes"] is None for r in rows) else sum(bool(r["hermes"]) for r in rows)
    return sum(r["tenure"] and not r["hermes"] for r in rows), hermes
