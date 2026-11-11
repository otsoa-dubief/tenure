"""End-to-end check inside a real Hermes install: tenure is discovered, enabled and called through Hermes' own
approval gate (``resolve_pre_tool_block``, the path a live agent uses), with a scripted owner answering the prompts.
File tools really run, through ``model_tools.handle_function_call``, in a throwaway project directory, and
``post_tool_call`` is fired by Hermes' own emitter, as model_tools.py fires it. Undo, passport, export and verify go
through the ``hermes tenure`` command line.

    HERMES_AGENT_DIR=/path/to/hermes-agent /path/to/hermes/python tests/integration/run_in_hermes.py

Uses a throwaway HERMES_HOME; your own profiles are never touched. No network. Exit code 0 when every check passes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
home = tempfile.mkdtemp(prefix="tenure-it-")
project = os.path.realpath(tempfile.mkdtemp(prefix="tenure-project-"))
os.environ["HERMES_HOME"] = home
os.environ["HERMES_INTERACTIVE"] = "1"          # a person at the CLI answers approvals
os.environ["TERMINAL_CWD"] = project
for name in ("HERMES_YOLO_MODE", "HERMES_CRON_SESSION", "ANTHROPIC_API_KEY"):
    os.environ.pop(name, None)
os.chdir(project)
# TENURE_IT_START=trusted checks the default trusted start; otherwise the study's start (every type on probation).
START = "trusted" if os.environ.get("TENURE_IT_START") == "trusted" else "probation"
os.makedirs(os.path.join(home, "plugins"))
shutil.copytree(os.path.join(REPO, "tenure"), os.path.join(home, "plugins", "tenure"),
                ignore=shutil.ignore_patterns("__pycache__"))
# low 1/20: a series of 21, longer than the 12 successes of the middle tier, so the climb shows T2 before T3.
# cron_mode approve: a cron job runs its asks unattended, so its automatic check is what judges them.
with open(os.path.join(home, "config.yaml"), "w") as f:
    f.write("approvals:\n  cron_mode: approve\n"
            "plugins:\n  enabled: [tenure]\n  entries:\n    tenure:\n      settings:\n"
            "        risks: {low: 1/20, medium: 1/5, high: cap}\n"
            f"        start: {START}\n")

sys.path.insert(0, os.environ.get("HERMES_AGENT_DIR") or os.path.expanduser("~/.hermes/hermes-agent"))
from hermes_cli import plugin_messages, plugins  # noqa: E402
import model_tools  # noqa: E402
import tools.approval as approval  # noqa: E402
from cron import execution_identity  # noqa: E402

HERMES = os.path.join(os.path.dirname(sys.executable), "hermes")      # the CLI of this very Hermes environment
if not os.path.exists(HERMES):
    HERMES = shutil.which("hermes") or HERMES
asked, answers, posted = [], [], []


def scripted_owner(command, description, **kwargs):
    asked.append(description)
    return answers.pop(0) if answers else "deny"


def capture_post(ctx, text):
    posted.append(text)
    return None


approval.prompt_dangerous_approval = scripted_owner
plugin_messages.post = capture_post               # what the plugin would post into the conversation
plugins.discover_plugins(force=True)
core = next((m for m in list(sys.modules.values()) if getattr(m, "PREFIX", None) == "tenure"
             and hasattr(m, "pre_tool_call")), None)
failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}" + ("" if ok else f" (wanted {want!r})"))
    if not ok:
        failures.append(label)


class Picks:
    def __init__(self, values=()):
        self.values = list(values)

    def random(self):
        return self.values.pop(0) if self.values else 0.99


counter = [0]


def run(tool, args, answer=None, session="it-1", call_id=None, real=True):
    """One tool call through Hermes' gate: 'ran' (no prompt), 'approved', 'refused'. When the gate lets it through,
    a real call executes the tool through model_tools.handle_function_call (which fires post_tool_call itself); a
    shell call that must not really run gets a synthetic clean result. A blocked call reports "blocked", as Hermes
    does."""
    counter[0] += 1
    before = len(asked)
    if answer:
        answers.append(answer)
    call = call_id or f"tc-{counter[0]}"
    ids = dict(session_id=session, task_id=session, tool_call_id=call)
    msg = plugins.resolve_pre_tool_block(tool, args, **ids)
    if msg is not None:
        model_tools._emit_post_tool_call_hook(function_name=tool, function_args=args, result=json.dumps(
            {"error": msg}), **ids, status="blocked", error_type="plugin_block", error_message=msg)
    elif real:
        out = model_tools.handle_function_call(tool, dict(args), skip_pre_tool_call_hook=True, **ids)
        if '"error"' in str(out):
            print(f"     ({tool} result: {str(out)[:200]})")
    else:
        model_tools._emit_post_tool_call_hook(function_name=tool, function_args=args,
                                              result='{"output": "", "exit_code": 0}', **ids, duration_ms=1)
    if len(asked) == before:
        answers.clear()
        return "ran" if msg is None else f"blocked without asking: {msg}"
    return "approved" if msg is None else "refused"


def write(content, answer=None, session="it-1", name="notes.md"):
    """Read then write, as an agent does: Hermes refuses to overwrite a file this session has not read since it last
    changed. The read is free: it never asks and never counts."""
    path = os.path.join(project, name)
    if os.path.exists(path):
        model_tools.handle_function_call("read_file", {"path": path}, session_id=session, task_id=session,
                                         tool_call_id=f"rd-{counter[0]}")
    return run("write_file", {"path": os.path.join(project, name), "content": content}, answer, session=session)


def tier(agent="model-a@test", key="file:write"):
    s = core.store_().recorded(agent, key)
    return None if s is None else (s.tier, s.series, len(s.sessions))


def cli(*argv):
    """``hermes tenure ...`` in a child process: Hermes' own argparse, the same home and project."""
    p = subprocess.run([HERMES, "tenure", *argv], capture_output=True, text=True, cwd=project,
                       env={**os.environ}, timeout=120)
    return p.returncode, (p.stdout + p.stderr).strip()


def read(name="notes.md"):
    with open(os.path.join(project, name), encoding="utf-8") as f:
        return f.read()


def since(mark):
    return posted[mark:]


# ---------------------------------------------------------------------------------------------- loaded
check("tenure loaded", core is not None, True)
if START == "trusted":
    core.ST.rng = Picks()
    mark = len(posted)
    check("trusted: a project file is written without a question", write("a\n"), "ran")
    undo_lines = [p for p in since(mark) if "/tenure undo" in p]
    check("trusted: ...and the owner is told, with an undo", len(undo_lines), 1)
    check("trusted: a command runs without a question", run("terminal", {"command": "npm test"}, real=False), "ran")
    check("trusted: a push still asks", run("terminal", {"command": "git push origin main"}, "once", real=False),
          "approved")
    uid = undo_lines[0].rsplit(" ", 1)[1] if undo_lines else "0"
    code, out = cli("undo", uid)
    check("trusted: the undo restores the file and counts a fault", (code, os.path.exists(os.path.join(project, "notes.md"))), (0, False))
    check("trusted: after its first mistake, file:write asks first", write("b\n", "once"), "approved")
    check("trusted: the other types keep their trust", run("terminal", {"command": "npm test"}, real=False), "ran")
    for cmd in ("cd src && npm test", "source .venv/bin/activate && pytest", "npx jest", "git commit -m 'fix'"):
        check(f"trusted: everyday work asks nothing: {cmd}", run("terminal", {"command": cmd}, real=False), "ran")
    for cmd in ("npm test && rm -rf build", "npm run deploy", "aws s3 cp a s3://b", "uv publish", "sudo make install",
                "git checkout -- .", "stripe charges create", "sed -i s/a/b/ notes.md"):
        check(f"trusted: still asks: {cmd}", run("terminal", {"command": cmd}, "once", real=False), "approved")
    check("trusted: inline code asks, and 'Allow for this session' is offered",
          run("terminal", {"command": "python3 -c 'print(1)'"}, "session", real=False), "approved")
    check("trusted: ...then Hermes' own session grant lets the next one run",
          run("terminal", {"command": "python3 -c 'print(2)'"}, real=False), "ran")
    code, out = cli("flag", "shell:npm")
    check("trusted: a flag ends the trust for that type", run("terminal", {"command": "npm test"}, "once", real=False),
          "approved")
    pp = os.path.join(project, "passport.json")
    led = os.path.join(project, "ledger.jsonl")
    cli("passport", "--out", pp, "--no-redact")
    cli("export", led)
    code, out = cli("verify", pp, led)
    check("trusted: the passport verifies against the ledger", (code, out.startswith("OK")), (0, True))
    with open(pp, encoding="utf-8") as f:
        kinds = {t["type"]: t["trusted"] for t in json.load(f)["types"]}
    check("trusted: the passport says which types are trusted, not earned",
          (kinds.get("shell:git:commit"), kinds.get("shell:npm"), kinds.get("file:write")), (True, False, False))
    print("\n" + core.cli.status_text(every=True))
    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(project, ignore_errors=True)
    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
    sys.exit(1 if failures else 0)
from tools import approval_context  # noqa: E402
check("runs under the Hermes default approvals.mode (smart): tenure's own asks still reach the owner",
      approval_context._get_approval_mode(), "smart")
check("six hooks registered", sorted(h for h in ("pre_api_request", "pre_tool_call", "post_approval_response",
                                                 "post_tool_call", "subagent_start", "subagent_stop")
                                       if plugins.has_hook(h)),
      ["post_approval_response", "post_tool_call", "pre_api_request", "pre_tool_call", "subagent_start",
       "subagent_stop"])
core.ST.rng = Picks()
plugins.invoke_hook("pre_api_request", model="model-a", provider="test", session_id="it-1")
with open(os.path.join(project, "README.md"), "w") as f:
    f.write("# throwaway\n")
check("read: never asks", run("read_file", {"path": os.path.join(project, "README.md")}), "ran")
check("git status: never asks", run("terminal", {"command": "git status"}, real=False), "ran")

# ---------------------------------------------------------------------------------- climb to NOTIFY, undo
n = core.params.required_n(core.settings()["risks"], "low")
check("series length at low stakes, 1/20", n, 21)
for k in range(12):                            # the middle tier's test: 12 verified successes at low stakes
    check(f"file write {k + 1}/12: asks", write(f"v{k + 1}", "once"), "approved")
check("file written for real", read(), "v12")
check("after 12 successes: T2", tier(), ("notify", 12, 1))
mark = len(posted)
check("T2: acts without asking", write("notified"), "ran")
check("T2: the file really changed", read(), "notified")
undo_posts = [p for p in since(mark) if "/tenure undo" in p]
check("T2: the owner is notified with an undo", len(undo_posts), 1)
undo_id = undo_posts[0].rsplit(" ", 1)[1] if undo_posts else "0"
code, out = cli("undo", undo_id)
print("     " + out.replace("\n", "\n     "))
check("hermes tenure undo: exit code", code, 0)
check("undo: the file is back as before the action", read(), "v12")
check("undo: counted as a fault, back to T1, series reset", tier(), ("ask", 0, 0))
code, out = cli("undo", undo_id)
check("undo twice: refused", (code, "already undone" in out), (1, True))

# --------------------------------------------------------------------------------- ALLOW after two sessions
k = 0
while tier()[0] != "notify" and k < 10:        # the score climbs back over the fault
    k += 1
    check(f"after the undo, write {k}: asks", write(f"w{k}", "once"), "approved")
check("back to T2 after the undo", tier()[0], "notify")
for _ in range(n):                             # the rest of the series acts then notifies, all in session it-1
    if tier()[1] >= n:
        break
    check(f"T2 write, series {tier()[1] + 1}/{n}: acts", write(f"s{tier()[1]}"), "ran")
check("full series from one session: still T2", tier(), ("notify", n, 1))
mark = len(posted)
check("T2 write for the tamper test: acts", write("tamper-me"), "ran")
tamper_ids = [p.rsplit(" ", 1)[1] for p in since(mark) if "/tenure undo" in p]
entry = core.store_().get_undo(int(tamper_ids[0])) if tamper_ids else None
victim = os.path.join(project, "victim.txt")
with open(victim, "w") as f:
    f.write("keep\n")
if entry:
    mpath = os.path.join(core.data_dir(), "undo", entry["snap_id"], "manifest.json")
    with open(mpath) as f:
        manifest = json.load(f)
    manifest["files"][0]["path"] = victim
    os.chmod(mpath, 0o600)
    with open(mpath, "w") as f:
        json.dump(manifest, f)
code, out = cli("undo", tamper_ids[0] if tamper_ids else "0")
print("     " + out)
check("a tampered undo manifest is refused", (code, "refused" in out), (1, True))
check("the path it named was never written", open(victim).read(), "keep\n")
check("the project file stays as the action left it", read(), "tamper-me")
check("one session only: still notifies", write("one-session"), "ran")
check("a second session completes the series: T3", (write("second", session="it-2"), tier()),
      ("ran", ("alone", n, 2)))
mark = len(posted)
check("T3: acts alone", write("alone", session="it-2"), "ran")
check("T3: no undo notice (acting alone)", [p for p in since(mark) if "/tenure undo" in p], [])
check("T3: the file really changed", read(), "alone")

# --------------------------------------------------------------------------------- spot check and descent
core.ST.rng = Picks([0.0])
mark = len(posted)
check("spot check: asks", write("spotted", "deny", session="it-2"), "refused")
check("a refused spot check never wrote the file", read(), "alone")
check("descent: one tier down, series reset", tier()[:2], ("notify", 0))
check("descent is announced", any("is back at T2" in p and "after a fault" in p for p in since(mark)), True)

# ------------------------------------------------------------------------------------------------- taint
model_tools._emit_post_tool_call_hook(function_name="web_extract", function_args={"urls": ["https://example.com"]},
                                      result='{"results": []}', session_id="it-5", task_id="it-5",
                                      tool_call_id="tc-web", duration_ms=1, status="ok")
before = len(asked)
check("suspended session: a write asks", write("tainted", "once", session="it-5"), "approved")
check("the ask says why", "suspended: external content read" in (asked[before] if len(asked) > before else ""),
      True)
check("other sessions are not suspended", write("clean", session="it-2"), "ran")
plugins.invoke_hook("subagent_start", parent_session_id="it-5", parent_turn_id="t", parent_subagent_id=None,
                    child_session_id="it-5-child", child_subagent_id="sa-1", child_role="leaf", child_goal="x")
check("subagent_start: the child of a suspended parent asks",
      write("child", "once", session="it-5-child"), "approved")

# ----------------------------------------------------------------- self-protection, through Hermes' own home
for cmd in ("hermes config set plugins.entries.tenure.settings.enabled false", "hermes plugins disable tenure",
            "hermes tenure strict off", "python -m hermes_cli config set approvals.mode off",
            "find ~ -name tenure.db -delete", f"sqlite3 {core.data_dir()}/tenure.db 'delete from ledger'",
            f"rm -rf {core.data_dir()}/undo"):
    before = len(asked)
    got = run("terminal", {"command": cmd}, "deny", session="it-2", real=False)
    why = asked[before] if len(asked) > before else ""
    check(f"capped: {cmd[:60]}", (got, "is capped: always asked" in why, "self:" in why), ("refused", True, True))
for path in (os.path.join(home, "config.yaml"), os.path.join(core.data_dir(), "undo", "x", "manifest.json")):
    check(f"capped write in the custom Hermes home: {os.path.relpath(path, home)}",
          core.classify.classify("write_file", {"path": path}, cwd=project).stakes, "cap")
check("hermes status: never asks", run("terminal", {"command": "hermes status"}, real=False), "ran")
level = os.path.join(home, "profiles", "coder")                   # R36: the terminal's cwd persists between calls
os.makedirs(level, exist_ok=True)
check("cd into a profile, alone: capped, then run for real",
      run("terminal", {"command": f"cd {level}"}, "once", session="it-6"), "approved")
before = len(asked)
got = run("terminal", {"command": "tar xf /tmp/tenure-it-none.tar"}, "deny", session="it-6", real=False)
check("the next call runs in that profile: capped", (got, "is capped: always asked" in "".join(asked[before:])),
      ("refused", True))

# --------------------------------------------------------------------------------- 'always' never bypasses
check("git push: high stakes, capped by the settings",
      run("terminal", {"command": "git push origin main"}, "always", real=False), "approved")
check("git push again: 'always' did not silence it",
      run("terminal", {"command": "git push origin main"}, "once", real=False), "approved")
check(".env: capped", run("write_file", {"path": os.path.join(project, ".env"), "content": "K=1"}, "deny"),
      "refused")
check(".env never written", os.path.exists(os.path.join(project, ".env")), False)
check("npm test: asks", run("terminal", {"command": "npm test"}, "always", real=False), "approved")
check("npm after 'always': still asks (one-off keys)", run("terminal", {"command": "npm test"}, "once", real=False),
      "approved")
check("'always' on call_0 in one session",
      run("terminal", {"command": "make build"}, "always", session="it-3", call_id="call_0", real=False), "approved")
check("the same call_0 in another session still asks",
      run("terminal", {"command": "make build"}, "once", session="it-4", call_id="call_0", real=False), "approved")
check("timeout counts for nothing", run("terminal", {"command": "npm test"}, "timeout", real=False), "refused")

# --------------------------------------------------------------------------------------------- model switch
a_state = tier()
mark = len(posted)
plugins.invoke_hook("pre_api_request", model="model-b", provider="test", session_id="it-1")
switch = [p for p in since(mark) if "new agent model-b@test" in p]
print("     " + (switch[0] if switch else "(no announcement)"))
check("model switch announced", len(switch), 1)
check("the announcement names the carry-over", any("carried over on trial" in p for p in switch), True)
b_state = tier("model-b@test")
check("model-b inherits half the series, provisional", (b_state[1], core.store_().recorded(
    "model-b@test", "file:write").provisional), (a_state[1] // 2, a_state[1] // 2))
check("new model: npm asks again", run("terminal", {"command": "npm test"}, "once", real=False), "approved")

# --------------------------------------------------------------------------------- cron: the check judges
token = execution_identity._CURRENT.set(execution_identity.CronExecution(
    job_id="job-1", job_name="nightly", execution_id="ex-1", source="builtin", scheduled_instant=None,
    started_at=None, profile="default"))
os.environ["HERMES_CRON_SESSION"] = "1"
try:
    check("cron: nobody answers", core.nobody_answers(), "cron")
    before_faults = core.store_().recorded("model-b@test", "file:write").faults
    mark = len(posted)
    # Hermes itself refuses a JSON or TOML write that does not parse; Python with a syntax error is written.
    check("cron: a broken Python write runs unattended",
          run("write_file", {"path": os.path.join(project, "job.py"), "content": "def broken(:\n"},
              session="cron-1"), "ran")
    check("cron: the file was written", read("job.py"), "def broken(:\n")
    check("cron: the automatic check counts a fault",
          core.store_().recorded("model-b@test", "file:write").faults, before_faults + 1)
    check("cron: the fault is announced", any("python syntax error" in p for p in since(mark)), True)
finally:
    os.environ.pop("HERMES_CRON_SESSION", None)
    execution_identity._CURRENT.reset(token)

# ----------------------------------------------------------------------------------------- the evidence
rows = core.store_().ledger()
kinds = [r["event"]["event"] for r in rows]
outcomes = [r["event"] for r in rows if r["event"]["event"] == "outcome"]
check("evidence chain intact", core.store.verify(rows), [])
check("evidence holds no content", any(x in json.dumps(rows) for x in ("notes.md", "K=1", "broken(", project,
                                                                       "it-1", "make build")), False)
check("the model change is a ledger input", kinds.count("agent"), 1)
check("sources seen", sorted({o["source"] for o in outcomes}),
      sorted({"approval", "notify", "undo", "alone", "spot", "check", "timeout"}))

# --------------------------------------------------------------------------------- passport, export, verify
pp, ledger = os.path.join(project, "passport.json"), os.path.join(project, "ledger.jsonl")
code, out = cli("passport", "--agent", "model-a@test", "--out", pp)
print("     " + out.replace("\n", "\n     "))
check("hermes tenure passport: exit code", code, 0)
code, out = cli("export", ledger)
check("hermes tenure export: exit code", code, 0)
code, out = cli("verify", pp, ledger)
print("     " + out)
check("verify with the ledger: OK", (code, out.startswith("OK:")), (0, True))
with open(pp, encoding="utf-8") as f:
    forged = json.load(f)
forged["types"][0]["series"] = forged["types"][0]["series"] + 5
bad = os.path.join(project, "passport-tampered.json")
with open(bad, "w", encoding="utf-8") as f:
    json.dump(forged, f)
code, out = cli("verify", bad, ledger)
print("     " + out.replace("\n", "\n     "))
check("a tampered passport FAILS", (code, out.startswith("OK")), (1, False))
with open(ledger, encoding="utf-8") as f:
    lines = f.read().splitlines()
cut = os.path.join(project, "ledger-tampered.jsonl")
with open(cut, "w", encoding="utf-8") as f:
    f.write("\n".join(lines[:5] + lines[6:]) + "\n")
code, out = cli("verify", pp, cut)
check("a tampered ledger FAILS", (code, out.startswith("OK")), (1, False))

print("\n" + core.cli.status_text("model-a@test"))
shutil.rmtree(home, ignore_errors=True)
shutil.rmtree(project, ignore_errors=True)
print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
