# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""``hermes tenure`` (owner's terminal) and ``/tenure`` (inside a conversation).

Three commands are shown (``help_text``):

    (nothing)                                  what the agent did lately and what can still be undone (study: status)
    undo [N]                                   alone, what can still be undone; with a number, put that action back
    trust [KIND [ask]]                         kinds that are not free; with a kind, free it now, or make it ask first

Every other command keeps its name and works as before, listed by ``advanced``:

    status [--profile P] [--model M] [--all]   what each agent has earned, per action type
    setup [careful|balanced|fast]              the three recommendations; with a name, use it
    explain                                    how tenure decides, and what the numbers guarantee
    models [--type T]                          each model's verified record on your own work
    flag [N]                                   alone, the last numbered actions; with a number, report that action as an error
    flag TYPE [note] [--model M]               report an error the agent made on its own: its tenure is revoked
    flag --call ID --session ID [--doubt]      a verifier: a fault (or, with --doubt, the next one asks) on one action
    flag N --doubt                             a verifier's doubt on numbered action N
    excuse [N]                                 alone, the faults of the last 10 minutes; with N, take that one back
    ok [N ...]                                 alone, the open act-then-tell actions; with numbers, those count as seen
    week [--model M]                           the last seven days: actions, questions, faults, undos, what is open
    revoke TYPE|all [--model M | --all]        take earned autonomy back without an error
    passport [--agent A] [--out FILE]          write the signed passport of an agent (--no-redact keeps type names)
    card [--model M] [--no-redact]             the passport as a short text card to paste in a chat or a post
    verify PASSPORT [LEDGER]                   check a passport; with the exported ledger, recompute it by replay
    anchor                                     one line to publish: the ledger's head, date and length
    export [PATH]                              write the evidence ledger (hash-chained JSON lines)
    strict on|off                              strict mode: a new model starts with an empty record
    mode simple|study                          simple (default): free, watched after a mistake, asks after a second;
                                               study: the preregistered rule, spot checks, guarantee and passport
    cleanup                                    list dead tenure keys in Hermes' permanent allowlist
    share [--out FILE]                         write a signed record of counts for the community benchmark (opt-in)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import sys
import time
import unicodedata

from . import community, fields, i18n, params, passport, personal, rule, store, undo
from .i18n import ljust, tr, width

ENOUGH = 20                                     # checks before a rate is called measured


def _core():
    return sys.modules[__package__]


class CliError(Exception):
    """A message for the owner, not a crash."""


class _Usage(Exception):
    pass


SETTINGS = "plugins.entries.tenure.settings"     # the plugin's settings in Hermes' config.yaml


def _stakes(level) -> str:
    return _core().stakes_name(level)


def presets_text(spot: float) -> str:
    lines = [tr("cli.presets.header", spot=round(1 / spot)), ""]
    for name in ("careful", "balanced", "fast"):
        d = params.describe(name, spot)
        parts = []
        for level in params.LEVELS:
            x = d[level]
            parts.append(tr("cli.presets.capped", level=_stakes(level)) if x["capped"] else
                         tr("cli.presets.level", level=_stakes(level), n=x["n"], risk=i18n.pct(x['risk'], 1)))
        line = "cli.presets.line_default" if name == params.DEFAULT_PRESET else "cli.presets.line"
        lines.append("  " + tr(line, name=name, levels=tr("cli.list.joiner").join(parts)))
    lines += ["", tr("cli.presets.footer", command="/tenure setup balanced", setting=f"{SETTINGS}.risks",
                     example="low: 1/50, medium: 1%, high: cap")]
    return "\n".join(lines)


def tier_name(tier) -> str:
    return _core().tier_name(tier)


_RANK = {rule.T1: 1, rule.T2: 2, rule.T3: 3}


# ------------------------------------------------------------------------------------------------ agents
def _agent(core, agent: str | None, st=None) -> str:
    """``agent``, else the profile's last active agent (``st``: a store already open, the dashboard's read-only one)."""
    return (agent or core.ST.last_agent or (st if st is not None else core.store_()).get_meta("agent:last")
            or "unknown@unknown")


def _targets(core, st, *, agent: str | None = None, model: str | None = None, every: bool = False) -> list[str]:
    """The agents a command acts on. An exact agent string wins; ``model`` (or ``agent``) matches the START of an
    agent string and must be unambiguous; ``every`` is all agents with a record; else the profile's last active
    agent."""
    known = st.agents()
    if every:
        if not known:
            raise CliError(tr("cli.err.no_agents"))
        return known
    wanted = agent or model
    if not wanted:
        return [_agent(core, None)]
    if wanted in known:
        return [wanted]
    found = [a for a in known if a.startswith(wanted)]
    if not found:
        raise CliError(tr("cli.err.no_match", wanted=repr(wanted), agents=_join(known) or tr("cli.none_yet")))
    if len(found) > 1:
        raise CliError(tr("cli.err.ambiguous", wanted=repr(wanted), n=len(found), agents=_join(found)))
    return found


def effective_tier(s: rule.TypeState, n: int | None) -> str:
    """The tier ``rule.decide`` would allow now at the type's stakes, ignoring randomness (no spot check, no
    suspension): capped, a trial or its wait means ask; T3 needs the full series, else it falls
    back to T2 (reversible, middle-tier score earned), else ask."""
    if n is None or s.trial_left > 0 or s.trial_wait > 0:
        return rule.T1
    middle = (s.reversible and s.stakes in params.WALD
              and s.wald <= params.wald_steps(s.stakes)[2] + rule.TOL)
    if s.tier == rule.T3 and s.series >= rule.required(s, n):
        return rule.T3
    if s.tier in (rule.T2, rule.T3) and middle:
        return rule.T2
    return rule.T1


def _join(items) -> str:
    return tr("cli.list.separator").join(items)


def _tier_cell(s: rule.TypeState, n: int | None, cfg: dict | None = None) -> str:
    eff = effective_tier(s, n)
    if cfg is not None and eff != rule.T3 and _core().trusted(cfg, s, n, s.stakes):
        return tr("cli.tier.trusted")
    if (cfg is not None and cfg.get("start") == "trusted" and eff == rule.T1 and not s.faults and not s.distrusted
            and not rule.trust_covers(s.key)):
        return tr("cli.tier.uncovered")                  # never faulted: not on probation, just outside the trust
    return tr("cli.tier.held", tier=tier_name(eff)) if _RANK[s.tier] > _RANK[eff] else tier_name(eff)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Columns aligned by terminal width: a CJK character takes two columns."""
    widths = [max(width(r[i]) for r in [header] + rows) for i in range(len(header))]
    return ["  ".join(ljust(c, w) for c, w in zip(r, widths)).rstrip() for r in [header] + rows]


def _cols(*names: str) -> list[str]:
    return [tr(f"cli.col.{x}") for x in names]


def _record(faults: int, successes: int) -> str:
    return f"{tr('cli.count.faults', n=faults)} / {tr('cli.count.checks', n=faults + successes)}"


# ------------------------------------------------------------------------------------------------ status
def _profile_store(core, profile: str):
    """Another profile's store, read only: ``<root>/profiles/<name>/plugin-data/tenure/tenure.db``."""
    home = os.path.abspath(core._hermes_home())
    parent = os.path.dirname(home)
    root = os.path.dirname(parent) if os.path.basename(parent) == "profiles" else home
    base = root if profile == "default" else os.path.join(root, "profiles", profile)
    path = os.path.join(base, "plugin-data", core.PREFIX, "tenure.db")
    try:
        return store.Store.open_readonly(path)
    except FileNotFoundError:
        raise CliError(tr("cli.err.profile_missing", profile=repr(profile), path=path))
    except Exception as e:
        raise CliError(tr("cli.err.profile_unreadable", profile=repr(profile), error=e))


def _status_agent(st, agent: str, cfg: dict) -> list[str]:
    rows = st.states(agent)
    lines = [agent]
    if not rows:
        lines.append("  " + tr("cli.status.empty"))
        return lines
    cells = []
    for _, s in rows:
        n = params.required_n(cfg["risks"], s.stakes)
        eff = effective_tier(s, n)
        if n is None:
            series, sessions, guar = "-", "-", tr("cli.status.capped")
        else:
            series = f"{s.series}/{rule.required(s, n)}"
            sessions = f"{len(rule.session_counts(s))}/{rule.sessions_needed(s.stakes)}"
            g = rule.guarantee(s, n, cfg["spot"])
            guar = "-"
            if eff == rule.T3:
                guar = tr("cli.status.guarantee_provisional" if g["conditional"] else "cli.status.guarantee",
                          rate=i18n.pct(g['aoql'], 2))
        notes = [tr("cli.status.note.provisional", n=s.provisional)] if s.provisional else []
        notes += [tr("cli.status.note.trial", n=s.trial_left)] if s.trial_left else []
        notes += [tr("cli.status.note.trial_wait", n=s.trial_wait)] if s.trial_wait else []
        notes += ([tr("cli.status.note.spot_due")]                        # it only holds an earned T3 back
                  if s.tier == rule.T3 and st.get_meta(_core()._due_key(agent, s.key)) else [])
        held = _core()._held_by(st, agent, s.key) if eff != rule.T1 else None   # the guard plays only where it acts
        notes += [tr("cli.status.held", held=held)] if held else []
        cells.append([s.key, _stakes(s.stakes), _tier_cell(s, n, cfg), series, sessions, _record(s.faults, s.successes),
                      tr("cli.status.notes", guarantee=guar, notes=tr("cli.list.joiner").join(notes)) if notes
                      else guar])
    lines += ["  " + ln for ln in _table(_cols("type", "stakes", "tier_now", "series", "sessions", "record",
                                               "guarantee"), cells)]
    return lines


def _simple_cells(st, agent: str, s: rule.TypeState, cfg: dict) -> list[str]:
    """Simple mode, one type: where it stands and what brings it back, in plain words."""
    core = _core()
    n = params.required_n(cfg["risks"], s.stakes)
    if s.pinned:
        state, next_ = tr("simple.state.ask"), tr("trust.state.pinned", command=f"/tenure trust {s.key}")
    elif not rule.simple_eligible(s, n):
        state, next_ = tr("simple.state.always"), "-"
    elif core.trusted(cfg, s, n, s.stakes):
        state, next_ = tr("simple.state.free"), "-"
    elif s.tier == rule.T2 and rule._middle(s):
        state, next_ = tr("simple.state.watched"), tr("simple.status.to_free", k=s.series, n=n)
    elif s.reversible and s.stakes in params.WALD:
        state, next_ = tr("simple.state.ask"), tr("simple.status.to_watched", n=core._to_t2(s))
    else:
        state, next_ = tr("simple.state.ask"), tr("simple.status.to_free", k=s.series, n=n)
    held = core._held_by(st, agent, s.key) if state != tr("simple.state.ask") else None
    if held:
        next_ = tr("cli.status.held", held=held)
    return [s.key, _stakes(s.stakes), state, next_, _record(s.faults, s.successes)]


def _status_simple(st, agent: str, cfg: dict) -> list[str]:
    rows = st.states(agent)
    if not rows:
        return [agent, "  " + tr("simple.status.empty")]
    cells = [_simple_cells(st, agent, s, cfg) for _, s in rows]
    return [agent] + ["  " + ln for ln in _table([tr("cli.col.type"), tr("cli.col.stakes"), tr("simple.col.state"),
                                                  tr("simple.col.next"), tr("cli.col.record")], cells)]


def status_text(agent: str | None = None, *, profile: str | None = None, model: str | None = None,
                every: bool = False) -> str:
    core = _core()
    cfg = core.settings()
    if profile:
        st = _profile_store(core, profile)
        last = passport._last_settings(st.ledger())
        if last:
            cfg = {**cfg, "risks": dict(last["risks"]), "spot": last.get("spot", cfg["spot"]),
                   "strict": bool(last.get("strict")), "start": last.get("start", "probation"),
                   "mode": rule.mode_of(last)}
        agents = (_targets(core, st, agent=agent, model=model, every=every) if (agent or model or every) else
                  [st.get_meta("agent:last") or "unknown@unknown"])
    else:
        st = core.store_()
        agents = _targets(core, st, agent=agent, model=model, every=every)
    header = ("cli.status.header.profile" if profile else "cli.status.header.here") + ("_strict" if cfg["strict"]
                                                                                        else "")
    simple = core.simple(cfg)
    if simple:
        lines = [tr("simple.status.header.profile" if profile else "simple.status.header.here", profile=profile,
                    preset=cfg["preset"]), tr("simple.status.intro", command="hermes tenure mode study")]
    else:
        lines = [tr(header, profile=profile, preset=cfg["preset"], spot=round(1 / cfg["spot"]))]
    if cfg.get("start") == "trusted" and not simple:
        lines.append(tr("cli.status.trusted_start", command="hermes tenure start probation"))
        ghosts = passport.ghost(st.ledger())          # what the study's start would have earned by now (estimate)
        shown = []
        for (a, k), g in sorted(ghosts.items()):
            real = st.recorded(a, k)
            covered = real is not None and core.trusted(cfg, real, params.required_n(cfg["risks"], real.stakes),
                                                        real.stakes)
            if a in agents and g.tier != rule.T1 and covered:   # only what the trusted start covers today
                n = params.required_n(cfg["risks"], g.stakes)
                shown.append(tr("cli.status.ghost_type", type=k, tier=tier_name(g.tier), series=g.series,
                                required=rule.required(g, n) if n else "-"))
        if shown:
            lines.append(tr("cli.status.ghost", types=_join(shown[:6])))
    copied = None if profile else st.get_meta(core.COPIED_META)
    if copied:
        lines.append(tr("cli.status.copied", date=time.strftime("%Y-%m-%d", time.localtime(float(copied)))))
    why = None if profile else core.nobody_answers()
    if why:
        lines.append(tr("cli.status.paused", why=why))
    if not profile and not cfg["enabled"]:
        lines.append(tr("cli.status.disabled", setting=f"{SETTINGS}.enabled"))
    vocab = None if profile else cfg.get("vocabulary")
    if vocab is not None and vocab.broken:
        lines.append(tr("cli.status.fields.broken"))
    if vocab is not None and vocab.unknown:
        lines.append(tr("cli.status.fields.unknown", names=_join(vocab.unknown)))
    for a in agents:
        lines += [""] + (_status_simple(st, a, cfg) if simple else _status_agent(st, a, cfg))
    others = [] if (agent or model or every) else [a for a in st.agents() if a not in agents]
    if others:
        lines += ["", tr("cli.status.others", n=len(others), agents=_join(others),
                         command="hermes tenure status --all")]
    ledger = st.ledger()
    problems = store.verify(ledger)
    lines += ["", tr("cli.status.chain_ok", n=len(ledger)) if not problems else
              tr("cli.status.chain_broken", n=len(ledger), problem=problems[0])]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ card
_RANK_KEY = {rule.T1: "ask", rule.T2: "notify", rule.T3: "alone"}
_CODE = {rule.T1: "T1", rule.T2: "T2", rule.T3: "T3"}


def _card_bar(s: rule.TypeState, n: int | None, eff: str, cells: int = 12) -> str:
    """The type's progress as text blocks: full at T3, the share of the series toward T3 otherwise, dots when
    capped. The same reading as the dithered bars of the screens."""
    if n is None:
        return "·" * cells
    if eff == rule.T3:
        return "█" * cells
    done = min(cells, int(cells * s.series / max(1, rule.required(s, n))))
    return "█" * max(done, 1 if s.series else 0) + "░" * (cells - max(done, 1 if s.series else 0))


def card_text(model: str | None = None, redact: bool = True) -> str:
    """The passport as a few lines of text to paste in a chat or a post: one bar per action type, from the real
    record. Verifiable evidence is the signed passport (hermes tenure passport)."""
    core = _core()
    cfg = core.settings()
    st = core.store_()
    agent = _targets(core, st, model=model)[0]
    rows = st.states(agent)
    if not rows:
        return tr("cli.card.empty", agent=agent)
    lines = [tr("cli.card.title", agent=agent)]
    shown = {s.key: (passport.redact_type(s.key) if redact else s.key) for _, s in rows}
    width_k = max(width(k) for k in shown.values())
    faults = successes = 0
    for _, s in sorted(rows, key=lambda r: r[1].key):
        n = params.required_n(cfg["risks"], s.stakes)
        eff = effective_tier(s, n)
        rank_key = f"tier.rank.{_RANK_KEY[eff]}"
        label = (f"CAP {tr('tier.rank.cap')}" if n is None else
                 tr("cli.tier.trusted") if eff != rule.T3 and core.trusted(cfg, s, n, s.stakes) else
                 f"{_CODE[eff]} {tr(rank_key)}")
        lines.append(f"{_card_bar(s, n, eff)} {ljust(shown[s.key], width_k)}  {label}")
        faults, successes = faults + s.faults, successes + s.successes
    lines.append(tr("cli.card.foot", record=_record(faults, successes)))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ explain
def _simple_climb(stakes: str) -> int:
    """Approvals in a row that take a reversible type asking after its second mistake back to watched: from the
    score a fault at the bar leaves."""
    a, _, ln_b = params.wald_steps(stakes)
    s = rule.TypeState(key="", stakes=stakes, reversible=True,
                       wald=(max(ln_b, 0.0) if stakes in rule.GRAVE else ln_b) + a)
    return _core()._to_t2(s)


def explain_simple(cfg: dict) -> str:
    n = {lv: params.required_n(cfg["risks"], lv) for lv in params.WALD}
    lines = [tr("simple.explain.title"),
             "  " + tr("simple.explain.free"),
             "  " + tr("simple.explain.watched", command="/tenure undo"),
             "  " + tr("simple.explain.ask", low=_simple_climb("low"), medium=_simple_climb("medium")),
             "  " + (tr("simple.explain.free_again", hours=_core().UNDO_WINDOW // 3600, low=n["low"],
                        medium=n["medium"]) if n["low"] and n["medium"] else
                     tr("simple.explain.free_again_capped", hours=_core().UNDO_WINDOW // 3600)),
             "  " + tr("simple.explain.always"),
             "  " + tr("cli.explain.reads"),
             "", tr("simple.explain.study", command="hermes tenure mode study")]
    return "\n".join(lines)


def explain_text() -> str:
    core = _core()
    cfg = core.settings()
    if core.simple(cfg):
        return explain_simple(cfg)
    d = params.describe(cfg["risks"], cfg["spot"])
    spot = round(1 / cfg["spot"])
    t2 = {lv: math.ceil(params.wald_steps(lv)[2] / params.wald_steps(lv)[1] - 1e-9) for lv in params.WALD}
    new_model = tr("cli.explain.new_model_strict" if cfg["strict"] else "cli.explain.new_model")
    lines = [tr("cli.explain.title"),
             "  " + (tr("cli.explain.t1_trusted") if cfg.get("start") == "trusted" else tr("cli.explain.t1")),
             "  " + tr("cli.explain.t2", low=t2["low"], medium=t2["medium"], command="/tenure undo N"),
             "  " + tr("cli.explain.t3", sessions=f"{rule.SESSIONS}-{rule.SESSIONS_BY_STAKES['medium']}", spot=spot),
             "  " + tr("cli.explain.fault"),
             "  " + new_model,
             "  " + tr("cli.explain.reads"),
             "", tr("cli.explain.guarantee_title")]
    for level in params.LEVELS:
        x = d[level]
        if x["capped"]:
            lines.append("  " + tr("cli.explain.level_capped", level=_stakes(level)))
            continue
        lines.append("  " + tr("cli.explain.level", level=_stakes(level), n=x["n"], aoql=i18n.pct(x['aoql'], 2),
                               worst=i18n.pct(x['worst_case'], 1), missed=i18n.pct(x['missed'], 0)))
    lines += ["", tr("cli.explain.footer")]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ models
def models_text(type_key: str | None = None) -> str:
    rows = personal.model_table(_core().store_(), type_key, min_n=ENOUGH)
    if not rows:
        return tr("cli.models.none_type", type=type_key) if type_key else tr("cli.models.none")
    cells = []
    for r in rows:
        rate = (tr("cli.models.no_check") if r["rate"] is None else
                tr("cli.models.rate", rate=i18n.pct(r['rate'], 1), low=i18n.pct(r['low'], 1), high=i18n.pct(r['high'], 1)))
        cells.append([r["type"], r["model"], r["provider"], _record(r["faults"], r["successes"]), rate,
                      "" if r["enough"] else tr("cli.models.few", n=ENOUGH)])
    lines = [tr("cli.models.title")]
    lines += _table(_cols("type", "model", "provider", "record", "fault_rate", "note"), cells)
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
            raise CliError(tr("cli.flag.unknown_type", type=type_key, agent=agent,
                              types=_join(sorted(known)) or tr("cli.none_yet")))
        s = known[type_key]
        core.sync_settings(st, cfg)
        core.record_outcome(st, cfg, agent=agent, type_key=type_key, stakes=s.stakes, reversible=s.reversible,
                            result="fault", source="flag")
        st.bump(agent, "faults")
        s = st.get_state(agent, type_key, s.stakes, s.reversible)
    return tr("cli.flag.done", type=type_key, agent=agent, tier=core.state_name(cfg, s))


def flag_action(n: int, note: str = "") -> str:
    """A fault the owner reports on numbered action ``n``: on the agent that acted and its type, by the same path
    as ``flag`` (stakes of the recorded state). Refused, with nothing written, when the action already counted as a
    fault or is unknown (or older than 24 hours). The note is not stored."""
    core = _core()
    cfg = core.settings()
    with core.txn() as st:
        r = st.recent(n)
        if r is None:
            raise CliError(tr("cli.flag.action_unknown", n=n, hours=store.RECENT_WINDOW // 3600))
        s = _fault_on(core, st, cfg, r)
    return tr("cli.flag.action_done", n=n, type=r["type"], agent=r["agent"], tier=core.state_name(cfg, s))


def _fault_on(core, st, cfg, r: dict):
    """A fault on one numbered action, by the path of ``flag``: the source ``flag`` is not in ``store.COUNTED``, so
    the wait after a failed trial does not count the action a second time. Refused when it already counted as a fault."""
    if r["flagged"]:
        raise CliError(tr("cli.flag.action_already", n=r["n"]))
    agent, type_key = r["agent"], r["type"]
    recorded = st.recorded(agent, type_key)
    stakes, reversible = (recorded.stakes, recorded.reversible) if recorded else ("medium", True)
    core.sync_settings(st, cfg)
    core.record_outcome(st, cfg, agent=agent, type_key=type_key, stakes=stakes, reversible=reversible,
                        result="fault", source="flag")
    st.bump(agent, "faults")
    st.mark_flagged(r["n"])
    if r["undo_id"] is not None:
        st.mark_undo_fault(r["undo_id"])                    # the undo that may follow counts no second fault
    return st.get_state(agent, type_key, stakes, reversible)


VERDICTS = ("fault", "doubt")


def report(verdict: str, *, n: int | None = None, session: str | None = None, call: str | None = None) -> str:
    """A verifier's verdict on one action that already ran (#6): a deterministic check of the owner's (a test, a
    business rule, a nightly reconciliation) reports ``fault`` or ``doubt``, never a success.

    - ``fault`` counts as a fault on the action's kind and model, exactly like ``/tenure flag <number>``: once per
      action, never twice in the wait after a failed trial, no new ledger event.
    - ``doubt`` records nothing in the ledger: the next action of that kind, for that model, asks first.

    Name the action by its number (``n``, from ``/tenure flag``) or by Hermes' ``session`` id and tool ``call`` id
    (both raw, as Hermes hands them to hooks). Actions are kept 24 hours. Returns the message for the owner; raises
    ``CliError`` (nothing written) when the action is unknown, ambiguous or already counted as a fault."""
    if verdict not in VERDICTS:
        raise ValueError(f"tenure: a verifier reports fault or doubt, not {verdict!r}")
    if (n is None) == (session is None and call is None) or (n is None and not (session and call)):
        raise ValueError("tenure: name the action by n, or by session and call together")
    core = _core()
    cfg = core.settings()
    hours = store.RECENT_WINDOW // 3600
    with core.txn() as st:
        if n is not None:
            r = st.recent(int(n))
            if r is None:
                raise CliError(tr("cli.flag.action_unknown", n=n, hours=hours))
        else:
            rows = st.recent_by_call(core.anon(session), core.anon(call))
            if not rows:
                raise CliError(tr("cli.report.call_unknown", call=str(call)[:40], hours=hours))
            if len(rows) > 1:
                raise CliError(tr("cli.report.call_ambiguous", call=str(call)[:40],
                                  numbers=_join([str(x["n"]) for x in rows])))
            r = rows[0]
        if verdict == "fault":
            s = _fault_on(core, st, cfg, r)
            return tr("cli.flag.action_done", n=r["n"], type=r["type"], agent=r["agent"],
                      tier=core.state_name(cfg, s))
        st.add_doubt(r["agent"], r["type"])
    return tr("cli.report.doubt_done", n=r["n"], type=r["type"], agent=r["agent"])


def flag_list(session: str | None, command: str = "hermes tenure flag") -> str:
    """The last 20 numbered actions of the last 24 hours, newest first: of one session (anonymised), else of the
    profile. The target shows when this process ran the action (summary in memory, same time); else, for an action
    that acted then told, the file its undo snapshot would restore. Reads only."""
    core = _core()
    st = core.store_()
    rows = st.recent_rows(session, limit=20)
    hours = store.RECENT_WINDOW // 3600
    others = st.count_recent(session) if session is not None else 0
    lines = []
    if rows:
        cells = []
        for r in rows:
            what = core.summary_of(st.path, r["n"], r["at"])
            if what.startswith(r["type"] + ": "):
                what = what[len(r["type"]) + 2:]
            uid = r["undo_id"]
            if not what and uid is not None:
                entry = st.get_undo(uid)
                d = undo.describe(entry["snap_id"], core.data_dir()) if entry and entry["snap_id"] else None
                if d:
                    what = tr("cli.undo.more_files", file=d["file"], n=d["files"] - 1) if d["files"] > 1 else d["file"]
            cells.append([str(r["n"]), time.strftime("%H:%M", time.localtime(r["at"])), r["type"], what, r["agent"],
                          "" if uid is None else str(uid)])
        lines.append(tr("cli.flag.title_session" if session is not None else "cli.flag.title_profile", hours=hours))
        lines += ["  " + ln for ln in _table(_cols("number", "time", "type", "target", "agent", "undo"), cells)]
        lines += ["", tr("cli.flag.footer", command=command)]
    else:
        lines.append(tr("cli.flag.none", hours=hours))
    if others:
        lines.append(tr("cli.flag.others", n=others))
    return "\n".join(lines)


def revoke(type_key: str, agent: str | None = None, model: str | None = None, every: bool = False) -> str:
    core = _core()
    cfg = core.settings()
    done = []
    with core.txn() as st:
        agents = _targets(core, st, agent=agent, model=model, every=every)
        for ag in agents:
            for _, s in st.states(ag):
                # a tool also takes its sensitive category types back (validated by parent_of, never a bare prefix)
                if type_key not in ("all", s.key) and fields.parent_of(s.key) != type_key:
                    continue
                if (type_key == "all" and s.tier == rule.T1 and not s.series and not s.provisional and s.wald >= 0
                        and not core.trusted(cfg, s, params.required_n(cfg["risks"], s.stakes), s.stakes)):
                    continue                                       # nothing earned or trusted to take back
                events = rule.revoke(s)
                st.put_state(ag, s)
                st.distrust(s.key)
                st.set_meta(core._due_key(ag, s.key), "")       # it re-earns from T1: every action is asked
                st.log({"event": "revoke", "agent": ag, "type": s.key})
                for ev in events:
                    st.log({**ev, "agent": ag})
                done.append(s.key if len(agents) == 1 else tr("cli.revoke.item_agent", type=s.key, agent=ag))
    who = agents[0] if len(agents) == 1 else tr("cli.count.agents", n=len(agents))
    return tr("cli.revoke.done", who=who, types=_join(done)) if done else tr("cli.revoke.nothing")


# ------------------------------------------------------------------------------------------------ undo
def _ago(seconds: float) -> str:
    s = max(0, int(seconds))
    return (tr("cli.ago.s", n=s) if s < 60 else tr("cli.ago.min", n=s // 60) if s < 3600 else
            tr("cli.ago.h", n=s // 3600))


def week_text(agent: str | None = None) -> str:
    """The last seven days, per agent: actions, questions asked, actions taken without a question, faults, undos and
    excuses, and what can still be undone or marked as seen. Reads only."""
    core = _core()
    st = core.store_()
    since = time.time() - 7 * 86400
    rows = [r for r in st.ledger() if r["at"] >= since and (r["event"] or {}).get("event") == "outcome"]
    agents = sorted({r["event"]["agent"] for r in rows})
    if agent:
        agents = [a for a in agents if a.startswith(agent)]
    lines = [tr("cli.week.title")]
    if not agents:
        return "\n".join(lines + [tr("cli.week.none")])
    for a in agents:
        mine = [r["event"] for r in rows if r["event"]["agent"] == a]
        by = lambda *srcs: sum(1 for e in mine if e["source"] in srcs)            # noqa: E731
        t = st.totals(a, since)
        mine_seq = {r["seq"] for r in rows if r["event"]["agent"] == a}
        recent = [r for r in st.ledger() if r["at"] >= since]
        excused_seq = {r["event"].get("seq") for r in recent if (r["event"] or {}).get("event") == "excuse"}
        undone = sum(1 for r in rows if r["event"]["agent"] == a and r["event"]["source"] == "undo"
                     and r["seq"] not in excused_seq)
        changes = sum(1 for r in recent if (r["event"] or {}).get("event") == "tier" and r["event"].get("agent") == a)
        spot = f'{by("spot") - sum(1 for e in mine if e["source"] == "spot" and e["result"] == "fault")}/{by("spot")}'
        asked = by("approval", "refusal", "spot", "timeout")
        lines.append(tr("cli.week.agent", agent=a, actions=t["actions"], asked=asked,
                        without=max(t["actions"] - asked, 0), faults=t["faults"], undone=undone,
                        excused=sum(1 for r in recent if (r["event"] or {}).get("event") == "excuse"
                                    and r["event"].get("seq") in mine_seq),
                        changes=changes, spot=spot, seen=by("seen"), unseen=by("unseen")))
    opened = st.open_credits(time.time() - core.UNDO_WINDOW)
    if opened and not core.simple():
        lines.append(tr("cli.week.open", n=len(opened), command="/tenure ok"))
    return "\n".join(lines)


def ok_list(session: str | None) -> str:
    """The act-then-tell actions still open (24 hours), of this conversation when known, with what each changed."""
    core = _core()
    st = core.store_()
    root = st.root_of(session) if session else None
    rows = st.open_credits(time.time() - core.UNDO_WINDOW, root)
    if not rows:
        return tr("cli.ok.none")
    cells = []
    for r in rows:
        entry = st.get_undo(r["undo_id"])
        d = undo.describe(entry["snap_id"], core.data_dir()) if entry and entry["snap_id"] else None
        what = (tr("cli.undo.more_files", file=d["file"], n=d["files"] - 1) if d and d["files"] > 1
                else d["file"] if d else "")
        cells.append([str(r["undo_id"]), time.strftime("%H:%M", time.localtime(r["at"])), r["type"], what])
    head = [tr("cli.col.number"), tr("cli.col.time"), tr("cli.col.type"), tr("cli.col.target")]
    return "\n".join([tr("cli.ok.title")] + ["  " + ln for ln in _table(head, cells)] + ["", tr("cli.ok.footer")])


def excuse_cmd(number: int | None) -> tuple[str, int]:
    """``excuse`` alone: the faults of the last minutes that can still be excused; with a number, excuse that one:
    the undo number of an undone action, or the number the notice gave after a refusal (``Store.number_fault``)."""
    core = _core()
    minutes = store.EXCUSE_WINDOW // 60
    plain = core.simple()
    if number is None:
        rows = core.excusable(core.store_())
        if not rows:
            return tr("simple.excuse.none" if plain else "cli.excuse.none", minutes=minutes), 0
        cause = {"refusal": tr("cli.excuse.source.refusal"), "undo": tr("cli.excuse.source.undo")}
        cells = [[str(r["n"]), time.strftime("%H:%M", time.localtime(r["at"])), r["type"], r["agent"],
                  cause.get(r["source"], r["source"])] for r in rows]
        lines = [tr("simple.excuse.title" if plain else "cli.excuse.title", minutes=minutes)]
        head = [tr("cli.col.number"), tr("cli.col.time"), tr("simple.col.kind" if plain else "cli.col.type"),
                tr("cli.col.agent"), tr("cli.col.cause")]
        lines += ["  " + ln for ln in _table(head, cells)]
        return "\n".join(lines + ["", tr("cli.excuse.footer")]), 0
    with core.txn() as st:
        try:
            return core.excuse(st, number), 0
        except ValueError as e:
            return str(e), 1


def undo_list() -> str:
    """The actions taken alone that can still be undone, newest first, with the file each would restore."""
    core = _core()
    st = core.store_()
    now = time.time()
    plain = core.simple()                             # simple mode: changes you can undo, a mistake when undone
    rows = st.db.execute("SELECT id, agent, type, at, snap_id FROM undo WHERE undone = 0 AND snap_id IS NOT NULL "
                         "AND at > ? ORDER BY id DESC LIMIT 20", (now - core.UNDO_WINDOW,)).fetchall()
    if not rows:
        return tr("simple.undo.none" if plain else "cli.undo.none", n=core.UNDO_WINDOW // 3600)
    total = st.db.execute("SELECT COUNT(*) FROM undo WHERE undone = 0 AND snap_id IS NOT NULL AND at > ?",
                          (now - core.UNDO_WINDOW,)).fetchone()[0]
    cells = []
    for uid, agent, key, at, snap in rows:
        d = undo.describe(snap, core.data_dir())
        what = ((tr("cli.undo.more_files", file=d["file"], n=d["files"] - 1) if d["files"] > 1 else d["file"])
                if d else tr("cli.undo.no_snapshot"))
        cells.append([str(uid), key, _plain(what), _ago(now - at), agent])
    lines = [tr("simple.undo.title" if plain else "cli.undo.title", n=core.UNDO_WINDOW // 3600)]
    head = ([tr("cli.col.number"), tr("simple.col.kind"), tr("simple.col.what"), tr("cli.col.when"),
             tr("cli.col.agent")] if plain else _cols("number", "type", "restores", "when", "agent"))
    lines += ["  " + ln for ln in _table(head, cells)]
    footer = (tr("cli.undo.footer_more", shown=len(rows), total=total, command="hermes tenure undo")
              if total > len(rows) else tr("cli.undo.footer", command="hermes tenure undo"))
    return "\n".join(lines + ["", footer])


def undo_action(entry_id: int) -> str:
    """Restore the files of an action taken alone: the hooks module's ``undo_entry``, the one implementation. The
    returned text's ``ok`` attribute is False when nothing was undone."""
    core = _core()
    with core.txn() as st:
        msg = core.undo_entry(st, entry_id)
    msg.cleanup()                                   # the snapshot goes only once the transaction has committed
    return msg


# ------------------------------------------------------------------------------------------------ home, trust
HOME_UNDO = 10                                   # undoable actions /tenure shows, newest first
_SAID = {"file:write": "kind.file_write", "file:write-outside": "kind.file_write_outside",
         "file:shell": "kind.file_shell", "file:shell:rm": "kind.file_shell_rm", "memory:write": "kind.memory_write",
         "file:unknown": "kind.file_unknown",
         "delegate:task": "kind.delegate_task", "shell:complex": "kind.shell_complex",
         "shell:stdin-code": "kind.shell_stdin_code", "code:execute": "kind.code_execute"}   # kinds with a label of their own


def _plain(text: str) -> str:
    """Control and format characters (a newline, a bidi override) as U+FFFD, as the end-of-turn line shows them."""
    return "".join("\ufffd" if unicodedata.category(c) in ("Cc", "Cf") else c for c in text)


def kind_label(key: str) -> str:
    """A kind of action in plain words, shown next to its key in simple mode: ``file:write`` is "file edits in the
    project", ``shell:docker`` "docker commands", ``shell:git:push`` "git push", ``mcp:github:create_issue``
    "Github: create_issue"; a category kind adds "touching identity/access fields". An unknown key is its own
    label."""
    split = fields._split(key)
    base = split[0] if split else key
    parts = base.split(":")
    label = None
    if base in _SAID:
        label = tr(_SAID[base])
    elif parts[0] == "shell" and len(parts) >= 2 and parts[1]:
        prog = parts[1]
        if len(parts) == 2:
            label = tr("kind.shell", prog=prog)
        elif parts[-1] == "inline":
            label = tr("kind.shell_inline", prog=prog)
        elif parts[-1] == "new-dependency":
            label = tr("kind.shell_new_dependency", prog=prog)
        else:
            label = " ".join(parts[1:])
    elif parts[0] == "mcp" and len(parts) >= 3 and parts[1]:
        label = tr("kind.mcp", server=parts[1][:1].upper() + parts[1][1:], tool=":".join(parts[2:]))
    if label is None:
        return key
    if split:
        label = tr("kind.fields", kind=label, fields="/".join(split[1]))
    return label


def _kind_named(key: str, reason: str = "") -> str:
    """``file:write (file edits in the project)``, with a short reason after the label when given."""
    label = kind_label(key)
    inner = label if label != key else ""
    if reason:
        inner = f"{inner}: {reason}" if inner else reason
    return f"{key} ({inner})" if inner else key


def _undo_label(core, st, rows_by_undo: dict, uid: int, snap: str | None, key: str) -> str:
    """What an undoable action did, as the end-of-turn line shows it: the command's first line, secrets masked
    (remembered in memory by this process only), else the files its undo restores, else nothing; a chained line adds
    how many files its undo holds, "(+N files)". Control and format characters become U+FFFD, as in that line."""
    r = rows_by_undo.get(uid)
    what = core.summary_of(st.path, r["n"], r["at"]) if r else ""
    if what.startswith(key + ": "):
        what = what[len(key) + 2:]
    what = what.strip().splitlines()[0] if what.strip() else ""
    count = st.get_meta(core.UNDO_FILES + str(uid)) if what else ""     # a chained line: the files of its one undo
    if not what and snap:
        d = undo.describe(snap, core.data_dir())
        if d:
            what = tr("cli.undo.more_files", file=d["file"], n=d["files"] - 1) if d["files"] > 1 else d["file"]
    what = _plain(what)
    cap = core.LABEL_CAP
    what = what if len(what) <= cap else what[:cap - 1] + "\u2026"
    return f"{what} ({tr('simple.turn.count', n=int(count))})" if count and count.isdigit() else what


def _fixed(cfg: dict, s: rule.TypeState) -> str | None:
    """Simple mode: why a kind always asks whatever its record, or None: it leaves the machine (out), high stakes
    (high), or the settings cap its stakes (capped). Read from the kind alone, never from its state."""
    if not params.simple_covers(s.key):
        return "out"
    if s.stakes == "high":
        return "high"
    if params.required_n(cfg["risks"], s.stakes) is None:
        return "capped"
    return None


def _pending(core, st, agent: str, key: str) -> int:
    """Watched actions of a kind still inside their undo window, each counting toward its series once it closes."""
    if st is None:
        return 0
    return sum(1 for r in st.open_credits(time.time() - core.UNDO_WINDOW) if r["agent"] == agent and r["type"] == key)


def _kind_info(core, cfg: dict, s: rule.TypeState, st=None, agent: str | None = None) -> dict:
    """Where a kind stands, for /tenure and /tenure trust. ``state``: free, pinned (asks, the person's choice), out,
    high, capped (always ask), noundo (free, but asks because tenure cannot undo it), held (its parent's mistake holds
    it), doubted (a verifier's doubt: its next action asks), watched or ask; ``base``: the same without held and
    doubted; ``left``: actions kept, or approvals, still needed to be free (watched: minus the watched actions already
    waiting out their undo window). Study mode: free, capped, watched or ask, with the successes still needed toward
    acting alone. ``st`` and ``agent`` add what the record alone does not say (simple mode)."""
    n = params.required_n(cfg["risks"], s.stakes)
    info = {"n": n, "left": 0, "held": None, "doubted": False}
    if not core.simple(cfg):
        eff = effective_tier(s, n)
        if n is None:
            state = "capped"
        elif eff == rule.T3 or core.trusted(cfg, s, n, s.stakes):
            state = "free"
        else:
            state = "watched" if eff == rule.T2 else "ask"
            info["left"] = max(rule.required(s, n) - s.series, 1)
        return {**info, "state": state, "base": state}
    fixed = _fixed(cfg, s)
    if s.pinned:
        base = "pinned"
    elif fixed:
        base = fixed
    elif core.trusted(cfg, s, n, s.stakes):
        base = ("noundo" if st is not None and not s.owner_freed and not rule.trust_covers(s.key)
                and st.get_meta(core.NOUNDO + s.key) else "free")
    elif rule.decide(s, n, cfg["spot"], suspended=False, rng=core._NoSpot, mode=rule.SIMPLE) == rule.NOTIFY:
        base = "watched"
        info["left"] = n - s.series - _pending(core, st, agent, s.key)
    else:
        base = "ask"
        info["left"] = max(n - s.series, 1)
    state = base
    if st is not None and agent and base in ("free", "noundo", "watched", "ask"):
        info["held"] = core._held_by(st, agent, s.key)
        info["doubted"] = st.doubted(agent, s.key)
        state = "held" if info["held"] else "doubted" if info["doubted"] else base
    return {**info, "state": state, "base": base}


def _kind_state(core, cfg: dict, s: rule.TypeState, st=None, agent: str | None = None) -> tuple[str, int]:
    """(state, left) of ``_kind_info``."""
    info = _kind_info(core, cfg, s, st, agent)
    return info["state"], info["left"]


def _short_why(info: dict) -> str:
    """Why a kind the record calls free asks anyway, in a few words for /tenure."""
    if info["state"] == "noundo":
        return tr("home.why.noundo")
    if info["state"] == "held":
        return tr("home.why.held", held=info["held"])
    if info["state"] == "doubted":
        return tr("home.why.doubted")
    return ""


def home_text(prefix: str = "/tenure") -> str:
    """``/tenure`` alone, simple mode: what the agent did lately in plain words. The actions that can still be undone
    (newest first, at most ten), how many ran without asking today (local time), which kinds are watched or ask
    first and why, and the two commands. Study mode keeps ``status``. Reads only."""
    core = _core()
    cfg = core.settings()
    if not core.simple(cfg):
        return status_text()
    st = core.store_()
    now = time.time()
    hours = core.UNDO_WINDOW // 3600
    since = now - core.UNDO_WINDOW
    rows = st.db.execute("SELECT id, type, at, snap_id FROM undo WHERE undone = 0 AND snap_id IS NOT NULL "
                         "AND at > ? ORDER BY id DESC LIMIT ?", (since, HOME_UNDO)).fetchall()
    total = st.db.execute("SELECT COUNT(*) FROM undo WHERE undone = 0 AND snap_id IS NOT NULL AND at > ?",
                          (since,)).fetchone()[0]
    lines = [tr("home.title")]
    why = core.nobody_answers()
    if why:
        lines.append(tr("cli.status.paused", why=why))
    if not cfg["enabled"]:
        lines.append(tr("cli.status.disabled", setting=f"{SETTINGS}.enabled"))
    if rows:
        by_undo = {r["undo_id"]: r for r in st.recent_rows(None, limit=500) if r["undo_id"] is not None}
        cells = [[str(uid), key, _undo_label(core, st, by_undo, uid, snap, key), _ago(now - at)]
                 for uid, key, at, snap in rows]
        lines.append(tr("home.undo_title", n=hours))
        lines += ["  " + ln for ln in _table([tr("cli.col.number"), tr("simple.col.kind"), tr("simple.col.what"),
                                               tr("cli.col.when")], cells)]
        if total > len(rows):
            lines.append("  " + tr("home.undo_more", n=total - len(rows), command=f"{prefix} undo"))
    else:
        lines.append(tr("home.undo_none", n=hours))
    lines.append(tr("home.today", n=st.totals(None, now)["alone"]))       # days are local (store.bump)
    watched, asks = [], []
    agent = _agent(core, None)
    for _, s in st.states(agent):
        info = _kind_info(core, cfg, s, st, agent)
        if info["state"] == "watched":
            watched.append(_kind_named(s.key))
        elif info["state"] in ("ask", "pinned"):
            asks.append(_kind_named(s.key))
        elif info["state"] in ("noundo", "held", "doubted"):
            asks.append(_kind_named(s.key, _short_why(info)))
    if watched:
        lines.append(tr("home.watched", types=_join(watched)))
    if asks:
        lines.append(tr("home.asks", types=_join(asks)))
    lines += ["", tr("home.footer", prefix=prefix)]
    return "\n".join(lines)


def _state_parts(core, cfg: dict, s: rule.TypeState, prefix: str, info: dict | None = None,
                 hidden: bool = False) -> list[tuple[str, dict]]:
    """What ``/tenure trust`` says of a kind, as (catalog key, values) pairs read one after the other: why it asks or
    is watched, and what brings it back. The dashboard shows the same pairs, so the same numbers; ``hidden``: it shows
    the kind's name redacted, so a command naming it could not be typed (the page says how to see the name)."""
    info = info or _kind_info(core, cfg, s)
    state, left = info["state"], info["left"]
    if state == "pinned":
        if hidden:
            return [("trust.state.pinned_hidden", {})]
        return [("trust.state.pinned", {"command": f"{prefix} trust {s.key}"})]
    if state in ("high", "capped") and s.key == "file:unknown" and core.simple(cfg):
        try:
            why = core.store_().get_meta(core.UNKNOWN_WHY) or "path"     # what the last such command hid
        except Exception:
            why = "path"
        return [("trust.state.unknown",
                 {"reason": tr(f"unknown.why.{why if why in ('glob', 'variable') else 'path'}")})]
    if state in ("out", "high", "capped", "noundo", "doubted"):
        return [(f"trust.state.{state}", {})]
    if state == "held":
        return [("trust.state.held", {"held": info["held"]})]
    if not core.simple(cfg):
        return [("trust.state.study", {"tier": tier_name(effective_tier(s, params.required_n(cfg["risks"], s.stakes))),
                                       "n": left})]
    n = info["n"]
    if state == "ask" and rule._middle(s) and s.series + core._to_t2(s) < n:
        # a reversible kind: approvals first bring it back to watched (the Wald score, as _simple_success moves it,
        # the series counting each one), then actions left undone through their window finish the series
        k = core._to_t2(s)
        return [("trust.state.ask_watched", {"n": k}), ("trust.state.then_free", {"n": n - s.series - k})]
    if state == "watched" and left <= 0:                # enough watched actions already wait out their window
        return [("trust.state.watched_wait", {"hours": core.UNDO_WINDOW // 3600})]
    return [(f"trust.state.{state}", {"n": left})]


def _state_text(core, cfg: dict, s: rule.TypeState, prefix: str, info: dict | None = None) -> str:
    return " ".join(tr(key, **values) for key, values in _state_parts(core, cfg, s, prefix, info))


def _trust_agent(core, st, model: str | None, session: str | None) -> str:
    """The agent ``trust`` acts on: the one ``--model`` names, else the conversation's own (the slash command knows
    its session), else the profile's last active agent."""
    if model:
        return _targets(core, st, model=model)[0]
    if session:
        return core.agent_of(session)
    return _targets(core, st)[0]


def _resolve_kind(core, cfg: dict, st, agent: str, kind: str, known: dict, prefix: str) -> str:
    """The recorded kind ``trust`` names: the key itself, else the one kind whose key ends with it (``git:push``,
    ``docker``, ``rm``), else the one ``shell:`` kind of that program (``git``). Several: the candidates are listed,
    nothing is written. None: the family it would be (``shell:docker``) has no record."""
    if kind in known:
        return kind
    cands = sorted(k for k in known if k.endswith(":" + kind))
    if not cands and ":" not in kind:
        cands = sorted(k for k in known if k.split(":")[:2] == ["shell", kind])
    if len(cands) == 1:
        return cands[0]
    if cands:
        raise CliError(tr("trust.ambiguous", kind=kind, types=_join(cands), command=f"{prefix} trust"))
    family = kind if ":" in kind else f"shell:{kind}"
    others = [k for k, x in known.items() if _kind_state(core, cfg, x, st, agent)[0] != "free"]
    raise CliError(tr("trust.unknown", type=family, agent=agent, types=_join(sorted(others)) or "-"))


def trust_list(prefix: str = "/tenure", model: str | None = None, session: str | None = None) -> str:
    """``/tenure trust`` alone: the kinds of action that ask, or are watched, in plain words, with why and what brings
    each back. Reads only."""
    core = _core()
    cfg = core.settings()
    st = core.store_()
    plain = core.simple(cfg)
    agent = _trust_agent(core, st, model, session)
    cells = []
    for _, s in st.states(agent):
        info = _kind_info(core, cfg, s, st if plain else None, agent)
        if info["state"] != "free":
            cells.append([_kind_named(s.key) if plain else s.key, _state_text(core, cfg, s, prefix, info)])
    if not cells:
        return tr("trust.none", agent=agent)
    head = [tr("simple.col.kind") if plain else tr("cli.col.type"), tr("simple.col.state")]
    lines = [tr("trust.title", agent=agent)] + ["  " + ln for ln in _table(head, cells)]
    if plain:
        lines += ["", tr("trust.footer", command=f"{prefix} trust")]
    else:
        lines += ["", tr("trust.study", command=f"{prefix} mode simple")]
    return "\n".join(lines)


def _for_agent(st, agent: str, text: str) -> str:
    """Name the agent when the profile has several: the word was given for one of them."""
    return text + " " + tr("trust.for", agent=agent) if len(st.agents()) > 1 else text


def trust_set(kind: str, to: str, prefix: str = "/tenure", model: str | None = None,
              session: str | None = None) -> str:
    """``/tenure trust KIND`` (free it now) or ``/tenure trust KIND ask`` (it asks first until freed again): a
    person's word, simple mode only. A kind that asks only because tenure cannot undo it is freed too: it then runs
    without an undo (the ``trust`` event says ``undo: false``); any other kind keeps its undo where its files can be
    saved, and asks where they cannot. Refused for a kind simple mode never frees (what leaves the machine, high stakes, a capped
    kind), whatever its state; asking those to ask writes nothing (they always do). A kind held by its parent, or
    doubted by a verifier, is explained. Code downloaded from the internet and run at once is never freed, record or
    not. Raises CliError with the owner's message, nothing written, when refused."""
    core = _core()
    cfg = core.settings()
    if not core.simple(cfg):
        raise CliError(tr("trust.study", command=f"{prefix} mode simple"))
    net = core.classify.NET_CODE[0]
    if kind in (net, net.split(":", 1)[1]):
        if to == rule.FREE:
            raise CliError(tr("trust.refused.net_code", type=net))
        return tr("trust.always", type=net)
    with core.txn() as st:
        agent = _trust_agent(core, st, model, session)
        known = {s.key: s for _, s in st.states(agent)}
        kind = _resolve_kind(core, cfg, st, agent, kind, known, prefix)
        s = known[kind]
        fixed = _fixed(cfg, s)
        if fixed:
            if to == rule.FREE:
                raise CliError(tr(f"trust.refused.{fixed}", type=kind, command=f"{prefix} setup"))
            return tr("trust.always", type=kind)
        info = _kind_info(core, cfg, s, st, agent)
        held, doubted = info["held"], info["doubted"]
        notes = (([tr("trust.held", type=kind, held=held, command=f"{prefix} trust {held}")] if held else [])
                 + ([tr("trust.doubted", type=kind)] if doubted else []))
        if to == rule.PIN:
            if info["base"] == "pinned":
                return tr("trust.already_pinned", type=kind, command=f"{prefix} trust {kind}")
            try:
                core.owner_trust(st, cfg, agent, s, rule.PIN)
            except ValueError as e:
                raise CliError(str(e))
            return _for_agent(st, agent, tr("trust.pinned", type=kind, command=f"{prefix} trust {kind}"))
        if info["base"] == "free":
            return " ".join(notes) if notes else tr("trust.already_free", type=kind)
        children = [k for k in known if k != kind and fields.parent_of(k) == kind and core._held_by(st, agent, k)]
        noundo = info["base"] == "noundo"                  # it asked only because tenure cannot undo it
        try:
            core.owner_trust(st, cfg, agent, s, rule.FREE, undo=not noundo)
        except ValueError as e:
            raise CliError(str(e))
        released = [k for k in children if not core._held_by(st, agent, k)]
        back = f"{prefix} trust {kind} ask"
        if noundo:
            words = [tr("trust.freed_noundo", type=kind, command=back)]
        else:
            words = [tr("trust.freed" if rule._middle(s) else "trust.freed_asks", type=kind, command=back)]
        if released:
            words.append(tr("trust.released", types=_join(released)))
        return _for_agent(st, agent, " ".join(words + notes))


def help_text(prefix: str = "/tenure") -> str:
    return tr("cli.help", prefix=prefix)


def advanced_text(prefix: str = "/tenure") -> str:
    return tr("cli.advanced.title", command=prefix) + "\n" + tr("cli.usage").rstrip("\n")


# ------------------------------------------------------------------------------------------------ passport
def passport_cmd(agent: str | None = None, out: str = "", redact: bool = True) -> str:
    core = _core()
    cfg = core.settings()
    if core.simple(cfg):
        return tr("simple.passport", command="hermes tenure mode study")
    with core.txn() as st:
        name = _targets(core, st, agent=agent)[0]
        if not st.states(name):
            return tr("cli.passport.none", agent=name)
        core.sync_settings(st, cfg)                    # the ledger holds the settings the states were computed with
        core._credit_due(st, cfg)                      # credits whose undo window closed, before the record is read
        p = passport.build(st, name, cfg, core.data_dir(), redact=redact)
    if not out:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
        out = os.path.join(core.data_dir(), f"passport-{stem}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, sort_keys=True)
        f.write("\n")
    lines = [tr("cli.passport.written", path=out),
             "  " + tr("cli.passport.summary", agent=name, types=tr("cli.count.types", n=len(p["types"])),
                       redaction=tr("cli.passport.redacted" if redact else "cli.passport.not_redacted"),
                       signature=tr("cli.passport.signed" if p["signature"] else "cli.passport.unsigned"),
                       head=p["ledger"]["head"][:16], events=tr("cli.count.events", n=p["ledger"]["count"])),
             tr("cli.passport.check", command="hermes tenure verify", path=out)]
    if not redact:
        lines.append(tr("cli.passport.warning"))
    return "\n".join(lines)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CliError(tr("cli.err.unreadable", path=path, error=getattr(e, "strerror", None) or e))


def _load_json(path: str):
    try:
        return json.loads(_read(path))
    except ValueError as e:
        raise CliError(tr("cli.err.not_json", path=path, error=e))


def _load_ledger(path: str) -> list[dict]:
    text = _read(path)
    try:
        if text.lstrip().startswith("["):
            return json.loads(text)
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except ValueError as e:
        raise CliError(tr("cli.err.not_ledger", path=path, error=e))


def verify_cmd(passport_path: str, ledger_path: str = "", key: str = "") -> tuple[str, int]:
    try:
        p = _load_json(passport_path)
        rows = _load_ledger(ledger_path) if ledger_path else None
    except CliError as e:
        return str(e), 1
    problems = passport.verify(p, rows)
    if key and isinstance(p, dict) and str(p.get("public_key", "")).lower() != key.strip().lower():
        problems = problems + [tr("cli.verify.key_differs", option="--key")]
    if not problems:
        lines = [tr("cli.verify.ok", types=tr("cli.count.types", n=len(p["types"])),
                    events=tr("cli.count.ledger_events", n=p["ledger"]["count"]))]
        if not key:
            lines.append(tr("cli.verify.pin", option="--key"))
        if rows and len(rows) > p["ledger"]["count"]:
            changed = passport.changes_since(p, rows)
            after = len(rows) - p["ledger"]["count"]
            lines.append(tr("cli.verify.after_changed", n=after, changes="; ".join(changed)) if changed else
                         tr("cli.verify.after", n=after))
        return "\n".join(lines), 0
    others = [x for x in problems if x != passport.NO_LEDGER]
    lines = []
    if others:
        lines.append(tr("cli.verify.problems", n=len(others)))
        lines += [f"  - {x}" for x in others]
    if passport.NO_LEDGER in problems:
        lines.append(tr("cli.verify.no_ledger") if not others else tr("cli.verify.no_ledger_types"))
    return "\n".join(lines), 1


# ------------------------------------------------------------------------------------------------ the rest
def anchor() -> str:
    return passport.anchor_line(_core().store_())


def export(path: str = "") -> str:
    core = _core()
    path = path or os.path.join(core.data_dir(), f"evidence-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    n = core.store_().export(path)
    return tr("cli.export.written", path=path, n=n, command="hermes tenure verify PASSPORT")


def share(out: str = "") -> tuple[str, int]:
    """Write the signed community record to a file the owner publishes himself: nothing is sent."""
    core = _core()
    cfg = core.settings()
    if core.simple(cfg):
        return tr("simple.passport", command="hermes tenure mode study"), 0
    st = core.store_()
    rows = community.counts(st)
    if not rows:
        return tr("cli.share.none"), 0
    try:
        rec = community.share_record(st, cfg, core.data_dir())
    except RuntimeError:
        return tr("cli.share.unsigned"), 1
    out = out or os.path.join(os.getcwd(), f"tenure-record-{rec['date']}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    table = _table(_cols("model", "provider", "type", "record"),
                   [[r["model"], r["provider"], r["family"], _record(r["faults"], r["successes"])] for r in rec["rows"]])
    lines = [tr("cli.share.written", path=out), "",
             tr("cli.share.contains", rows=tr("cli.share.rows", n=len(rec["rows"])), date=rec["date"],
                version=rec["tenure"], rule=rec["rule"], preset=rec["preset"]), "",
             *["  " + x for x in table], "",
             tr("cli.share.never"),
             tr("cli.share.not_sent"),
             tr("cli.share.how", repo=f"github.com/{community.REPO}")]
    return "\n".join(lines), 0


def _save_setting(core, key: str, value) -> str | None:
    """Write one plugin setting through Hermes, then log it in the ledger: None on success, else the reason."""
    if core.ST.ctx is None:
        return tr("cli.setup.no_context")
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
    # manual and smart (the Hermes default) both work: tenure's own approvals skip the smart guardian and
    # always reach a person. Only off lets Hermes settle every ask by itself.
    if mode == "off":
        warn = tr("cli.setup.paused", setting="approvals.mode") + "\n"
    if not name:
        return warn + presets_text(cfg["spot"])
    name = name.strip().lower()
    if name not in params.PRESETS:
        return tr("cli.setup.unknown", name=repr(name)) + " " + presets_text(cfg["spot"])
    err = _save_setting(core, "preset", name) or _save_setting(core, "risks", {})   # a preset replaces own risks
    if err:
        return warn + tr("cli.setup.save_failed", error=err, setting=f"{SETTINGS}.preset", name=name)
    return warn + tr("cli.setup.in_force", name=name) + "\n" + presets_text(core.settings()["spot"])


def start(value: str) -> str:
    core = _core()
    err = _save_setting(core, "start", value)
    if err:
        return tr("cli.start.save_failed", error=err, setting=f"{SETTINGS}.start", value=value)
    return tr("cli.start.trusted") if value == "trusted" else tr("cli.start.probation")


def mode(value: str) -> str:
    """Simple or study mode, saved like the other settings: the ledger logs the change and every record is replayed
    under the new mode."""
    core = _core()
    err = _save_setting(core, "mode", value)
    if err:
        return tr("simple.mode.save_failed", error=err, setting=f"{SETTINGS}.mode", value=value)
    return tr("simple.mode.simple" if value == rule.SIMPLE else "simple.mode.study")


def strict(value: str) -> str:
    core = _core()
    on = value == "on"
    err = _save_setting(core, "strict", on)
    if err:
        return tr("cli.strict.save_failed", error=err, setting=f"{SETTINGS}.strict", value=str(on).lower())
    return tr("cli.strict.on") if on else tr("cli.strict.off")


def _allowlist() -> list[str] | None:
    try:
        from hermes_cli import config as hermes_config
        raw = (hermes_config.load_config() or {}).get("command_allowlist") or []
    except Exception:
        return None
    return [str(x) for x in raw] if isinstance(raw, (list, tuple, set)) else []


_DEAD = re.compile(r"^(plugin_rule:)?tenure:")


def cleanup() -> str:
    """List, never edit: tenure keys in Hermes' permanent allowlist. Every ask uses a one-off key, so an entry
    there can never match again; it only clutters the list."""
    allow = _allowlist()
    if allow is None:
        return tr("cli.cleanup.no_config", module="hermes_cli.config")
    dead = [k for k in allow if _DEAD.match(k)]
    if not dead:
        return tr("cli.cleanup.none", n=len(allow))
    keep = [k for k in allow if not _DEAD.match(k)]
    return "\n".join([tr("cli.cleanup.dead", n=len(dead), setting="command_allowlist", total=len(allow)),
                      *[f"  {k}" for k in dead], "",
                      tr("cli.cleanup.remove"),
                      f"  hermes config set command_allowlist {shlex.quote(json.dumps(keep))}"])


# ------------------------------------------------------------------------------------------------ parsing
class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)

    def exit(self, status=0, message=None):
        raise _Usage(message or "")


def _add_subcommands(subparser) -> None:
    """Every command keeps its name; the help shows three (``help_text``), ``advanced`` lists the others."""
    subs = subparser.add_subparsers(dest="tenure_command", help=argparse.SUPPRESS)
    p = subs.add_parser("undo", help="Alone, what can still be undone; with a number, put that action back")
    p.add_argument("id", type=int, nargs="?", help="the number from the notice; without it, the list")
    p = subs.add_parser("trust", help="Kinds of action that are not free; with a kind, free it now (ask: it always "
                                      "asks first)")
    p.add_argument("kind", nargs="?", help="an action type, e.g. file:write; without it, the list")
    p.add_argument("level", nargs="?", choices=(rule.PIN,), help="ask: the kind asks first until you free it")
    p.add_argument("--model", help="Start of an agent string (default: the last active agent)")
    subs.add_parser("advanced", help="Every other command, one line each")
    p = subs.add_parser("status", help="What each agent has earned, per action type")
    p.add_argument("--profile", help="Another Hermes profile (read only)")
    p.add_argument("--model", help="Start of an agent string, e.g. gpt-5")
    p.add_argument("--all", action="store_true", help="Every agent with a record")
    p = subs.add_parser("card", help="The passport as a short text card to paste in a chat or a post")
    p.add_argument("--model", help="Start of an agent string, e.g. gpt-5")
    p.add_argument("--no-redact", action="store_true", help="Keep script, target and alias names readable")
    p = subs.add_parser("setup", help="The three recommendations; with a name, use it")
    p.add_argument("preset", nargs="?", default="", help="careful, balanced or fast")
    subs.add_parser("explain", help="How tenure decides and what the numbers guarantee")
    p = subs.add_parser("models", help="Each model's verified record on your own work")
    p.add_argument("--type", help="One action type")
    p = subs.add_parser("week", help="The last seven days: actions, questions, faults, undos, what is still open")
    p.add_argument("--model", help="Start of an agent string")
    p = subs.add_parser("ok", help="Seen and fine: the act-then-tell actions you name count now; alone, the open ones")
    p.add_argument("ids", type=int, nargs="*", help="the undo numbers of the actions you saw; without them, the list")
    p = subs.add_parser("excuse", help="Take back a fault of the last 10 minutes that was not the agent's mistake")
    p.add_argument("id", type=int, nargs="?", help="the number from the notice; without it, the list")
    p = subs.add_parser("flag", help="Report an error the agent made on its own: counts as a fault, the type drops at "
                                     "least one tier; alone, the last numbered actions")
    p.add_argument("type", nargs="?", help="an action type, or an action's number; without it, the last actions")
    p.add_argument("note", nargs="*")
    p.add_argument("--model", help="Start of an agent string (default: the last active agent); not with a number")
    p.add_argument("--call", help="A verifier: the tool call id of the action (with --session)")
    p.add_argument("--session", help="A verifier: the Hermes session id of the action (with --call)")
    p.add_argument("--doubt", action="store_true",
                   help="A verifier's doubt instead of a fault: the next action of that kind asks first")
    p = subs.add_parser("revoke", help="Take earned autonomy back (a type, or all)")
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
    p.add_argument("--key", default="", help="The public key you expect (hex): anything else is reported")
    subs.add_parser("anchor", help="One line to publish: the ledger's head, date and length")
    p = subs.add_parser("export", help="Write the evidence ledger as hash-chained JSON lines")
    p.add_argument("path", nargs="?", default="")
    p = subs.add_parser("start", help="trusted: no question before a type's first mistake; probation: the study's start")
    p.add_argument("value", choices=params.STARTS)
    p = subs.add_parser("strict", help="Strict mode: a new model starts with an empty record")
    p.add_argument("value", choices=("on", "off"))
    p = subs.add_parser("mode", help="simple (default): free, watched after a mistake, asks after a second; "
                                     "study: the preregistered rule, with spot checks, guarantee and passport")
    p.add_argument("value", choices=params.MODES)
    subs.add_parser("cleanup", help="List dead tenure keys in Hermes' permanent allowlist")
    p = subs.add_parser("share", help="Write a signed record of counts for the community benchmark (nothing is sent)")
    p.add_argument("--out", default="", help="Output file (default: tenure-record-<date>.json here)")


def _win_console() -> bool:
    """Windows: stdin is a real console. ``isatty()`` is also true for the NUL device (``< NUL``), a character device
    like a console; only a console answers GetConsoleMode."""
    try:
        import ctypes
        import msvcrt
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
    except Exception:
        return False


def interactive() -> bool:
    """A person at a real terminal: stdin is a tty, and on Windows a console (``_win_console``). The agent's own
    processes are refused before this (``agent_process``), whatever their terminal."""
    try:
        if not sys.stdin.isatty():
            return False
    except Exception:
        return False
    return _win_console() if sys.platform == "win32" else True


def _usage() -> str:
    """A command line that does not parse: every command, the hidden ones included."""
    return advanced_text("hermes tenure")


def execute(ns) -> tuple[str, int]:
    """(text, exit code) for a parsed command line."""
    def g(name, default=None):
        return getattr(ns, name, default)
    cmd = g("tenure_command") or "home"
    prefix = "/tenure" if g("tenure_slash") else "hermes tenure"
    try:
        if cmd == "home":
            return home_text(prefix), 0
        if cmd == "advanced":
            return advanced_text(prefix), 0
        if cmd == "trust":
            if not g("kind"):
                if g("level"):
                    return help_text(prefix), 1
                return trust_list(prefix, model=g("model"), session=g("tenure_sid")), 0
            if _core().agent_process():
                raise CliError(tr("ask.person_only"))        # run by the agent's own tools or code: never, slash or not
            if not g("tenure_slash") and not interactive():
                words = " ".join(x for x in (g("kind"), g("level")) if x)
                raise CliError(tr("trust.terminal", slash=f"/tenure trust {words}",
                                  cli=f"hermes tenure trust {words}"))       # a script or the agent's own terminal
            why = _core().nobody_answers()
            if why:
                raise CliError(tr("trust.nobody", why=why))
            return trust_set(g("kind"), rule.PIN if g("level") else rule.FREE, prefix, model=g("model"),
                             session=g("tenure_sid")), 0
        if cmd == "status":
            return status_text(profile=g("profile"), model=g("model"), every=bool(g("all"))), 0
        if cmd == "card":
            return card_text(model=g("model"), redact=not g("no_redact", False)), 0
        if cmd == "setup":
            return setup_preset(g("preset", "")), 0
        if cmd == "explain":
            return explain_text(), 0
        if cmd == "models":
            return models_text(g("type")), 0
        if cmd == "week":
            return week_text(g("model")), 0
        if cmd in ("ok", "excuse") and _core().agent_process():
            raise CliError(tr("ask.person_only"))            # run by the agent's own tools or code: never, slash or not
        if cmd == "ok":
            if not g("tenure_slash") and not interactive():
                raise CliError(tr("cli.ok.terminal"))         # a script or the agent's own terminal: never
            core = _core()
            if core.simple():                                 # harmless, and not needed in simple mode
                return tr("simple.ok"), 0
            if not g("ids"):                                  # never a blanket "all": the list, to name what you saw
                return ok_list(g("tenure_session")), 0
            with core.txn() as st:
                try:
                    return core.seen(st, list(g("ids"))), 0
                except ValueError as e:
                    return str(e), 1
        if cmd == "excuse":
            if g("id") is not None and not g("tenure_slash") and not interactive():
                raise CliError(tr("cli.excuse.terminal"))    # a script or the agent's own terminal: never
            return excuse_cmd(g("id"))
        if cmd == "undo":
            if g("id") is None:
                return undo_list(), 0
            text = undo_action(g("id"))
            return text, 0 if text.ok else 1
        if cmd == "flag":
            what, note = g("type"), " ".join(g("note") or [])
            if g("call") or g("session") or g("doubt"):          # a verifier (#6): by call id, or a doubt
                if g("model") or note:
                    return _usage(), 1
                verdict = "doubt" if g("doubt") else "fault"
                if g("call") or g("session"):
                    if what is not None or not (g("call") and g("session")):
                        return _usage(), 1
                    return report(verdict, session=g("session"), call=g("call")), 0
                if what is None or not re.fullmatch(r"[0-9]{1,18}", what):
                    return _usage(), 1
                return report(verdict, n=int(what)), 0
            if what is None:
                if g("model"):
                    return _usage(), 1
                return flag_list(g("tenure_session"), g("tenure_command_name") or "hermes tenure flag"), 0
            if re.fullmatch(r"[0-9]+", what):
                if g("model"):
                    raise CliError(tr("cli.flag.action_model", n=what))     # the number already names the agent
                if len(what) > 18:      # past any real number; int() of thousands of digits raises ValueError
                    raise CliError(tr("cli.flag.action_unknown", n=what[:18] + "\u2026",
                                      hours=store.RECENT_WINDOW // 3600))
                return flag_action(int(what), note), 0
            return flag(what, note, model=g("model")), 0
        if cmd == "revoke":
            return revoke(g("type"), model=g("model"), every=bool(g("all"))), 0
        if cmd == "passport":
            return passport_cmd(agent=g("agent"), out=g("out", ""), redact=not g("no_redact", False)), 0
        if cmd == "verify":
            return verify_cmd(g("passport"), g("ledger", ""), g("key", "") or "")
        if cmd == "anchor":
            return anchor(), 0
        if cmd == "export":
            return export(g("path", "")), 0
        if cmd == "start":
            return start(g("value")), 0
        if cmd == "strict":
            return strict(g("value")), 0
        if cmd == "mode":
            return mode(g("value")), 0
        if cmd == "cleanup":
            return cleanup(), 0
        if cmd == "share":
            return share(g("out", "") or "")
    except CliError as e:
        return str(e), 1
    return help_text(prefix), 1


def slash(raw_args="", **kwargs):
    try:
        parser = _Parser(prog="/tenure", add_help=False)
        _add_subcommands(parser)
        if (raw_args or "").strip() in ("help", "-h", "--help"):
            return help_text("/tenure")
        try:
            raw = raw_args or ""
            ns = parser.parse_args(shlex.split(raw.replace("\\", "/") if os.name == "nt" else raw))
        except _Usage as e:
            return (f"tenure: {e}\n" if str(e) else "") + help_text("/tenure")
        # `flag` alone lists the current session (none: the profile); Hermes hands the session id in
        ns.tenure_session = _core().anon(kwargs.get("session_id") or kwargs.get("session_key")) or None
        ns.tenure_sid = str(kwargs.get("session_id") or "") or None     # trust acts on this conversation's agent
        ns.tenure_command_name = "/tenure flag"
        ns.tenure_slash = True                             # typed in the chat (the agent's own process still refused)
        return execute(ns)[0]
    except Exception as e:
        return f"tenure: {type(e).__name__}: {e}"


def setup(subparser):
    """``hermes tenure --help`` shows the three commands and where the others are, nothing else."""
    _add_subcommands(subparser)
    try:
        subparser.formatter_class = argparse.RawDescriptionHelpFormatter
        subparser.usage = "hermes tenure [undo [N] | trust [KIND [ask]]]"
        subparser.description = help_text("hermes tenure")
    except Exception:
        pass
    subparser.set_defaults(func=run)


def run(args):
    text, code = execute(args)
    print(text)
    if code:
        sys.exit(code)
