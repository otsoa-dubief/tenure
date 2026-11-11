"""The trusted start: no question Hermes would not ask, until a type makes its first fault. Then the study rule
applies to that type, from T1. Actions that leave the machine, self-protection and suspended sessions still ask."""
import os
import sys

from test_plugin import A, FAST, NPM, climb, ledger, outcomes, plugin, post, pre, state, write  # noqa: F401

TRUST = {**FAST, "start": "trusted"}


def test_a_reversible_type_acts_then_tells_from_the_first_action(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("write_file", write("t1")) == "ran" and ctx.prompts == []
    assert "/tenure undo" in ctx.posted[-1]
    assert outcomes(mod)[-1]["source"] == "notify"


def test_a_command_runs_like_hermes_without_tenure(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", NPM) == "ran" and ctx.prompts == []
    last = outcomes(mod, type="shell:npm")[-1]
    assert (last["result"], last["source"]) == ("neutral", "alone")


def test_what_leaves_the_machine_and_self_protection_still_ask(plugin):
    mod, ctx = plugin({"start": "trusted", "preset": "careful"})   # careful does not cap high stakes
    assert ctx.call("terminal", {"command": "git push origin main"}) == "approved"
    assert ctx.call("skill_manage", {"action": "create", "name": "x"}) == "approved"
    assert len(ctx.prompts) == 2


def test_the_first_fault_puts_the_type_on_probation_and_the_study_rule_applies(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("t1"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    mod.cli.slash(f"undo {uid}")
    s = state(mod, "file:write")
    assert s.distrusted and s.tier == mod.rule.T1
    assert ctx.call("write_file", write("t2")) == "approved"            # asks now, only for this type
    assert ctx.call("terminal", NPM) == "ran"                            # other types keep their trust
    k = 1
    while state(mod, "file:write").tier == mod.rule.T1:                 # the study's Wald climb, after a fault
        climb(ctx, 1, name=f"back{k}")
        k += 1
    assert state(mod, "file:write").tier == mod.rule.T2
    assert len(ctx.prompts) == k == 17                                   # 17 approvals after a first fault, all asked


def test_a_flag_on_a_command_takes_its_trust_back(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent=A)
    assert ctx.call("terminal", NPM) == "approved"


def test_a_revoke_takes_the_trust_back(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    mod.cli.revoke("shell:npm", agent=A)
    assert ctx.call("terminal", NPM) == "approved"


def test_a_suspended_session_asks_for_commands(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("terminal", {"command": "make build"}) == "approved"


def test_trust_earns_no_tier_keeps_its_undo_and_claims_no_guarantee(plugin):
    mod, ctx = plugin(TRUST)
    mod.ST.rng.values = [0.0] * 40                                       # every draw would be a spot check
    for i in range(12):                                                  # FAST: 4 in a row over 2 sessions = T3
        assert ctx.call("write_file", write(f"sp{i}"), session=f"s{i % 2}") == "ran"
        assert "/tenure undo" in ctx.posted[-1]                          # every action keeps its undo
    s = state(mod, "file:write")
    assert ctx.prompts == [] and s.tier == mod.rule.T1 and s.series == 0 and s.successes == 12
    assert not [e for e in ledger(mod, "tier")]                          # no "Tenure granted" for unearned trust
    text = mod.cli.slash("status")
    assert "Trusted (until a mistake)" in text and "unchecked errors under" not in text


def test_a_fault_ends_the_trust_for_every_model_of_the_profile(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)                                            # model-a: trusted
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent="model-b@nous")
    assert ctx.call("terminal", NPM) == "approved"
    mod.pre_api_request(model="model-a", provider="nous", session_id="s1")   # back to the first model
    assert ctx.call("terminal", NPM) == "approved"
    mod.pre_api_request(model="model-c", provider="nous", session_id="s1")   # and a new one
    assert ctx.call("terminal", NPM) == "approved"
    assert ctx.call("write_file", write("other")) == "ran"               # other types keep their trust


def test_refusing_hermes_own_prompt_on_a_trusted_call_is_a_fault(plugin):
    mod, ctx = plugin(TRUST)
    args = {"command": "make clean"}
    assert pre(mod, "terminal", args, "h1") is None                      # tenure lets it through, Hermes asks
    mod.post_approval_response(pattern_key="recursive delete", tool_call_id="h1", choice="deny",
                               surface="cli", session_id="s1")
    post(mod, "terminal", args, "h1", status="blocked", result='{"error": "denied"}')
    s = state(mod, "shell:make:clean")
    assert s.faults == 1 and s.distrusted
    assert ctx.call("terminal", args) == "approved"


def test_without_a_start_setting_the_trusted_start_applies(plugin, monkeypatch):
    monkeypatch.setattr(mod_params(), "DEFAULT_START", "trusted")
    mod, ctx = plugin(FAST)
    assert mod.settings()["start"] == "trusted"
    assert ctx.call("write_file", write("d1")) == "ran" and ctx.prompts == []


def mod_params():
    from tenure import params
    return params


def test_the_study_start_asks_first(plugin):
    mod, ctx = plugin({**FAST, "start": "probation"})
    assert ctx.call("write_file", write("p1")) == "approved"


def test_the_passport_replays_a_trusted_record(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("r1"))
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent=A)
    replayed = mod.passport.replay(mod.store_().ledger())[A]
    for key in ("file:write", "shell:npm"):
        live, again = state(mod, key).to_dict(), replayed[key].to_dict()
        live.pop("changed_at"), again.pop("changed_at")
        assert live == again
    assert replayed["shell:npm"].distrusted and not replayed["file:write"].distrusted


def test_the_first_fault_says_so_in_the_chat(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("n1"))
    uid = int(ctx.posted[-1].rsplit(" ", 1)[1])
    out = mod.cli.slash(f"undo {uid}")
    assert "T1" in out and "On probation · file:write" in out
    tiers = [e for e in ledger(mod, "tier") if e.get("from") == "trusted"]
    assert len(tiers) == 1 and tiers[0]["to"] == mod.rule.T1
    assert mod._say(tiers, 0.1)[0].startswith("tenure · ↓ On probation · file:write")


def test_status_shows_trusted_types_and_the_start(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", NPM)
    text = mod.cli.slash("status")
    assert "Trusted start" in text and "Trusted (until a mistake)" in text


def test_the_start_command_saves_the_setting(plugin):
    mod, ctx = plugin(TRUST)
    assert mod.cli.slash("start probation").startswith("Study start")
    assert ctx.settings["start"] == "probation"
    assert ctx.call("write_file", write("st")) == "approved"


def test_a_state_stored_before_the_trusted_start_keeps_its_faults():
    from tenure import rule
    assert rule.TypeState.from_dict({"key": "file:write", "stakes": "low", "faults": 2}).distrusted
    assert not rule.TypeState.from_dict({"key": "file:write", "stakes": "low"}).distrusted


def test_the_signed_passport_says_trusted_not_earned_and_verifies(plugin, tmp_path):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("pp"))
    ctx.call("terminal", NPM)
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)
    mod.cli.flag("shell:npm", agent="model-b@nous")                     # ends the trust for model-a too
    rows = mod.store_().ledger()
    p = mod.passport.build(mod.store_(), A, mod.settings(), mod.data_dir(), redact=False, rows=rows)
    t = {e["type"]: e for e in p["types"]}
    assert t["file:write"]["trusted"] is True and t["shell:npm"]["trusted"] is False
    assert mod.passport.verify(p, rows) == []


def test_trust_covers_files_memory_and_known_dev_tools_only(plugin):
    mod, ctx = plugin(TRUST)
    for cmd in ("npm test", "python -m pytest", "git commit -m x", "make build", "cargo test"):
        assert ctx.call("terminal", {"command": cmd}) == "ran", cmd
    for cmd in ("stripe charges create", "vercel deploy --prod", "psql $DATABASE_URL -c 'drop table t'",
                "heroku run rake db:drop", "rm -rf build"):
        assert ctx.call("terminal", {"command": cmd}) == "approved", cmd
    assert ctx.call("memory", {"action": "add", "content": "x"}) == "ran"


def test_a_start_switch_mid_call_gives_no_study_credit(plugin):
    mod, ctx = plugin(TRUST)
    assert pre(mod, "write_file", write("mid"), "m1") is None             # trusted: acts, then tells
    ctx.settings["start"] = "probation"
    post(mod, "write_file", write("mid"), "m1")
    s = state(mod, "file:write")
    assert (s.series, s.successes) == (0, 0) and outcomes(mod)[-1]["source"] == "alone"
    replayed = mod.passport.replay(mod.store_().ledger())[A]["file:write"].to_dict()
    live = s.to_dict()
    live.pop("changed_at"), replayed.pop("changed_at")
    assert live == replayed


def test_a_trusted_write_that_cannot_be_saved_asks(plugin, monkeypatch):
    mod, ctx = plugin(TRUST)
    monkeypatch.setattr(mod.undo, "snapshot", lambda *a, **k: None)
    assert ctx.call("write_file", write("big")) == "approved"


def test_trusted_messages_match_status(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("c1"))
    ctx.call("terminal", NPM)
    assert "Trusted (until a mistake)" in mod.cli.slash("card")
    mod.pre_api_request(model="model-b", provider="nous", session_id="s1")
    ctx.call("terminal", NPM)
    said = "\n".join(ctx.posted)
    assert "0 carried over on trial" in said and "2 types keep the trusted start" in said


def test_revoke_all_takes_back_trust_but_skips_what_has_nothing(plugin):
    mod, ctx = plugin({**FAST, "start": "probation"})
    ctx.call("terminal", {"command": "docker run x"}, answer="deny")
    assert mod.cli.slash("revoke all").startswith(mod.i18n.tr("cli.revoke.nothing")[:10])


def test_under_cron_trusted_actions_run_keep_their_undo_and_teach_nothing(plugin):
    mod, ctx = plugin(TRUST)
    ctx.cron = True
    assert ctx.call("write_file", write("cr")) == "ran" and "/tenure undo" in ctx.posted[-1]
    assert ctx.call("terminal", NPM) == "ran"
    assert state(mod, "file:write").successes == 0 and ctx.prompts == []


def test_after_outside_content_trusted_file_writes_keep_their_undo_and_commands_ask(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("write_file", write("after-web")) == "ran" and "/tenure undo" in ctx.posted[-1]
    assert ctx.call("terminal", NPM) == "approved"
    assert "/new" in ctx.prompts[-1]["message"]


def test_a_local_curl_does_not_suspend_the_session(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", {"command": "curl -s http://localhost:3000/health"})
    ctx.call("terminal", {"command": "curl -s http://127.0.0.1:8080/"})
    assert ctx.call("terminal", NPM) == "ran"


def test_after_a_fault_the_ask_names_the_next_step(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("write_file", write("f1"))
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    ctx.call("write_file", write("f2"))
    msg = ctx.prompts[-1]["message"]
    assert "more approvals" in msg and "then tells you" in msg and "/52" not in msg


def test_pip_is_covered_like_npm(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "pip install requests"}) == "ran"
    assert ctx.call("terminal", {"command": "pip3 install -e ."}) == "ran"


def test_inline_code_asks_once_per_session_when_allowed_for_the_session(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "python -c 'print(1)'"}, answer="session") == "approved"
    assert "for this session" in ctx.prompts[-1]["message"]
    assert ctx.call("terminal", {"command": "python -c 'print(2)'"}) == "ran"            # Hermes' session grant
    assert ctx.call("terminal", {"command": "python -c 'print(3)'"}, session="s2") == "approved"
    s = state(mod, "shell:python:inline")
    assert (s.successes, s.neutrals) == (2, 1)                                               # the grant teaches nothing


def test_after_outside_content_a_session_answer_covers_that_command(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("terminal", NPM, answer="session") == "approved"
    assert ctx.call("terminal", NPM) == "ran"
    assert ctx.call("terminal", {"command": "make build"}) == "ran"                         # one answer covers them


def test_everyday_diagnostics_and_money(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "lsof -i :3000"}) == "ran"
    assert ctx.call("terminal", {"command": "chmod +x run.sh"}) == "ran"
    assert mod.classify.classify("terminal", {"command": "stripe charges create"}, cwd="/p", home="/h").stakes == "high"
    assert mod.classify.classify("terminal", {"command": "env"}, cwd="/p", home="/h").type == "shell:env"


def test_session_answer_covers_local_uncovered_commands_but_not_probation(plugin):
    mod, ctx = plugin(TRUST)
    assert ctx.call("terminal", {"command": "rm old.py"}, answer="session") == "approved"
    assert "not covered by the trusted start" in ctx.prompts[-1]["message"]
    assert "/105" not in ctx.prompts[-1]["message"]
    assert ctx.call("terminal", {"command": "rm old2.py"}) == "ran"
    ctx.call("write_file", write("pb"))
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")      # file:write on probation: each answer counts
    assert ctx.call("write_file", write("pb2"), answer="session") == "approved"
    assert ctx.call("write_file", write("pb3")) == "approved"
    assert ctx.call("terminal", {"command": "git push origin main"}, answer="session") == "approved"
    assert ctx.call("terminal", {"command": "git push origin main"}) == "approved"   # what leaves the machine: each time


def test_the_first_outside_read_is_explained_once(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    ctx.call("web_search", {"query": "y"})
    said = [p for p in ctx.posted if "/new" in p]
    assert len(said) == 1 and "commands ask" in said[0]


class Handle:
    """Hermes' PluginMessage: a posted message that can be edited in place."""
    def __init__(self, box, i):
        self.box, self.i = box, i

    def edit(self, text):
        self.box[self.i] = text
        return self


def test_writes_in_one_turn_share_one_edited_message(plugin):
    mod, ctx = plugin(TRUST)
    def post(text):
        ctx.posted.append(text)
        return Handle(ctx.posted, len(ctx.posted) - 1)
    ctx.post_message = post
    for i in range(3):
        assert ctx.call("write_file", write(f"g{i}")) == "ran"
    acted = [p for p in ctx.posted if "acted" in p]
    assert len(acted) == 1 and "3 times" in acted[0] and "/tenure undo 3" in acted[0] and "1–3" in acted[0]
    mod.post_llm_call(session_id="s1")                                  # the turn ends: the next write posts anew
    ctx.call("write_file", write("g9"))
    assert len([p for p in ctx.posted if "acted" in p]) == 2


def test_after_outside_content_one_session_answer_covers_every_covered_command(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("terminal", NPM, answer="session") == "approved"
    assert ctx.call("terminal", {"command": "make build"}) == "ran"
    assert ctx.call("terminal", {"command": "python -m pytest"}) == "ran"


def test_help_prints_the_usage_without_an_error(plugin):
    mod, ctx = plugin(TRUST)
    for arg in ("help", "-h", "--help"):
        out = mod.cli.slash(arg)
        assert "invalid choice" not in out and "status" in out and "start trusted|probation" in out


def test_a_never_faulted_uncovered_type_is_not_called_probation(plugin):
    mod, ctx = plugin(TRUST)
    ctx.call("terminal", {"command": "rm old.py"})
    text = mod.cli.slash("status")
    row = [ln for ln in text.splitlines() if "shell:rm" in ln][0]
    assert "asks (not covered)" in row and "T1" not in row


def _mk(ctx, name, text="old\n"):
    path = os.path.join(ctx.cwd, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def test_a_plain_rm_of_a_project_file_runs_with_an_undo(plugin):
    mod, ctx = plugin(TRUST)
    path = _mk(ctx, "notes.txt")
    assert ctx.call("terminal", {"command": "rm notes.txt"}) == "ran" and ctx.prompts == []
    assert "/tenure undo" in ctx.posted[-1]
    os.remove(path)                                                      # what the command did
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert open(path).read() == "old\n"
    assert state(mod, "file:shell").distrusted                          # an undo is a fault, as for any write


def test_an_undone_mv_puts_both_files_back(plugin):
    mod, ctx = plugin(TRUST)
    a = _mk(ctx, "a.txt")
    b = os.path.join(ctx.cwd, "b.txt")
    assert ctx.call("terminal", {"command": "mv a.txt b.txt"}) == "ran" and ctx.prompts == []
    os.rename(a, b)
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert os.path.exists(a) and not os.path.exists(b)


def test_sed_in_place_and_a_redirect_run_with_an_undo(plugin):
    mod, ctx = plugin(TRUST)
    _mk(ctx, "app.py", "a = 1\n")
    sed = "sed -i '' 's/a/b/' app.py" if sys.platform == "darwin" else "sed -i 's/a/b/' app.py"
    assert ctx.call("terminal", {"command": sed}) == "ran"
    assert ctx.call("terminal", {"command": "echo hi > out.txt"}) == "ran"
    assert ctx.prompts == []


def test_a_recursive_rm_or_a_glob_still_asks(plugin):
    mod, ctx = plugin(TRUST)
    _mk(ctx, "build/x.o")
    _mk(ctx, "a.log")
    assert ctx.call("terminal", {"command": "rm -r build"}) == "approved"
    assert ctx.call("terminal", {"command": "rm *.log"}) == "approved"
    assert state(mod, "file:shell") is None


def test_after_outside_content_a_file_command_keeps_going_with_its_undo(plugin):
    mod, ctx = plugin(TRUST)
    path = _mk(ctx, "notes.txt")
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("terminal", {"command": "rm notes.txt"}) == "ran"            # like a file write: saved first
    assert "/tenure undo" in ctx.posted[-1]
    os.remove(path)
    mod.cli.slash(f"undo {int(ctx.posted[-1].rsplit(' ', 1)[1])}")
    assert open(path).read() == "old\n"


def test_a_session_answer_after_outside_content_never_runs_a_file_command_without_its_undo(plugin):
    mod, ctx = plugin(TRUST)
    _mk(ctx, "keep.txt")
    ctx.call("web_search", {"query": "x"})
    assert ctx.call("terminal", {"command": "npm install"}, answer="session") == "approved"
    assert ctx.call("terminal", {"command": "rm keep.txt"}) == "ran"
    assert "/tenure undo" in ctx.posted[-1]


def test_the_study_start_asks_for_a_file_command(plugin):
    mod, ctx = plugin({**FAST, "start": "probation"})
    _mk(ctx, "notes.txt")
    assert ctx.call("terminal", {"command": "rm notes.txt"}) == "approved"


def test_classify_reads_a_plain_rm_as_an_undoable_file_change(plugin):
    mod, ctx = plugin(TRUST)
    _mk(ctx, "notes.txt")
    a = mod.classify.classify("terminal", {"command": "rm notes.txt"}, cwd=ctx.cwd)
    assert (a.type, a.stakes, a.reversible) == ("file:shell", "low", True)
    assert mod.classify.files_written("terminal", {"command": "rm notes.txt"}, ctx.cwd) == [
        os.path.join(ctx.cwd, "notes.txt")]
    assert mod.classify.classify("terminal", {"command": "rm -r notes.txt"}, cwd=ctx.cwd).type == "shell:rm"


def test_a_heredoc_whose_body_reads_like_commands_is_still_a_file_change(plugin):
    mod, ctx = plugin(TRUST)
    for body in ("- item one\n- item two\n", "console.log('hi');\nprocess.exit(1)\n", "#!/bin/sh\necho start\nnpm test\n"):
        a = mod.classify.classify("terminal", {"command": f"cat <<'EOF' > out.txt\n{body}EOF"}, cwd=ctx.cwd)
        assert (a.type, a.stakes) == ("file:shell", "low"), body
    a = mod.classify.classify("terminal", {"command": "cat <<'EOF' | sh\nrm -rf /\nEOF"}, cwd=ctx.cwd)
    assert a.type != "file:shell"
    a = mod.classify.classify("terminal", {"command": "cat <<'EOF' > s.sh\nrm -rf /\nEOF"}, cwd=ctx.cwd)
    assert a.stakes == "cap"                                             # self-protection still reads the body


def test_a_chain_of_plain_file_commands_runs_with_one_undo(plugin):
    mod, ctx = plugin(TRUST)
    _mk(ctx, "a.txt")
    _mk(ctx, "b.txt")
    assert ctx.call("terminal", {"command": "rm a.txt && rm b.txt"}) == "ran" and ctx.prompts == []
    assert "/tenure undo" in ctx.posted[-1]
