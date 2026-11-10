"""Seeds a throwaway Hermes root with realistic tenure evidence, for the dashboard smoke test and its screenshots.

Every outcome goes through Hermes' own hook dispatch and approval gate, as in run_in_hermes.py: a scripted owner
answers the prompts, and post_tool_call fires after each call the way model_tools.py fires it. A simulated clock
spreads the week over the last six days, so the timeline reads like a real one.

    HERMES_HOME=<root or root/profiles/name> HERMES_AGENT_DIR=<hermes source> <hermes python> dashboard_seed.py \
        (main|ops) PROJECT_DIR

``main`` (the root profile): two agents (two models), file:write at T2 with one undoable action, shell:pytest at T3,
shell:git:commit in trial, shell:git:push capped, a suspended session, and a signing key for the passport.
``ops`` (a second profile): a small local model with a short record.
Never run it against your own ~/.hermes: it refuses to.
"""
import os
import shutil
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
mode, project = sys.argv[1], os.path.abspath(sys.argv[2])
home = os.environ["HERMES_HOME"]
if os.path.realpath(home).startswith(os.path.realpath(os.path.expanduser("~/.hermes"))):
    sys.exit("refusing to seed ~/.hermes")
os.environ["HERMES_INTERACTIVE"] = "1"
os.environ.pop("HERMES_YOLO_MODE", None)
os.environ["TERMINAL_CWD"] = project
os.makedirs(project, exist_ok=True)
os.chdir(project)

# ------------------------------------------------------------------------------------------- simulated clock
REAL = time.time
NOW = REAL()
clock = [NOW - 6 * 86400]


def at(t):
    clock[0] = t


def tick(seconds):
    clock[0] = min(clock[0] + seconds, REAL() - 30)


time.time = lambda: clock[0]

sys.path.insert(0, os.environ["HERMES_AGENT_DIR"])
from hermes_cli import lifecycle, plugins  # noqa: E402
import tools.approval as approval  # noqa: E402

answers = []
asked = []


def owner(command, description, **kwargs):
    asked.append(description)
    return answers.pop(0) if answers else "once"


approval.prompt_dangerous_approval = owner
plugins.discover_plugins(force=True)
core = next((m for m in list(sys.modules.values()) if getattr(m, "PREFIX", None) == "tenure"
             and hasattr(m, "pre_tool_call")), None)
if core is None:
    sys.exit("tenure was not loaded by Hermes")


class Picks:
    """Spot-check draws: a fixed sequence, then never."""
    def __init__(self, values=()):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


core.ST.rng = Picks()
n_calls = [0]


def model(name, provider, session):
    plugins.invoke_hook("pre_api_request", model=name, provider=provider, session_id=session)


def run(tool, args, session, answer="once", step=900):
    """One tool call through the gate and back: the owner answers ``answer`` if asked."""
    tick(step)
    n_calls[0] += 1
    answers[:] = [answer]
    ids = dict(session_id=session, task_id=session, tool_call_id=f"call_{n_calls[0]}")
    msg = plugins.resolve_pre_tool_block(tool, args, **ids)
    if msg is None and tool == "write_file":           # the tool runs: the file is really written
        path = os.path.join(project, args["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(args["content"])
    lifecycle.invoke_hook("post_tool_call", tool_name=tool, args=args, result='{"success": true, "exit_code": 0}',
                          **ids, duration_ms=12, status="ok" if msg is None else "blocked",
                          error_type=None if msg is None else "plugin_block", error_message=msg)
    answers.clear()


def write(i, session, **kw):
    name = ("src/shop/cart.py", "src/shop/prices.py", "tests/test_cart.py", "src/shop/api.py")[i % 4]
    run("write_file", {"path": name, "content": f"VERSION = {i}\n\n\ndef total(xs):\n    return sum(xs)\n"},
        session, **kw)


def sh(command, session, **kw):
    run("terminal", {"command": command}, session, **kw)


if mode == "main":
    A, B = ("claude-sonnet-4-5", "anthropic"), ("gpt-5-codex", "openai")
    at(NOW - 6 * 86400 + 9 * 3600)
    model(*A, "mon")
    for i in range(14):                                    # file:write climbs to T2 (Wald), approved one by one
        write(i, "mon")
        sh("pytest -q", "mon")
    for i in range(48):
        sh("pytest -q", "mon", step=600)
    sh("git push origin main", "mon")
    for k in range(5):
        sh("git commit -m 'cart: totals'", "mon")
    at(NOW - 4 * 86400 + 10 * 3600)
    model(*A, "wed")
    for i in range(60):                                    # a second session: pytest reaches T3 at 105
        sh("pytest -q", "wed", step=500)
        if i % 5 == 0:
            write(100 + i, "wed")                          # T2: acts, then notifies with an undo
    for k in range(12):
        sh("git commit -m 'prices: rounding'", "wed")
    sh("git push origin main", "wed")
    core.ST.rng = Picks([0.0])
    sh("pytest -q", "wed")                                 # a spot check at T3, approved
    sh("git commit -m 'wip'", "wed", answer="deny")      # a refused commit: medium fault, trial opens
    sh("git commit -m 'prices: rounding, tested'", "wed")  # first of three trial actions
    for k in range(4):
        sh("npm test", "wed")
    at(NOW - 26 * 3600)
    model(*A, "thu")
    for i in range(6):
        sh("pytest -q", "thu", step=400)
    sh("git push origin main", "thu")
    # The owner switches model: half of each record carries over, provisionally.
    at(NOW - 5 * 3600)
    model(*B, "fri")
    for i in range(6):
        write(200 + i, "fri", step=420)
        sh("pytest -q", "fri", step=300)
    sh("npm test", "fri")
    run("web_extract", {"urls": ["https://example.com/changelog"]}, "fri-docs")  # an external read: suspended
    model(*A, "sat")
    tick(1200)
    write(300, "sat", step=600)                            # the last act-then-notify write: still undoable
    # A signing key, as `hermes tenure setup` creates it: the dashboard's passport is then signed.
    core.passport.keypair(core.data_dir())
elif mode == "ops":
    C = ("qwen3:8b-q4_K_M", "ollama")
    at(NOW - 2 * 86400 + 14 * 3600)
    model(*C, "ops-1")
    for i in range(9):
        write(i, "ops-1", step=1500)
    for i in range(3):
        sh("npm test", "ops-1", step=1500)
    sh("rm -rf build", "ops-1", answer="deny")
else:
    sys.exit("usage: dashboard_seed.py (main|ops) PROJECT_DIR")

print(f"seeded {mode}: {n_calls[0]} calls, {len(asked)} asks, {len(core.store_().ledger())} ledger events")
shutil.rmtree(os.path.join(project, ".pytest_cache"), ignore_errors=True)
