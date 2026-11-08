# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""``hermes clearance`` (owner's terminal) and ``/clearance`` (inside a conversation).

    status [--profile P] [--model M] [--all]   what each agent has earned, per action type
    setup [careful|balanced|fast]              the three recommendations; with a name, use it
    explain                                    how clearance decides, and what the numbers guarantee
    models [--type T]                          each model's verified record on your own work
    undo ID                                    put back the files of an action taken alone (counts a fault)
    flag TYPE [note] [--model M]               report an error the agent made on its own: its clearance is revoked
    revoke TYPE|all [--model M | --all]        take a clearance back without an error
    passport [--agent A] [--out FILE]          write the signed passport of an agent (--no-redact keeps type names)
    verify PASSPORT [LEDGER]                   check a passport; with the exported ledger, recompute it by replay
    anchor                                     one line to publish: the ledger's head, date and length
    export [PATH]                              write the evidence ledger (hash-chained JSON lines)
    strict on|off                              strict mode: a new model starts with an empty record
    cleanup                                    list dead clearance keys in Hermes' permanent allowlist
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time

from . import params, passport, personal, rule, store, undo

ENOUGH = 20                                     # checks before a rate is called measured


def _core():
    return sys.modules[__package__]


class CliError(Exception):
    """A message for the owner, not a crash."""


class _Usage(Exception):
    pass


def presets_text(spot: float) -> str:
    lines = [f"Recommendations (1 spot check in {round(1 / spot)} once a type is cleared):", ""]
    for name in ("careful", "balanced", "fast"):
        d = params.describe(name, spot)
        parts = []
        for level in params.LEVELS:
            x = d[level]
            parts.append(f"{level}: always asked" if x["capped"] else
                         f"{level}: {x['n']} approvals (risk {x['risk']:.1%})")
        default = " (default)" if name == params.DEFAULT_PRESET else ""
        lines.append(f"  {name}{default}: " + "; ".join(parts))
    lines += ["", "Low stakes: files in the project, memory, reactions. Medium: commands, code, files elsewhere, "
                  "internal tools. High: anything that leaves the machine (messages to others, pushes, uploads, "
                  "publications) and money. Use one: /clearance setup balanced. Or set "
                  "plugins.entries.clearance.settings.risks in config.yaml (e.g. low: 1/50, medium: 1%, high: cap)."]
    return "\n".join(lines)


TIERS = {rule.T1: "T1 ask", rule.T2: "T2 notify", rule.T3: "T3 alone"}
_RANK = {rule.T1: 1, rule.T2: 2, rule.T3: 3}


# ------------------------------------------------------------------------------------------------ agents
def _agent(core, agent: str | None) -> str:
    return agent or core.ST.last_agent or core.store_().get_meta("agent:last") or "unknown@unknown"


def _targets(core, st, *, agent: str | None = None, model: str | None = None, every: bool = False) -> list[str]:
    """The agents a command acts on. An exact agent string wins; ``model`` (or ``agent``) matches the START of an
    agent string and must be unambiguous; ``every`` is all agents with a record; else the profile's last active
    agent."""
    known = st.agents()
    if every:
        if not known:
            raise CliError("No agent has a record yet.")
        return known
    wanted = agent or model
    if not wanted:
        return [_agent(core, None)]
    if wanted in known:
        return [wanted]
    found = [a for a in known if a.startswith(wanted)]
    if not found:
        raise CliError(f"No agent starts with {wanted!r}. Agents: {', '.join(known) or 'none yet'}.")
    if len(found) > 1:
        raise CliError(f"{wanted!r} matches {len(found)} agents ({', '.join(found)}): be more specific.")
    return found


def effective_tier(s: rule.TypeState, n: int | None) -> str:
    """The tier ``rule.decide`` would allow now at the type's stakes, ignoring randomness (no spot check, no
    suspension): capped, a trial or its wait means ask; T3 needs the full series and two sessions, else it falls
    back to T2 (reversible, middle-tier score earned), else ask."""
    if n is None or s.trial_left > 0 or s.trial_wait > 0:
        return rule.T1
    middle = (s.reversible and s.stakes in params.WALD
              and s.wald <= params.wald_steps(s.stakes)[2] + rule.TOL)
    if s.tier == rule.T3 and s.series >= rule.required(s, n) and len(s.sessions) >= rule.SESSIONS:
        return rule.T3
    if s.tier in (rule.T2, rule.T3) and middle:
        return rule.T2
    return rule.T1


def _tier_cell(s: rule.TypeState, n: int | None) -> str:
    eff = effective_tier(s, n)
    return TIERS[eff] + (" (held: settings)" if _RANK[s.tier] > _RANK[eff] else "")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [header] + rows]


def _record(faults: int, successes: int) -> str:
    return f"{faults} faults / {faults + successes} checks"


# ------------------------------------------------------------------------------------------------ status
def _profile_store(core, profile: str):
    """Another profile's store, read only: ``<root>/profiles/<name>/plugin-data/clearance/clearance.db``."""
    home = os.path.abspath(core._hermes_home())
    parent = os.path.dirname(home)
    root = os.path.dirname(parent) if os.path.basename(parent) == "profiles" else home
    base = root if profile == "default" else os.path.join(root, "profiles", profile)
    path = os.path.join(base, "plugin-data", core.PREFIX, "clearance.db")
    try:
        return store.Store.open_readonly(path)
    except FileNotFoundError:
        raise CliError(f"No clearance record for profile {profile!r} (looked for {path}).")
    except Exception as e:
        raise CliError(f"Cannot read the record of profile {profile!r}: {e}")


def _status_agent(st, agent: str, cfg: dict) -> list[str]:
    rows = st.states(agent)
    lines = [agent]
    if not rows:
        lines.append("  No action type has a record yet. Reads never ask; everything else asks until its type "
                     "earns autonomy.")
        return lines
    cells = []
    for _, s in rows:
        n = params.required_n(cfg["risks"], s.stakes)
        eff = effective_tier(s, n)
        if n is None:
            series, sessions, guar = "-", "-", "capped: always asked"
        else:
            series = f"{s.series}/{rule.required(s, n)}"
            sessions = f"{len(s.sessions)}/{rule.SESSIONS}"
            g = rule.guarantee(s, n, cfg["spot"])
            guar = "-"
            if eff == rule.T3:
                guar = (f"unchecked errors under {g['aoql']:.2%} of its actions"
                        + (" (provisional)" if g["conditional"] else ""))
        notes = [f"{s.provisional} provisional"] if s.provisional else []
        notes += [f"trial: {s.trial_left} to go"] if s.trial_left else []
        notes += [f"trial failed: {s.trial_wait} actions to wait"] if s.trial_wait else []
        cells.append([s.key, s.stakes, _tier_cell(s, n), series, sessions, _record(s.faults, s.successes),
                      guar + (f" [{'; '.join(notes)}]" if notes else "")])
    lines += ["  " + ln for ln in _table(["type", "stakes", "tier now", "series", "sessions", "record", "guarantee"],
                                          cells)]
    return lines


def status_text(agent: str | None = None, *, profile: str | None = None, model: str | None = None,
                every: bool = False) -> str:
    core = _core()
    cfg = core.settings()
    if profile:
        st = _profile_store(core, profile)
        last = passport._last_settings(st.ledger())
        if last:
            cfg = {**cfg, "risks": dict(last["risks"]), "spot": last.get("spot", cfg["spot"]),
                   "strict": bool(last.get("strict"))}
        agents = (_targets(core, st, agent=agent, model=model, every=every) if (agent or model or every) else
                  [st.get_meta("agent:last") or "unknown@unknown"])
    else:
        st = core.store_()
        agents = _targets(core, st, agent=agent, model=model, every=every)
    where = f"profile {profile}" if profile else "this profile"
    lines = [f"clearance: {where}, preset {cfg['preset'] if not profile else 'as last logged'}, "
             f"1 spot check in {round(1 / cfg['spot'])}{', strict mode' if cfg['strict'] else ''}"]
    why = None if profile else core.nobody_answers()
    if why:
        lines.append(f"Learning paused here: nobody answers approvals ({why}). Earned tiers still run.")
    if not profile and not cfg["enabled"]:
        lines.append("clearance is disabled (plugins.entries.clearance.settings.enabled: false).")
    for a in agents:
        lines += [""] + _status_agent(st, a, cfg)
    ledger = st.ledger()
    problems = store.verify(ledger)
    lines += ["", f"Evidence: {len(ledger)} entries, " + ("chain intact." if not problems else
                                                          f"CHAIN BROKEN ({problems[0]}).")]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ explain
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
        lines.append(f"  {level}: i = {x['n']}. For an agent whose error rate is stable, errors that run "
                     f"without your approval stay under {x['aoql']:.2%} of its actions of that type. For an agent "
                     f"that turns bad after clearance, at most {x['worst_case']:.1%} until the first caught error.")
    lines += ["", "The guarantee covers the errors you would refuse when asked; an error nobody would notice "
                  "cannot be counted. Measured against theory by simulation in the test suite."]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ models
def models_text(type_key: str | None = None) -> str:
    rows = personal.model_table(_core().store_(), type_key, min_n=ENOUGH)
    if not rows:
        return "No record yet" + (f" for {type_key}." if type_key else ".")
    cells = []
    for r in rows:
        rate = ("no check yet" if r["rate"] is None else
                f"{r['rate']:.1%} (95% interval {r['low']:.1%} to {r['high']:.1%})")
        cells.append([r["type"], r["model"], r["provider"], _record(r["faults"], r["successes"]), rate,
                      "" if r["enough"] else f"under {ENOUGH} checks: too few to compare"])
    lines = ["Verified record per model, on your own work (faults / checks):"]
    lines += _table(["type", "model", "provider", "record", "fault rate", "note"], cells)
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ flag, revoke
def flag(type_key: str, note: str = "", agent: str | None = None, model: str | None = None) -> str:
    """A fault the owner reports after the fact. The note is not stored: the ledger never holds free text."""
    core = _core()
    cfg = core.settings()
    with core.txn() as st:
        agent = _targets(core, st, agent=agent, model=model)[0]
        known = {s.key: s for _, s in st.states(agent)}
        if type_key not in known:
            raise CliError(f"No record of {type_key} for {agent}. Types: {', '.join(sorted(known)) or 'none yet'}.")
        s = known[type_key]
        core.sync_settings(st, cfg)
        core.record_outcome(st, cfg, agent=agent, type_key=type_key, stakes=s.stakes, reversible=s.reversible,
                            result="fault", source="flag")
        st.bump(agent, "faults")
        s = st.get_state(agent, type_key, s.stakes, s.reversible)
    return f"clearance: fault recorded on {type_key} for {agent}; it is now at {TIERS[s.tier]}."


def revoke(type_key: str, agent: str | None = None, model: str | None = None, every: bool = False) -> str:
    core = _core()
    done = []
    with core.txn() as st:
        agents = _targets(core, st, agent=agent, model=model, every=every)
        for ag in agents:
            for _, s in st.states(ag):
                if type_key not in ("all", s.key):
                    continue
                if type_key == "all" and s.tier == rule.T1 and not s.series and not s.provisional and s.wald >= 0:
                    continue                                       # nothing earned to take back
                events = rule.revoke(s)
                st.put_state(ag, s)
                st.log({"event": "revoke", "agent": ag, "type": s.key})
                for ev in events:
                    st.log({**ev, "agent": ag})
                done.append(s.key if len(agents) == 1 else f"{s.key} ({ag})")
    who = agents[0] if len(agents) == 1 else f"{len(agents)} agents"
    return f"clearance revoked for {who}: {', '.join(done)}." if done else "Nothing to revoke."


# ------------------------------------------------------------------------------------------------ undo
def undo_action(entry_id: int) -> str:
    """Restore the files of an action taken alone: the hooks module's ``undo_entry``, the one implementation. The
    returned text's ``ok`` attribute is False when nothing was undone."""
    core = _core()
    with core.txn() as st:
        msg = core.undo_entry(st, entry_id)
    msg.cleanup()                                   # the snapshot goes only once the transaction has committed
    return msg


# ------------------------------------------------------------------------------------------------ passport
def passport_cmd(agent: str | None = None, out: str = "", redact: bool = True) -> str:
    core = _core()
    cfg = core.settings()
    with core.txn() as st:
        name = _targets(core, st, agent=agent)[0]
        if not st.states(name):
            return f"No record for {name}: nothing to put in a passport."
        core.sync_settings(st, cfg)                    # the ledger holds the settings the states were computed with
        p = passport.build(st, name, cfg, core.data_dir(), redact=redact)
    if not out:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
        out = os.path.join(core.data_dir(), f"passport-{stem}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, sort_keys=True)
        f.write("\n")
    lines = [f"Passport written: {out}",
             f"  {name}: {len(p['types'])} types, {'redacted' if redact else 'NOT redacted'}, "
             f"{'signed' if p['signature'] else 'UNSIGNED (the cryptography package is missing)'}, "
             f"ledger head {p['ledger']['head'][:16]} ({p['ledger']['count']} events)",
             f"Anyone can check it: hermes clearance verify {out} <exported ledger>"]
    if not redact:
        lines.append("Warning: type names are written as they are. A name can carry a script, a make target or a "
                     "git alias of yours. Share only a redacted passport.")
    return "\n".join(lines)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CliError(f"Cannot read {path}: {getattr(e, 'strerror', None) or e}.")


def _load_json(path: str):
    try:
        return json.loads(_read(path))
    except ValueError as e:
        raise CliError(f"{path} is not valid JSON ({e}).")


def _load_ledger(path: str) -> list[dict]:
    text = _read(path)
    try:
        if text.lstrip().startswith("["):
            return json.loads(text)
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError as e:
        raise CliError(f"{path} is not an exported ledger ({e}).")


def verify_cmd(passport_path: str, ledger_path: str = "") -> tuple[str, int]:
    try:
        p = _load_json(passport_path)
        rows = _load_ledger(ledger_path) if ledger_path else None
    except CliError as e:
        return str(e), 1
    problems = passport.verify(p, rows)
    if not problems:
        return (f"OK: signature valid, ledger chain intact, {len(p['types'])} types recomputed by replay of "
                f"{p['ledger']['count']} ledger events."), 0
    others = [x for x in problems if x != passport.NO_LEDGER]
    lines = []
    if others:
        lines.append(f"{len(others)} problem(s):")
        lines += [f"  - {x}" for x in others]
    if passport.NO_LEDGER in problems:
        lines.append("signature and chain not checked against types: pass the ledger" if not others else
                     "types not checked: pass the ledger")
    return "\n".join(lines), 1


# ------------------------------------------------------------------------------------------------ the rest
def anchor() -> str:
    return passport.anchor_line(_core().store_())


def export(path: str = "") -> str:
    core = _core()
    path = path or os.path.join(core.data_dir(), f"evidence-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    n = core.store_().export(path)
    return f"Evidence written: {path} ({n} entries). Check a passport against it: hermes clearance verify PASSPORT {path}"


def _save_setting(core, key: str, value) -> str | None:
    """Write one plugin setting through Hermes, then log it in the ledger: None on success, else the reason."""
    if core.ST.ctx is None:
        return "no Hermes context"
    try:
        core.ST.ctx.set_config(key, value)
        cfg = core.settings()
        with core.txn() as st:
            core.sync_settings(st, cfg)
    except Exception as e:
        return type(e).__name__
    return None


def approvals_mode() -> str | None:
    """``approvals.mode`` of the Hermes config, lower case (YAML turns an unquoted ``off`` into False); None when
    Hermes' config cannot be read; "manual" when unset."""
    try:
        from hermes_cli import config as hermes_config
        mode = ((hermes_config.load_config() or {}).get("approvals") or {}).get("mode", "manual")
    except Exception:
        return None
    if mode is False:
        return "off"
    return str(mode).strip().lower() or "manual"


def setup_preset(name: str = "") -> str:
    core = _core()
    cfg = core.settings()
    warn = ""
    mode = approvals_mode()
    if mode is not None and mode != "manual":
        warn = f"learning is paused: approvals.mode is {mode}. Set approvals.mode: manual to let clearance learn.\n"
    if not name:
        return warn + presets_text(cfg["spot"])
    name = name.strip().lower()
    if name not in params.PRESETS:
        return f"Unknown preset {name!r}. " + presets_text(cfg["spot"])
    err = _save_setting(core, "preset", name)
    if err:
        return warn + (f"Could not save the preset ({err}). "
                       f"Set plugins.entries.clearance.settings.preset: {name}")
    return warn + f"Preset {name} in force.\n" + presets_text(core.settings()["spot"])


def strict(value: str) -> str:
    core = _core()
    on = value == "on"
    err = _save_setting(core, "strict", on)
    if err:
        return f"Could not save strict mode ({err}). Set plugins.entries.clearance.settings.strict: {str(on).lower()}"
    return ("Strict mode on: a new model starts with an empty record, nothing is carried over." if on else
            "Strict mode off: a new model inherits half of the previous model's record, unless a public benchmark "
            "vetoes the type.")


def _allowlist() -> list[str] | None:
    try:
        from hermes_cli import config as hermes_config
        raw = (hermes_config.load_config() or {}).get("command_allowlist") or []
    except Exception:
        return None
    return [str(x) for x in raw] if isinstance(raw, (list, tuple, set)) else []


_DEAD = re.compile(r"^(plugin_rule:)?clearance:")


def cleanup() -> str:
    """List, never edit: clearance keys in Hermes' permanent allowlist. Every ask uses a one-off key, so an entry
    there can never match again; it only clutters the list."""
    allow = _allowlist()
    if allow is None:
        return "Cannot read Hermes' config (hermes_cli.config is not available here): nothing checked."
    dead = [k for k in allow if _DEAD.match(k)]
    if not dead:
        return f"No clearance key in the permanent allowlist ({len(allow)} entries checked)."
    keep = [k for k in allow if not _DEAD.match(k)]
    return "\n".join([f"{len(dead)} dead clearance key(s) in the permanent allowlist (command_allowlist), of "
                      f"{len(allow)} entries. Every ask uses a one-off key: these never match again.",
                      *[f"  {k}" for k in dead], "",
                      "Remove them (clearance does not edit your config):",
                      f"  hermes config set command_allowlist {shlex.quote(json.dumps(keep))}"])


# ------------------------------------------------------------------------------------------------ parsing
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)

    def exit(self, status=0, message=None):
        raise _Usage(message or "")


def _add_subcommands(subparser) -> None:
    subs = subparser.add_subparsers(dest="clearance_command")
    p = subs.add_parser("status", help="What each agent has earned, per action type")
    p.add_argument("--profile", help="Another Hermes profile (read only)")
    p.add_argument("--model", help="Start of an agent string, e.g. gpt-5")
    p.add_argument("--all", action="store_true", help="Every agent with a record")
    p = subs.add_parser("setup", help="The three recommendations; with a name, use it")
    p.add_argument("preset", nargs="?", default="", help="careful, balanced or fast")
    subs.add_parser("explain", help="How clearance decides and what the numbers guarantee")
    p = subs.add_parser("models", help="Each model's verified record on your own work")
    p.add_argument("--type", help="One action type")
    p = subs.add_parser("undo", help="Restore the files of an action taken alone")
    p.add_argument("id", type=int)
    p = subs.add_parser("flag", help="Report an error the agent made on its own: revokes the type's clearance")
    p.add_argument("type")
    p.add_argument("note", nargs="*")
    p.add_argument("--model", help="Start of an agent string (default: the last active agent)")
    p = subs.add_parser("revoke", help="Take a clearance back (a type, or all)")
    p.add_argument("type")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--model", help="Start of an agent string (default: the last active agent)")
    g.add_argument("--all", action="store_true", help="Every agent")
    p = subs.add_parser("passport", help="Write the signed passport of an agent")
    p.add_argument("--agent", help="Start of an agent string (default: the last active agent)")
    p.add_argument("--out", default="", help="Output file")
    p.add_argument("--no-redact", action="store_true", help="Keep type names as they are (they can carry names)")
    p = subs.add_parser("verify", help="Check a passport, against the exported ledger when given")
    p.add_argument("passport")
    p.add_argument("ledger", nargs="?", default="")
    subs.add_parser("anchor", help="One line to publish: the ledger's head, date and length")
    p = subs.add_parser("export", help="Write the evidence ledger as hash-chained JSON lines")
    p.add_argument("path", nargs="?", default="")
    p = subs.add_parser("strict", help="Strict mode: a new model starts with an empty record")
    p.add_argument("value", choices=("on", "off"))
    subs.add_parser("cleanup", help="List dead clearance keys in Hermes' permanent allowlist")


def _usage() -> str:
    return __doc__.split("\n\n", 1)[1]


def execute(ns) -> tuple[str, int]:
    """(text, exit code) for a parsed command line."""
    def g(name, default=None):
        return getattr(ns, name, default)
    cmd = g("clearance_command") or "status"
    try:
        if cmd == "status":
            return status_text(profile=g("profile"), model=g("model"), every=bool(g("all"))), 0
        if cmd == "setup":
            return setup_preset(g("preset", "")), 0
        if cmd == "explain":
            return explain_text(), 0
        if cmd == "models":
            return models_text(g("type")), 0
        if cmd == "undo":
            text = undo_action(g("id"))
            return text, 0 if text.ok else 1
        if cmd == "flag":
            return flag(g("type"), " ".join(g("note") or []), model=g("model")), 0
        if cmd == "revoke":
            return revoke(g("type"), model=g("model"), every=bool(g("all"))), 0
        if cmd == "passport":
            return passport_cmd(agent=g("agent"), out=g("out", ""), redact=not g("no_redact", False)), 0
        if cmd == "verify":
            return verify_cmd(g("passport"), g("ledger", ""))
        if cmd == "anchor":
            return anchor(), 0
        if cmd == "export":
            return export(g("path", "")), 0
        if cmd == "strict":
            return strict(g("value")), 0
        if cmd == "cleanup":
            return cleanup(), 0
    except CliError as e:
        return str(e), 1
    return _usage(), 1


def slash(raw_args="", **kwargs):
    try:
        parser = _Parser(prog="/clearance", add_help=False)
        _add_subcommands(parser)
        try:
            ns = parser.parse_args(shlex.split(raw_args or ""))
        except _Usage as e:
            return (f"clearance: {e}\n" if str(e) else "") + _usage()
        return execute(ns)[0]
    except Exception as e:
        return f"clearance: {type(e).__name__}: {e}"


def setup(subparser):
    _add_subcommands(subparser)
    subparser.set_defaults(func=run)


def run(args):
    text, code = execute(args)
    print(text)
    if code:
        sys.exit(code)
