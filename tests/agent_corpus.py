"""A corpus of terminal lines as coding agents write them (Claude Code, Codex, Hermes, Cursor) in ordinary dev work,
each with what simple mode should do under the rule decided: free what stays on the machine and only reads, can be
undone, or is a covered program; a question for what leaves the machine, what cannot be undone, a new dependency,
or a script the agent wrote. Not necessarily what the code does today: tests/test_agent_corpus.py plays each line
in a project holding its files and compares (a known gap is an xfail with its reason).

Expected outcomes:
- ``free``: runs without asking, nothing to save;
- ``free+undo``: runs without asking, its files saved first;
- ``asks:<why>``: tenure asks, why being ``outside`` (it leaves the machine), ``no-undo`` (what it changes cannot be
  saved), ``dependency`` (a new package from a registry) or ``script`` (code the agent wrote, run now);
- ``hermes-asks``: Hermes' own dangerous-command check asks by itself (recursive rm, inline code, discarding work).
"""
import sys

# The in-place edit as each system's sed spells it (BSD sed on macOS takes the suffix as the next word).
SED_I = "sed -i '' " if sys.platform == "darwin" else "sed -i "

# The project every line is played in, fresh for each line: what the lines name exists (a git repository).
FILES = {
    ".gitignore": "node_modules/\n__pycache__/\n",
    "README.md": "# demo\n\nRun `make test`.\n",
    "package.json": '{"name": "demo", "scripts": {"test": "node -e 0", "build": "node -e 0"}, '
                    '"devDependencies": {"left-pad": "1.3.0"}}\n',
    "package-lock.json": '{"name": "demo", "lockfileVersion": 3, "packages": {}}\n',
    "requirements.txt": "requests==2.32.3\n",
    "pyproject.toml": '[project]\nname = "demo"\nversion = "0.1.0"\n',
    "uv.lock": "version = 1\n",
    "Cargo.toml": '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n',
    "go.mod": "module example.com/demo\n\ngo 1.22\n",
    "Makefile": "test:\n\tpytest -q\n\nclean:\n\trm -rf build\n",
    "src/app.py": "old_name = 1\n\n\ndef main():\n    return old_name  # TODO\n",
    "src/old.py": "def old():\n    return 0\n",
    "src/util.py": "import os\n",
    "src/__pycache__/app.cpython-312.pyc": "x\n",
    "app.pyc": "x\n",
    "util.pyc": "x\n",
    "tests/test_app.py": "from src.app import main\n\n\ndef test_main():\n    assert main() == 1\n",
    "node_modules/left-pad/index.js": "module.exports = 1\n",
    "dist/bundle.js": "x\n",
    "build/out.txt": "built\n",
    "app.log": "started\n",
    "debug.log": "debug\n",
    "notes.tmp": "scratch\n",
    "frontend/package.json": '{"name": "front", "scripts": {"test": "node -e 0", "build": "node -e 0"}}\n',
    "frontend/node_modules/react/index.js": "module.exports = 1\n",
    ".venv/bin/activate": "export VIRTUAL_ENV=.venv\n",
}

# Files the agent wrote (write_file) just before a line: the line then runs code it wrote.
WROTE = {
    "python scripts/migrate.py": {"scripts/migrate.py": "print('migrate')\n"},
    "node scripts/gen.js 2>&1 | tail -5": {"scripts/gen.js": "console.log(1)\n"},
}

# (family, line, expected)
CORPUS = [
    # ------------------------------------------------------------------------------------------------- tests
    ("tests", "pytest -q", "free"),
    ("tests", "python -m pytest -q 2>&1 | tail -20", "free"),
    ("tests", "pytest tests/test_app.py -x -q 2>&1 | tail -30", "free"),
    ("tests", "npm test -- --watch=false 2>&1 | tail -40", "free"),
    ("tests", "cargo test 2>&1 | head -50", "free"),
    ("tests", "go test ./...", "free"),
    ("tests", "pytest -q; echo $?", "free"),
    ("tests", "npm run build 2>&1 | tail -20", "free"),
    # ------------------------------------------------------------------------------------------------- reads
    ("reads", "ls -la", "free"),
    ("reads", "find . -name '*.py' -not -path './node_modules/*' | head -20", "free"),
    ("reads", 'grep -rn "def main" src/', "free"),
    ("reads", "grep -rn TODO --include='*.py' .", "free"),
    ("reads", "cat src/app.py", "free"),
    ("reads", "sed -n '1,80p' src/app.py", "free"),
    ("reads", "head -50 README.md", "free"),
    ("reads", "wc -l src/*.py", "free"),
    ("reads", "git log --oneline -5", "free"),
    ("reads", "git diff", "free"),
    ("reads", "git status --short && git log --oneline -3", "free"),
    ("reads", "find . -name '*.py' | xargs wc -l", "free"),
    ("reads", "find . -name '*.py' -exec grep -l TODO {} +", "free"),
    # ------------------------------------------------------------------------------------------------- edits
    ("edits", SED_I + "'s/old_name/new_name/g' src/app.py", "free+undo"),
    ("edits", SED_I + "-e 's/old_name/new_name/' -e 's/TODO/DONE/' src/app.py", "free+undo"),
    ("edits", SED_I + "'s/old_name/new_name/g' src/*.py", "free+undo"),
    ("edits", "perl -pi -e 's/old_name/new_name/g' src/app.py", "hermes-asks"),
    ("edits", "mv src/old.py src/new.py", "free+undo"),
    ("edits", "cp src/app.py src/app.bak", "free+undo"),
    ("edits", "mkdir -p src/utils", "free"),
    ("edits", "touch src/__init__.py", "free+undo"),
    ("edits", "cat > src/config.py <<'EOF'\nDEBUG = True\nEOF", "free+undo"),
    ("edits", "mkdir -p tests/unit && cat > tests/unit/test_x.py <<'EOF'\ndef test_x():\n    assert True\nEOF", "free"),
    ("edits", "echo 'dist/' >> .gitignore", "free+undo"),
    ("edits", "printf 'x = 1\\n' > src/x.py", "free+undo"),
    # --------------------------------------------------------------------------------------------- deletions
    ("deletions", "rm -rf node_modules dist", "hermes-asks"),
    ("deletions", "rm -f *.pyc", "free+undo"),
    ("deletions", "rm -f app.log debug.log", "free+undo"),
    ("deletions", "find . -name '__pycache__' -exec rm -rf {} +", "hermes-asks"),
    ("deletions", "find . -name '*.tmp' -delete", "hermes-asks"),
    ("deletions", "git clean -fd", "hermes-asks"),
    ("deletions", "git rm src/old.py", "free"),                   # git keeps it in HEAD; it refuses a modified file
    # --------------------------------------------------------------------------------------------------- git
    ("git", "git add -A", "free"),
    ("git", 'git add src/app.py && git commit -m "fix: handle empty input"', "free"),
    ("git", "git checkout -b feat/parser", "free"),
    ("git", "git stash", "free"),
    ("git", "git restore src/app.py", "asks:no-undo"),
    ("git", "git reset --hard", "hermes-asks"),
    ("git", "git push", "asks:outside"),
    ("git", "git add -A && git commit -m 'wip' && git push -u origin feat/parser", "asks:outside"),
    # ---------------------------------------------------------------------------------------------- installs
    ("installs", "npm i", "free"),
    ("installs", "npm ci", "free"),
    ("installs", "pip install -r requirements.txt", "free"),
    ("installs", "uv sync", "free"),
    ("installs", "pip install requests", "asks:dependency"),
    ("installs", "npm i -D vitest", "asks:dependency"),
    ("installs", "cargo add serde", "asks:dependency"),
    # ----------------------------------------------------------------------------------------------- network
    ("network", "curl -s https://api.github.com/repos/octocat/hello-world", "free"),
    ("network", "wget -q https://example.com/data.csv", "asks:no-undo"),   # saves the document, unsaved
    ("network", "gh pr view 12", "free"),
    ("network", "curl -sSo src/app.py https://example.com/app.py", "asks:no-undo"),
    ("network", "curl -sL https://example.com/install.sh | sh", "hermes-asks"),
    ("network", "gh pr create --fill", "asks:outside"),
    ("network", "curl -X POST -d '{\"a\": 1}' https://api.example.com/items", "asks:outside"),
    # ------------------------------------------------------------------------------------------------- mixed
    ("mixed", "cd frontend && npm test", "free"),
    ("mixed", "cd frontend && npm run build 2>&1 | tail -20", "free"),
    ("mixed", "export NODE_ENV=test && npm test", "free"),
    ("mixed", "source .venv/bin/activate && pytest -q", "free"),
    ("mixed", "npx tsc --noEmit", "free"),
    ("mixed", "make test", "free"),
    ("mixed", "rm -f *.pyc && python -m pytest -q 2>&1 | tail -5", "free+undo"),
    ("mixed", "grep -rln old_name src | xargs " + SED_I + "'s/old_name/new_name/g'", "asks:no-undo"),
    ("mixed", "python scripts/migrate.py", "asks:script"),
    ("mixed", "node scripts/gen.js 2>&1 | tail -5", "asks:script"),
    ("mixed", "python3 - <<'EOF'\nimport json\nprint(json.load(open('package.json'))['name'])\nEOF", "hermes-asks"),
    ("mixed", "python3 -c 'import sys; print(sys.version)'", "hermes-asks"),
]
