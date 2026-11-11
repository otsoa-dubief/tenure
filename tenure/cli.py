# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""``hermes tenure`` (owner's terminal) and ``/tenure`` (inside a conversation).

    status [--profile P] [--model M] [--all]   what each agent has earned, per action type
    setup [careful|balanced|fast]              the three recommendations; with a name, use it
    explain                                    how tenure decides, and what the numbers guarantee
    models [--type T]                          each model's verified record on your own work
    undo [ID]                                  put back the files of an action that acted, then told you (counts a fault); alone, the list
    flag TYPE [note] [--model M]               report an error the agent made on its own: its tenure is revoked
    revoke TYPE|all [--model M | --all]        take earned autonomy back without an error
    passport [--agent A] [--out FILE]          write the signed passport of an agent (--no-redact keeps type names)
    card [--model M] [--no-redact]             the passport as a short text card to paste in a chat or a post
    verify PASSPORT [LEDGER]                   check a passport; with the exported ledger, recompute it by replay
    anchor                                     one line to publish: the ledger's head, date and length
    export [PATH]                              write the evidence ledger (hash-chained JSON lines)
    strict on|off                              strict mode: a new model starts with an empty record
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

from . import community, i18n, params, passport, personal, rule, store, undo
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
def _agent(core, agent: str | None) -> str:
    return agent or core.ST.last_agent or core.store_().get_meta("agent:last") or "unknown@unknown"


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


def _join(items) -> str:
    return tr("cli.list.separator").join(items)


def _tier_cell(s: rule.TypeState, n: int | None, cfg: dict | None = None) -> str:
    eff = effective_tier(s, n)
    if cfg is not None and eff != rule.T3 and _core().trusted(cfg, s, n, s.stakes):
        return tr("cli.tier.trusted")
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
            sessions = f"{len(s.sessions)}/{rule.SESSIONS}"
            g = rule.guarantee(s, n, cfg["spot"])
            guar = "-"
            if eff == rule.T3:
                guar = tr("cli.status.guarantee_provisional" if g["conditional"] else "cli.status.guarantee",
                          rate=i18n.pct(g['aoql'], 2))
        notes = [tr("cli.status.note.provisional", n=s.provisional)] if s.provisional else []
        notes += [tr("cli.status.note.trial", n=s.trial_left)] if s.trial_left else []
        notes += [tr("cli.status.note.trial_wait", n=s.trial_wait)] if s.trial_wait else []
        cells.append([s.key, _stakes(s.stakes), _tier_cell(s, n, cfg), series, sessions, _record(s.faults, s.successes),
                      tr("cli.status.notes", guarantee=guar, notes=tr("cli.list.joiner").join(notes)) if notes
                      else guar])
    lines += ["  " + ln for ln in _table(_cols("type", "stakes", "tier_now", "series", "sessions", "record",
                                               "guarantee"), cells)]
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
                   "strict": bool(last.get("strict")), "start": last.get("start", "probation")}
        agents = (_targets(core, st, agent=agent, model=model, every=every) if (agent or model or every) else
                  [st.get_meta("agent:last") or "unknown@unknown"])
    else:
        st = core.store_()
        agents = _targets(core, st, agent=agent, model=model, every=every)
    header = ("cli.status.header.profile" if profile else "cli.status.header.here") + ("_strict" if cfg["strict"]
                                                                                        else "")
    lines = [tr(header, profile=profile, preset=cfg["preset"], spot=round(1 / cfg["spot"]))]
    if cfg.get("start") == "trusted":
        lines.append(tr("cli.status.trusted_start", command="hermes tenure start probation"))
    copied = None if profile else st.get_meta(core.COPIED_META)
    if copied:
        lines.append(tr("cli.status.copied", date=time.strftime("%Y-%m-%d", time.localtime(float(copied)))))
    why = None if profile else core.nobody_answers()
    if why:
        lines.append(tr("cli.status.paused", why=why))
    if not profile and not cfg["enabled"]:
        lines.append(tr("cli.status.disabled", setting=f"{SETTINGS}.enabled"))
    for a in agents:
        lines += [""] + _status_agent(st, a, cfg)
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
        label = (f"CAP {tr('tier.rank.cap')}" if n is None else
                 tr("cli.tier.trusted") if eff != rule.T3 and core.trusted(cfg, s, n, s.stakes) else
                 f"{_CODE[eff]} {tr(f"tier.rank.{_RANK_KEY[eff]}")}")
        lines.append(f"{_card_bar(s, n, eff)} {ljust(shown[s.key], width_k)}  {label}")
        faults, successes = faults + s.faults, successes + s.successes
    lines.append(tr("cli.card.foot", record=_record(faults, successes)))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ explain
def explain_text() -> str:
    core = _core()
    cfg = core.settings()
    d = params.describe(cfg["risks"], cfg["spot"])
    spot = round(1 / cfg["spot"])
    t2 = {lv: math.ceil(params.wald_steps(lv)[2] / params.wald_steps(lv)[1] - 1e-9) for lv in params.WALD}
    new_model = tr("cli.explain.new_model_strict" if cfg["strict"] else "cli.explain.new_model")
    lines = [tr("cli.explain.title"),
             "  " + (tr("cli.explain.t1_trusted") if cfg.get("start") == "trusted" else tr("cli.explain.t1")),
             "  " + tr("cli.explain.t2", low=t2["low"], medium=t2["medium"], command="/tenure undo N"),
             "  " + tr("cli.explain.t3", sessions=rule.SESSIONS, spot=spot),
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
                               worst=i18n.pct(x['worst_case'], 1)))
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
    return tr("cli.flag.done", type=type_key, agent=agent, tier=tier_name(s.tier))


def revoke(type_key: str, agent: str | None = None, model: str | None = None, every: bool = False) -> str:
    core = _core()
    cfg = core.settings()
    done = []
    with core.txn() as st:
        agents = _targets(core, st, agent=agent, model=model, every=every)
        for ag in agents:
            for _, s in st.states(ag):
                if type_key not in ("all", s.key):
                    continue
                if (type_key == "all" and s.tier == rule.T1 and not s.series and not s.provisional and s.wald >= 0
                        and not core.trusted(cfg, s, params.required_n(cfg["risks"], s.stakes), s.stakes)):
                    continue                                       # nothing earned or trusted to take back
                events = rule.revoke(s)
                st.put_state(ag, s)
                st.distrust(s.key)
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


def undo_list() -> str:
    """The actions taken alone that can still be undone, newest first, with the file each would restore."""
    core = _core()
    st = core.store_()
    now = time.time()
    rows = st.db.execute("SELECT id, agent, type, at, snap_id FROM undo WHERE undone = 0 AND snap_id IS NOT NULL "
                         "AND at > ? ORDER BY id DESC LIMIT 20", (now - core.UNDO_WINDOW,)).fetchall()
    if not rows:
        return tr("cli.undo.none", n=core.UNDO_WINDOW // 3600)
    total = st.db.execute("SELECT COUNT(*) FROM undo WHERE undone = 0 AND snap_id IS NOT NULL AND at > ?",
                          (now - core.UNDO_WINDOW,)).fetchone()[0]
    cells = []
    for uid, agent, key, at, snap in rows:
        d = undo.describe(snap, core.data_dir())
        what = ((tr("cli.undo.more_files", file=d["file"], n=d["files"] - 1) if d["files"] > 1 else d["file"])
                if d else tr("cli.undo.no_snapshot"))
        cells.append([str(uid), key, what, _ago(now - at), agent])
    lines = [tr("cli.undo.title", n=core.UNDO_WINDOW // 3600)]
    lines += ["  " + ln for ln in _table(_cols("number", "type", "restores", "when", "agent"), cells)]
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


# ------------------------------------------------------------------------------------------------ passport
def passport_cmd(agent: str | None = None, out: str = "", redact: bool = True) -> str:
    core = _core()
    cfg = core.settings()
    with core.txn() as st:
        name = _targets(core, st, agent=agent)[0]
        if not st.states(name):
            return tr("cli.passport.none", agent=name)
        core.sync_settings(st, cfg)                    # the ledger holds the settings the states were computed with
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
    err = _save_setting(core, "preset", name)
    if err:
        return warn + tr("cli.setup.save_failed", error=err, setting=f"{SETTINGS}.preset", name=name)
    return warn + tr("cli.setup.in_force", name=name) + "\n" + presets_text(core.settings()["spot"])


def start(value: str) -> str:
    core = _core()
    err = _save_setting(core, "start", value)
    if err:
        return tr("cli.start.save_failed", error=err, setting=f"{SETTINGS}.start", value=value)
    return tr("cli.start.trusted") if value == "trusted" else tr("cli.start.probation")


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
    subs = subparser.add_subparsers(dest="tenure_command")
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
    p = subs.add_parser("undo", help="Restore the files of an action that acted, then told you")
    p.add_argument("id", type=int, nargs="?", help="the number from the notice; without it, the list")
    p = subs.add_parser("flag", help="Report an error the agent made on its own: counts as a fault, the type drops at least one tier")
    p.add_argument("type")
    p.add_argument("note", nargs="*")
    p.add_argument("--model", help="Start of an agent string (default: the last active agent)")
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
    subs.add_parser("cleanup", help="List dead tenure keys in Hermes' permanent allowlist")
    p = subs.add_parser("share", help="Write a signed record of counts for the community benchmark (nothing is sent)")
    p.add_argument("--out", default="", help="Output file (default: tenure-record-<date>.json here)")


def _usage() -> str:
    return tr("cli.usage")


def execute(ns) -> tuple[str, int]:
    """(text, exit code) for a parsed command line."""
    def g(name, default=None):
        return getattr(ns, name, default)
    cmd = g("tenure_command") or "status"
    try:
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
        if cmd == "undo":
            if g("id") is None:
                return undo_list(), 0
            text = undo_action(g("id"))
            return text, 0 if text.ok else 1
        if cmd == "flag":
            return flag(g("type"), " ".join(g("note") or []), model=g("model")), 0
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
        if cmd == "cleanup":
            return cleanup(), 0
        if cmd == "share":
            return share(g("out", "") or "")
    except CliError as e:
        return str(e), 1
    return _usage(), 1


def slash(raw_args="", **kwargs):
    try:
        parser = _Parser(prog="/tenure", add_help=False)
        _add_subcommands(parser)
        try:
            ns = parser.parse_args(shlex.split(raw_args or ""))
        except _Usage as e:
            return (f"tenure: {e}\n" if str(e) else "") + _usage()
        return execute(ns)[0]
    except Exception as e:
        return f"tenure: {type(e).__name__}: {e}"


def setup(subparser):
    _add_subcommands(subparser)
    subparser.set_defaults(func=run)


def run(args):
    text, code = execute(args)
    print(text)
    if code:
        sys.exit(code)
