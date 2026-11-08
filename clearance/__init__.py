# Copyright 2026 Otsoa Dubief
# SPDX-License-Identifier: Apache-2.0
"""clearance: earned autonomy for Hermes, per action type, with a statistical guarantee.

Every action that changes something asks the owner, through Hermes' own approval prompt, until its type has been
approved ``i`` times in a row; then the agent acts alone on that type, except for random spot checks, and one
refusal (or an error the owner flags) sends the type back to asking. ``i`` comes from the risk the owner accepts
(``params``). Records are kept per model: a new model starts with an empty record.

Hooks: pre_tool_call (decide), post_approval_response (count the owner's answer), pre_api_request (which model is
acting). CLI: ``hermes clearance``. Slash command: ``/clearance``. Local only: no network, no LLM call.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import uuid

from . import classify, params, rule, store

log = logging.getLogger("clearance")
PREFIX = "clearance"
NEVER = 10 ** 9                  # a clearance number no record reaches (types capped by the owner's settings)


class _State:
    def __init__(self):
        self.ctx = None
        self.store = None
        self.store_path = ""
        self.models: dict[str, str] = {}          # session -> model of its latest API request
        self.last_model = ""
        self.rng = random.SystemRandom()


ST = _State()


# --------------------------------------------------------------------------------------------------- settings
def _hermes_home() -> str:
    try:
        from hermes_constants import get_hermes_home
        return str(get_hermes_home())
    except Exception:
        return os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")


def data_dir() -> str:
    return os.path.join(_hermes_home(), "plugin-data", "clearance")


def store_() -> store.Store:
    path = os.path.join(data_dir(), "clearance.db")
    if ST.store is None or ST.store_path != path:
        ST.store, ST.store_path = store.Store(path), path
    return ST.store


def _get(key, default=None):
    try:
        return ST.ctx.get_config(key, default) if ST.ctx is not None else default
    except Exception:
        return default


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_risk(value, default):
    """A risk from the owner's settings: 0.02, "2%", "1/50", or "cap" (always ask)."""
    if value is None or str(value).strip().lower() in ("cap", "capped", "never", "none", "null", "always ask"):
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if text.endswith("%"):
            v = float(text[:-1]) / 100
        elif "/" in text:
            a, b = text.split("/", 1)
            v = float(a) / float(b)
        else:
            v = float(text)
    except (ValueError, ZeroDivisionError):
        return default
    return v if 0 < v < 1 else default


def settings() -> dict:
    preset = str(_get("preset", params.DEFAULT_PRESET) or params.DEFAULT_PRESET).strip().lower()
    if preset not in params.PRESETS:
        preset = params.DEFAULT_PRESET
    risks = dict(params.PRESETS[preset])
    custom = _get("risks")
    if isinstance(custom, dict):
        for level in params.LEVELS:
            if level in custom:
                risks[level] = parse_risk(custom[level], risks[level])
    spot = parse_risk(_get("spot_check", params.DEFAULT_SPOT), params.DEFAULT_SPOT)
    if spot is None:
        spot = params.DEFAULT_SPOT
    overrides = _get("types")
    return dict(preset=preset, risks=risks, spot=spot, overrides=overrides if isinstance(overrides, dict) else {},
                enabled=_truthy(_get("enabled", True)))


# ---------------------------------------------------------------------------------------------------- context
def _session_cwd() -> str:
    try:
        if ST.ctx is not None and hasattr(ST.ctx, "session_cwd"):
            cwd = ST.ctx.session_cwd()
            if cwd:
                return str(cwd)
    except Exception:
        pass
    return os.environ.get("TERMINAL_CWD") or os.getcwd()


def ask_key(model: str, type_key: str, generation: int) -> str:
    """Rule key of an ordinary ask: per type, model and generation, so that Hermes' own "session"/"always" grants
    end with a revocation and never carry over to another model."""
    tag = hashlib.sha256(model.encode("utf-8")).hexdigest()[:8]
    return f"{PREFIX}:{type_key}:{tag}:g{generation}"


def current_model(session_id: str = "") -> str:
    return ST.models.get(str(session_id or "")) or ST.last_model or "unknown-model"


def nobody_answers(session_id: str = "") -> str | None:
    """Why no person will answer an approval now, or None: --yolo, or a cron job (public signals only).

    Hermes calls post_approval_response only for a person's decision (or a smart-mode verdict, which carries
    decided_by): with --yolo, /yolo, approvals.mode off, a cron or single-query run, or a "session"/"always" grant,
    it settles the ask itself without the hook, so nothing is counted there anyway. This check matters for cron,
    where a spot check on a cleared type would otherwise fall to cron_mode and fail the job."""
    if _truthy(os.environ.get("HERMES_YOLO_MODE", "")):
        return "--yolo"
    try:
        if ST.ctx is not None and ST.ctx.current_cron_execution() is not None:
            return "cron"
    except Exception:
        pass
    return None


def _announce(text: str) -> None:
    try:
        if ST.ctx is not None and hasattr(ST.ctx, "post_message"):
            ST.ctx.post_message(text)
    except Exception:
        log.debug("clearance: post_message failed", exc_info=True)


def _say(event: dict, spot: float) -> str | None:
    t = event.get("type")
    if event["event"] == "cleared":
        how = ("by your own 'always'" if event.get("manual")
               else f"after {event.get('approvals_in_a_row')} approvals in a row")
        return (f"clearance: {t} is cleared {how}. The agent now acts alone on it; 1 action in {round(1 / spot)} "
                f"is still spot-checked, and one refusal revokes it.")
    if event["event"] == "revoked":
        return (f"clearance: {t} clearance revoked ({event.get('reason')}). Every action of this type asks again; "
                f"next clearance after {event.get('next_required')} approvals in a row.")
    return None


def type_state(model: str, key: str, stakes: str) -> rule.TypeState:
    st = store_()
    with st.transaction():
        return st.get_state(model, key, stakes)


# ------------------------------------------------------------------------------------------------------ hooks
def pre_api_request(model="", provider="", session_id="", **kwargs):
    try:
        if not model:
            return None
        sid, model = str(session_id or kwargs.get("task_id") or ""), str(model)
        old = ST.models.get(sid)
        ST.models[sid], ST.last_model = model, model
        if old != model:
            st = store_()
            with st.transaction():
                if old:
                    st.log(dict(event="model", old_model=old, new_model=model))
                st.set_meta("model:last", model)
            if old:
                _announce(f"clearance: the agent now runs on {model}. Its record starts empty: every type asks again "
                          f"until it earns clearance.")
    except Exception:
        log.exception("clearance: pre_api_request failed")
    return None


def _message(act, s, need, risk) -> str:
    if need is None:
        return (f"clearance — {act.summary}\n{act.type} ({act.stakes} stakes) is capped by your settings: always "
                f"asked ({s.approvals} approvals on record).")
    return (f"clearance — {act.summary}\n{act.type} ({act.stakes} stakes): {s.streak}/{need} approvals in a row "
            f"before the agent acts alone (accepted risk {risk:.2%}). Approve if the action is right; deny if it "
            f"is wrong.")


def pre_tool_call(tool_name="", args=None, session_id="", tool_call_id="", task_id="", **kwargs):
    try:
        cfg = settings()
        if not cfg["enabled"]:
            return None
        act = classify.classify(tool_name, args if isinstance(args, dict) else {}, cwd=_session_cwd(),
                                overrides=cfg["overrides"])
        if act.stakes == classify.FREE:
            return None
        one_off = tool_call_id or uuid.uuid4().hex
        if act.stakes == classify.CAP:
            return {"action": "approve", "rule_key": f"{PREFIX}:cap:{act.type}:{one_off}",
                    "message": f"clearance — {act.summary}\n{act.type} is capped: always asked."}
        model = current_model(session_id or task_id)
        risk = cfg["risks"].get(act.stakes)
        need = None if risk is None else params.clearance_number(risk, cfg["spot"])
        nobody = nobody_answers(session_id)
        st = store_()
        with st.transaction():
            s = st.get_state(model, act.type, act.stakes)
            cleared = s.level == rule.CLEARED and need is not None
            if nobody:
                # Nobody answers: a cleared type runs (cron can use what was earned); the rest goes to Hermes'
                # own policy for that context (cron_mode, yolo...). Nothing is learned without a person.
                if cleared:
                    return None
                return {"action": "approve", "rule_key": ask_key(model, act.type, s.generation),
                        "message": _message(act, s, need if need is None else rule.required(s, need), risk)}
            decision = rule.ASK if need is None else rule.decide(s, need, cfg["spot"], ST.rng)
            if decision == rule.ALLOW:
                return None
            spot = decision == rule.SPOT
            if spot:
                key = f"{PREFIX}:spot:{act.type}:{one_off}"
            elif need is None:
                key = f"{PREFIX}:capped:{act.type}:{one_off}"      # "always" must not silence a capped type
            else:
                key = ask_key(model, act.type, s.generation)
            st.add_pending(tool_call_id or key, model, act.type, s.generation, spot=spot, rule_key=key,
                           stakes=act.stakes)
            st.expire_pending()
        if spot:
            msg = (f"clearance spot check — {act.summary}\n{act.type} is cleared; 1 action in "
                   f"{round(1 / cfg['spot'])} is still checked. Deny if the action is wrong: the clearance is "
                   f"revoked.")
        else:
            msg = _message(act, s, need if need is None else rule.required(s, need), risk)
        return {"action": "approve", "rule_key": key, "message": msg}
    except Exception as e:
        log.exception("clearance: pre_tool_call failed")
        return {"action": "approve", "message": f"clearance: internal error ({type(e).__name__}); asking you instead "
                                                f"of letting the action through."}


def outcome(choice, decided_by=None) -> str:
    """approved / refused / neutral. Timeouts, cancellations, transport failures and answers given by a model
    (smart approvals) are not the owner's judgement and count for nothing."""
    c = str(choice or "").strip().lower()
    if decided_by and str(decided_by).strip().lower() not in ("human", "user", "owner", "person"):
        return "neutral"
    if c.startswith("smart"):
        return "neutral"
    if c in ("once", "session", "always", "approve", "approved", "yes", "allow"):
        return "approved"
    if c in ("deny", "denied", "no", "reject", "rejected"):
        return "refused"
    return "neutral"


def post_approval_response(command="", description="", pattern_key="", pattern_keys=None, session_key="", surface="",
                           turn_id="", tool_call_id="", choice="", **kwargs):
    try:
        key = str(pattern_key or "")
        key = key[len("plugin_rule:"):] if key.startswith("plugin_rule:") else ""
        ours = key.startswith(PREFIX + ":")
        if not ours and not tool_call_id:
            return None
        cfg = settings()
        st = store_()
        say = []
        with st.transaction():
            p = st.pop_pending(tool_call_id=str(tool_call_id or ""), rule_key=key if ours else "")
            if p is None:
                return None
            result = "neutral" if nobody_answers(session_key) else outcome(choice, kwargs.get("decided_by"))
            stakes = p.get("stakes") or classify.MEDIUM
            s = st.get_state(p["model"], p["type"], stakes)
            risk = cfg["risks"].get(stakes)
            need = NEVER if risk is None else params.clearance_number(risk, cfg["spot"])
            if result == "approved":
                events = rule.on_approval(s, need, manual=(str(choice).lower() == "always" and risk is not None),
                                          spot=p["spot"])
            elif result == "refused":
                events = rule.on_refusal(s, need, spot=p["spot"])
            else:
                events = rule.on_neutral(s, str(choice))
            st.put_state(p["model"], s)
            st.log(dict(event=result, type=p["type"], stakes=stakes, spot=p["spot"], generation=p["generation"],
                        model=p["model"], choice=str(choice), surface=str(surface)))
            for ev in events:
                st.log({**ev, "model": p["model"]})
                say.append(_say(ev, cfg["spot"]))
        for text in filter(None, say):
            _announce(text)
    except Exception:
        log.exception("clearance: post_approval_response failed")
    return None


# --------------------------------------------------------------------------------------------------- commands
def _slash(raw_args="", **kwargs):
    from . import cli
    return cli.slash(raw_args, **kwargs)


def register(ctx):
    ST.ctx = ctx
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_approval_response", post_approval_response)
    ctx.register_hook("pre_api_request", pre_api_request)
    from . import cli
    ctx.register_cli_command(name="clearance", help="Earned autonomy per action type: status, setup, flag, revoke, "
                                                     "export and verify the evidence",
                             setup_fn=cli.setup, handler_fn=cli.run)
    ctx.register_command("clearance", handler=_slash,
                         description="What the agent has earned, per action type; setup, flag, revoke, export")
