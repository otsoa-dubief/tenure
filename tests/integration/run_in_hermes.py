"""End-to-end check inside a real Hermes install: clearance is discovered, enabled and called through Hermes' own
hook dispatch and approval gate (the path a live agent uses), with a scripted owner answering the prompts.

    HERMES_AGENT_DIR=/path/to/hermes-agent /path/to/hermes/python tests/integration/run_in_hermes.py

Uses a throwaway HERMES_HOME; your own profiles are never touched. Exit code 0 when every check passes.
"""
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
home = tempfile.mkdtemp(prefix="clearance-it-")
os.environ["HERMES_HOME"] = home
os.environ["HERMES_INTERACTIVE"] = "1"          # a person at the CLI answers approvals
os.environ.pop("HERMES_YOLO_MODE", None)
os.makedirs(os.path.join(home, "plugins"))
shutil.copytree(os.path.join(REPO, "clearance"), os.path.join(home, "plugins", "clearance"),
                ignore=shutil.ignore_patterns("__pycache__"))
with open(os.path.join(home, "config.yaml"), "w") as f:
    f.write("plugins:\n  enabled: [clearance]\n  entries:\n    clearance:\n      settings:\n"
            "        risks: {low: 1/4, medium: 1/5, high: cap}\n")

sys.path.insert(0, os.environ.get("HERMES_AGENT_DIR") or os.path.expanduser("~/.hermes/hermes-agent"))
from hermes_cli import plugins  # noqa: E402
import tools.approval as approval  # noqa: E402

asked = []
answers = []


def scripted_owner(command, description, **kwargs):
    asked.append(description)
    return answers.pop(0) if answers else "deny"


approval.prompt_dangerous_approval = scripted_owner
plugins.discover_plugins(force=True)
core = next((m for m in list(sys.modules.values()) if getattr(m, "PREFIX", None) == "clearance"
             and hasattr(m, "pre_tool_call")), None)
failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        failures.append(label)


class Picks:
    def __init__(self, values=()):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


counter = [0]


def run(tool, args, answer=None, session="it-1"):
    """What happens to one tool call: 'ran' (no prompt), 'approved', 'refused'."""
    counter[0] += 1
    before = len(asked)
    if answer:
        answers.append(answer)
    msg = plugins.resolve_pre_tool_block(tool, args, session_id=session, task_id=session,
                                         tool_call_id=f"tc-{counter[0]}")
    if len(asked) == before:
        answers.clear()
        return "ran" if msg is None else f"blocked without asking: {msg}"
    return "approved" if msg is None else "refused"


check("clearance loaded", core is not None, True)
core.ST.rng = Picks()
plugins.invoke_hook("pre_api_request", model="model-a", provider="test", session_id="it-1")
check("read: never asks", run("read_file", {"path": "README.md"}), "ran")
check("git status: never asks", run("terminal", {"command": "git status"}), "ran")
i = core.params.clearance_number(0.25, 0.1)
for n in range(i):
    check(f"file write {n + 1}/{i}: asks", run("write_file", {"path": "notes.md", "content": "x"}, "once"), "approved")
check("file write after clearance: runs alone", run("write_file", {"path": "notes.md", "content": "x"}), "ran")
core.ST.rng = Picks([0.0])
check("spot check: asks", run("write_file", {"path": "notes.md", "content": "y"}, "deny"), "refused")
check("after a refused spot check: asks again", run("write_file", {"path": "notes.md", "content": "z"}, "once"),
      "approved")
check("git push: high stakes, capped by the settings", run("terminal", {"command": "git push origin main"}, "always"),
      "approved")
check("git push again: 'always' did not silence it", run("terminal", {"command": "git push origin main"}, "once"),
      "approved")
check(".env: capped", run("write_file", {"path": ".env", "content": "K=1"}, "deny"), "refused")
check("npm test: asks", run("terminal", {"command": "npm test"}, "always"), "approved")
check("npm after 'always': cleared by hand", run("terminal", {"command": "npm test"}), "ran")
plugins.invoke_hook("pre_api_request", model="model-b", provider="test", session_id="it-1")
check("new model: npm asks again", run("terminal", {"command": "npm test"}, "once"), "approved")
check("timeout counts for nothing", run("write_file", {"path": "a.md", "content": "x"}, "timeout"), "refused")
rows = core.store_().ledger()
check("evidence chain intact", core.store.verify(rows), [])
check("evidence holds no content", any("notes.md" in str(r) or "K=1" in str(r) for r in rows), False)
print(core.cli.status_text("model-a"))
print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
