# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""``hermes clearance`` (owner's terminal) and ``/clearance`` (inside a conversation).

    status            what the agent has earned, per action type, for the current model
    setup [preset]    the three recommendations side by side; with a name, use it
    flag TYPE [note]  report an error the agent made on its own: the type's clearance is revoked
    revoke TYPE|all   take a clearance back without an error
    export [PATH]     write the evidence ledger (hash-chained JSON lines)
    verify [PATH]     check an evidence file, or the live ledger
    explain           how clearance decides, and what the numbers guarantee
"""
from __future__ import annotations

import os
import shlex
import sys
import time

from . import params, rule, store


def _core():
    return sys.modules[__package__]


def _pct(x):
    return "capped" if x is None else f"{x:.2%}"


def presets_text(spot: float) -> str:
    lines = [f"Recommendations (1 spot check in {round(1 / spot)} once a type is cleared):", ""]
    for name in ("careful", "balanced", "fast"):
        d = params.describe(name, spot)
        parts = []
        for level in params.LEVELS:
            x = d[level]
            parts.append(f"{level}: always asked" if x["capped"] else
                         f"{level}: {x['approvals']} approvals (risk {x['risk']:.1%})")
        default = " (default)" if name == params.DEFAULT_PRESET else ""
        lines.append(f"  {name}{default}: " + "; ".join(parts))
    lines += ["", "Low stakes: files in the project, memory, reactions. Medium: commands, code, files elsewhere, "
                  "internal tools. High: anything that leaves the machine (messages to others, pushes, uploads, "
                  "publications) and money. Use one: /clearance setup balanced. Or set "
                  "plugins.entries.clearance.settings.risks in config.yaml (e.g. low: 1/50, medium: 1%, high: cap)."]
    return "\n".join(lines)


TIERS = {rule.T1: "T1 ask", rule.T2: "T2 notify", rule.T3: "T3 alone"}


def _agent(core, agent: str | None) -> str:
    return agent or core.ST.last_agent or core.store_().get_meta("agent:last") or "unknown@unknown"


def status_text(agent: str | None = None) -> str:
    core = _core()
    cfg = core.settings()
    agent = _agent(core, agent)
    with core.txn() as st:
        rows = st.states(agent)
    lines = [f"clearance — record for {agent} (preset {cfg['preset']}, 1 spot check in {round(1 / cfg['spot'])}"
             f"{', strict mode' if cfg['strict'] else ''})"]
    why = core.nobody_answers()
    if why:
        lines.append(f"Learning paused here: nobody answers approvals ({why}). Earned tiers still run.")
    if not cfg["enabled"]:
        lines.append("clearance is disabled (plugins.entries.clearance.settings.enabled: false).")
    if not rows:
        lines.append("No action type has a record yet. Reads never ask; everything else asks until its type earns "
                     "autonomy.")
    for _, s in rows:
        n = params.required_n(cfg["risks"], s.stakes)
        k = len(s.sessions)
        series = ("always asked (capped by your settings)" if n is None else
                  f"{s.series}/{rule.required(s, n)} in a row, {k} session{'' if k == 1 else 's'}")
        notes = [f"{s.provisional} provisional"] if s.provisional else []
        notes += [f"trial: {s.trial_left} to go"] if s.trial_left else []
        notes += [f"trial failed: {s.trial_wait} actions to wait"] if s.trial_wait else []
        lines.append(f"  {s.key:<28} {s.stakes:<6} {TIERS[s.tier]:<9} {series:<38} {s.successes} successes, "
                     f"{s.faults} faults, {s.spot_checks} spot checks" + (f" ({'; '.join(notes)})" if notes else ""))
    ledger = st.ledger()
    problems = store.verify(ledger)
    lines.append(f"Evidence: {len(ledger)} entries, " + ("chain intact." if not problems else
                                                          f"CHAIN BROKEN ({problems[0]})."))
    return "\n".join(lines)


def explain_text() -> str:
    core = _core()
    cfg = core.settings()
    d = params.describe(cfg["risks"], cfg["spot"])
    lines = ["How clearance decides (Dodge's continuous sampling plan CSP-1, one per action type):",
             "  1. Every action of a type asks you, until i of them in a row are approved: i is the clearance number.",
             f"  2. Then the agent acts alone on that type; 1 action in {round(1 / cfg['spot'])} is still "
             f"spot-checked at random.",
             "  3. A refused spot check, or an error you flag, revokes the clearance: back to step 1. At medium or high "
             "stakes, the next climb is 25 % longer.",
             "  4. A new model starts with an empty record. Reads never ask; secrets, the agent's own skills and "
             "plugins, and sensitive files always ask.",
             "", "What it guarantees, with your settings (errors you catch never run: a refused action is blocked):"]
    for level in params.LEVELS:
        x = d[level]
        if x["capped"]:
            lines.append(f"  {level}: always asked.")
            continue
        lines.append(f"  {level}: i = {x['approvals']}. For an agent whose error rate is stable, errors that run "
                     f"without your approval stay under {x['guarantee']:.2%} of its actions of that type. For an agent "
                     f"that turns bad after clearance, at most {x['worst_case']:.1%} until the first caught error.")
    lines += ["", "The guarantee covers the errors you would refuse when asked; an error nobody would notice "
                  "cannot be counted. Measured against theory by simulation in the test suite."]
    return "\n".join(lines)


def flag(type_key: str, note: str = "", agent: str | None = None) -> str:
    """A fault the owner reports after the fact. The note is not stored: the ledger never holds free text."""
    core = _core()
    cfg = core.settings()
    agent = _agent(core, agent)
    with core.txn() as st:
        known = {s.key: s for _, s in st.states(agent)}
        if type_key not in known:
            return f"No record of {type_key} for {agent}. Types: {', '.join(sorted(known)) or 'none yet'}."
        s = known[type_key]
        core.sync_settings(st, cfg)
        core.record_outcome(st, cfg, agent=agent, type_key=type_key, stakes=s.stakes, reversible=s.reversible,
                            result="fault", source="flag")
        st.bump(agent, "faults")
        s = st.get_state(agent, type_key, s.stakes, s.reversible)
    return f"clearance: fault recorded on {type_key} for {agent}; it is now at {TIERS[s.tier]}."


def revoke(type_key: str, agent: str | None = None) -> str:
    core = _core()
    agent = _agent(core, agent)
    done = []
    with core.txn() as st:
        for _, s in st.states(agent):
            if type_key not in ("all", s.key):
                continue
            if type_key == "all" and s.tier == rule.T1 and not s.series and not s.provisional and s.wald >= 0:
                continue                                       # nothing earned to take back
            events = rule.revoke(s)
            st.put_state(agent, s)
            st.log({"event": "revoke", "agent": agent, "type": s.key})
            for ev in events:
                st.log({**ev, "agent": agent})
            done.append(s.key)
    return f"clearance revoked for {agent}: {', '.join(done)}." if done else "Nothing to revoke."


def export(path: str = "") -> str:
    core = _core()
    path = path or os.path.join(core.data_dir(), f"evidence-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    n = core.store_().export(path)
    return f"Evidence written: {path} ({n} entries). Check it with: hermes clearance verify {path}"


def verify(path: str = "") -> str:
    import json
    if path:
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    else:
        rows = _core().store_().ledger()
    problems = store.verify(rows)
    return f"{len(rows)} entries: chain intact." if not problems else f"{len(problems)} problem(s): " + "; ".join(problems[:5])


def setup_preset(name: str = "") -> str:
    core = _core()
    cfg = core.settings()
    if not name:
        return presets_text(cfg["spot"])
    name = name.strip().lower()
    if name not in params.PRESETS:
        return f"Unknown preset {name!r}. " + presets_text(cfg["spot"])
    try:
        core.ST.ctx.set_config("preset", name)
    except Exception as e:
        return f"Could not save the preset ({type(e).__name__}). Set plugins.entries.clearance.settings.preset: {name}"
    return f"Preset {name} in force.\n" + presets_text(cfg["spot"])


def _dispatch(words: list[str]) -> str:
    cmd = words[0].lower() if words else "status"
    rest = words[1:]
    if cmd == "status":
        return status_text()
    if cmd == "setup":
        return setup_preset(rest[0] if rest else "")
    if cmd == "explain":
        return explain_text()
    if cmd == "flag" and rest:
        return flag(rest[0], " ".join(rest[1:]))
    if cmd == "revoke" and rest:
        return revoke(rest[0])
    if cmd == "export":
        return export(rest[0] if rest else "")
    if cmd == "verify":
        return verify(rest[0] if rest else "")
    return __doc__.split("\n\n", 1)[1]


def slash(raw_args="", **kwargs):
    try:
        return _dispatch(shlex.split(raw_args or ""))
    except Exception as e:
        return f"clearance: {type(e).__name__}: {e}"


def setup(subparser):
    subs = subparser.add_subparsers(dest="clearance_command")
    subs.add_parser("status", help="What the agent has earned, per action type")
    p = subs.add_parser("setup", help="The three recommendations; with a name, use it")
    p.add_argument("preset", nargs="?", default="")
    subs.add_parser("explain", help="How clearance decides and what the numbers guarantee")
    p = subs.add_parser("flag", help="Report an error the agent made on its own: revokes the type's clearance")
    p.add_argument("type")
    p.add_argument("note", nargs="*")
    p = subs.add_parser("revoke", help="Take a clearance back (a type, or all)")
    p.add_argument("type")
    p = subs.add_parser("export", help="Write the evidence ledger as hash-chained JSON lines")
    p.add_argument("path", nargs="?", default="")
    p = subs.add_parser("verify", help="Check an evidence file, or the live ledger")
    p.add_argument("path", nargs="?", default="")
    subparser.set_defaults(func=run)


def run(args):
    sub = getattr(args, "clearance_command", None) or "status"
    words = [sub]
    for name in ("preset", "type", "path"):
        v = getattr(args, name, None)
        if v:
            words.append(v)
    if getattr(args, "note", None):
        words += list(args.note)
    print(_dispatch(words))
