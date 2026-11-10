/*
 * tenure: the live map. Dashboard tab of the tenure plugin.
 *
 * What each agent has earned, per action type: discrete tiers with their evidence, the personal benchmark per model,
 * the model-switch preview, the passport and its verification, the undo list and the risk dial.
 *
 * Plain IIFE, no build step. React, fetchJSON (the dashboard's auth: session token header, or the gated cookie) and
 * the theme come from window.__HERMES_PLUGIN_SDK__. Every number shown comes from the plugin API
 * (/api/plugins/tenure/); the only arithmetic done here is the series length N of the risk dial's live preview
 * (the study's formula, in exact integers) and the successes still missing before the middle tier (Wald steps).
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var REG = window.__HERMES_PLUGINS__;
  if (!SDK || !REG) return;

  var React = SDK.React;
  var h = React.createElement;
  var Fragment = React.Fragment;
  var useState = SDK.hooks.useState;
  var useEffect = SDK.hooks.useEffect;
  var useRef = SDK.hooks.useRef;
  var useMemo = SDK.hooks.useMemo;
  var useCallback = SDK.hooks.useCallback;

  var UI = SDK.components || {};

  // ---------------------------------------------------------------------------------------------------- i18n
  // Catalogs: tenure/locales/<lang>/dashboard.json, embedded below by scripts/build_locales.py (do not edit by hand).
  /* TENURE_LOCALES_BEGIN */
const TENURE_LOCALES = {
  "en": {
    "cell.asked_suffix": " asked",
    "cell.capped_by_settings": "Capped by the risk settings",
    "cell.held": "stored {tier} (held: settings)",
    "cell.kind_irreversible": "{type} · {stakes}, irreversible",
    "cell.kind_reversible": "{type} · {stakes}, reversible",
    "cell.provisional_long": {
      "one": "{count} carried over from the previous model, provisional",
      "other": "{count} carried over from the previous model, provisional"
    },
    "cell.record": "Record: {successes} successes · {faults} faults · {neutrals} neutral · {spot} spot checks",
    "cell.series": "Series {series}/{required} in a row",
    "cell.sessions": {
      "one": "{count} session",
      "other": "{count} sessions"
    },
    "cell.tier_now": "Tier now: {tier} ({name})",
    "common.arrow": "→",
    "common.capped": "capped",
    "common.list_sep": ", ",
    "common.loading": "Loading…",
    "common.no_public_measure": "no public measure",
    "common.one_in": "1 in {k}",
    "common.percent": "{v}%",
    "common.profile": "profile {profile}",
    "confirm.again": "Click again to confirm",
    "confirm.default": "Confirm",
    "copy.button": "Copy",
    "copy.done": "Copied",
    "count.agents": {
      "one": "{n} agent",
      "other": "{n} agents"
    },
    "count.faults": {
      "one": "{n} fault",
      "other": "{n} faults"
    },
    "count.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "counters.actions.label": {
      "one": "action",
      "other": "actions"
    },
    "counters.actions.sub": "covered",
    "counters.alone.label": "acted without asking",
    "counters.alone.sub": "ran without asking, of {total}",
    "counters.aria": "Last 7 days",
    "counters.checked.label": "checked",
    "counters.checked.sub": "by you, of {total}",
    "counters.faults.label": "faults caught",
    "counters.faults.sub": {
      "one": "{faults} / {n} check",
      "other": "{faults} / {n} checks"
    },
    "counters.window": "last 7 days, every profile",
    "drawer.aria": "Agent {agent}",
    "drawer.close": "Close",
    "drawer.close_title": "Close (Esc)",
    "drawer.eyebrow": "Agent · profile {profile}",
    "drawer.eyebrow_read_only": "Agent · profile {profile} (read-only here)",
    "drawer.flag.button": "Flag",
    "drawer.flag.confirm": "Flag?",
    "drawer.flag.done": "Fault recorded on {type}: now {tier}.",
    "drawer.flag.title": "Record a fault on this type, after the fact",
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} faults / checks · ",
    "drawer.own_profile_only": "Actions apply to this dashboard's profile only",
    "drawer.revoke.button": "Revoke",
    "drawer.revoke.confirm": "Revoke?",
    "drawer.revoke.done": "Revoked {type}: back to T1.",
    "drawer.revoke.title": "Take back what this type earned: back to T1",
    "drawer.revoke_all.button": "Revoke all",
    "drawer.revoke_all.confirm": "Revoke every type?",
    "drawer.revoke_all.done": {
      "one": "Revoked {count} type: back to T1.",
      "other": "Revoked {count} types: back to T1."
    },
    "drawer.revoke_note": "Takes effect at the next action. Every revocation is a ledger event.",
    "drawer.revoke_note_other": "Flag and revoke act on the dashboard's own profile. Use: {cmd}",
    "drawer.sessions_of": {
      "one": "{n}/{total} session",
      "other": "{n}/{total} sessions"
    },
    "drawer.stakes_reversible": "{stakes} · reversible",
    "drawer.types_title": "Action types",
    "error.request_failed": "request failed",
    "event.confirmed": "carried-over evidence confirmed by its own",
    "event.fault.check": "automatic check failed",
    "event.fault.flag": "flagged as a fault by you",
    "event.fault.other": "fault ({source})",
    "event.fault.refusal": "refused by you",
    "event.fault.spot": "spot check refused or failed",
    "event.fault.undo": "undone by you",
    "event.neutral.alone": "acted alone (earned)",
    "event.neutral.ambiguous": "ambiguous call · no evidence",
    "event.neutral.blocked": "blocked by another guard · no evidence",
    "event.neutral.error": "tool error · no evidence",
    "event.neutral.expired": "never reported back · no evidence",
    "event.neutral.nobody": "nobody to answer · no evidence",
    "event.neutral.other": "neutral ({source})",
    "event.neutral.timeout": "no answer · no evidence",
    "event.neutral_expired": "pending action expired · no evidence",
    "event.revoked": "revoked by you",
    "event.success.approved": "approved by you, ran cleanly",
    "event.success.notify": "acted, then notified · not undone",
    "event.success.spot": "spot check approved by you",
    "event.switch": "model switch",
    "event.switch_from": "model switch from {from}",
    "event.tier": "tier {from} → {to} · {why}",
    "event.trial.failed": {
      "one": "trial failed: wait {wait} action",
      "other": "trial failed: wait {wait} actions"
    },
    "event.trial.opened": {
      "one": "trial opened: next {left} must succeed",
      "other": "trial opened: next {left} must succeed"
    },
    "event.trial.passed": "trial passed",
    "event.trial.reopens": {
      "one": "trial reopens: next {left} must succeed",
      "other": "trial reopens: next {left} must succeed"
    },
    "event.why.fault": "fault",
    "event.why.series_complete": "series complete",
    "event.why.series_n": "series {required}/{required}",
    "event.why.sessions": {
      "one": "{count} session",
      "other": "{count} sessions"
    },
    "event.why.settings": "stricter settings",
    "event.why.stakes": "stakes changed",
    "event.why.wald": "sequential test passed",
    "flag.carried_over": "carried over",
    "flag.carried_over_n": {
      "one": "{n} carried over",
      "other": "{n} carried over"
    },
    "flag.carried_over_provisional": {
      "one": "{n} carried over, provisional",
      "other": "{n} carried over, provisional"
    },
    "flag.carried_over_title": {
      "one": "{count} carried over, provisional",
      "other": "{count} carried over, provisional"
    },
    "flag.fault_on_record": "fault on record",
    "flag.fault_on_record_title": "Fault on record",
    "flag.provisional": "provisional",
    "flag.trial": "trial",
    "guarantee.capped": "Capped: every action asks.",
    "guarantee.text": "Unchecked errors stay under {aoql} of its actions of this type; for an agent that turns bad after tenure, at most {worst} until the first caught error.",
    "guarantee.text_conditional": "Unchecked errors stay under {aoql} of its actions of this type; for an agent that turns bad after tenure, at most {worst} until the first caught error. Conditional on the previous model's evidence still holding.",
    "help.agent": "Agent drawer of the focused row",
    "help.aria": "Keyboard shortcuts",
    "help.close": "Close",
    "help.help": "This help",
    "help.next_prev": "Next / previous agent",
    "help.open": "Open the focused agent",
    "help.raw": "Raw type names on / off",
    "help.title": "Keyboard",
    "legend.a_share": "a share",
    "legend.alone": "acts on its own, {share} spot-checked",
    "legend.ask": "asks first",
    "legend.capped": "capped: always asks",
    "legend.carried": "from the previous model, provisional",
    "legend.notify": "acts, then notifies with an undo (reversible types)",
    "legend.series": "clean runs in a row, of the N needed",
    "map.aria": "Agents by action type",
    "map.empty.after": ", and climbs only on verified successes: reversible types reach the middle tier after a run of verified successes without a fault, and T3 after a full series of N from two sessions.",
    "map.empty.before": "tenure starts counting at the first action an agent asks to run. Reads never ask. Every action type starts at ",
    "map.empty.bold": "T1, asks first",
    "map.empty.title": "No evidence yet",
    "map.open_hint": "open ",
    "map.th.agent": "Agent",
    "map.th.agent_sub": "profile · model@provider",
    "map.th.capped": "capped · always asks",
    "map.th.risk": {
      "one": "risk {risk} · {n} in a row to act on its own",
      "other": "risk {risk} · {n} in a row to act on its own"
    },
    "missing.always_asks": "always asks",
    "missing.earned": "earned · spot-checked",
    "missing.more_to_t2": {
      "one": "{n} more to T2",
      "other": "{n} more to T2"
    },
    "missing.more_to_t3": {
      "one": "{n} more to T3",
      "other": "{n} more to T3"
    },
    "missing.rechecking": "re-checking",
    "missing.second_session": "needs a 2nd session",
    "missing.trial_left": {
      "one": "trial · {n} of {total} to go",
      "other": "trial · {n} of {total} to go"
    },
    "missing.trial_wait": {
      "one": "trial failed · wait {n}",
      "other": "trial failed · wait {n}"
    },
    "models.empty.body": "Each verified action adds to the model's record on that type, here and in {cmd}.",
    "models.empty.title": "No record yet",
    "models.lede": "Your own benchmark: each model's verified record on your work, per action type, with the 95% range of its fault rate. Ranked by the top of its range, never by one score. Beside it, the public measure, as information: ",
    "models.lede_bold": "public capability on their tasks, not reliability on yours.",
    "models.no_checks": "no checks yet",
    "models.no_public": "No public measure for this action type.",
    "models.not_enough": "not enough evidence",
    "models.personal_title": "On your work",
    "models.public_note": "Public capability on their tasks, not reliability on yours.",
    "models.public_title": "Public measure",
    "models.source": "{source}. Best published score, any harness; not a controlled comparison.",
    "models.source_accessed": "{source}, accessed {accessed}. Best published score, any harness; not a controlled comparison.",
    "page.error": "Could not read tenure: {error}",
    "page.live": "live · ",
    "page.loading": "Loading the record…",
    "page.polling": "Polling every {s} s",
    "page.raw_off": "redacted names",
    "page.raw_on": "raw names",
    "page.raw_title": "Show raw action type names (r)",
    "page.retrying": "retrying · ",
    "page.subtitle": "Autonomy earned per action type, on verified evidence",
    "page.title": "Tenure",
    "page.unreadable": "Unreadable: {profiles}. Its database exists but cannot be opened; other profiles are shown.",
    "passport.agent": "Agent",
    "passport.checked_by": "Checked by the dashboard against this profile's ledger. Anyone can re-check it:",
    "passport.download": "Download JSON",
    "passport.empty.body": "A passport covers an agent's record; it appears with the first verified action.",
    "passport.empty.title": "No passport yet",
    "passport.field.agent": "Agent",
    "passport.field.generated": "Generated",
    "passport.field.ledger": "Ledger",
    "passport.field.profile": "Profile",
    "passport.field.protocol": "Protocol",
    "passport.field.public_key": "Public key",
    "passport.field.rule": "Rule",
    "passport.field.settings": "Settings",
    "passport.field.signature": "Signature",
    "passport.field.type_names": "Type names",
    "passport.guarantee": "unchecked errors under {aoql} · {worst} if it turns bad",
    "passport.note": "Signed and tamper-evident: a change after it is signed or anchored shows on verification. An older passport still verifies against a longer ledger; the verifier says what changed since.",
    "passport.types_title": "Attested types",
    "passport.value.hashed": "{profile} (hashed)",
    "passport.value.ledger": {
      "one": "{n} event · head {head}",
      "other": "{n} events · head {head}"
    },
    "passport.value.none": "none",
    "passport.value.raw": "raw",
    "passport.value.redacted": "redacted after the program and subcommand",
    "passport.value.unsigned": "unsigned",
    "preset.balanced": "balanced",
    "preset.careful": "careful",
    "preset.custom": "custom",
    "preset.fast": "fast",
    "profile.pending": "applies from the next action",
    "profile.preset": "{preset} preset",
    "profile.read_only": " · read-only here",
    "profile.sessions_suspended": {
      "one": "{n} session suspended: external content read",
      "other": "{n} sessions suspended: external content read"
    },
    "profile.spot": "spot checks {rate}",
    "profile.strict": "strict",
    "profile.suspended": {
      "one": "{n} suspended: external content read",
      "other": "{n} suspended: external content read"
    },
    "profile.this_dashboard": " · this dashboard",
    "settings.about.body": "The same rule as a preregistered study, replayed on 6,000+ simulated agents (results pending). Added layers make it stricter: spot checks ({spot} cleared actions still asks), two distinct sessions in the series that reaches T3, and suspension after a session reads external content.",
    "settings.about.carry": "Carry-over is our addition; strict mode is the study.",
    "settings.about.title": "About the rule",
    "settings.apply": "Apply",
    "settings.checks_in_row": {
      "one": " check in a row",
      "other": " checks in a row"
    },
    "settings.empty.body": "The balanced preset applies until the first action is recorded.",
    "settings.empty.title": "No settings logged yet",
    "settings.in_force": "in force: {value}",
    "settings.in_force_profile": "In force in profile {profile}.",
    "settings.preset_aria": "Preset",
    "settings.read_only.body": "This dashboard process cannot write tenure's settings (Hermes gives plugins no other public writer). Run:",
    "settings.read_only.bold": "Read-only here.",
    "settings.reset": "Reset",
    "settings.risk_help": "The share of errors you accept running unchecked, per stakes level. N is the series of verified successes in a row a type needs to act on its own.",
    "settings.risk_title": "Accepted risk",
    "settings.rung_cap": "cap",
    "settings.same_as": "Same as: {cmds}",
    "settings.saved": "Settings saved.",
    "settings.saved_long": "Saved. The new settings are logged in the ledger and apply from the next action.",
    "settings.stakes.high": "High stakes",
    "settings.stakes.low": "Low stakes",
    "settings.stakes.medium": "Medium stakes",
    "settings.stakes_risk.high": "high stakes risk",
    "settings.stakes_risk.low": "low stakes risk",
    "settings.stakes_risk.medium": "medium stakes risk",
    "settings.strict": "Strict mode",
    "settings.strict_off": "Off: a new model inherits part of the previous record, provisionally",
    "settings.strict_on": "On: a new model starts with an empty record (the study's rule)",
    "stakes.group.high": "high stakes",
    "stakes.group.low": "low stakes",
    "stakes.group.medium": "medium stakes",
    "stakes.high": "high",
    "stakes.low": "low",
    "stakes.medium": "medium",
    "stale.message": "Last refresh failed ({error}). Showing the data from {time}.",
    "switch.count.carried": {
      "one": "{n} carried",
      "other": "{n} carried"
    },
    "switch.count.kept": {
      "one": "{n} kept",
      "other": "{n} kept"
    },
    "switch.count.reset": {
      "one": "{n} reset",
      "other": "{n} reset"
    },
    "switch.count.vetoed": {
      "one": "{n} vetoed",
      "other": "{n} vetoed"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "No agent to preview yet",
    "switch.footnote": "Public scores inform; they never grant autonomy. A veto only blocks carry-over, beyond a fixed margin.",
    "switch.from": "From",
    "switch.lede": "Before you change model: what the new agent would inherit, type by type. A new model or provider is a new agent. Carry-over is our addition; strict mode is the study.",
    "switch.none": "none",
    "switch.pick.body": "Type any model id. Nothing changes until Hermes actually runs the new model.",
    "switch.pick.title": "Pick a target model",
    "switch.placeholder": "model id, e.g. {example} or model@provider",
    "switch.preview": "Preview",
    "switch.provisional": {
      "one": "{n} provisional",
      "other": "{n} provisional"
    },
    "switch.status.carried.label": "carried, provisional",
    "switch.status.carried.text": "Part of the series carries over, marked provisional until the new model adds its own.",
    "switch.status.kept.label": "kept",
    "switch.status.kept.text": "The new agent already has its own record here; it is never overwritten.",
    "switch.status.reset.label": "reset",
    "switch.status.reset.text": "Starts from zero: high stakes, capped, or strict mode.",
    "switch.status.vetoed.label": "vetoed",
    "switch.status.vetoed.text": "The public benchmark shows the new model weaker on this type: nothing carries over.",
    "switch.strict": "strict mode: nothing carries over",
    "switch.to": "To model",
    "switch.to_aria": "Target model",
    "tabs.aria": "Tenure views",
    "th.after_switch": "after the switch",
    "th.agent": "agent",
    "th.faults_checks": "faults / checks",
    "th.guarantee": "guarantee",
    "th.now": "now",
    "th.outcome": "outcome",
    "th.public_measure": "public measure",
    "th.range": "95% range · 0–{max}",
    "th.rate": "rate",
    "th.series": "series",
    "th.sessions": "sessions",
    "th.tier": "tier",
    "th.type": "type",
    "th.undo_effect": "effect of undo",
    "th.when": "when",
    "th.your_record": "your record",
    "tier.capped.chip": "CAP",
    "tier.capped.title": "Capped: always asks",
    "tier.chip.title": "{tier}, {name}",
    "tier.name.alone": "acts on its own",
    "tier.name.ask": "asks first",
    "tier.name.notify": "acts, then notifies",
    "time.ago": "{duration} ago",
    "time.days": {
      "one": "{n}d",
      "other": "{n}d"
    },
    "time.hours_minutes": {
      "one": "{n}h {mm}m",
      "other": "{n}h {mm}m"
    },
    "time.minutes": {
      "one": "{n}m",
      "other": "{n}m"
    },
    "time.seconds": {
      "one": "{n}s",
      "other": "{n}s"
    },
    "timeline.all_types": "All types",
    "timeline.count": {
      "one": "{n}×",
      "other": "{n}×"
    },
    "timeline.empty": "No evidence for this filter",
    "timeline.filter_label": "Filter by type",
    "timeline.loading": "Loading the evidence…",
    "timeline.note": "From the hash-chained ledger, newest first, last 200 events. Repeated outcomes are grouped.",
    "timeline.title": "Evidence timeline",
    "toast.transition": "{agent} · {type}: {from} → {to}",
    "totals.actions": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "totals.alone": "{n} without asking",
    "totals.checked": "{n} checked",
    "totals.faults": {
      "one": "{n} fault",
      "other": "{n} faults"
    },
    "transitions.empty": "None since this page opened. Every automatic tier change is listed here and in each agent's timeline.",
    "transitions.title": "Tier changes seen on this page",
    "transitions.why.after_fault": "after a fault",
    "transitions.why.on_evidence": "on evidence",
    "transitions.why.trial_open": "trial open",
    "undo.button": "Undo",
    "undo.confirm": "Undo #{id}?",
    "undo.effect.already": "restores the files · the automatic check already counted a fault",
    "undo.effect.fault": "restores the files · counts as a fault",
    "undo.empty.body": "Actions at T2 (act, then notify) keep a snapshot of the files they wrote for 24 hours. They appear here, newest first, each with its own undo.",
    "undo.empty.title": "Nothing to undo",
    "undo.lede": "Recent act-then-notify actions. Undo restores the files from their snapshot and counts as a fault of the type.",
    "undo.own_profile_only": "Undo acts on this dashboard's profile only",
    "undo.title": "Restore the files",
    "undo.window_ends": "window ends in {duration}",
    "verdict.chain": "Hash chain intact",
    "verdict.ok.replay": "Replaying the ledger with the rule gives the same tiers",
    "verdict.ok.signature": "Signature valid (Ed25519)",
    "verdict.ok.title": "Verified",
    "verdict.problems": {
      "one": "{count} problem found",
      "other": "{count} problems found"
    },
    "verdict.unsigned.no_key": "No signing key yet: {cmd} creates one",
    "verdict.unsigned.replay": "Replay gives the same tiers",
    "verdict.unsigned.title": "Unsigned, otherwise verified",
    "view.map": "Map",
    "view.models": "Your benchmark",
    "view.passport": "Passport",
    "view.settings": "Settings",
    "view.switch": "Switch preview",
    "view.undo": "Undo"
  }
};
/* TENURE_LOCALES_END */

  // The dashboard's language (SDK.useI18n().locale), set by TenurePage on every render so that switching language
  // in the dashboard re-renders the whole tab. Fallback chain: exact -> base language (zh-hant -> zh) -> en.
  var LANG = "en";
  function resolveLang(loc) {
    var l = String(loc || "en").toLowerCase().replace(/_/g, "-");
    if (TENURE_LOCALES[l]) return l;
    var base = l.split("-")[0];
    return TENURE_LOCALES[base] ? base : "en";
  }
  function setLocale(loc) { LANG = resolveLang(loc); }
  var PLURALS = {};
  function pluralCategory(lang, n) {
    try {
      return (PLURALS[lang] || (PLURALS[lang] = new Intl.PluralRules(lang))).select(n);
    } catch (e) { return n === 1 ? "one" : "other"; }
  }
  /** The active locale's text for ``key`` (en if missing), ``{name}`` replaced from ``vars`` (numbers through num()).
   * A value that is an object of CLDR plural categories is chosen by ``vars.n``. */
  function t(key, vars) {
    var lang = LANG, cat = TENURE_LOCALES[lang], v = cat ? cat[key] : undefined;
    if (v == null) { lang = "en"; v = TENURE_LOCALES.en[key]; }
    if (v == null) return key;
    if (typeof v === "object") {
      var c = pluralCategory(lang, Number(vars && vars.n));
      v = v[c] != null ? v[c] : v.other;
    }
    return String(v).replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, function (m, name) {
      if (!vars || !Object.prototype.hasOwnProperty.call(vars, name)) return m;
      var x = vars[name];
      return x == null || typeof x === "number" ? num(x) : String(x);     // num: "—" when unknown, as before
    });
  }
  function isRtl() { return (document.documentElement.getAttribute("dir") || "").toLowerCase() === "rtl"; }

  var BASE = "/api/plugins/tenure";
  var POLL_MS = 2000;
  var WEEK = 7 * 86400;
  var PASSPORT_MS = 30000;  // a passport replays the ledger: fetched on open, after an action, else every 30 s

  // ----------------------------------------------------------------------------------------- pinned rule values
  // Mirrors of tenure/params.py and rule.py, used only to say what evidence is still missing and to preview N.
  var TIER = { ask: "T1", notify: "T2", alone: "T3" };
  function tierName(tier) { return t("tier.name." + tier); }
  var STAKES = ["low", "medium", "high"];
  var TRIAL = 3;            // rule.TRIAL
  var SESSIONS = 2;         // rule.SESSIONS
  var WALD = { low: [0.10, 0.30], medium: [0.05, 0.20] };     // params.WALD, alpha = beta = 0.05
  var LN_B = Math.log(0.05 / 0.95);
  var PRESETS = {           // params.PRESETS; null = capped
    careful: { low: 1 / 100, medium: 1 / 200, high: 1 / 1000 },
    balanced: { low: 1 / 50, medium: 1 / 100, high: null },
    fast: { low: 1 / 20, medium: 1 / 50, high: null }
  };
  var LADDER = [20, 50, 100, 200, 500, 1000, null];   // "1 in k" choices on the dial; null = capped

  /** params.study_n: N = ceil(1 / (0.95 * bar)) - 1, in exact integers when the bar is 1/k. */
  function studyN(bar) {
    if (bar == null) return null;
    var k = 1 / bar;
    if (Math.abs(k - Math.round(k)) < 1e-9) {
      k = Math.round(k);
      return Math.floor((20 * k + 18) / 19) - 1;     // ceil(20k / 19) - 1
    }
    return Math.ceil(1 / (0.95 * bar)) - 1;
  }

  /** Verified successes without a fault still needed before the middle tier (T2), from the Wald score. */
  function toT2(ty) {
    var w = WALD[ty.stakes];
    if (!w || !ty.reversible) return null;
    var step = -Math.log((1 - w[1]) / (1 - w[0]));
    return Math.max(0, Math.ceil((ty.wald - LN_B) / step - 1e-9));
  }

  // --------------------------------------------------------------------------------------------------- helpers
  function cx() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) if (arguments[i]) out.push(arguments[i]);
    return out.join(" ");
  }
  function qs(params) {
    var parts = [];
    for (var k in params) {
      if (params[k] === undefined || params[k] === null || params[k] === false) continue;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(params[k] === true ? "1" : params[k]));
    }
    return parts.length ? "?" + parts.join("&") : "";
  }
  function apiGet(path, params) { return SDK.fetchJSON(BASE + path + qs(params || {})); }
  function apiPost(path, body, params) {
    return SDK.fetchJSON(BASE + path + qs(params || {}), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
  }
  function errText(err) {
    var raw = err && err.message ? String(err.message) : String(err || "");
    var m = raw.match(/^(\d{3}):\s*([\s\S]*)$/);
    var body = m ? m[2] : raw;
    try {
      var d = JSON.parse(body);
      if (d && typeof d.detail === "string") return d.detail;
    } catch (e) { /* not JSON */ }
    return body || t("error.request_failed");
  }
  // Newer hosts throw an ApiError (``status``, human ``message``); older ones Error("<status>: <body>").
  function errStatus(err) {
    if (err && typeof err.status === "number") return err.status;
    var m = String((err && err.message) || "").match(/^(\d{3}):/);
    return m ? Number(m[1]) : 0;
  }
  // Numbers and percents follow the active locale (en: en-US, as before); the wording around them is in the catalog.
  var NUMFMT = {};
  function numFormat(opts, key) {
    var id = LANG + "|" + key;
    if (!NUMFMT[id]) {
      try { NUMFMT[id] = new Intl.NumberFormat(LANG === "en" ? "en-US" : LANG, opts); }
      catch (e) { NUMFMT[id] = new Intl.NumberFormat("en-US", opts); }
    }
    return NUMFMT[id];
  }
  function num(n) { return n == null ? "—" : numFormat(undefined, "n").format(Number(n)); }
  function pct(x) {
    if (x == null) return "—";
    var v = x * 100;
    if (LANG === "en") {
      if (v === 0 || v < 0.005) return "0%";
      return (v < 10 ? v.toFixed(2) : v.toFixed(1)).replace(/\.?0+$/, "") + "%";
    }
    if (v === 0 || v < 0.005) return numFormat({ style: "percent" }, "p0").format(0);
    return numFormat({ style: "percent", maximumFractionDigits: v < 10 ? 2 : 1 }, v < 10 ? "p2" : "p1").format(x);
  }
  /** One decimal, as the public scores are published (en: toFixed(1), as before). */
  function dec1(x) {
    if (LANG === "en") return x.toFixed(1);
    return numFormat({ minimumFractionDigits: 1, maximumFractionDigits: 1 }, "d1").format(x);
  }
  function totals(tot) {
    tot = tot || {};
    return [t("totals.actions", { n: tot.actions }), t("totals.checked", { n: tot.checked }),
      t("totals.alone", { n: tot.alone }), t("totals.faults", { n: tot.faults })].join(" · ");
  }
  function totalsLines(tot) {
    tot = tot || {};
    return [h("div", { key: 1 }, t("totals.actions", { n: tot.actions }) + " · " + t("totals.checked", { n: tot.checked })),
      h("div", { key: 2 }, t("totals.alone", { n: tot.alone }) + " · " + t("totals.faults", { n: tot.faults }))];
  }
  function oneIn(r) { return r == null ? t("common.capped") : t("common.one_in", { k: Math.round(1 / r) }); }
  /** A duration in seconds, short units: "12s", "5m", "2h 05m", "3d". */
  function duration(sec) {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return t("time.seconds", { n: sec });
    if (sec < 3600) return t("time.minutes", { n: Math.floor(sec / 60) });
    if (sec < 86400) {
      return t("time.hours_minutes", { n: Math.floor(sec / 3600), mm: String(Math.floor(sec % 3600 / 60)).padStart(2, "0") });
    }
    return t("time.days", { n: Math.floor(sec / 86400) });
  }
  function ago(sec) { return t("time.ago", { duration: duration(sec) }); }
  // English day labels as before ("Mon 9 Nov"); other languages take the browser's own short date.
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function hm(at) {
    var d = new Date(at * 1000);
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  function hms(ms) {
    var d = new Date(ms);
    return hm(ms / 1000) + ":" + String(d.getSeconds()).padStart(2, "0");
  }
  function dayLabel(at) {
    var d = new Date(at * 1000);
    if (LANG !== "en") {
      try { return new Intl.DateTimeFormat(LANG, { weekday: "short", day: "numeric", month: "short" }).format(d); }
      catch (e) { /* fall back to English */ }
    }
    return DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()];
  }
  function dayKey(at) { var d = new Date(at * 1000); return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
  function short(hash, n) { return hash ? String(hash).slice(0, n || 12) : "—"; }
  function agentKey(profile, agent) { return profile + "\u0000" + agent; }
  function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    } catch (e) { /* fall through */ }
    var ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
    return Promise.resolve();
  }
  function luminance(color) {
    var m = String(color || "").trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (!m) return 0;
    var x = m[1].length === 3 ? m[1].replace(/(.)/g, "$1$1") : m[1];
    var c = [0, 2, 4].map(function (i) { return parseInt(x.substr(i, 2), 16) / 255; });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  function typing(e) {
    var el = e.target;
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  /** Poll ``fn`` every POLL_MS while the page is visible; ``deps`` restart it. */
  function usePoll(fn, deps, enabled, every) {
    var period = every || POLL_MS;
    var state = useState({ data: null, error: null, at: 0 });
    var set = state[1];
    var alive = useRef(true);
    var tickRef = useRef(0);
    useEffect(function () {
      alive.current = true;
      if (enabled === false) return function () { alive.current = false; };
      var timer = null;
      var my = ++tickRef.current;
      function run() {
        if (document.hidden) { timer = setTimeout(run, period); return; }
        Promise.resolve().then(fn).then(function (data) {
          if (alive.current && my === tickRef.current) set({ data: data, error: null, at: Date.now() });
        }, function (err) {
          if (alive.current && my === tickRef.current) set(function (s) { return { data: s.data, error: err, at: s.at }; });
        }).then(function () {
          if (alive.current && my === tickRef.current) timer = setTimeout(run, period);
        });
      }
      run();
      return function () { alive.current = false; if (timer) clearTimeout(timer); };
      // eslint-disable-next-line
    }, deps);
    return state[0];
  }

  /** Height of a host bar fixed or sticky at the top of the window (the dashboard's mobile header), so an overlay
   * opens below it instead of under it. 0 when there is none. */
  function useHostBarOffset() {
    var st = useState(0), set = st[1];
    useEffect(function () {
      var el = document.elementFromPoint(Math.floor(window.innerWidth / 2), 2);
      while (el && el !== document.body) {
        if (el.closest && el.closest(".tnr")) break;
        var pos = getComputedStyle(el).position;
        if (pos === "fixed" || pos === "sticky") {
          var r = el.getBoundingClientRect();
          if (r.top <= 0 && r.bottom > 0 && r.bottom < window.innerHeight / 3) { set(Math.round(r.bottom)); return; }
        }
        el = el.parentElement;
      }
    }, []);
    return st[0];
  }

  // ------------------------------------------------------------------------------------------------ small parts
  function Kbd(props) { return h("kbd", { className: "tnr-kbd" }, props.children); }

  var TIER_TONE = { ask: "outline", notify: "secondary", alone: "success" };
  function TierChip(props) {
    var tier = props.tier;
    var B = UI.Badge || "span";
    if (props.capped) return h(B, { tone: "outline", className: "tnr-tier", title: t("tier.capped.title") }, t("tier.capped.chip"));
    return h(B, { tone: TIER_TONE[tier] || "outline", className: "tnr-tier tnr-tier--" + tier,
      title: t("tier.chip.title", { tier: TIER[tier], name: tierName(tier) }) }, TIER[tier]);
  }

  // State flags keep the tab's own readable style: the SDK Badge uses a display face too small for a phrase.
  function Flag(props) {
    return h("span", { className: "tnr-flag tnr-flag--" + props.kind, title: props.title || "" }, props.children);
  }

  /** The dashboard's Select (a native one if the SDK has none): options as [value, label] pairs. */
  function Sel(props) {
    if (UI.Select && UI.SelectOption) {
      return h(UI.Select, { value: props.value, onValueChange: props.onChange, className: "tnr-select-ui" },
        props.options.map(function (o) { return h(UI.SelectOption, { key: o[0], value: o[0] }, o[1]); }));
    }
    return h("select", { className: "tnr-select", value: props.value, "aria-label": props.label,
      onChange: function (e) { props.onChange(e.target.value); } },
      props.options.map(function (o) { return h("option", { key: o[0], value: o[0] }, o[1]); }));
  }

  function Empty(props) {
    return h("div", { className: "tnr-empty" },
      h("div", { className: "tnr-empty-title" }, props.title),
      props.children ? h("div", { className: "tnr-empty-body" }, props.children) : null);
  }

  function Btn(props) {
    var k = props.kind;
    if (UI.Button) {
      return h(UI.Button, {
        type: "button", size: "sm", className: props.className, onClick: props.onClick, disabled: props.disabled,
        title: props.title, "aria-live": props.live ? "polite" : undefined,
        ghost: k === "ghost" || k === "danger-ghost", destructive: k === "danger" || k === "danger-ghost", outlined: !k
      }, props.children);
    }
    return h("button", {
      type: "button", className: cx("tnr-btn", k && "tnr-btn--" + k, props.className),
      onClick: props.onClick, disabled: props.disabled, title: props.title, "aria-live": props.live ? "polite" : undefined
    }, props.children);
  }

  /** A button that asks once more before it acts: first click arms it, second click within 4 s confirms. */
  function ConfirmBtn(props) {
    var s = useState(false), armed = s[0], setArmed = s[1];
    var b = useState(false), busy = b[0], setBusy = b[1];
    useEffect(function () {
      if (!armed) return undefined;
      var tm = setTimeout(function () { setArmed(false); }, 4000);
      return function () { clearTimeout(tm); };
    }, [armed]);
    return h(Btn, {
      kind: armed ? "danger" : props.kind, disabled: props.disabled || busy, live: true,
      title: armed ? t("confirm.again") : props.title,
      onClick: function () {
        if (!armed) { setArmed(true); return; }
        setArmed(false); setBusy(true);
        Promise.resolve(props.onConfirm()).then(function () { setBusy(false); }, function () { setBusy(false); });
      }
    }, busy ? "…" : armed ? props.confirm || t("confirm.default") : props.children);
  }

  function CopyCmd(props) {
    var s = useState(false), done = s[0], setDone = s[1];
    return h("div", { className: "tnr-cmd" },
      h("code", null, props.cmd),
      h(Btn, {
        kind: "ghost", onClick: function () {
          copyText(props.cmd).then(function () { setDone(true); setTimeout(function () { setDone(false); }, 1500); });
        }
      }, done ? t("copy.done") : t("copy.button")));
  }

  // ----------------------------------------------------------------------------------------- evidence wording
  /** What a type still needs, said as missing evidence (never a gauge). */
  function missing(ty) {
    if (ty.capped) return { text: t("missing.always_asks"), tone: "muted" };
    if (ty.trial_wait) return { text: t("missing.trial_wait", { n: ty.trial_wait }), tone: "warn" };
    if (ty.trial_left) return { text: t("missing.trial_left", { n: String(ty.trial_left), total: String(TRIAL) }), tone: "warn" };
    var eff = ty.effective_tier;
    if (eff === "alone") return { text: t("missing.earned"), tone: "ok" };
    var gap = (ty.required || 0) - ty.series;
    if (gap <= 0 && ty.sessions < SESSIONS) return { text: t("missing.second_session"), tone: "muted" };
    var parts = [];
    if (eff === "ask") {
      var t2 = toT2(ty);
      if (t2) parts.push(t("missing.more_to_t2", { n: t2 }));
    }
    if (gap > 0) parts.push(t("missing.more_to_t3", { n: gap }));
    return { text: parts.join(" · ") || t("missing.rechecking"), tone: "muted" };
  }

  function guaranteeText(g) {
    if (!g || g.capped) return t("guarantee.capped");
    return t(g.conditional ? "guarantee.text_conditional" : "guarantee.text", { aoql: pct(g.aoql), worst: pct(g.worst_case) });
  }

  var PRESET_IDS = ["careful", "balanced", "fast", "custom"];
  function presetName(p) { return PRESET_IDS.indexOf(p) >= 0 ? t("preset." + p) : p; }
  function profileSettings(st) {
    var parts = [t("profile.preset", { preset: presetName(st.preset) }), t("profile.spot", { rate: oneIn(st.spot) })];
    if (st.strict) parts.push(t("profile.strict"));
    if (st.pending) parts.push(t("profile.pending"));
    return parts.join(" · ");
  }

  function cellTitle(ty) {
    var stakes = t("stakes.group." + ty.stakes);
    var tierNow = t("cell.tier_now", { tier: TIER[ty.effective_tier], name: tierName(ty.effective_tier) });
    var lines = [t(ty.reversible ? "cell.kind_reversible" : "cell.kind_irreversible", { type: ty.type, stakes: stakes }),
      ty.tier !== ty.effective_tier ? tierNow + " · " + t("cell.held", { tier: TIER[ty.tier] }) : tierNow,
      ty.capped ? t("cell.capped_by_settings") : t("cell.series", { series: String(ty.series), required: String(ty.required) }) +
        " · " + t("cell.sessions", { n: ty.sessions, count: String(ty.sessions) }),
      t("cell.record", { successes: String(ty.successes), faults: String(ty.faults), neutrals: String(ty.neutrals),
        spot: String(ty.spot_checks) })];
    if (ty.provisional) lines.push(t("cell.provisional_long", { n: ty.provisional, count: String(ty.provisional) }));
    if (ty.unresolved_fault) lines.push(t("flag.fault_on_record_title"));
    return lines.join("\n");
  }

  // ------------------------------------------------------------------------------------------------ the header
  function Counters(props) {
    var tot = props.totals;
    var cells = [
      { n: tot ? tot.actions : null, label: t("counters.actions.label", { n: tot ? tot.actions : 0 }), sub: t("counters.actions.sub") },
      { n: tot ? tot.checked : null, label: t("counters.checked.label"), sub: tot ? t("counters.checked.sub", { total: tot.actions }) : "" },
      { n: tot ? tot.alone : null, label: t("counters.alone.label"), sub: tot ? t("counters.alone.sub", { total: tot.actions }) : "" },
      { n: tot ? tot.faults : null, label: t("counters.faults.label"),
        sub: tot ? t("counters.faults.sub", { faults: tot.faults, n: tot.checked }) : "" }
    ];
    return h("div", { className: "tnr-counters", "aria-label": t("counters.aria") },
      cells.map(function (c, i) {
        return h(Fragment, { key: i },
          i ? h("span", { className: "tnr-counter-dot", "aria-hidden": true }, "·") : null,
          h("div", { className: "tnr-counter" },
            h("span", { className: "tnr-counter-n" }, num(c.n)),
            h("span", { className: "tnr-counter-label" }, c.label),
            h("span", { className: "tnr-counter-sub" }, c.sub)));
      }),
      h("span", { className: "tnr-counter-window" }, t("counters.window")));
  }

  var VIEWS = [
    { id: "map", key: "m" },            // label: the catalog key view.<id>
    { id: "models", key: "b" },
    { id: "switch", key: "w" },
    { id: "passport", key: "p" },
    { id: "undo", key: "u" },
    { id: "settings", key: "s" }
  ];

  function Tabs(props) {
    var List = UI.TabsList || "div", Trigger = UI.TabsTrigger || "button";
    return h("nav", { className: "tnr-tabs", "aria-label": t("tabs.aria") },
      h(List, { role: "tablist", className: "tnr-tablist" },
        VIEWS.map(function (v) {
          var badge = v.id === "undo" && props.undoCount ? h("span", { className: "tnr-tab-count" }, num(props.undoCount)) : null;
          var active = props.view === v.id;
          return h(Trigger, {
            key: v.id, type: "button", role: "tab", "aria-selected": active, active: active, value: v.id,
            tabIndex: active ? 0 : -1, id: "tnr-tab-" + v.id, "aria-controls": "tnr-panel",
            className: cx("tnr-tab", active && "is-active"),
            onClick: function () { props.onView(v.id); },
            onKeyDown: function (e) {
              var fwd = isRtl() ? "ArrowLeft" : "ArrowRight", back = isRtl() ? "ArrowRight" : "ArrowLeft";
              var i = VIEWS.indexOf(v), next = e.key === fwd ? i + 1 : e.key === back ? i - 1 : null;
              if (next === null) return;
              var w = VIEWS[(next + VIEWS.length) % VIEWS.length];
              props.onView(w.id);
              e.preventDefault();
              setTimeout(function () { var el = document.getElementById("tnr-tab-" + w.id); if (el) el.focus(); }, 0);
            }
          }, t("view." + v.id), badge);
        })));
  }

  // ------------------------------------------------------------------------------------------------------- map
  function columns(profiles) {
    var seen = {}, groups = { low: [], medium: [], high: [] };
    profiles.forEach(function (p) {
      (p.agents || []).forEach(function (a) {
        a.types.forEach(function (ty) {
          if (seen[ty.type]) return;
          seen[ty.type] = 1;
          (groups[ty.stakes] || (groups[ty.stakes] = [])).push(ty.type);
        });
      });
    });
    var out = [];
    Object.keys(groups).sort(function (a, b) {
      return (STAKES.indexOf(a) + 9) % 9 - (STAKES.indexOf(b) + 9) % 9;
    }).forEach(function (s) {
      groups[s].sort();
      if (groups[s].length) out.push({ stakes: s, types: groups[s] });
    });
    return out;
  }

  function Cell(props) {
    var ty = props.t;
    if (!ty) return h("td", { className: "tnr-cell tnr-cell--none" }, h("span", { className: "tnr-none" }, "—"));
    var miss = missing(ty);
    var held = ty.tier !== ty.effective_tier;
    var flags = [];
    if (ty.provisional) {
      flags.push(h(Flag, { key: "p", kind: "prov", title: t("flag.carried_over_title", { n: ty.provisional, count: String(ty.provisional) }) },
        t("flag.carried_over_n", { n: ty.provisional })));
    }
    if (ty.unresolved_fault) flags.push(h(Flag, { key: "f", kind: "fault", title: t("flag.fault_on_record_title") }, t("flag.fault_on_record")));
    return h("td", {
      className: cx("tnr-cell", "tnr-cell--" + (ty.capped ? "cap" : ty.effective_tier), ty.provisional && "is-prov",
        (ty.trial_left || ty.trial_wait) && "is-trial"),
      title: cellTitle(ty)
    },
      h("div", { className: "tnr-cell-top" },
        h(TierChip, { tier: ty.effective_tier, capped: ty.capped }),
        ty.capped ? h("span", { className: "tnr-cell-ev" }, num(ty.successes + ty.faults), h("span", { className: "tnr-dim" }, t("cell.asked_suffix")))
          : h("span", { className: "tnr-cell-ev" }, num(ty.series), h("span", { className: "tnr-dim" }, "/" + num(ty.required)))),
      h("div", { className: "tnr-cell-mid" },
        ty.capped ? h("span", null, t("count.faults", { n: ty.faults })) : h("span", null, t("count.sessions", { n: ty.sessions })),
        held ? h("span", { className: "tnr-held" }, t("cell.held", { tier: TIER[ty.tier] })) : null),
      h("div", { className: "tnr-cell-miss tnr-tone--" + miss.tone }, miss.text),
      flags.length ? h("div", { className: "tnr-cell-flags" }, flags) : null);
  }

  function MapView(props) {
    var profiles = props.profiles;
    var cols = useMemo(function () { return columns(profiles); }, [profiles]);
    var rows = props.rows;
    if (!rows.length) {
      return h(Empty, { title: t("map.empty.title") },
        t("map.empty.before"), h("b", null, t("map.empty.bold")), t("map.empty.after"));
    }
    var current = props.settings;
    var byProfile = [];
    rows.forEach(function (r, i) {
      var last = byProfile[byProfile.length - 1];
      if (!last || last.profile !== r.profile) byProfile.push(last = { profile: r.profile, info: r.info, rows: [] });
      last.rows.push({ r: r, i: i });
    });
    var ncols = cols.reduce(function (n, g) { return n + g.types.length; }, 0);
    var table = h("div", { className: "tnr-map-scroll" },
      h("table", { className: "tnr-map", role: "grid", "aria-label": t("map.aria"), style: { minWidth: 248 + ncols * 140 } },
        h("colgroup", null, h("col", { className: "tnr-col-agent" }),
          cols.map(function (g) {
            return g.types.map(function (ty) {
              return h("col", { key: ty, className: "tnr-col-type", style: { width: "calc((100% - 248px) / " + ncols + ")" } });
            });
          })),
        h("thead", null,
          h("tr", { className: "tnr-map-groups" },
            h("th", { className: "tnr-th-agent", rowSpan: 2, scope: "col" },
              h("span", { className: "tnr-th-label" }, t("map.th.agent")),
              h("span", { className: "tnr-th-sub" }, t("map.th.agent_sub"))),
            cols.map(function (g) {
              var n = current ? studyN(current.risks[g.stakes]) : null;
              return h("th", { key: g.stakes, colSpan: g.types.length, className: "tnr-th-group tnr-stakes--" + g.stakes, scope: "colgroup" },
                h("span", { className: "tnr-th-label" }, t("stakes.group." + g.stakes)),
                h("span", { className: "tnr-th-sub" }, n == null ? (g.stakes === "high" ? t("map.th.capped") : "") :
                  t("map.th.risk", { risk: oneIn(current.risks[g.stakes]), n: n })));
            })),
          h("tr", { className: "tnr-map-types" },
            cols.map(function (g) {
              return g.types.map(function (ty) {
                return h("th", { key: ty, scope: "col", className: "tnr-th-type" }, h("code", null, ty));
              });
            }))),
        byProfile.map(function (grp) {
          return h("tbody", { key: grp.profile },
            h("tr", { className: "tnr-map-profile" },
              h("th", { colSpan: ncols + 1, scope: "rowgroup" },
                h("span", { className: "tnr-profile-name" }, grp.profile),
                h("span", { className: "tnr-dim" }, grp.info.current ? t("profile.this_dashboard") : t("profile.read_only")),
                grp.info.suspended ? h(Flag, { kind: "warn" }, t("profile.sessions_suspended", { n: grp.info.suspended })) : null,
                grp.info.settings ? h("span", { className: "tnr-dim tnr-profile-preset" }, profileSettings(grp.info.settings)) : null)),
            grp.rows.map(function (x) {
              var r = x.r, a = r.agent;
              var byType = {};
              a.types.forEach(function (ty) { byType[ty.type] = ty; });
              var tot = a.totals || {};
              return h("tr", {
                key: r.key, className: cx("tnr-map-row", x.i === props.focus && "is-focus"),
                onClick: function () { props.onFocus(x.i); props.onOpen(r); },
                "aria-selected": x.i === props.focus
              },
                h("th", { scope: "row", className: "tnr-td-agent" },
                  h("div", { className: "tnr-agent-model" }, a.model, h("span", { className: "tnr-dim" }, "@" + a.provider)),
                  h("div", { className: "tnr-agent-tot" }, totalsLines(tot)),
                  h("div", { className: "tnr-agent-flags" },
                    a.provisional ? h(Flag, { kind: "prov" }, t("flag.provisional")) : null,
                    a.trial ? h(Flag, { kind: "warn" }, t("flag.trial")) : null,
                    a.unresolved_fault ? h(Flag, { kind: "fault" }, t("flag.fault_on_record")) : null,
                    h("span", { className: "tnr-open-hint" }, t("map.open_hint"), h(Kbd, null, "↵")))),
                cols.map(function (g) {
                  return g.types.map(function (ty) { return h(Cell, { key: ty, t: byType[ty] }); });
                }));
            }));
        })));

    var cards = h("div", { className: "tnr-map-cards" },
      byProfile.map(function (grp) {
        return h("section", { key: grp.profile, className: "tnr-card-group" },
          h("div", { className: "tnr-map-profile tnr-map-profile--card" },
            h("span", { className: "tnr-profile-name" }, grp.profile),
            h("span", { className: "tnr-dim" }, grp.info.current ? t("profile.this_dashboard") : t("profile.read_only")),
            grp.info.suspended ? h(Flag, { kind: "warn" }, t("profile.suspended", { n: grp.info.suspended })) : null),
          grp.rows.map(function (x) {
            var r = x.r, a = r.agent, tot = a.totals || {};
            return h("button", {
              type: "button", key: r.key, className: cx("tnr-agent-card", x.i === props.focus && "is-focus"),
              onClick: function () { props.onFocus(x.i); props.onOpen(r); }
            },
              h("div", { className: "tnr-agent-model" }, a.model, h("span", { className: "tnr-dim" }, "@" + a.provider)),
              h("div", { className: "tnr-agent-tot" }, totals(tot)),
              h("div", { className: "tnr-card-types" },
                a.types.slice().sort(function (p, q) {
                  return STAKES.indexOf(p.stakes) - STAKES.indexOf(q.stakes) || (p.type < q.type ? -1 : 1);
                }).map(function (ty) {
                  var miss = missing(ty);
                  return h("div", { key: ty.type, className: "tnr-card-type" },
                    h(TierChip, { tier: ty.effective_tier, capped: ty.capped }),
                    h("code", { className: "tnr-card-type-name" }, ty.type),
                    h("span", { className: "tnr-card-type-ev" }, ty.capped ? t("common.capped") : num(ty.series) + "/" + num(ty.required)),
                    h("span", { className: "tnr-card-type-miss tnr-tone--" + miss.tone },
                      ty.tier !== ty.effective_tier ? t("cell.held", { tier: TIER[ty.tier] }) :
                        ty.provisional ? t("flag.carried_over_n", { n: ty.provisional }) + " · " + miss.text :
                          ty.unresolved_fault ? t("flag.fault_on_record") + " · " + miss.text : miss.text));
                })));
          }));
      }));

    return h("div", { className: "tnr-mapview" },
      table, cards,
      h(Legend, { spot: props.settings && props.settings.spot }),
      h(Transitions, { items: props.transitions }));
  }

  function Legend(props) {
    return h("div", { className: "tnr-legend" },
      h("span", null, h(TierChip, { tier: "ask" }), " " + t("legend.ask")),
      h("span", null, h(TierChip, { tier: "notify" }), " " + t("legend.notify")),
      h("span", null, h(TierChip, { tier: "alone" }), " " + t("legend.alone", { share: props.spot ? oneIn(props.spot) : t("legend.a_share") })),
      h("span", null, h(TierChip, { capped: true }), " " + t("legend.capped")),
      h("span", null, h("span", { className: "tnr-mono" }, "n/N"), " " + t("legend.series")),
      h("span", null, h(Flag, { kind: "prov" }, t("flag.carried_over")), " " + t("legend.carried")));
  }

  function Transitions(props) {
    return h("section", { className: "tnr-transitions", "aria-live": "polite" },
      h("div", { className: "tnr-section-title" }, t("transitions.title")),
      props.items.length ? h("ol", { className: "tnr-trans-list" },
        props.items.slice(0, 8).map(function (x) {
          return h("li", { key: x.id },
            h("span", { className: "tnr-mono tnr-dim" }, hms(x.at)),
            h("span", null, x.agent),
            h("code", null, x.type),
            h("span", { className: "tnr-trans-move" }, h(TierChip, { tier: x.from, capped: false }), " " + t("common.arrow") + " ", h(TierChip, { tier: x.to, capped: false })),
            h("span", { className: "tnr-dim" }, t("transitions.why." + x.why)));
        })) : h("div", { className: "tnr-dim tnr-trans-empty" }, t("transitions.empty")));
  }

  // ---------------------------------------------------------------------------------------------- agent drawer
  var FAULT_SOURCES = ["refusal", "spot", "check", "undo", "flag"];
  var NEUTRAL_SOURCES = ["alone", "error", "blocked", "timeout", "nobody", "expired", "ambiguous"];
  var TIER_REASONS = ["wald", "fault", "settings", "stakes"];
  function describeEvent(e) {
    var src = e.source;
    if (e.event === "outcome") {
      if (e.result === "success") {
        return { glyph: "✓", tone: "ok", text: src === "notify" ? t("event.success.notify") :
          src === "spot" ? t("event.success.spot") : t("event.success.approved") };
      }
      if (e.result === "fault") {
        return { glyph: "✕", tone: "fault", text: FAULT_SOURCES.indexOf(src) >= 0 ? t("event.fault." + src) : t("event.fault.other", { source: String(src) }) };
      }
      return { glyph: "○", tone: "muted", text: NEUTRAL_SOURCES.indexOf(src) >= 0 ? t("event.neutral." + src) : t("event.neutral.other", { source: String(src) }) };
    }
    if (e.event === "tier") {
      var series = e.required ? t("event.why.series_n", { required: String(e.required) }) : t("event.why.series_complete");
      var why = e.reason === "series" ? (e.sessions ? series + " · " + t("event.why.sessions", { n: e.sessions, count: String(e.sessions) }) : series) :
        TIER_REASONS.indexOf(e.reason) >= 0 ? t("event.why." + e.reason) : e.reason;
      return { glyph: "◆", tone: "move", move: [e.from, e.to], text: t("event.tier", { from: TIER[e.from], to: TIER[e.to], why: why }) };
    }
    if (e.event === "trial") {
      var left = String(e.left || TRIAL);
      var tt = e.to === "open" ? (e.reason === "wait over" ? t("event.trial.reopens", { n: e.left || TRIAL, left: left }) :
        t("event.trial.opened", { n: e.left || TRIAL, left: left })) :
        e.to === "wait" ? t("event.trial.failed", { n: Number(e.wait) || 0, wait: String(e.wait || "") }) : t("event.trial.passed");
      return { glyph: "◇", tone: "warn", text: tt };
    }
    if (e.event === "revoke" || e.event === "revoked") return { glyph: "↺", tone: "fault", text: t("event.revoked") };
    if (e.event === "confirmed") return { glyph: "✓", tone: "ok", text: t("event.confirmed") };
    if (e.event === "agent") return { glyph: "⇄", tone: "move", text: e.from ? t("event.switch_from", { from: e.from }) : t("event.switch") };
    if (e.event === "neutral_expired") return { glyph: "○", tone: "muted", text: t("event.neutral_expired") };
    return { glyph: "·", tone: "muted", text: e.event };
  }

  /** Consecutive identical events (same kind, result, source and type) collapse into one row with a count. */
  function runs(events) {
    var out = [];
    events.forEach(function (e) {
      var sig = [e.event, e.result, e.source, e.type, e.reason, e.from, e.to].join("|");
      var last = out[out.length - 1];
      if (last && last.sig === sig && e.event === "outcome" && dayKey(last.first.at) === dayKey(e.at)) {
        last.count += 1; last.last = e;
      } else out.push({ sig: sig, first: e, last: e, count: 1 });
    });
    return out;
  }

  function Timeline(props) {
    var events = props.events;
    if (!events) return h("div", { className: "tnr-dim tnr-pad" }, t("timeline.loading"));
    if (!events.length) return h(Empty, { title: t("timeline.empty") });
    var groups = [];
    runs(events).forEach(function (r) {
      var k = dayKey(r.first.at);
      var g = groups[groups.length - 1];
      if (!g || g.key !== k) groups.push(g = { key: k, label: dayLabel(r.first.at), items: [] });
      g.items.push(r);
    });
    return h("div", { className: "tnr-timeline" },
      groups.map(function (g) {
        return h("section", { key: g.key, className: "tnr-tl-day" },
          h("div", { className: "tnr-tl-daylabel" }, g.label),
          h("ol", null, g.items.map(function (r) {
            var d = describeEvent(r.first);
            var span = r.count > 1 && hm(r.last.at) !== hm(r.first.at) ? hm(r.last.at) + "–" + hm(r.first.at) : hm(r.first.at);
            return h("li", { key: r.first.seq, className: cx("tnr-tl-item", "tnr-tone--" + d.tone, d.tone === "move" && "is-move") },
              h("span", { className: "tnr-tl-time" }, span),
              h("span", { className: "tnr-tl-glyph", "aria-hidden": true }, d.glyph),
              h("span", { className: "tnr-tl-text" },
                r.count > 1 ? h("b", { className: "tnr-tl-count" }, t("timeline.count", { n: r.count })) : null,
                d.text),
              r.first.type ? h("code", { className: "tnr-tl-type" }, r.first.type) : null,
              h("span", { className: "tnr-tl-seq" }, "#" + (r.count > 1 ? r.last.seq + "–" + r.first.seq : r.first.seq)));
          })));
      }));
  }

  function AgentDrawer(props) {
    var row = props.row, a = row.agent;
    var closeRef = useRef(null);
    useEffect(function () {
      var before = document.activeElement;
      var el = closeRef.current && (closeRef.current.querySelector ? closeRef.current.querySelector("button") || closeRef.current : closeRef.current);
      if (el && el.focus) el.focus();
      return function () { if (before && before.focus) before.focus(); };
    }, []);
    var mine = row.info.current;
    var fs = useState("all"), filter = fs[0], setFilter = fs[1];
    var top = useHostBarOffset();
    var tl = usePoll(function () {
      return apiGet("/timeline", { agent: a.agent, of: row.profile, raw: props.raw });
    }, [a.agent, row.profile, props.raw, props.version]);
    var events = tl.data ? tl.data.events : null;
    var shown = events && filter !== "all" ? events.filter(function (e) { return e.type === filter; }) : events;
    var types = a.types.slice().sort(function (p, q) {
      return STAKES.indexOf(p.stakes) - STAKES.indexOf(q.stakes) || (p.type < q.type ? -1 : 1);
    });
    function act(path, body, ok) {
      return apiPost(path, body, { raw: props.raw }).then(function (res) { props.onDone(ok(res), "success"); },
        function (err) { props.onDone(errText(err), "error"); throw err; });
    }
    var tot = a.totals || {};
    return h("div", { className: "tnr-drawer-wrap", style: top ? { top: top } : null,
      onClick: function (e) { if (e.target === e.currentTarget) props.onClose(); } },
      h("aside", { className: "tnr-drawer", role: "dialog", "aria-modal": true, "aria-label": t("drawer.aria", { agent: a.agent }),
        onKeyDown: function (e) {                       // focus stays in the dialog: Tab wraps around
          if (e.key !== "Tab") return;
          var f = e.currentTarget.querySelectorAll("button:not([disabled]), select, input, [tabindex='0']");
          if (!f.length) return;
          var first = f[0], last = f[f.length - 1];
          if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
          else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
        } },
        h("header", { className: "tnr-drawer-head" },
          h("div", null,
            h("div", { className: "tnr-drawer-eyebrow" }, t(mine ? "drawer.eyebrow" : "drawer.eyebrow_read_only", { profile: row.profile })),
            h("div", { className: "tnr-drawer-title" }, a.model, h("span", { className: "tnr-dim" }, "@" + a.provider)),
            h("div", { className: "tnr-agent-tot" }, totals(tot),
              row.info.suspended ? h(Flag, { kind: "warn" }, t("profile.suspended", { n: row.info.suspended })) : null)),
          h("span", { ref: closeRef }, h(Btn, { kind: "ghost", onClick: props.onClose, title: t("drawer.close_title") }, t("drawer.close")))),
        h("div", { className: "tnr-drawer-body" },
          h("div", { className: "tnr-section-title" }, t("drawer.types_title")),
          h("table", { className: "tnr-dtable" },
            h("thead", null, h("tr", null,
              h("th", null, t("th.type")), h("th", null, t("th.tier")), h("th", { className: "tnr-num" }, t("th.series")),
              h("th", { className: "tnr-num" }, t("th.sessions")), h("th", { className: "tnr-num" }, t("th.faults_checks")), h("th", null, ""))),
            h("tbody", null, types.map(function (ty) {
              var miss = missing(ty);
              return h(Fragment, { key: ty.type },
                h("tr", { className: "tnr-dtable-main" },
                  h("td", null, h("code", null, ty.type), h("div", { className: "tnr-dim tnr-small" },
                    ty.reversible ? t("drawer.stakes_reversible", { stakes: t("stakes." + ty.stakes) }) : t("stakes." + ty.stakes))),
                  h("td", null, h(TierChip, { tier: ty.effective_tier, capped: ty.capped }),
                    ty.tier !== ty.effective_tier ? h("div", { className: "tnr-held" }, t("cell.held", { tier: TIER[ty.tier] })) : null),
                  h("td", { className: "tnr-num" }, ty.capped ? "—" : num(ty.series) + "/" + num(ty.required)),
                  h("td", { className: "tnr-num" }, ty.capped ? "—" : num(ty.sessions) + "/" + SESSIONS),
                  h("td", { className: "tnr-num" }, num(ty.faults) + " / " + num(ty.successes + ty.faults)),
                  h("td", { className: "tnr-dtable-actions" },
                    h(ConfirmBtn, {
                      disabled: !mine, confirm: t("drawer.flag.confirm"),
                      title: mine ? t("drawer.flag.title") : t("drawer.own_profile_only"),
                      onConfirm: function () {
                        return act("/flag", { agent: a.agent, type: ty.type }, function (r) {
                          return t("drawer.flag.done", { type: ty.type, tier: TIER[r.tier] });
                        });
                      }
                    }, t("drawer.flag.button")),
                    h(ConfirmBtn, {
                      disabled: !mine, confirm: t("drawer.revoke.confirm"),
                      title: mine ? t("drawer.revoke.title") : t("drawer.own_profile_only"),
                      onConfirm: function () {
                        return act("/revoke", { agent: a.agent, type: ty.type }, function () { return t("drawer.revoke.done", { type: ty.type }); });
                      }
                    }, t("drawer.revoke.button")))),
                h("tr", { className: "tnr-dtable-sub" },
                  h("td", { colSpan: 6 },
                    h("span", { className: "tnr-mobile-only" }, t("drawer.mobile_summary", {
                      sessions: ty.capped ? t("common.capped") : t("drawer.sessions_of", { n: ty.sessions, total: String(SESSIONS) }),
                      faults: ty.faults, checks: ty.successes + ty.faults })),
                    h("span", { className: "tnr-tone--" + miss.tone }, miss.text),
                    ty.provisional ? h("span", null, " · " + t("flag.carried_over_provisional", { n: ty.provisional })) : null,
                    ty.unresolved_fault ? h("span", { className: "tnr-tone--fault" }, " · " + t("flag.fault_on_record")) : null,
                    ty.effective_tier === "alone" ? h("div", { className: "tnr-guarantee" }, guaranteeText(ty.guarantee)) : null)));
            }))),
          h("div", { className: "tnr-drawer-revoke" },
            h(ConfirmBtn, {
              kind: "danger-ghost", disabled: !mine, confirm: t("drawer.revoke_all.confirm"),
              onConfirm: function () {
                return act("/revoke", { agent: a.agent, all: true }, function (r) {
                  return t("drawer.revoke_all.done", { n: r.revoked.length, count: String(r.revoked.length) });
                });
              }
            }, t("drawer.revoke_all.button")),
            h("span", { className: "tnr-dim tnr-small" }, mine ? t("drawer.revoke_note") :
              t("drawer.revoke_note_other", { cmd: "hermes -p " + row.profile + " tenure revoke" }))),
          h("div", { className: "tnr-section-title tnr-tl-head" },
            h("span", null, t("timeline.title")),
            h(Sel, { value: filter, onChange: setFilter, label: t("timeline.filter_label"),
              options: [["all", t("timeline.all_types")]].concat(types.map(function (ty) { return [ty.type, ty.type]; })) })),
          h("div", { className: "tnr-dim tnr-small tnr-tl-note" }, t("timeline.note")),
          tl.error ? h("div", { className: "tnr-error" }, errText(tl.error)) : h(Timeline, { events: shown }))));
  }

  // ---------------------------------------------------------------------------------------------------- models
  function Interval(props) {
    var w = 96, max = props.max || 1;
    var x = function (v) { return 2 + (w - 4) * Math.min(1, v / max); };
    var lo = x(props.low), hi = x(props.high), p = props.rate == null ? null : x(props.rate);
    return h("svg", { className: "tnr-interval", width: w, height: 14, viewBox: "0 0 " + w + " 14", "aria-hidden": true },
      h("line", { x1: 2, x2: w - 2, y1: 7, y2: 7, className: "tnr-interval-axis" }),
      h("line", { x1: lo, x2: hi, y1: 7, y2: 7, className: "tnr-interval-range" }),
      h("line", { x1: lo, x2: lo, y1: 3, y2: 11, className: "tnr-interval-range" }),
      h("line", { x1: hi, x2: hi, y1: 3, y2: 11, className: "tnr-interval-range" }),
      p == null ? null : h("circle", { cx: p, cy: 7, r: 2.5, className: "tnr-interval-point" }));
  }

  function Stale(props) {
    return props.res.error && props.res.data ? h("div", { className: "tnr-msg tnr-tone--warn" },
      t("stale.message", { error: errText(props.res.error), time: hms(props.res.at) })) : null;
  }

  function ModelsView(props) {
    var res = usePoll(function () { return apiGet("/models", { raw: props.raw }); }, [props.raw, props.version]);
    if (res.error && !res.data) return h("div", { className: "tnr-error" }, errText(res.error));
    if (!res.data) return h("div", { className: "tnr-dim tnr-pad" }, t("common.loading"));
    var rows = res.data.rows;
    if (!rows.length) return h(Empty, { title: t("models.empty.title") }, t("models.empty.body", { cmd: "hermes tenure models" }));
    var byType = [];
    rows.forEach(function (r) {
      var g = byType[byType.length - 1];
      if (!g || g.type !== r.type) byType.push(g = { type: r.type, rows: [] });
      g.rows.push(r);
    });
    return h("div", { className: "tnr-models" }, h(Stale, { res: res }),
      h("p", { className: "tnr-lede" },
        t("models.lede"), h("b", null, t("models.lede_bold"))),
      byType.map(function (g) {
        var max = Math.max.apply(null, g.rows.filter(function (r) { return r.successes + r.faults; }).map(function (r) { return r.high; }).concat([0.05]));
        max = Math.min(1, Math.ceil(max * 20) / 20);
        var bench = g.rows[0].benchmark;
        var card = g.rows[0].public || {};
        return h("section", { key: g.type, className: "tnr-model-block" },
          h("div", { className: "tnr-model-head" }, h("code", null, g.type),
            h("span", { className: "tnr-dim" }, t("count.agents", { n: g.rows.length }))),
          h("div", { className: "tnr-model-split" },
            h("div", { className: "tnr-model-personal" },
              h("div", { className: "tnr-section-title" }, t("models.personal_title")),
              h("table", { className: "tnr-dtable tnr-dtable--models" },
                h("thead", null, h("tr", null,
                  h("th", { className: "tnr-num" }, "#"), h("th", null, t("th.agent")), h("th", { className: "tnr-num" }, t("th.faults_checks")),
                  h("th", { className: "tnr-num" }, t("th.rate")), h("th", null, t("th.range", { max: pct(max) })), h("th", { className: "tnr-num" }, t("th.sessions")))),
                h("tbody", null, g.rows.map(function (r, i) {
                  var n = r.successes + r.faults;
                  return h("tr", { key: r.profile + r.agent },
                    h("td", { className: "tnr-num tnr-dim" }, i + 1),
                    h("td", null, h("div", null, r.model, h("span", { className: "tnr-dim" }, "@" + r.provider)),
                      h("div", { className: "tnr-dim tnr-small" }, t("common.profile", { profile: r.profile }))),
                    h("td", { className: "tnr-num" }, num(r.faults) + " / " + num(n)),
                    h("td", { className: "tnr-num" }, !n ? h("span", { className: "tnr-dim" }, t("models.no_checks")) : r.enough ? pct(r.rate) :
                      h("span", { className: "tnr-dim" }, t("models.not_enough"))),
                    h("td", null, n ? h("div", { className: "tnr-interval-cell" }, h(Interval, { low: r.low, high: r.high, rate: r.rate, max: max }),
                      h("span", { className: "tnr-mono tnr-small" }, pct(r.low) + "–" + pct(r.high))) : h("span", { className: "tnr-dim tnr-small" }, "—")),
                    h("td", { className: "tnr-num" }, num(r.sessions_in_series)));
                })))),
            h("div", { className: "tnr-model-public" },
              h("div", { className: "tnr-section-title" }, t("models.public_title")),
              bench ? h(Fragment, null,
                h("div", { className: "tnr-public-bench" }, bench, h("span", { className: "tnr-dim" }, card.version ? " · " + card.version : "")),
                h("table", { className: "tnr-dtable" }, h("tbody", null, g.rows.map(function (r) {
                  return h("tr", { key: r.profile + r.agent },
                    h("td", null, r.model),
                    h("td", { className: "tnr-num" }, r.public && r.public.new != null ? t("common.percent", { v: dec1(r.public.new) }) :
                      h("span", { className: "tnr-dim" }, t("common.no_public_measure"))));
                }))),
                h("div", { className: "tnr-public-src tnr-small tnr-dim" },
                  t(card.accessed ? "models.source_accessed" : "models.source", { source: card.source || "", accessed: card.accessed || "" })))
                : h("div", { className: "tnr-dim" }, t("models.no_public")),
              h("div", { className: "tnr-public-note" }, t("models.public_note")))));
      }));
  }

  // ---------------------------------------------------------------------------------------------- switch preview
  // Labels and texts: catalog keys switch.status.<id>.label and switch.status.<id>.text.
  var STATUS = { carried: { tone: "prov" }, reset: { tone: "muted" }, vetoed: { tone: "fault" }, kept: { tone: "ok" } };
  function statusLabel(k) { return STATUS[k] ? t("switch.status." + k + ".label") : k; }
  function statusText(k) { return STATUS[k] ? t("switch.status." + k + ".text") : ""; }

  function SwitchView(props) {
    var agents = props.rows;
    var fromS = useState(""), from = fromS[0], setFrom = fromS[1];
    var toS = useState(""), to = toS[0], setTo = toS[1];
    var draftS = useState(""), draft = draftS[0], setDraft = draftS[1];
    var resS = useState(null), res = resS[0], setRes = resS[1];
    var errS = useState(null), err = errS[0], setErr = errS[1];
    var fromRow = agents.filter(function (r) { return r.key === from; })[0] || agents[0];
    useEffect(function () { if (!from && agents[0]) setFrom(agents[0].key); }, [agents.length]);
    var models = useMemo(function () {
      var seen = {};
      agents.forEach(function (r) { seen[r.agent.model] = 1; });
      return Object.keys(seen).sort();
    }, [agents]);
    useEffect(function () {
      if (!fromRow || !to) { setRes(null); return; }
      var alive = true;
      setErr(null);
      apiGet("/preview", { agent: fromRow.agent.agent, to: to, of: fromRow.profile, raw: props.raw }).then(function (d) {
        if (alive) setRes(d);
      }, function (e) { if (alive) { setRes(null); setErr(errText(e)); } });
      return function () { alive = false; };
    }, [fromRow && fromRow.key, to, props.raw, props.version]);
    if (!agents.length) return h(Empty, { title: t("switch.empty") });
    var counts = {};
    if (res) res.types.forEach(function (ty) { counts[ty.status] = (counts[ty.status] || 0) + 1; });
    return h("div", { className: "tnr-switch" },
      h("p", { className: "tnr-lede" }, t("switch.lede")),
      h("form", {
        className: "tnr-switch-form", onSubmit: function (e) { e.preventDefault(); setTo(draft.trim()); }
      },
        h("label", { className: "tnr-field" }, h("span", null, t("switch.from")),
          h(Sel, { value: fromRow ? fromRow.key : "", onChange: setFrom, label: t("switch.from"),
            options: agents.map(function (r) { return [r.key, r.agent.agent + " · " + r.profile]; }) })),
        h("span", { className: "tnr-switch-arrow", "aria-hidden": true }, t("common.arrow")),
        h("label", { className: "tnr-field tnr-field--grow" }, h("span", null, t("switch.to")),
          h("input", {
            className: "tnr-input", list: "tnr-models-list", placeholder: t("switch.placeholder", { example: models[0] || "gpt-5" }),
            value: draft, onChange: function (e) { setDraft(e.target.value); }, "aria-label": t("switch.to_aria"), name: "to"
          }),
          h("datalist", { id: "tnr-models-list" }, models.map(function (m) { return h("option", { key: m, value: m }); }))),
        h(Btn, { kind: "primary", className: "tnr-switch-go" }, t("switch.preview"))),
      err ? h("div", { className: "tnr-error" }, err) : null,
      !to ? h(Empty, { title: t("switch.pick.title") }, t("switch.pick.body")) : null,
      res ? h(Fragment, null,
        h("div", { className: "tnr-switch-summary" },
          h("span", null, h("b", null, res.from), " " + t("common.arrow") + " ", h("b", null, res.to)),
          ["carried", "reset", "vetoed", "kept"].map(function (k) {
            return counts[k] ? h(Flag, { key: k, kind: STATUS[k].tone }, t("switch.count." + k, { n: counts[k] })) : null;
          }),
          res.strict ? h(Flag, { kind: "warn" }, t("switch.strict")) : null),
        h("dl", { className: "tnr-switch-legend" }, ["carried", "reset", "vetoed", "kept"].map(function (k) {
          return h(Fragment, { key: k }, h("dt", null, h(Flag, { kind: STATUS[k].tone }, statusLabel(k))), h("dd", null, statusText(k)));
        })),
        h("div", { className: "tnr-table-scroll" },
          h("table", { className: "tnr-dtable tnr-dtable--switch" },
            h("thead", null, h("tr", null, h("th", null, t("th.type")), h("th", null, t("th.outcome")), h("th", null, t("th.now")),
              h("th", null, t("th.after_switch")), h("th", null, t("th.public_measure")), h("th", null, t("th.your_record")))),
            h("tbody", null, res.types.map(function (ty) {
              var st = STATUS[ty.status] || { tone: "muted" };
              var c = ty.card || {};
              var delta = c.delta != null ? t("switch.delta", { delta: (c.delta > 0 ? "+" : "") + dec1(c.delta) }) : "";
              return h("tr", { key: ty.type },
                h("td", null, h("code", null, ty.type), h("div", { className: "tnr-dim tnr-small" }, t("stakes." + ty.stakes))),
                h("td", null, h(Flag, { kind: st.tone }, statusLabel(ty.status))),
                h("td", null, h(TierChip, { tier: ty.old.effective_tier, capped: ty.old.capped }), " ",
                  h("span", { className: "tnr-mono" }, ty.old.capped ? t("common.capped") : num(ty.old.series) + "/" + num(ty.old.required))),
                h("td", null, h(TierChip, { tier: ty.new.effective_tier, capped: ty.new.capped }), " ",
                  h("span", { className: "tnr-mono" }, ty.new.capped ? t("common.capped") : num(ty.new.series) + "/" + num(ty.new.required)),
                  ty.new.provisional ? h("div", { className: "tnr-small tnr-tone--prov" }, t("switch.provisional", { n: ty.new.provisional })) : null),
                h("td", null, c.benchmark ? h(Fragment, null,
                  h("div", { className: "tnr-small" }, c.benchmark),
                  h("div", { className: "tnr-mono" }, (c.old != null ? dec1(c.old) : "—") + " " + t("common.arrow") + " " + (c.new != null ? dec1(c.new) : "—") + delta)) :
                  h("span", { className: "tnr-dim tnr-small" }, t("common.no_public_measure"))),
                h("td", null, ty.personal.length ? ty.personal.map(function (p) {
                  return h("div", { key: p.agent, className: "tnr-small" }, h("span", { className: "tnr-mono" }, num(p.faults) + " / " + num(p.successes + p.faults)),
                    h("span", { className: "tnr-dim" }, " " + p.model));
                }) : h("span", { className: "tnr-dim tnr-small" }, t("switch.none"))));
            })))),
        h("div", { className: "tnr-dim tnr-small tnr-pad-top" }, t("switch.footnote"))) : null);
  }

  // ---------------------------------------------------------------------------------------------------- passport
  function verdict(verify, doc) {
    if (!verify) return null;
    if (!verify.length) {
      return { tone: "ok", title: t("verdict.ok.title"), lines: [t("verdict.ok.signature"), t("verdict.chain"), t("verdict.ok.replay")] };
    }
    if (verify.length === 1 && verify[0] === "unsigned") {
      return { tone: "warn", title: t("verdict.unsigned.title"), lines: [t("verdict.chain"), t("verdict.unsigned.replay"),
        t("verdict.unsigned.no_key", { cmd: "hermes tenure passport" })] };
    }
    // The problems themselves come from the verifier (tenure/passport.py), in the core catalog's language.
    return { tone: "fault", title: t("verdict.problems", { n: verify.length, count: String(verify.length) }), lines: verify };
  }

  function PassportView(props) {
    var agents = props.rows;
    var selS = useState(""), sel = selS[0], setSel = selS[1];
    var row = agents.filter(function (r) { return r.key === sel; })[0] || agents[0];
    var res = usePoll(function () {
      return row ? apiGet("/passport", { agent: row.agent.agent, of: row.profile, raw: props.raw }) : null;
    }, [row && row.key, props.raw, props.version], !!row, PASSPORT_MS);
    if (!agents.length) return h(Empty, { title: t("passport.empty.title") }, t("passport.empty.body"));
    var d = res.data && res.data.passport;
    var v = res.data ? verdict(res.data.verify, d) : null;
    function download() {
      var blob = new Blob([JSON.stringify(d, null, 2) + "\n"], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "passport-" + row.agent.model.replace(/[^A-Za-z0-9._-]+/g, "_") + ".json";
      document.body.appendChild(link); link.click(); document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }
    return h("div", { className: "tnr-passport" },
      h("div", { className: "tnr-passport-bar" },
        h("label", { className: "tnr-field" }, h("span", null, t("passport.agent")),
          h(Sel, { value: row ? row.key : "", onChange: setSel, label: t("passport.agent"),
            options: agents.map(function (r) { return [r.key, r.agent.agent + " · " + r.profile]; }) })),
        h(Btn, { kind: "primary", onClick: download, disabled: !d }, t("passport.download")),
        h("span", { className: "tnr-dim tnr-small" }, t("passport.note"))),
      res.error && !res.data ? h("div", { className: "tnr-error" }, errText(res.error)) : h(Stale, { res: res }),
      !d ? h("div", { className: "tnr-dim tnr-pad" }, t("common.loading")) : h("div", { className: "tnr-passport-grid" },
        h("section", { className: cx("tnr-verdict", "tnr-verdict--" + v.tone) },
          h("div", { className: "tnr-verdict-title" }, v.title),
          h("ul", null, v.lines.map(function (l, i) { return h("li", { key: i }, l); })),
          h("div", { className: "tnr-small tnr-dim" }, t("passport.checked_by")),
          h(CopyCmd, { cmd: "hermes tenure verify " + "passport-" + row.agent.model.replace(/[^A-Za-z0-9._-]+/g, "_") + ".json" })),
        h("section", { className: "tnr-passport-fields" },
          h("dl", null,
            [["protocol", d.protocol], ["agent", d.agent.model + "@" + d.agent.provider],
              ["profile", t("passport.value.hashed", { profile: d.agent.profile })], ["rule", d.rule.name + " · " + short(d.rule.fingerprint, 16)],
              ["settings", short(d.settings_fingerprint, 16)],
              ["ledger", t("passport.value.ledger", { n: d.ledger.count, head: short(d.ledger.head, 16) })],
              ["public_key", short(d.public_key, 24) || t("passport.value.none")],
              ["signature", d.signature ? short(d.signature, 24) + "…" : t("passport.value.unsigned")],
              ["generated", d.generated_at], ["type_names", d.redacted ? t("passport.value.redacted") : t("passport.value.raw")]
            ].map(function (kv) {
              return h(Fragment, { key: kv[0] }, h("dt", null, t("passport.field." + kv[0])), h("dd", { className: "tnr-mono" }, kv[1]));
            }))),
        h("section", { className: "tnr-passport-types" },
          h("div", { className: "tnr-section-title" }, t("passport.types_title")),
          h("table", { className: "tnr-dtable" },
            h("thead", null, h("tr", null, h("th", null, t("th.type")), h("th", null, t("th.tier")), h("th", { className: "tnr-num" }, t("th.series")),
              h("th", { className: "tnr-num" }, t("th.sessions")), h("th", null, t("th.guarantee")))),
            h("tbody", null, d.types.map(function (ty) {
              var g = ty.guarantee || {};
              var gtext = g.capped ? t("legend.capped") : t("passport.guarantee", { aoql: pct(g.aoql), worst: pct(g.worst_case) });
              return h("tr", { key: ty.type },
                h("td", null, h("code", null, ty.type), h("div", { className: "tnr-dim tnr-small" }, t("stakes." + ty.stakes))),
                h("td", null, h(TierChip, { tier: ty.tier, capped: !!g.capped })),
                h("td", { className: "tnr-num" }, ty.required == null ? "—" : num(ty.series) + "/" + num(ty.required)),
                h("td", { className: "tnr-num" }, num(ty.sessions)),
                h("td", { className: "tnr-small" }, !g.capped && g.conditional ? gtext + " · " + t("flag.provisional") : gtext));
            }))))));
  }

  // --------------------------------------------------------------------------------------------------------- undo
  function UndoView(props) {
    var list = props.undoable || [];
    if (!list.length) {
      return h(Empty, { title: t("undo.empty.title") }, t("undo.empty.body"));
    }
    return h("div", { className: "tnr-undo" },
      h("p", { className: "tnr-lede" }, t("undo.lede")),
      h("div", { className: "tnr-table-scroll" },
        h("table", { className: "tnr-dtable" },
          h("thead", null, h("tr", null, h("th", { className: "tnr-num" }, "#"), h("th", null, t("th.when")), h("th", null, t("th.agent")), h("th", null, t("th.type")),
            h("th", null, t("th.undo_effect")), h("th", null, ""))),
          h("tbody", null, list.map(function (u) {
            var mine = u.profile === props.current;
            return h("tr", { key: u.profile + u.id },
              h("td", { className: "tnr-num tnr-dim" }, u.id),
              h("td", { className: "tnr-mono" }, ago(u.age), h("div", { className: "tnr-dim tnr-small" }, t("undo.window_ends", { duration: duration(86400 - u.age) }))),
              h("td", null, u.agent, h("div", { className: "tnr-dim tnr-small" }, t("common.profile", { profile: u.profile }))),
              h("td", null, h("code", null, u.type)),
              h("td", { className: "tnr-small" }, u.counts_as_fault ? t("undo.effect.fault") : t("undo.effect.already")),
              h("td", { className: "tnr-dtable-actions" }, h(ConfirmBtn, {
                kind: "ghost", disabled: !mine, confirm: t("undo.confirm", { id: String(u.id) }),
                title: mine ? t("undo.title") : t("undo.own_profile_only"),
                onConfirm: function () {
                  return apiPost("/undo", { id: u.id }, { raw: props.raw }).then(function (r) {
                    props.onDone(r.message, r.ok ? "success" : "error");
                  }, function (e) { props.onDone(errText(e), "error"); });
                }
              }, t("undo.button"))));
          })))));
  }

  // ------------------------------------------------------------------------------------------------- settings
  function SettingsView(props) {
    var cur = props.settings;
    var presetS = useState(null), preset = presetS[0], setPreset = presetS[1];
    var risksS = useState(null), risks = risksS[0], setRisks = risksS[1];
    var strictS = useState(null), strict = strictS[0], setStrict = strictS[1];
    var readOnly = props.readOnly, setReadOnly = props.onReadOnly;
    var msgS = useState(null), msg = msgS[0], setMsg = msgS[1];
    if (!cur) return h(Empty, { title: t("settings.empty.title") }, t("settings.empty.body"));
    var pr = preset || cur.preset;
    var rk = risks || cur.risks;
    var sx = strict == null ? cur.strict : strict;
    var custom = pr === "custom";
    var dirty = pr !== cur.preset || sx !== cur.strict || STAKES.some(function (s) { return rk[s] !== cur.risks[s]; });

    function pickPreset(name) { setPreset(name); setRisks(Object.assign({}, PRESETS[name])); }
    function pickRisk(level, k) {
      var next = Object.assign({}, rk); next[level] = k == null ? null : 1 / k;
      var match = Object.keys(PRESETS).filter(function (n) {
        return STAKES.every(function (s) { return PRESETS[n][s] === next[s] || (PRESETS[n][s] != null && next[s] != null && Math.abs(PRESETS[n][s] - next[s]) < 1e-12); });
      })[0];
      setRisks(next); setPreset(match || "custom");
    }
    function cmds() {
      var out = [];
      if (pr !== cur.preset || (custom && dirty)) {
        if (!custom) out.push("hermes tenure setup " + pr);
        else STAKES.forEach(function (s) {
          if (rk[s] !== cur.risks[s]) out.push("hermes config set plugins.entries.tenure.settings.risks." + s + " " + (rk[s] == null ? "cap" : "1/" + Math.round(1 / rk[s])));
        });
      }
      if (sx !== cur.strict) out.push("hermes tenure strict " + (sx ? "on" : "off"));
      return out;
    }
    function apply() {
      var body = {};
      if (custom) body.risks = (function () { var r = {}; STAKES.forEach(function (s) { r[s] = rk[s] == null ? "cap" : "1/" + Math.round(1 / rk[s]); }); return r; })();
      else if (pr !== cur.preset) body.preset = pr;
      if (sx !== cur.strict) body.strict = sx;
      apiPost("/settings", body, { raw: props.raw }).then(function () {
        setMsg({ tone: "ok", text: t("settings.saved_long") });
        setPreset(null); setRisks(null); setStrict(null);
        props.onDone(t("settings.saved"), "success");
      }, function (e) {
        if (errStatus(e) === 501) setReadOnly(true);
        else setMsg({ tone: "fault", text: errText(e) });
      });
    }
    var commands = cmds();
    var shownCmds = commands.length ? commands : ["hermes tenure setup " + (cur.preset === "custom" ? "balanced" : cur.preset)];
    return h("div", { className: "tnr-settings" },
      h("section", { className: "tnr-dial" },
        h("div", { className: "tnr-dial-head" },
          h("div", null, h("div", { className: "tnr-section-title" }, t("settings.risk_title")),
            h("div", { className: "tnr-dim tnr-small" }, t("settings.risk_help"))),
          h("div", { className: "tnr-seg", role: "radiogroup", "aria-label": t("settings.preset_aria") },
            ["careful", "balanced", "fast"].map(function (n) {
              return h("button", {
                key: n, type: "button", role: "radio", "aria-checked": pr === n, disabled: readOnly,
                className: cx("tnr-seg-btn", pr === n && "is-on"), onClick: function () { pickPreset(n); }
              }, presetName(n));
            }),
            custom ? h("span", { className: "tnr-seg-btn is-on is-static" }, presetName("custom")) : null)),
        h("div", { className: "tnr-dial-rows" },
          STAKES.map(function (s) {
            var n = studyN(rk[s]), was = studyN(cur.risks[s]);
            return h("div", { key: s, className: "tnr-dial-row" },
              h("div", { className: "tnr-dial-level" }, h("span", { className: "tnr-stakes-dot tnr-stakes--" + s }), t("settings.stakes." + s)),
              h("div", { className: "tnr-ladder", role: "radiogroup", "aria-label": t("settings.stakes_risk." + s) },
                LADDER.map(function (k) {
                  var on = k == null ? rk[s] == null : rk[s] != null && Math.abs(1 / rk[s] - k) < 1e-6;
                  return h("button", {
                    key: String(k), type: "button", role: "radio", "aria-checked": on, disabled: readOnly,
                    className: cx("tnr-rung", on && "is-on"), onClick: function () { pickRisk(s, k); }
                  }, k == null ? t("settings.rung_cap") : "1/" + k);
                })),
              h("div", { className: "tnr-dial-n" },
                n == null ? h("span", null, h("b", null, t("common.capped")), h("span", { className: "tnr-dim" }, " · " + t("missing.always_asks"))) :
                  h("span", null, h("span", { className: "tnr-dim" }, oneIn(rk[s]) + " " + t("common.arrow") + " "), h("b", { className: "tnr-mono" }, num(n)),
                    h("span", { className: "tnr-dim" }, t("settings.checks_in_row", { n: n }))),
                n !== was ? h("span", { className: "tnr-dial-was tnr-small" }, t("settings.in_force", { value: was == null ? t("common.capped") : num(was) })) : null));
          })),
        h("div", { className: "tnr-dial-row tnr-dial-strict" },
          h("div", { className: "tnr-dial-level" }, t("settings.strict")),
          h("label", { className: "tnr-switch-toggle" },
            h("input", { type: "checkbox", checked: sx, disabled: readOnly, onChange: function (e) { setStrict(e.target.checked); } }),
            h("span", { className: "tnr-toggle-track", "aria-hidden": true }),
            h("span", null, sx ? t("settings.strict_on") : t("settings.strict_off"))),
          h("div", { className: "tnr-dial-n tnr-dim tnr-small" }, t("profile.spot", { rate: oneIn(cur.spot) }))),
        readOnly ? h("div", { className: "tnr-readonly" },
          h("div", null, h("b", null, t("settings.read_only.bold")), " " + t("settings.read_only.body")),
          shownCmds.map(function (c) { return h(CopyCmd, { key: c, cmd: c }); }))
          : h("div", { className: "tnr-dial-foot" },
            h(Btn, { kind: "primary", disabled: !dirty, onClick: apply }, t("settings.apply")),
            dirty ? h(Btn, { kind: "ghost", onClick: function () { setPreset(null); setRisks(null); setStrict(null); } }, t("settings.reset")) : null,
            h("span", { className: "tnr-dim tnr-small" }, dirty ? t("settings.same_as", { cmds: commands.join("  &&  ") }) :
              t("settings.in_force_profile", { profile: props.profile })))),
      msg ? h("div", { className: "tnr-msg tnr-tone--" + msg.tone }, msg.text) : null,
      h("section", { className: "tnr-about" },
        h("div", { className: "tnr-section-title" }, t("settings.about.title")),
        h("p", null, t("settings.about.body", { spot: oneIn(cur.spot) })),
        h("p", { className: "tnr-dim" }, t("settings.about.carry"))));
  }

  // ------------------------------------------------------------------------------------------------------ help
  function Help(props) {
    // The keys stay as they are; only their descriptions are translated.
    var keys = [["m", t("view.map")], ["b", t("view.models")], ["w", t("view.switch")], ["p", t("view.passport")], ["u", t("view.undo")],
      ["s", t("view.settings")], ["a", t("help.agent")], ["j / k", t("help.next_prev")], ["↵", t("help.open")],
      ["r", t("help.raw")], ["esc", t("help.close")], ["?", t("help.help")]];
    return h("div", { className: "tnr-drawer-wrap", onClick: props.onClose },
      h("div", { className: "tnr-help", role: "dialog", "aria-label": t("help.aria") },
        h("div", { className: "tnr-section-title" }, t("help.title")),
        h("dl", null, keys.map(function (k) {
          return h(Fragment, { key: k[0] }, h("dt", null, h(Kbd, null, k[0])), h("dd", null, k[1]));
        }))));
  }

  // ------------------------------------------------------------------------------------------------------ page
  function TenurePage() {
    var viewS = useState("map"), view = viewS[0], setView = viewS[1];
    var rawS = useState(false), raw = rawS[0], setRaw = rawS[1];
    var focusS = useState(0), focus = focusS[0], setFocus = focusS[1];
    var drawerS = useState(null), drawer = drawerS[0], setDrawer = drawerS[1];
    var helpS = useState(false), help = helpS[0], setHelp = helpS[1];
    var verS = useState(0), version = verS[0], setVersion = verS[1];
    var toastS = useState(null), toast = toastS[0], setToast = toastS[1];
    var transS = useState([]), transitions = transS[0], setTransitions = transS[1];
    var prev = useRef(null);
    var toneS = useState("dark"), tone = toneS[0], setTone = toneS[1];
    var roS = useState(false), settingsRO = roS[0], setSettingsRO = roS[1];   // 501 once: read-only for the visit
    // The dashboard's language: reading the host's i18n context re-renders the tab when the user switches language.
    var i18n = typeof SDK.useI18n === "function" ? SDK.useI18n() : null;
    setLocale(i18n && i18n.locale);

    var tick = usePoll(function () {
      return Promise.all([apiGet("/agents", { raw: raw }),
        apiGet("/activity", { since: Math.floor(Date.now() / 1000) - WEEK, raw: raw })]).then(function (r) {
        return { agents: r[0], activity: r[1] };
      });
    }, [raw, version]);
    var agentsRes = tick;

    var data = tick.data ? tick.data.agents : null;
    var profiles = data ? data.profiles : [];
    var rows = useMemo(function () {
      var out = [];
      profiles.forEach(function (p) {
        (p.agents || []).forEach(function (a) {
          out.push({ key: agentKey(p.profile, a.agent), profile: p.profile, agent: a, info: p });
        });
      });
      return out;
    }, [data]);
    var currentProfile = data ? data.current : "";
    var current = profiles.filter(function (p) { return p.current; })[0];

    // Every automatic tier change is announced: diff the effective tiers between two polls.
    useEffect(function () {
      if (!data) return;
      var now = {};
      rows.forEach(function (r) {
        r.agent.types.forEach(function (ty) { now[r.key + "\u0000" + ty.type] = { tier: ty.effective_tier, r: r, t: ty }; });
      });
      var before = prev.current;
      prev.current = now;
      if (!before) return;
      var found = [];
      Object.keys(now).forEach(function (k) {
        var b = before[k], n = now[k];
        if (b && b.tier !== n.tier) {
          found.push({ id: k + Date.now(), at: Date.now(), agent: n.r.agent.agent, type: n.t.type, from: b.tier, to: n.tier,
            why: (n.t.trial_left ? "trial_open" : n.t.faults > (b.t.faults || 0) ? "after_fault" : "on_evidence") });
        }
      });
      if (found.length) {
        setTransitions(function (xs) { return found.concat(xs).slice(0, 30); });
        var f = found[0];
        setToast({ text: t("toast.transition", { agent: f.agent, type: f.type, from: TIER[f.from], to: TIER[f.to] }), type: "info", at: Date.now() });
      }
    }, [data]);

    // Hermes themes say nothing about light or dark: read it from the background, so status colors keep contrast.
    useEffect(function () {
      var tn = luminance(getComputedStyle(document.documentElement).getPropertyValue("--background-base")) > 0.5 ? "light" : "dark";
      if (tn !== tone) setTone(tn);
    });

    useEffect(function () {
      if (!toast) return undefined;
      var tm = setTimeout(function () { setToast(null); }, 4500);
      return function () { clearTimeout(tm); };
    }, [toast]);

    var focusRow = rows[Math.min(focus, Math.max(0, rows.length - 1))];
    var drawerRow = drawer ? rows.filter(function (r) { return r.key === drawer; })[0] : null;

    var onKey = useCallback(function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e)) return;
      var k = e.key;
      if (k === "Escape") { if (help) setHelp(false); else if (drawer) setDrawer(null); return; }
      if (help && k !== "?") return;
      var v = VIEWS.filter(function (x) { return x.key === k; })[0];
      if (v) { setView(v.id); setDrawer(null); e.preventDefault(); return; }
      if (k === "?") { setHelp(!help); e.preventDefault(); return; }
      if (k === "r") { setRaw(!raw); return; }
      if (k === "a" && focusRow) { setDrawer(focusRow.key); return; }
      if (view !== "map" || drawer) return;
      if (k === "j" || k === "ArrowDown") { setFocus(Math.min(rows.length - 1, focus + 1)); e.preventDefault(); }
      else if (k === "k" || k === "ArrowUp") { setFocus(Math.max(0, focus - 1)); e.preventDefault(); }
      else if (k === "Enter" && focusRow) {
        var tag = ((e.target && e.target.tagName) || "").toLowerCase();
        if (tag === "button" || tag === "a" || (e.target && e.target.getAttribute && e.target.getAttribute("role") === "tab")) return;
        setDrawer(focusRow.key);
      }
    }, [help, drawer, raw, view, focus, rows, focusRow]);
    // Shortcuts only while focus is inside the tab (WCAG 2.1.4): the root takes focus when the tab opens.
    var rootRef = useRef(null);
    useEffect(function () { if (rootRef.current && document.activeElement === document.body) rootRef.current.focus(); }, []);

    function done(text, type) { setToast({ text: text, type: type, at: Date.now() }); setVersion(version + 1); }

    var activity = tick.data ? tick.data.activity : null;
    var err = tick.error;
    var unreadable = profiles.filter(function (p) { return p.error; });
    var updated = agentsRes.at ? hms(agentsRes.at) : "—";

    var body;
    if (!data && !err) body = h("div", { className: "tnr-dim tnr-pad" }, t("page.loading"));
    else if (!data && err) body = h("div", { className: "tnr-error" }, t("page.error", { error: errText(err) }));
    else if (view === "map") {
      body = h(MapView, { profiles: profiles, rows: rows, settings: current && current.settings, focus: focus, onFocus: setFocus,
        onOpen: function (r) { setDrawer(r.key); }, transitions: transitions });
    } else if (view === "models") body = h(ModelsView, { raw: raw, version: version });
    else if (view === "switch") body = h(SwitchView, { rows: rows, raw: raw, version: version });
    else if (view === "passport") body = h(PassportView, { rows: rows, raw: raw, version: version });
    else if (view === "undo") body = h(UndoView, { undoable: activity && activity.undoable, current: currentProfile, onDone: done, raw: raw });
    else body = h(SettingsView, { settings: current && current.settings, profile: currentProfile, raw: raw, onDone: done,
      readOnly: settingsRO, onReadOnly: setSettingsRO });

    return h("div", { className: "tnr", "data-tone": tone, ref: rootRef, tabIndex: -1, onKeyDown: onKey, style: { outline: "none" } },
      h("header", { className: "tnr-head" },
        h("div", { className: "tnr-title-row" },
          h("h1", { className: "tnr-title" }, t("page.title")),
          h("span", { className: "tnr-subtitle" }, t("page.subtitle")),
          h("div", { className: "tnr-head-right" },
            h("span", { className: cx("tnr-live", err && "is-stale"), title: err ? errText(err) : t("page.polling", { s: POLL_MS / 1000 }) },
              h("span", { className: "tnr-live-dot", "aria-hidden": true }), err ? t("page.retrying") : t("page.live"),
              h("span", { className: "tnr-mono" }, updated)),
            h("button", { type: "button", className: cx("tnr-chip-btn", raw && "is-on"), onClick: function () { setRaw(!raw); }, title: t("page.raw_title") },
              raw ? t("page.raw_on") : t("page.raw_off")),
            h("button", { type: "button", className: "tnr-chip-btn", onClick: function () { setHelp(true); }, title: t("help.aria") }, h(Kbd, null, "?")))),
        h(Counters, { totals: activity && activity.totals })),
      h(Tabs, { view: view, onView: function (v) { setView(v); setDrawer(null); }, undoCount: activity && activity.undoable ? activity.undoable.length : 0 }),
      unreadable.length ? h("div", { className: "tnr-msg tnr-tone--warn" }, t("page.unreadable", {
        profiles: unreadable.map(function (p) { return p.profile; }).join(t("common.list_sep")) })) : null,
      data && err ? h("div", { className: "tnr-msg tnr-tone--warn" }, t("stale.message", { error: errText(err), time: updated })) : null,
      h("main", { className: "tnr-body", "data-view": view, id: "tnr-panel", role: "tabpanel", "aria-labelledby": "tnr-tab-" + view }, body),
      drawerRow ? h(AgentDrawer, { row: drawerRow, raw: raw, version: version, onClose: function () { setDrawer(null); }, onDone: done }) : null,
      help ? h(Help, { onClose: function () { setHelp(false); } }) : null,
      toast ? h("div", { className: "tnr-toast tnr-toast--" + toast.type, role: "status" }, toast.text) : null);
  }

  REG.register("tenure", TenurePage);
})();
