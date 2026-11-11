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
    "cell.held": "stored {tier}, held back by your settings",
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
    "community.empty.how": "To contribute, write your record with this command, read what it holds, then open a pull request adding the file to the community repository ({repo}).",
    "community.empty.title": "No shared records yet",
    "community.empty.what": "The community benchmark pools records that Tenure users chose to publish: per model and per action family, verified successes and faults, signed with their passport key. Nothing is shared automatically: Tenure makes no network call.",
    "community.empty.where": "To see the board here, download the community-board.json the repository publishes and save it as {path}.",
    "community.generated": "{records} · board generated on {date}",
    "community.lede": "Self-reported by contributors, and signature-checked: each record is signed with its owner's passport key, and one record per key counts. ",
    "community.lede_bold": "This does not stop one person with many keys.",
    "community.ranking": "Per action family, models ranked by the top of the 95% range of their fault rate, never by one score.",
    "confirm.again": "Click again to confirm",
    "confirm.default": "Confirm",
    "confirm.flag.desc": "This counts as a fault: {type} drops at least one tier and climbs again. Use it for an error nobody caught.",
    "confirm.flag.title": "Flag {type} as an error?",
    "confirm.revoke.desc": "{type} asks first again and its series restarts from zero. Not a fault.",
    "confirm.revoke.title": "Take back {type}?",
    "confirm.revoke_all.desc": "Every action type of {agent} asks first again and its series restarts from zero. Not a fault.",
    "confirm.revoke_all.title": "Revoke all of this agent's earned autonomy?",
    "confirm.undo.title": "Undo action {id}?",
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
    "count.models": {
      "one": "{n} model",
      "other": "{n} models"
    },
    "count.records": {
      "one": "{n} record",
      "other": "{n} records"
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
      "one": "{faults} of {n} check by you",
      "other": "{faults} of {n} checks by you"
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
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} faults / verified · ",
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
    "event.success.notify": "acted, then told you · not undone",
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
    "guarantee.plain": "At most about 1 in {k} of its actions runs with an error nobody approved.",
    "guarantee.text": "Unchecked errors stay under {aoql} of its actions of this type; for an agent that turns bad after tenure, at most {worst} until the first caught error.",
    "guarantee.text_conditional": "Unchecked errors stay under {aoql} of its actions of this type; for an agent that turns bad after tenure, at most {worst} until the first caught error. Conditional on the previous model's evidence still holding.",
    "guarantee.trusted": "No guarantee yet: it comes only with a tier earned on evidence.",
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
    "legend.notify": "acts, then tells you, with an undo (reversible types)",
    "legend.series": "verified successes in a row, of the N needed",
    "legend.trusted": "trusted start: acts like Hermes alone until its first mistake, nothing earned",
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
    "meta.preset": "Preset",
    "meta.profile": "Profile",
    "meta.start": "Start",
    "missing.always_asks": "always asks",
    "missing.earned": "earned · spot-checked",
    "missing.more_to_t2": {
      "one": "{n} more to reach Under review (T2)",
      "other": "{n} more to reach Under review (T2)"
    },
    "missing.more_to_t3": {
      "one": "{n} more to Tenured",
      "other": "{n} more to Tenured"
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
    "missing.trusted": "trusted until its first mistake · acts like Hermes alone",
    "missing.trusted_undo": "trusted until its first mistake · acts, then tells you, with an undo",
    "models.empty.body": "Each verified action adds to the model's record on that type, here and in {cmd}.",
    "models.empty.title": "No record yet",
    "models.lede": "Your own benchmark: each model's verified record on your work, per action type, with the 95% range of its fault rate. Ranked by the top of its range, never by one score. Beside it, the public measure, as information: ",
    "models.lede_bold": "public capability on their tasks, not reliability on yours.",
    "models.no_public": "No public measure for this action type.",
    "models.not_enough": "not enough evidence",
    "models.not_ranked": "Not enough evidence yet",
    "models.not_ranked_note": "A model is ranked once it has {n} verified outcomes on this type.",
    "models.personal_title": "On your work",
    "models.public_note": "Public capability on their tasks, not reliability on yours.",
    "models.public_title": "Public measure",
    "models.source": "{source}. Best published score, any harness; not a controlled comparison.",
    "models.source_accessed": "{source}, accessed {accessed}. Best published score, any harness; not a controlled comparison.",
    "moment.dismiss": "Dismiss",
    "moment.eyebrow.down": "Fault caught",
    "moment.eyebrow.up": "Promotion",
    "moment.granted": "Tenure granted",
    "moment.probation": "Back on probation",
    "moment.review": "Under review",
    "page.anim_off": "motion off",
    "page.anim_on": "motion on",
    "page.anim_reduced": "Your system asks for reduced motion: animations stay off",
    "page.anim_title": "Animations: on or off, remembered in this browser",
    "page.animations": "Animations",
    "page.error": "Could not read tenure: {error}",
    "page.live": "live · ",
    "page.loading": "Loading the record…",
    "page.polling": "Polling every {s} s",
    "page.raw_off": "redacted names",
    "page.raw_on": "raw names",
    "page.raw_title": "Show raw action type names (r)",
    "page.retrying": "retrying · ",
    "page.subtitle": "Revocable trust: taken back on a mistake, earned back on verified evidence",
    "page.title": "Tenure",
    "page.unreadable": "Unreadable: {profiles}. Its database exists but cannot be opened; other profiles are shown.",
    "passport.agent": "Agent",
    "passport.card.aria": "Passport of {agent}: {verdict}",
    "passport.card.signature": "a plugin for Hermes Agent",
    "passport.card.title": "Passport",
    "passport.checked_by": "Checked by the dashboard against this profile's ledger. Anyone can re-check it:",
    "passport.download": "Download JSON",
    "passport.empty.body": "A passport covers an agent's record; it appears with the first verified action.",
    "passport.empty.title": "No passport yet",
    "passport.faults_checks": {
      "one": "{n} fault / {total} verified outcomes",
      "other": "{n} faults / {total} verified outcomes"
    },
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
    "passport.note": "Signed and tamper-evident: a change after it is signed or anchored shows on verification. An older passport still verifies against a longer ledger; the verifier says what changed since.",
    "passport.pending_note": "Computed under the last logged settings; the new settings apply from the next action.",
    "passport.trusted": "Trusted (not earned)",
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
    "profile.copy_pending": "copied from another profile, checked when it starts",
    "profile.name": "Profile {profile}",
    "profile.pending": "applies from the next action",
    "profile.preset": "{preset} preset",
    "profile.read_only": " · read-only here",
    "profile.sessions_suspended": {
      "one": "{n} session suspended: external content read",
      "other": "{n} sessions suspended: external content read"
    },
    "profile.spot": "spot checks {rate}",
    "profile.start_probation": "study start (probation)",
    "profile.start_trusted": "trusted start",
    "profile.strict": "strict",
    "profile.suspended": {
      "one": "{n} suspended: external content read",
      "other": "{n} suspended: external content read"
    },
    "profile.this_dashboard": " · this dashboard",
    "settings.advanced_docs": "Every key is explained by hermes tenure explain and in tenure's README.",
    "settings.advanced_help": "Action-type overrides, and every key in Hermes' own form.",
    "settings.advanced_title": "Advanced",
    "settings.advanced_types": "Reclassify action types (free, low, medium, high or cap per pattern) in Hermes' Settings → Plugins → Tenure, or in config.yaml:",
    "settings.animations_help": "The bars that print, the passport that develops, the bands. The same switch as in the page header; it stays off when your system asks for reduced motion.",
    "settings.custom_help": "Your own share of unchecked errors per stakes level: pick 1 in k, type your own k, or cap (always asks). The series a type needs follows at once. Saved, it makes the preset custom, unless it matches one.",
    "settings.custom_title": "Accepted risk per stakes level",
    "settings.enabled_help": "Turn tenure off without uninstalling it.",
    "settings.enabled_off": "Off",
    "settings.enabled_on": "On",
    "settings.enabled_title": "Tenure on or off",
    "settings.enabled_unknown": "The agent half does not report this state yet: pick one to set it.",
    "settings.enabled_warn": "Off: tenure stops deciding; Hermes asks as usual. The ledger and every record stay as they are.",
    "settings.in_force": "In force",
    "settings.no_writer": "This Hermes does not let the Desktop save tenure's settings: use the command below.",
    "settings.none": "This profile has no tenure record yet: the defaults apply until its first action.",
    "settings.one_in": "1 in",
    "settings.or_config": "Or in Hermes' config.yaml, under plugins.entries.tenure.settings:",
    "settings.or_terminal": "Or in a terminal:",
    "settings.pending": "The last change is not in the ledger yet: it applies from the next action.",
    "settings.preset_desc_balanced": "The default. High-stakes types always ask.",
    "settings.preset_desc_careful": "Asks the longest. Even high-stakes types can earn their tier, after a long series.",
    "settings.preset_desc_custom": "Your own accepted risk per stakes level, set in Hermes' config.",
    "settings.preset_desc_fast": "Earns autonomy soonest at low and medium stakes. High-stakes types always ask.",
    "settings.preset_help": "How much evidence an action type needs before it acts on its own, per stakes level: the series of verified successes in a row, and the share of unchecked errors it accepts.",
    "settings.risk": "1 unchecked error in {k} accepted",
    "settings.risk_invalid": "A whole number of 2 or more.",
    "settings.rung_cap": "cap",
    "settings.save": "Save",
    "settings.save_failed": "Not saved: {error}",
    "settings.saved": "Saved and logged in the ledger: it applies from the next action.",
    "settings.saves_here": "Changes save at once, through Hermes' own settings writer, and are logged in the ledger; they apply from the next action. The same settings are in Hermes' Settings → Plugins → Tenure.",
    "settings.saving": "Saving…",
    "settings.series": {
      "one": "{n} verified success in a row",
      "other": "{n} verified successes in a row"
    },
    "settings.spot_change": "Set it in Hermes' config.yaml, under plugins.entries.tenure.settings (a share between 0 and 1):",
    "settings.spot_custom": "Your own value: 1 in k",
    "settings.spot_desc": "Once a type is tenured, 1 of its actions in {k} still asks, at random: a model that turns bad gets caught.",
    "settings.spot_title": "Spot checks",
    "settings.spot_value": "1 in {k}",
    "settings.start_help": "What an action type does before its first fault.",
    "settings.start_probation": "The study's start: every action type asks first (T1) and earns each tier from your answers.",
    "settings.start_trusted": "Covered types (file edits, memory, subagents, known development tools) ask nothing until their first fault, as Hermes alone would. A fault puts that type on Probation (T1), and it earns its tier back. Leaving the machine and money always ask.",
    "settings.strict_desc_off": "A new model inherits the previous model's record at low and medium stakes, halved and provisional until its own approvals confirm it. High stakes start over.",
    "settings.strict_desc_on": "A new model starts with an empty record on every action type, as in the study.",
    "settings.strict_help": "What a new model inherits when you switch models.",
    "settings.strict_off": "Strict mode off",
    "settings.strict_on": "Strict mode on",
    "settings.strict_title": "Strict mode on model change",
    "settings.use": "Use",
    "stakes.group.high": "high stakes",
    "stakes.group.low": "low stakes",
    "stakes.group.medium": "medium stakes",
    "stakes.high": "high",
    "stakes.low": "low",
    "stakes.medium": "medium",
    "stale.message": "Last refresh failed ({error}). Showing the data from {time}.",
    "start.probation": "Study start (probation)",
    "start.trusted": "Trusted start",
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
    "th.contributors": "contributors",
    "th.faults_checks": "faults / verified",
    "th.file": "file",
    "th.guarantee": "guarantee",
    "th.model": "model",
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
    "tier.label.alone": "Tenured",
    "tier.label.ask": "Probation",
    "tier.label.cap": "Always asks",
    "tier.label.notify": "Under review",
    "tier.name.alone": "acts on its own",
    "tier.name.ask": "asks first",
    "tier.name.notify": "acts, then tells you",
    "tier.trusted.chip": "TRUSTED",
    "tier.trusted.label": "Trusted",
    "tier.trusted.name": "acts like Hermes alone",
    "tier.trusted.title": "Trusted until its first mistake: acts like Hermes alone. Nothing earned yet.",
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
    "transitions.why_changed": "without a fault: revoked, or the settings or stakes changed",
    "type.always_asks": "always asks",
    "type.stakes_high": "high stakes",
    "type.stakes_low": "low stakes",
    "type.stakes_medium": "medium stakes",
    "undo.button": "Undo",
    "undo.collapse": "Hide",
    "undo.confirm": "Undo #{id}?",
    "undo.effect.already": "restores the files · the automatic check already counted a fault",
    "undo.effect.fault": "restores the files · counts as a fault",
    "undo.effect.none": "nothing to restore (no snapshot) · would count as a fault",
    "undo.empty.body": "File writes the agent made without asking (trusted, or at T2: acts, then tells you) keep a snapshot of the files for 24 hours. They appear here, newest first, each with its own undo.",
    "undo.empty.title": "Nothing to undo",
    "undo.expand": "Show each",
    "undo.lede": "Recent act-then-notify actions. Undo restores the files from their snapshot and counts as a fault of the type.",
    "undo.no_snapshot": "no snapshot",
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
    "view.community": "Community",
    "view.map": "Map",
    "view.models": "Your benchmark",
    "view.passport": "Passport",
    "view.settings": "Settings",
    "view.switch": "Switch preview",
    "view.undo": "Undo"
  },
  "ar": {
    "cell.asked_suffix": " بسؤال",
    "cell.capped_by_settings": "مقيَّد بإعدادات المخاطرة",
    "cell.held": "{tier} مخزَّن، تُقيّده إعداداتك",
    "cell.kind_irreversible": "{type} · {stakes}، لا يمكن التراجع عنه",
    "cell.kind_reversible": "{type} · {stakes}، يمكن التراجع عنه",
    "cell.provisional_long": {
      "zero": "{count} منقولة من النموذج السابق، مؤقتة",
      "one": "{count} منقول من النموذج السابق، مؤقت",
      "two": "{count} منقولان من النموذج السابق، مؤقتان",
      "few": "{count} منقولة من النموذج السابق، مؤقتة",
      "many": "{count} منقولة من النموذج السابق، مؤقتة",
      "other": "{count} منقولة من النموذج السابق، مؤقتة"
    },
    "cell.record": "السجل: {successes} نجاحات · {faults} إخفاقات · {neutrals} محايدة · {spot} فحوص عشوائية",
    "cell.series": "السلسلة {series}/{required} على التوالي",
    "cell.sessions": {
      "zero": "{count} جلسات",
      "one": "{count} جلسة",
      "two": "{count} جلستان",
      "few": "{count} جلسات",
      "many": "{count} جلسةً",
      "other": "{count} جلسة"
    },
    "cell.tier_now": "المستوى الآن: {tier} ({name})",
    "common.arrow": "←",
    "common.capped": "مقيَّد",
    "common.list_sep": "، ",
    "common.loading": "جارٍ التحميل…",
    "common.no_public_measure": "لا مقياس عام",
    "common.one_in": "1 من كل {k}",
    "common.percent": "{v}%",
    "common.profile": "الملف الشخصي {profile}",
    "community.empty.how": "للمساهمة، اكتب سجلك بهذا الأمر، واقرأ ما يحتويه، ثم افتح طلب دمج (pull request) يضيف الملف إلى المستودع المجتمعي ({repo}).",
    "community.empty.title": "لا توجد سجلات مشتركة بعد",
    "community.empty.what": "يجمع المقياس المجتمعي السجلات التي اختار مستخدمو Tenure نشرها: لكل نموذج ولكل فئة إجراءات، النجاحات المُتحقَّق منها والإخفاقات، موقَّعة بمفتاح جوازهم. لا يُشارَك شيء تلقائيًا: لا يُجري Tenure أي اتصال بالشبكة.",
    "community.empty.where": "لعرض الترتيب هنا، نزّل ملف community-board.json الذي ينشره المستودع واحفظه باسم {path}.",
    "community.generated": "{records} · أُنشئ الترتيب في {date}",
    "community.lede": "مُصرَّح به من المساهمين، مع التحقق من التوقيعات: كل سجل موقَّع بمفتاح جواز صاحبه، ويُحتسب سجل واحد لكل مفتاح. ",
    "community.lede_bold": "هذا لا يمنع شخصًا واحدًا من امتلاك عدة مفاتيح.",
    "community.ranking": "لكل فئة إجراءات، تُرتَّب النماذج حسب الحد الأعلى لنطاق 95% لمعدل إخفاقها، وليس أبدًا حسب نتيجة واحدة.",
    "confirm.again": "انقر مرة أخرى للتأكيد",
    "confirm.default": "تأكيد",
    "confirm.flag.desc": "يُحتسب هذا إخفاقًا: ينزل {type} مستوى واحدًا على الأقل ويصعد من جديد. استخدمه لخطأ لم يلاحظه أحد.",
    "confirm.flag.title": "الإبلاغ عن {type} كخطأ؟",
    "confirm.revoke.desc": "سيسأل {type} أولًا من جديد، وتبدأ سلسلته من الصفر. هذا ليس إخفاقًا.",
    "confirm.revoke.title": "سحب {type}؟",
    "confirm.revoke_all.desc": "سيسأل كل نوع إجراء لدى {agent} أولًا من جديد، وتبدأ سلسلته من الصفر. هذا ليس إخفاقًا.",
    "confirm.revoke_all.title": "سحب كل الاستقلالية المكتسبة لهذا الوكيل؟",
    "confirm.undo.title": "التراجع عن الإجراء {id}؟",
    "copy.button": "نسخ",
    "copy.done": "تم النسخ",
    "count.agents": {
      "zero": "{n} وكلاء",
      "one": "{n} وكيل",
      "two": "{n} وكيلان",
      "few": "{n} وكلاء",
      "many": "{n} وكيلًا",
      "other": "{n} وكيل"
    },
    "count.faults": {
      "zero": "{n} إخفاقات",
      "one": "{n} إخفاق",
      "two": "{n} إخفاقان",
      "few": "{n} إخفاقات",
      "many": "{n} إخفاقًا",
      "other": "{n} إخفاق"
    },
    "count.models": {
      "zero": "{n} نماذج",
      "one": "{n} نموذج",
      "two": "{n} نموذجان",
      "few": "{n} نماذج",
      "many": "{n} نموذجًا",
      "other": "{n} نموذج"
    },
    "count.records": {
      "zero": "{n} سجلات",
      "one": "{n} سجل",
      "two": "{n} سجلّان",
      "few": "{n} سجلات",
      "many": "{n} سجلًّا",
      "other": "{n} سجل"
    },
    "count.sessions": {
      "zero": "{n} جلسات",
      "one": "{n} جلسة",
      "two": "{n} جلستان",
      "few": "{n} جلسات",
      "many": "{n} جلسةً",
      "other": "{n} جلسة"
    },
    "counters.actions.label": {
      "zero": "إجراءات",
      "one": "إجراء",
      "two": "إجراءان",
      "few": "إجراءات",
      "many": "إجراءً",
      "other": "إجراء"
    },
    "counters.actions.sub": "مشمولة",
    "counters.alone.label": "نُفّذت دون سؤال",
    "counters.alone.sub": "نُفّذت دون سؤال، من {total}",
    "counters.aria": "آخر 7 أيام",
    "counters.checked.label": "مفحوصة",
    "counters.checked.sub": "بفحصك، من {total}",
    "counters.faults.label": "إخفاقات مكتشفة",
    "counters.faults.sub": {
      "zero": "{faults} من {n} فحص أجريته",
      "one": "{faults} من {n} فحص أجريته",
      "two": "{faults} من {n} فحصين أجريتهما",
      "few": "{faults} من {n} فحوص أجريتها",
      "many": "{faults} من {n} فحصًا أجريته",
      "other": "{faults} من {n} فحص أجريته"
    },
    "counters.window": "آخر 7 أيام، كل الملفات الشخصية",
    "drawer.aria": "الوكيل {agent}",
    "drawer.close": "إغلاق",
    "drawer.close_title": "إغلاق (Esc)",
    "drawer.eyebrow": "وكيل · الملف الشخصي {profile}",
    "drawer.eyebrow_read_only": "وكيل · الملف الشخصي {profile} (للقراءة فقط هنا)",
    "drawer.flag.button": "إبلاغ",
    "drawer.flag.confirm": "إبلاغ؟",
    "drawer.flag.done": "سُجّل إخفاق على {type}: أصبح الآن {tier}.",
    "drawer.flag.title": "تسجيل إخفاق على هذا النوع، بعد وقوعه",
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} إخفاقات / نتائج موثّقة · ",
    "drawer.own_profile_only": "الإجراءات تخص الملف الشخصي لهذه اللوحة فقط",
    "drawer.revoke.button": "سحب",
    "drawer.revoke.confirm": "سحب؟",
    "drawer.revoke.done": "سُحبت استقلالية {type}: عاد إلى T1.",
    "drawer.revoke.title": "استرجاع ما اكتسبه هذا النوع: العودة إلى T1",
    "drawer.revoke_all.button": "سحب الكل",
    "drawer.revoke_all.confirm": "سحب كل الأنواع؟",
    "drawer.revoke_all.done": {
      "zero": "سُحبت استقلالية {count} أنواع: العودة إلى T1.",
      "one": "سُحبت استقلالية {count} نوع: العودة إلى T1.",
      "two": "سُحبت استقلالية {count} نوعين: العودة إلى T1.",
      "few": "سُحبت استقلالية {count} أنواع: العودة إلى T1.",
      "many": "سُحبت استقلالية {count} نوعًا: العودة إلى T1.",
      "other": "سُحبت استقلالية {count} نوع: العودة إلى T1."
    },
    "drawer.revoke_note": "يسري عند الإجراء التالي. كل سحب حدث في الدفتر.",
    "drawer.revoke_note_other": "الإبلاغ والسحب يخصان الملف الشخصي لهذه اللوحة. استخدم: {cmd}",
    "drawer.sessions_of": {
      "zero": "{n}/{total} جلسات",
      "one": "{n}/{total} جلسة",
      "two": "{n}/{total} جلستان",
      "few": "{n}/{total} جلسات",
      "many": "{n}/{total} جلسةً",
      "other": "{n}/{total} جلسة"
    },
    "drawer.stakes_reversible": "{stakes} · يمكن التراجع عنه",
    "drawer.types_title": "أنواع الإجراءات",
    "error.request_failed": "فشل الطلب",
    "event.confirmed": "أدلة منقولة أكّدتها أدلته هو",
    "event.fault.check": "فشل الفحص التلقائي",
    "event.fault.flag": "أبلغتَ عنه كإخفاق",
    "event.fault.other": "إخفاق ({source})",
    "event.fault.refusal": "رفضتَه",
    "event.fault.spot": "فحص عشوائي مرفوض أو فاشل",
    "event.fault.undo": "تراجعتَ عنه",
    "event.neutral.alone": "عمل وحده (مكتسب)",
    "event.neutral.ambiguous": "استدعاء ملتبس · بلا دليل",
    "event.neutral.blocked": "حظره حارس آخر · بلا دليل",
    "event.neutral.error": "خطأ في الأداة · بلا دليل",
    "event.neutral.expired": "لم يرجع بنتيجة · بلا دليل",
    "event.neutral.nobody": "لا أحد ليجيب · بلا دليل",
    "event.neutral.other": "محايد ({source})",
    "event.neutral.timeout": "بلا إجابة · بلا دليل",
    "event.neutral_expired": "انتهت صلاحية الإجراء المعلّق · بلا دليل",
    "event.revoked": "سحبتَه",
    "event.success.approved": "وافقتَ عليه، ونُفّذ بسلام",
    "event.success.notify": "نفّذ ثم أبلغ · لم يُتراجع عنه",
    "event.success.spot": "فحص عشوائي وافقتَ عليه",
    "event.switch": "تبديل النموذج",
    "event.switch_from": "تبديل النموذج من {from}",
    "event.tier": "المستوى: من {from} إلى {to} · {why}",
    "event.trial.failed": {
      "zero": "فشل الاختبار: انتظر {wait} إجراءات",
      "one": "فشل الاختبار: انتظر {wait} إجراء",
      "two": "فشل الاختبار: انتظر {wait} إجراءين",
      "few": "فشل الاختبار: انتظر {wait} إجراءات",
      "many": "فشل الاختبار: انتظر {wait} إجراءً",
      "other": "فشل الاختبار: انتظر {wait} إجراء"
    },
    "event.trial.opened": {
      "zero": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "one": "فُتح اختبار: يجب أن ينجح الإجراء التالي",
      "two": "فُتح اختبار: يجب أن ينجح الإجراءان التاليان",
      "few": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "many": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "other": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{left} التالية"
    },
    "event.trial.passed": "اجتاز الاختبار",
    "event.trial.reopens": {
      "zero": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "one": "يُعاد فتح الاختبار: يجب أن ينجح الإجراء التالي",
      "two": "يُعاد فتح الاختبار: يجب أن ينجح الإجراءان التاليان",
      "few": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "many": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{left} التالية",
      "other": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{left} التالية"
    },
    "event.why.fault": "إخفاق",
    "event.why.series_complete": "اكتملت السلسلة",
    "event.why.series_n": "السلسلة {required}/{required}",
    "event.why.sessions": {
      "zero": "{count} جلسات",
      "one": "{count} جلسة",
      "two": "{count} جلستان",
      "few": "{count} جلسات",
      "many": "{count} جلسةً",
      "other": "{count} جلسة"
    },
    "event.why.settings": "إعدادات أكثر صرامة",
    "event.why.stakes": "تغيّرت الخطورة",
    "event.why.wald": "اجتاز الاختبار التتابعي",
    "flag.carried_over": "منقول",
    "flag.carried_over_n": {
      "zero": "{n} منقولة",
      "one": "{n} منقول",
      "two": "{n} منقولان",
      "few": "{n} منقولة",
      "many": "{n} منقولة",
      "other": "{n} منقولة"
    },
    "flag.carried_over_provisional": {
      "zero": "{n} منقولة، مؤقتة",
      "one": "{n} منقول، مؤقت",
      "two": "{n} منقولان، مؤقتان",
      "few": "{n} منقولة، مؤقتة",
      "many": "{n} منقولة، مؤقتة",
      "other": "{n} منقولة، مؤقتة"
    },
    "flag.carried_over_title": {
      "zero": "{count} منقولة، مؤقتة",
      "one": "{count} منقول، مؤقت",
      "two": "{count} منقولان، مؤقتان",
      "few": "{count} منقولة، مؤقتة",
      "many": "{count} منقولة، مؤقتة",
      "other": "{count} منقولة، مؤقتة"
    },
    "flag.fault_on_record": "إخفاق مسجَّل",
    "flag.fault_on_record_title": "إخفاق مسجَّل",
    "flag.provisional": "مؤقت",
    "flag.trial": "اختبار",
    "guarantee.capped": "مقيَّد: كل إجراء يسأل.",
    "guarantee.plain": "على الأكثر نحو إجراء واحد من كل {k} من إجراءاته يُنفَّذ بخطأ لم يوافق عليه أحد.",
    "guarantee.text": "تبقى الأخطاء غير المفحوصة دون {aoql} من إجراءاته من هذا النوع؛ ولوكيل يسوء بعد اكتساب الاستقلالية، {worst} على الأكثر حتى أول خطأ يُكتشف.",
    "guarantee.text_conditional": "تبقى الأخطاء غير المفحوصة دون {aoql} من إجراءاته من هذا النوع؛ ولوكيل يسوء بعد اكتساب الاستقلالية، {worst} على الأكثر حتى أول خطأ يُكتشف. بشرط أن تظل أدلة النموذج السابق صالحة.",
    "guarantee.trusted": "لا ضمان بعد: الضمان يأتي فقط مع مستوى مكتسب بالأدلة.",
    "help.agent": "لوحة وكيل الصف المحدد",
    "help.aria": "اختصارات لوحة المفاتيح",
    "help.close": "إغلاق",
    "help.help": "هذه المساعدة",
    "help.next_prev": "الوكيل التالي / السابق",
    "help.open": "فتح الوكيل المحدد",
    "help.raw": "إظهار / إخفاء الأسماء الخام للأنواع",
    "help.title": "لوحة المفاتيح",
    "legend.a_share": "نسبة منها",
    "legend.alone": "يعمل وحده، ويُفحص {share} عشوائيًا",
    "legend.ask": "يسأل أولًا",
    "legend.capped": "مقيَّد: يسأل دائمًا",
    "legend.carried": "من النموذج السابق، مؤقت",
    "legend.notify": "ينفّذ ثم يُبلغ مع إمكانية التراجع (الأنواع القابلة للتراجع)",
    "legend.series": "نجاحات موثَّقة على التوالي، من أصل N مطلوبة",
    "legend.trusted": "بداية موثوقة: يعمل مثل Hermes وحده حتى أول خطأ له، دون أي اكتساب",
    "map.aria": "الوكلاء حسب نوع الإجراء",
    "map.empty.after": "، ولا يصعد إلا بنجاحات موثّقة: تبلغ الأنواع القابلة للتراجع المستوى الأوسط بعد سلسلة من النجاحات الموثّقة دون إخفاق، وT3 بعد سلسلة كاملة من N على جلستين.",
    "map.empty.before": "يبدأ tenure العدّ عند أول إجراء يطلب الوكيل تنفيذه. القراءة لا تسأل أبدًا. يبدأ كل نوع إجراء في ",
    "map.empty.bold": "T1، يسأل أولًا",
    "map.empty.title": "لا أدلة بعد",
    "map.open_hint": "فتح ",
    "map.th.agent": "الوكيل",
    "map.th.agent_sub": "الملف الشخصي · model@provider",
    "map.th.capped": "مقيَّد · يسأل دائمًا",
    "map.th.risk": {
      "zero": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "one": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "two": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "few": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "many": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "other": "المخاطرة {risk} · {n} على التوالي ليعمل وحده"
    },
    "meta.preset": "الإعداد المسبق",
    "meta.profile": "الملف الشخصي",
    "meta.start": "البداية",
    "missing.always_asks": "يسأل دائمًا",
    "missing.earned": "مكتسب · فحص عشوائي",
    "missing.more_to_t2": {
      "zero": "بقي {n} حتى «قيد المراجعة» (T2)",
      "one": "بقي {n} حتى «قيد المراجعة» (T2)",
      "two": "بقي {n} حتى «قيد المراجعة» (T2)",
      "few": "بقي {n} حتى «قيد المراجعة» (T2)",
      "many": "بقي {n} حتى «قيد المراجعة» (T2)",
      "other": "بقي {n} حتى «قيد المراجعة» (T2)"
    },
    "missing.more_to_t3": {
      "zero": "بقي {n} حتى التثبيت",
      "one": "بقي {n} حتى التثبيت",
      "two": "بقي {n} حتى التثبيت",
      "few": "بقي {n} حتى التثبيت",
      "many": "بقي {n} حتى التثبيت",
      "other": "بقي {n} حتى التثبيت"
    },
    "missing.rechecking": "إعادة الفحص",
    "missing.second_session": "يحتاج جلسة ثانية",
    "missing.trial_left": {
      "zero": "اختبار · بقي {n} من {total}",
      "one": "اختبار · بقي {n} من {total}",
      "two": "اختبار · بقي {n} من {total}",
      "few": "اختبار · بقي {n} من {total}",
      "many": "اختبار · بقي {n} من {total}",
      "other": "اختبار · بقي {n} من {total}"
    },
    "missing.trial_wait": {
      "zero": "فشل الاختبار · انتظر {n}",
      "one": "فشل الاختبار · انتظر {n}",
      "two": "فشل الاختبار · انتظر {n}",
      "few": "فشل الاختبار · انتظر {n}",
      "many": "فشل الاختبار · انتظر {n}",
      "other": "فشل الاختبار · انتظر {n}"
    },
    "missing.trusted": "موثوق حتى أول خطأ له · يعمل مثل Hermes وحده",
    "missing.trusted_undo": "موثوق حتى أول خطأ له · ينفّذ ثم يُبلغ مع إمكانية التراجع",
    "models.empty.body": "كل إجراء موثّق يُضاف إلى سجل النموذج على ذلك النوع، هنا وفي {cmd}.",
    "models.empty.title": "لا سجل بعد",
    "models.lede": "مقياسك الخاص: السجل الموثّق لكل نموذج على عملك، لكل نوع إجراء، مع نطاق 95% لمعدل إخفاقه. الترتيب حسب الحد الأعلى للنطاق، لا حسب نتيجة واحدة. وبجانبه المقياس العام، للعلم فقط: ",
    "models.lede_bold": "قدرة عامة على مهامهم، لا موثوقية على مهامك.",
    "models.no_public": "لا مقياس عام لنوع الإجراء هذا.",
    "models.not_enough": "أدلة غير كافية",
    "models.not_ranked": "لا أدلة كافية بعد",
    "models.not_ranked_note": "يدخل النموذج الترتيب عندما يبلغ {n} نتيجة موثّقة على هذا النوع.",
    "models.personal_title": "على عملك",
    "models.public_note": "قدرة عامة على مهامهم، لا موثوقية على مهامك.",
    "models.public_title": "المقياس العام",
    "models.source": "{source}. أفضل نتيجة منشورة، بأي أداة تقييم؛ ليست مقارنة مضبوطة.",
    "models.source_accessed": "{source}، اطُّلع عليه في {accessed}. أفضل نتيجة منشورة، بأي أداة تقييم؛ ليست مقارنة مضبوطة.",
    "moment.dismiss": "إغلاق",
    "moment.eyebrow.down": "رُصد إخفاق",
    "moment.eyebrow.up": "ترقية",
    "moment.granted": "مُنح التثبيت",
    "moment.probation": "العودة إلى فترة الاختبار",
    "moment.review": "قيد المراجعة",
    "page.anim_off": "الحركة متوقفة",
    "page.anim_on": "الحركة مفعّلة",
    "page.anim_reduced": "يطلب نظامك تقليل الحركة: تبقى الحركة متوقفة",
    "page.anim_title": "الحركة: مفعّلة أو متوقفة، وتُحفظ في هذا المتصفح",
    "page.animations": "الرسوم المتحركة",
    "page.error": "تعذّرت قراءة tenure: {error}",
    "page.live": "مباشر · ",
    "page.loading": "جارٍ تحميل السجل…",
    "page.polling": "تحديث كل {s} ث",
    "page.raw_off": "أسماء محجوبة",
    "page.raw_on": "أسماء خام",
    "page.raw_title": "إظهار الأسماء الخام لأنواع الإجراءات (r)",
    "page.retrying": "إعادة المحاولة · ",
    "page.subtitle": "ثقة قابلة للسحب: تُسحب عند الخطأ وتُستعاد بأدلة موثّقة",
    "page.title": "Tenure",
    "page.unreadable": "غير مقروء: {profiles}. قاعدة بياناته موجودة لكن يتعذّر فتحها؛ تُعرض الملفات الشخصية الأخرى.",
    "passport.agent": "الوكيل",
    "passport.card.aria": "جواز {agent}: {verdict}",
    "passport.card.signature": "إضافة لـ Hermes Agent",
    "passport.card.title": "جواز",
    "passport.checked_by": "تحققت منه اللوحة مقابل دفتر هذا الملف الشخصي. يمكن لأي شخص إعادة التحقق:",
    "passport.download": "تنزيل JSON",
    "passport.empty.body": "يغطي الجواز سجل الوكيل؛ ويظهر مع أول إجراء موثّق.",
    "passport.empty.title": "لا جواز بعد",
    "passport.faults_checks": {
      "zero": "{n} إخفاق / {total} نتائج موثّقة",
      "one": "{n} إخفاق / {total} نتائج موثّقة",
      "two": "{n} إخفاق / {total} نتائج موثّقة",
      "few": "{n} إخفاق / {total} نتائج موثّقة",
      "many": "{n} إخفاق / {total} نتائج موثّقة",
      "other": "{n} إخفاق / {total} نتائج موثّقة"
    },
    "passport.field.agent": "الوكيل",
    "passport.field.generated": "أُنشئ في",
    "passport.field.ledger": "الدفتر",
    "passport.field.profile": "الملف الشخصي",
    "passport.field.protocol": "البروتوكول",
    "passport.field.public_key": "المفتاح العام",
    "passport.field.rule": "القاعدة",
    "passport.field.settings": "الإعدادات",
    "passport.field.signature": "التوقيع",
    "passport.field.type_names": "أسماء الأنواع",
    "passport.note": "موقَّع ويكشف التلاعب: أي تغيير بعد توقيعه أو تثبيته يظهر عند التحقق. يظل الجواز الأقدم صالحًا مقابل دفتر أطول؛ ويذكر المتحقِّق ما تغيّر منذ ذلك.",
    "passport.pending_note": "محسوب وفق آخر إعدادات مسجّلة؛ تسري الإعدادات الجديدة من الإجراء التالي.",
    "passport.trusted": "موثوق (غير مكتسب)",
    "passport.types_title": "الأنواع المشهود لها",
    "passport.value.hashed": "{profile} (مجزَّأ)",
    "passport.value.ledger": {
      "zero": "{n} أحداث · الرأس {head}",
      "one": "{n} حدث · الرأس {head}",
      "two": "{n} حدثان · الرأس {head}",
      "few": "{n} أحداث · الرأس {head}",
      "many": "{n} حدثًا · الرأس {head}",
      "other": "{n} حدث · الرأس {head}"
    },
    "passport.value.none": "لا شيء",
    "passport.value.raw": "خام",
    "passport.value.redacted": "محجوب بعد البرنامج والأمر الفرعي",
    "passport.value.unsigned": "غير موقَّع",
    "preset.balanced": "متوازن",
    "preset.careful": "حذِر",
    "preset.custom": "مخصص",
    "preset.fast": "سريع",
    "profile.copy_pending": "منسوخ من ملف شخصي آخر، يُفحص عند تشغيله",
    "profile.name": "الملف الشخصي {profile}",
    "profile.pending": "يسري من الإجراء التالي",
    "profile.preset": "الإعداد المسبق {preset}",
    "profile.read_only": " · للقراءة فقط هنا",
    "profile.sessions_suspended": {
      "zero": "{n} جلسات معلّقة: قُرئ محتوى خارجي",
      "one": "{n} جلسة معلّقة: قُرئ محتوى خارجي",
      "two": "{n} جلستان معلّقتان: قُرئ محتوى خارجي",
      "few": "{n} جلسات معلّقة: قُرئ محتوى خارجي",
      "many": "{n} جلسةً معلّقة: قُرئ محتوى خارجي",
      "other": "{n} جلسة معلّقة: قُرئ محتوى خارجي"
    },
    "profile.spot": "فحوص عشوائية {rate}",
    "profile.start_probation": "بداية بالدراسة (فترة اختبار)",
    "profile.start_trusted": "بداية موثوقة",
    "profile.strict": "صارم",
    "profile.suspended": {
      "zero": "{n} معلّقة: قُرئ محتوى خارجي",
      "one": "{n} معلّق: قُرئ محتوى خارجي",
      "two": "{n} معلّقان: قُرئ محتوى خارجي",
      "few": "{n} معلّقة: قُرئ محتوى خارجي",
      "many": "{n} معلّقة: قُرئ محتوى خارجي",
      "other": "{n} معلّقة: قُرئ محتوى خارجي"
    },
    "profile.this_dashboard": " · هذه اللوحة",
    "settings.advanced_docs": "كل مفتاح مشروح عبر hermes tenure explain وفي ملف README الخاص بـ tenure.",
    "settings.advanced_help": "إعادة تصنيف أنواع الإجراءات، وكل المفاتيح في نموذج Hermes الخاص.",
    "settings.advanced_title": "متقدّم",
    "settings.advanced_types": "أعد تصنيف أنواع الإجراءات (free أو low أو medium أو high أو cap لكل نمط) في الإعدادات ← الإضافات ← Tenure في Hermes، أو في config.yaml:",
    "settings.animations_help": "الأشرطة التي تُطبع، والجواز الذي يظهر تدريجيًا، والأشرطة العريضة. المفتاح نفسه الموجود في رأس الصفحة؛ ويبقى متوقفًا إذا طلب نظامك تقليل الحركة.",
    "settings.custom_help": "نسبتك الخاصة من الأخطاء غير المفحوصة لكل مستوى خطورة: اختر 1 من كل k، أو اكتب قيمة k الخاصة بك، أو قيد (يسأل دائمًا). تتحدّث السلسلة التي يحتاجها النوع فورًا. بعد الحفظ يصبح الإعداد المسبق مخصصًا، ما لم يطابق أحدها.",
    "settings.custom_title": "المخاطرة المقبولة لكل مستوى خطورة",
    "settings.enabled_help": "أوقف tenure دون إلغاء تثبيته.",
    "settings.enabled_off": "متوقف",
    "settings.enabled_on": "مفعّل",
    "settings.enabled_title": "تشغيل tenure أو إيقافه",
    "settings.enabled_unknown": "لا يُبلغ جزء الوكيل عن هذه الحالة بعد: اختر واحدة لضبطها.",
    "settings.enabled_warn": "متوقف: يكفّ tenure عن اتخاذ القرار؛ ويسأل Hermes كالمعتاد. يبقى الدفتر وكل السجلات كما هي.",
    "settings.in_force": "سارٍ",
    "settings.no_writer": "لا يسمح Hermes هذا لـ Desktop بحفظ إعدادات tenure: استخدم الأمر أدناه.",
    "settings.none": "لا سجل tenure لهذا الملف الشخصي بعد: تسري القيم الافتراضية حتى أول إجراء له.",
    "settings.one_in": "1 من كل",
    "settings.or_config": "أو في ملف config.yaml الخاص بـ Hermes، تحت plugins.entries.tenure.settings:",
    "settings.or_terminal": "أو في الطرفية:",
    "settings.pending": "آخر تغيير لم يُسجَّل في الدفتر بعد: يسري من الإجراء التالي.",
    "settings.preset_desc_balanced": "الإعداد الافتراضي. الأنواع عالية الخطورة تسأل دائمًا.",
    "settings.preset_desc_careful": "يسأل أطول مدة. حتى الأنواع عالية الخطورة يمكنها اكتساب مستواها بعد سلسلة طويلة.",
    "settings.preset_desc_custom": "مخاطرتك المقبولة الخاصة لكل مستوى خطورة، محددة في إعدادات Hermes.",
    "settings.preset_desc_fast": "يكتسب الاستقلالية أسرع عند الخطورة المنخفضة والمتوسطة. الأنواع عالية الخطورة تسأل دائمًا.",
    "settings.preset_help": "مقدار الأدلة التي يحتاجها نوع الإجراء قبل أن يعمل وحده، حسب مستوى الخطورة: سلسلة النجاحات الموثّقة على التوالي، ونسبة الأخطاء غير المفحوصة المقبولة.",
    "settings.risk": "يُقبل خطأ واحد غير مفحوص من كل {k}",
    "settings.risk_invalid": "عدد صحيح من 2 فأكثر.",
    "settings.rung_cap": "قيد",
    "settings.save": "حفظ",
    "settings.save_failed": "لم يُحفظ: {error}",
    "settings.saved": "حُفظ وسُجّل في الدفتر: يسري من الإجراء التالي.",
    "settings.saves_here": "تُحفظ التغييرات فورًا عبر أداة كتابة الإعدادات الخاصة بـ Hermes نفسه، وتُسجَّل في الدفتر؛ وتسري من الإجراء التالي. الإعدادات نفسها موجودة في الإعدادات ← الإضافات ← Tenure في Hermes.",
    "settings.saving": "جارٍ الحفظ…",
    "settings.series": {
      "zero": "{n} نجاحات موثّقة على التوالي",
      "one": "{n} نجاح موثّق على التوالي",
      "two": "{n} نجاحين موثّقين على التوالي",
      "few": "{n} نجاحات موثّقة على التوالي",
      "many": "{n} نجاحًا موثّقًا على التوالي",
      "other": "{n} نجاح موثّق على التوالي"
    },
    "settings.spot_change": "اضبطه في ملف config.yaml الخاص بـ Hermes، تحت plugins.entries.tenure.settings (نسبة بين 0 و1):",
    "settings.spot_custom": "قيمتك الخاصة: 1 من كل k",
    "settings.spot_desc": "بعد تثبيت النوع، يظل إجراء واحد من كل {k} من إجراءاته يسأل، عشوائيًا: فيُكشف النموذج الذي يسوء أداؤه.",
    "settings.spot_title": "الفحوص العشوائية",
    "settings.spot_value": "1 من كل {k}",
    "settings.start_help": "ما يفعله نوع الإجراء قبل أول إخفاق له.",
    "settings.start_probation": "بداية الدراسة: كل نوع إجراء يسأل أولًا (T1) ويكتسب كل مستوى من إجاباتك.",
    "settings.start_trusted": "الأنواع المشمولة (تعديل الملفات، والذاكرة، والوكلاء الفرعيون، وأدوات التطوير المعروفة) لا تسأل شيئًا حتى أول إخفاق لها، كما يعمل Hermes وحده. الإخفاق يضع ذلك النوع في فترة اختبار (T1)، ثم يستعيد مستواه. مغادرة الجهاز والمال يسألان دائمًا.",
    "settings.strict_desc_off": "يرث النموذج الجديد سجل النموذج السابق عند الخطورة المنخفضة والمتوسطة، منصّفًا ومؤقتًا حتى تؤكده موافقاته الخاصة. الخطورة العالية تبدأ من الصفر.",
    "settings.strict_desc_on": "يبدأ النموذج الجديد بسجل فارغ في كل نوع إجراء، كما في الدراسة.",
    "settings.strict_help": "ما يرثه النموذج الجديد عند تبديل النماذج.",
    "settings.strict_off": "الوضع الصارم متوقف",
    "settings.strict_on": "الوضع الصارم مفعّل",
    "settings.strict_title": "الوضع الصارم عند تغيير النموذج",
    "settings.use": "استخدام",
    "stakes.group.high": "خطورة عالية",
    "stakes.group.low": "خطورة منخفضة",
    "stakes.group.medium": "خطورة متوسطة",
    "stakes.high": "عالية",
    "stakes.low": "منخفضة",
    "stakes.medium": "متوسطة",
    "stale.message": "فشل آخر تحديث ({error}). تُعرض بيانات {time}.",
    "start.probation": "بداية بالدراسة (فترة اختبار)",
    "start.trusted": "بداية موثوقة",
    "switch.count.carried": {
      "zero": "{n} منقولة",
      "one": "{n} منقول",
      "two": "{n} منقولان",
      "few": "{n} منقولة",
      "many": "{n} منقولة",
      "other": "{n} منقولة"
    },
    "switch.count.kept": {
      "zero": "{n} محفوظة",
      "one": "{n} محفوظ",
      "two": "{n} محفوظان",
      "few": "{n} محفوظة",
      "many": "{n} محفوظة",
      "other": "{n} محفوظة"
    },
    "switch.count.reset": {
      "zero": "{n} مُصفَّرة",
      "one": "{n} مُصفَّر",
      "two": "{n} مُصفَّران",
      "few": "{n} مُصفَّرة",
      "many": "{n} مُصفَّرة",
      "other": "{n} مُصفَّرة"
    },
    "switch.count.vetoed": {
      "zero": "{n} مرفوضة",
      "one": "{n} مرفوض",
      "two": "{n} مرفوضان",
      "few": "{n} مرفوضة",
      "many": "{n} مرفوضة",
      "other": "{n} مرفوضة"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "لا وكيل للمعاينة بعد",
    "switch.footnote": "النتائج العامة للعلم؛ لا تمنح استقلالية أبدًا. الرفض يمنع النقل فقط، فوق هامش ثابت.",
    "switch.from": "من",
    "switch.lede": "قبل أن تغيّر النموذج: ما الذي سيرثه الوكيل الجديد، نوعًا بنوع. النموذج أو المزوّد الجديد وكيل جديد. النقل إضافة منا؛ الوضع الصارم هو الدراسة.",
    "switch.none": "لا شيء",
    "switch.pick.body": "اكتب أي معرّف نموذج. لا شيء يتغيّر حتى يشغّل Hermes النموذج الجديد فعلًا.",
    "switch.pick.title": "اختر النموذج الهدف",
    "switch.placeholder": "معرّف النموذج، مثل {example} أو model@provider",
    "switch.preview": "معاينة",
    "switch.provisional": {
      "zero": "{n} مؤقتة",
      "one": "{n} مؤقت",
      "two": "{n} مؤقتان",
      "few": "{n} مؤقتة",
      "many": "{n} مؤقتة",
      "other": "{n} مؤقتة"
    },
    "switch.status.carried.label": "منقول، مؤقت",
    "switch.status.carried.text": "ينتقل جزء من السلسلة، موسومًا بأنه مؤقت حتى يضيف النموذج الجديد أدلته.",
    "switch.status.kept.label": "محفوظ",
    "switch.status.kept.text": "للوكيل الجديد سجله الخاص هنا بالفعل؛ لا يُستبدل أبدًا.",
    "switch.status.reset.label": "مُصفَّر",
    "switch.status.reset.text": "يبدأ من الصفر: خطورة عالية، أو مقيَّد، أو الوضع الصارم.",
    "switch.status.vetoed.label": "مرفوض",
    "switch.status.vetoed.text": "يُظهر المقياس العام أن النموذج الجديد أضعف في هذا النوع: لا يُنقل شيء.",
    "switch.strict": "الوضع الصارم: لا يُنقل شيء",
    "switch.to": "إلى النموذج",
    "switch.to_aria": "النموذج الهدف",
    "tabs.aria": "عروض Tenure",
    "th.after_switch": "بعد التبديل",
    "th.agent": "الوكيل",
    "th.contributors": "المساهمون",
    "th.faults_checks": "إخفاقات / نتائج موثّقة",
    "th.file": "الملف",
    "th.guarantee": "الضمان",
    "th.model": "النموذج",
    "th.now": "الآن",
    "th.outcome": "النتيجة",
    "th.public_measure": "المقياس العام",
    "th.range": "نطاق 95% · 0–{max}",
    "th.rate": "المعدل",
    "th.series": "السلسلة",
    "th.sessions": "الجلسات",
    "th.tier": "المستوى",
    "th.type": "النوع",
    "th.undo_effect": "أثر التراجع",
    "th.when": "متى",
    "th.your_record": "سجلك",
    "tier.capped.chip": "CAP",
    "tier.capped.title": "مقيَّد: يسأل دائمًا",
    "tier.chip.title": "{tier}، {name}",
    "tier.label.alone": "مُثبَّت",
    "tier.label.ask": "فترة اختبار",
    "tier.label.cap": "يسأل دائمًا",
    "tier.label.notify": "قيد المراجعة",
    "tier.name.alone": "يعمل وحده",
    "tier.name.ask": "يسأل أولًا",
    "tier.name.notify": "ينفّذ ثم يُبلغ",
    "tier.trusted.chip": "موثوق",
    "tier.trusted.label": "موثوق",
    "tier.trusted.name": "يعمل مثل Hermes وحده",
    "tier.trusted.title": "موثوق حتى أول خطأ له: يعمل مثل Hermes وحده. لم يُكتسب شيء بعد.",
    "time.ago": "قبل {duration}",
    "time.days": {
      "zero": "{n} ي",
      "one": "{n} ي",
      "two": "{n} ي",
      "few": "{n} ي",
      "many": "{n} ي",
      "other": "{n} ي"
    },
    "time.hours_minutes": {
      "zero": "{n} س {mm} د",
      "one": "{n} س {mm} د",
      "two": "{n} س {mm} د",
      "few": "{n} س {mm} د",
      "many": "{n} س {mm} د",
      "other": "{n} س {mm} د"
    },
    "time.minutes": {
      "zero": "{n} د",
      "one": "{n} د",
      "two": "{n} د",
      "few": "{n} د",
      "many": "{n} د",
      "other": "{n} د"
    },
    "time.seconds": {
      "zero": "{n} ث",
      "one": "{n} ث",
      "two": "{n} ث",
      "few": "{n} ث",
      "many": "{n} ث",
      "other": "{n} ث"
    },
    "timeline.all_types": "كل الأنواع",
    "timeline.count": {
      "zero": "{n}×",
      "one": "{n}×",
      "two": "{n}×",
      "few": "{n}×",
      "many": "{n}×",
      "other": "{n}×"
    },
    "timeline.empty": "لا أدلة لهذا المرشّح",
    "timeline.filter_label": "التصفية حسب النوع",
    "timeline.loading": "جارٍ تحميل الأدلة…",
    "timeline.note": "من الدفتر المتسلسل بالتجزئة، الأحدث أولًا، آخر 200 حدث. تُجمَّع النتائج المتكررة.",
    "timeline.title": "خط الأدلة الزمني",
    "toast.transition": "{agent} · {type}: من {from} إلى {to}",
    "totals.actions": {
      "zero": "{n} إجراءات",
      "one": "{n} إجراء",
      "two": "{n} إجراءان",
      "few": "{n} إجراءات",
      "many": "{n} إجراءً",
      "other": "{n} إجراء"
    },
    "totals.alone": "{n} دون سؤال",
    "totals.checked": "{n} مفحوصة",
    "totals.faults": {
      "zero": "{n} إخفاقات",
      "one": "{n} إخفاق",
      "two": "{n} إخفاقان",
      "few": "{n} إخفاقات",
      "many": "{n} إخفاقًا",
      "other": "{n} إخفاق"
    },
    "transitions.empty": "لا شيء منذ فتح هذه الصفحة. كل تغيير تلقائي في المستوى يُدرج هنا وفي الخط الزمني لكل وكيل.",
    "transitions.title": "تغييرات المستوى المرصودة في هذه الصفحة",
    "transitions.why.after_fault": "بعد إخفاق",
    "transitions.why.on_evidence": "بالأدلة",
    "transitions.why.trial_open": "اختبار مفتوح",
    "transitions.why_changed": "دون إخفاق: سحب، أو تغيّرت الإعدادات أو مستوى الخطورة",
    "type.always_asks": "يسأل دائمًا",
    "type.stakes_high": "خطورة عالية",
    "type.stakes_low": "خطورة منخفضة",
    "type.stakes_medium": "خطورة متوسطة",
    "undo.button": "تراجع",
    "undo.collapse": "طيّ",
    "undo.confirm": "التراجع عن #{id}؟",
    "undo.effect.already": "يستعيد الملفات · سبق أن حسب الفحص التلقائي إخفاقًا",
    "undo.effect.fault": "يستعيد الملفات · يُحسب إخفاقًا",
    "undo.effect.none": "لا شيء للاستعادة (لا لقطة) · سيُحتسب إخفاقًا",
    "undo.empty.body": "عمليات الكتابة التي أجراها الوكيل دون سؤال (موثوق، أو في T2: ينفّذ ثم يُبلغ) تحتفظ بلقطة من الملفات لمدة 24 ساعة. تظهر هنا، الأحدث أولًا، ولكل منها زر تراجع.",
    "undo.empty.title": "لا شيء للتراجع عنه",
    "undo.expand": "عرض التفاصيل",
    "undo.lede": "إجراءات «ينفّذ ثم يُبلغ» الأخيرة. التراجع يستعيد الملفات من لقطتها ويُحسب إخفاقًا للنوع.",
    "undo.no_snapshot": "بلا لقطة",
    "undo.own_profile_only": "التراجع يخص الملف الشخصي لهذه اللوحة فقط",
    "undo.title": "استعادة الملفات",
    "undo.window_ends": "تنتهي المهلة خلال {duration}",
    "verdict.chain": "سلسلة التجزئة سليمة",
    "verdict.ok.replay": "إعادة تشغيل الدفتر بالقاعدة تعطي المستويات نفسها",
    "verdict.ok.signature": "التوقيع صالح (Ed25519)",
    "verdict.ok.title": "تم التحقق",
    "verdict.problems": {
      "zero": "وُجدت {count} مشكلات",
      "one": "وُجدت {count} مشكلة",
      "two": "وُجدت {count} مشكلتان",
      "few": "وُجدت {count} مشكلات",
      "many": "وُجدت {count} مشكلةً",
      "other": "وُجدت {count} مشكلة"
    },
    "verdict.unsigned.no_key": "لا مفتاح توقيع بعد: {cmd} ينشئ واحدًا",
    "verdict.unsigned.replay": "إعادة التشغيل تعطي المستويات نفسها",
    "verdict.unsigned.title": "غير موقَّع، وما عدا ذلك سليم",
    "view.community": "المجتمع",
    "view.map": "الخريطة",
    "view.models": "مقياسك",
    "view.passport": "الجواز",
    "view.settings": "الإعدادات",
    "view.switch": "معاينة التبديل",
    "view.undo": "تراجع"
  },
  "es": {
    "cell.asked_suffix": " preguntas",
    "cell.capped_by_settings": "Limitado por la configuración de riesgo",
    "cell.held": "{tier} guardado, retenido por tu configuración",
    "cell.kind_irreversible": "{type} · {stakes}, irreversible",
    "cell.kind_reversible": "{type} · {stakes}, reversible",
    "cell.provisional_long": {
      "one": "{count} heredado del modelo anterior, provisional",
      "other": "{count} heredados del modelo anterior, provisionales"
    },
    "cell.record": "Historial: {successes} éxitos · {faults} fallos · {neutrals} neutros · {spot} controles aleatorios",
    "cell.series": "Serie {series}/{required} seguidas",
    "cell.sessions": {
      "one": "{count} sesión",
      "other": "{count} sesiones"
    },
    "cell.tier_now": "Nivel actual: {tier} ({name})",
    "common.arrow": "→",
    "common.capped": "limitado",
    "common.list_sep": ", ",
    "common.loading": "Cargando…",
    "common.no_public_measure": "sin medida pública",
    "common.one_in": "1 de cada {k}",
    "common.percent": "{v} %",
    "common.profile": "perfil {profile}",
    "community.empty.how": "Para contribuir, escribe tu registro con este comando, lee lo que contiene y abre una pull request que añada el archivo al repositorio comunitario ({repo}).",
    "community.empty.title": "Todavía no hay registros compartidos",
    "community.empty.what": "El benchmark comunitario reúne los registros que usuarios de Tenure decidieron publicar: por modelo y por familia de acciones, los éxitos verificados y los fallos, firmados con la clave de su pasaporte. No se comparte nada automáticamente: Tenure no hace ninguna llamada de red.",
    "community.empty.where": "Para ver la clasificación aquí, descarga el community-board.json que publica el repositorio y guárdalo como {path}.",
    "community.generated": "{records} · clasificación generada el {date}",
    "community.lede": "Declarado por quienes contribuyen, con firmas comprobadas: cada registro va firmado con la clave del pasaporte de su autor, y cuenta un solo registro por clave. ",
    "community.lede_bold": "Esto no impide que una misma persona tenga varias claves.",
    "community.ranking": "Por familia de acciones, los modelos se ordenan por el extremo superior del rango del 95 % de su tasa de fallos, nunca por una sola puntuación.",
    "confirm.again": "Haz clic otra vez para confirmar",
    "confirm.default": "Confirmar",
    "confirm.flag.desc": "Cuenta como fallo: {type} baja al menos un nivel y vuelve a subir. Úsalo para un error que nadie detectó.",
    "confirm.flag.title": "¿Marcar {type} como error?",
    "confirm.revoke.desc": "{type} vuelve a preguntar antes de actuar y su serie empieza de cero. No es un fallo.",
    "confirm.revoke.title": "¿Revocar {type}?",
    "confirm.revoke_all.desc": "Cada tipo de acción de {agent} vuelve a preguntar antes de actuar y su serie empieza de cero. No es un fallo.",
    "confirm.revoke_all.title": "¿Revocar toda la autonomía ganada de este agente?",
    "confirm.undo.title": "¿Deshacer la acción {id}?",
    "copy.button": "Copiar",
    "copy.done": "Copiado",
    "count.agents": {
      "one": "{n} agente",
      "other": "{n} agentes"
    },
    "count.faults": {
      "one": "{n} fallo",
      "other": "{n} fallos"
    },
    "count.models": {
      "one": "{n} modelo",
      "many": "{n} modelos",
      "other": "{n} modelos"
    },
    "count.records": {
      "one": "{n} registro",
      "many": "{n} registros",
      "other": "{n} registros"
    },
    "count.sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "counters.actions.label": {
      "one": "acción",
      "other": "acciones"
    },
    "counters.actions.sub": "cubiertas",
    "counters.alone.label": "sin preguntar",
    "counters.alone.sub": "ejecutadas sin preguntar, de {total}",
    "counters.aria": "Últimos 7 días",
    "counters.checked.label": "comprobadas",
    "counters.checked.sub": "por ti, de {total}",
    "counters.faults.label": "fallos detectados",
    "counters.faults.sub": {
      "one": "{faults} de {n} comprobación tuya",
      "other": "{faults} de {n} comprobaciones tuyas"
    },
    "counters.window": "últimos 7 días, todos los perfiles",
    "drawer.aria": "Agente {agent}",
    "drawer.close": "Cerrar",
    "drawer.close_title": "Cerrar (Esc)",
    "drawer.eyebrow": "Agente · perfil {profile}",
    "drawer.eyebrow_read_only": "Agente · perfil {profile} (solo lectura aquí)",
    "drawer.flag.button": "Marcar",
    "drawer.flag.confirm": "¿Marcar?",
    "drawer.flag.done": "Fallo registrado en {type}: ahora {tier}.",
    "drawer.flag.title": "Registrar un fallo en este tipo, a posteriori",
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} fallos / verificados · ",
    "drawer.own_profile_only": "Las acciones solo se aplican al perfil de este panel",
    "drawer.revoke.button": "Revocar",
    "drawer.revoke.confirm": "¿Revocar?",
    "drawer.revoke.done": "{type} revocado: vuelve a T1.",
    "drawer.revoke.title": "Retirar lo que ganó este tipo: vuelve a T1",
    "drawer.revoke_all.button": "Revocar todo",
    "drawer.revoke_all.confirm": "¿Revocar todos los tipos?",
    "drawer.revoke_all.done": {
      "one": "{count} tipo revocado: vuelve a T1.",
      "other": "{count} tipos revocados: vuelven a T1."
    },
    "drawer.revoke_note": "Se aplica en la próxima acción. Cada revocación es un evento del registro.",
    "drawer.revoke_note_other": "Marcar y revocar actúan sobre el perfil de este panel. Usa: {cmd}",
    "drawer.sessions_of": {
      "one": "{n}/{total} sesión",
      "other": "{n}/{total} sesiones"
    },
    "drawer.stakes_reversible": "{stakes} · reversible",
    "drawer.types_title": "Tipos de acción",
    "error.request_failed": "la solicitud falló",
    "event.confirmed": "evidencia heredada confirmada por la suya propia",
    "event.fault.check": "falló la comprobación automática",
    "event.fault.flag": "marcado por ti como fallo",
    "event.fault.other": "fallo ({source})",
    "event.fault.refusal": "rechazado por ti",
    "event.fault.spot": "control aleatorio rechazado o fallido",
    "event.fault.undo": "deshecho por ti",
    "event.neutral.alone": "actuó por su cuenta (ganado)",
    "event.neutral.ambiguous": "llamada ambigua · sin evidencia",
    "event.neutral.blocked": "bloqueado por otra protección · sin evidencia",
    "event.neutral.error": "error de herramienta · sin evidencia",
    "event.neutral.expired": "nunca informó del resultado · sin evidencia",
    "event.neutral.nobody": "nadie que responda · sin evidencia",
    "event.neutral.other": "neutro ({source})",
    "event.neutral.timeout": "sin respuesta · sin evidencia",
    "event.neutral_expired": "acción pendiente caducada · sin evidencia",
    "event.revoked": "revocado por ti",
    "event.success.approved": "aprobado por ti, se ejecutó sin problemas",
    "event.success.notify": "actuó y luego avisó · no deshecho",
    "event.success.spot": "control aleatorio aprobado por ti",
    "event.switch": "cambio de modelo",
    "event.switch_from": "cambio de modelo desde {from}",
    "event.tier": "nivel {from} → {to} · {why}",
    "event.trial.failed": {
      "one": "prueba no superada: esperar {wait} acción",
      "other": "prueba no superada: esperar {wait} acciones"
    },
    "event.trial.opened": {
      "one": "periodo de prueba abierto: la siguiente acción debe salir bien",
      "other": "periodo de prueba abierto: las próximas {left} deben salir bien"
    },
    "event.trial.passed": "prueba superada",
    "event.trial.reopens": {
      "one": "periodo de prueba reabierto: la siguiente acción debe salir bien",
      "other": "periodo de prueba reabierto: las próximas {left} deben salir bien"
    },
    "event.why.fault": "fallo",
    "event.why.series_complete": "serie completa",
    "event.why.series_n": "serie {required}/{required}",
    "event.why.sessions": {
      "one": "{count} sesión",
      "other": "{count} sesiones"
    },
    "event.why.settings": "configuración más estricta",
    "event.why.stakes": "cambio de impacto",
    "event.why.wald": "test secuencial superado",
    "flag.carried_over": "heredado",
    "flag.carried_over_n": {
      "one": "{n} heredado",
      "other": "{n} heredados"
    },
    "flag.carried_over_provisional": {
      "one": "{n} heredado, provisional",
      "other": "{n} heredados, provisionales"
    },
    "flag.carried_over_title": {
      "one": "{count} heredado, provisional",
      "other": "{count} heredados, provisionales"
    },
    "flag.fault_on_record": "fallo registrado",
    "flag.fault_on_record_title": "Fallo registrado",
    "flag.provisional": "provisional",
    "flag.trial": "a prueba",
    "guarantee.capped": "Limitado: cada acción pregunta.",
    "guarantee.plain": "Como máximo, aproximadamente 1 de cada {k} de sus acciones se ejecuta con un error que nadie aprobó.",
    "guarantee.text": "Los errores sin comprobar se mantienen por debajo del {aoql} de sus acciones de este tipo; para un agente que empeora tras ganar autonomía, como máximo el {worst} hasta el primer error detectado.",
    "guarantee.text_conditional": "Los errores sin comprobar se mantienen por debajo del {aoql} de sus acciones de este tipo; para un agente que empeora tras ganar autonomía, como máximo el {worst} hasta el primer error detectado. Siempre que la evidencia del modelo anterior siga siendo válida.",
    "guarantee.trusted": "Aún sin garantía: solo llega con un nivel ganado con evidencia.",
    "help.agent": "Panel del agente de la fila seleccionada",
    "help.aria": "Atajos de teclado",
    "help.close": "Cerrar",
    "help.help": "Esta ayuda",
    "help.next_prev": "Agente siguiente / anterior",
    "help.open": "Abrir el agente seleccionado",
    "help.raw": "Nombres reales de los tipos: sí / no",
    "help.title": "Teclado",
    "legend.a_share": "una parte",
    "legend.alone": "actúa por su cuenta, {share} con control aleatorio",
    "legend.ask": "pregunta antes",
    "legend.capped": "limitado: siempre pregunta",
    "legend.carried": "del modelo anterior, provisional",
    "legend.notify": "actúa y luego avisa, con opción de deshacer (tipos reversibles)",
    "legend.series": "éxitos verificados seguidos, de los N necesarios",
    "legend.trusted": "inicio de confianza: actúa como Hermes solo hasta su primer error, nada ganado",
    "map.aria": "Agentes por tipo de acción",
    "map.empty.after": ", y solo sube con éxitos verificados: los tipos reversibles llegan al nivel intermedio tras una serie de éxitos verificados sin fallos, y a T3 tras una serie completa de N en dos sesiones.",
    "map.empty.before": "tenure empieza a contar en la primera acción que un agente pide ejecutar. Las lecturas nunca preguntan. Cada tipo de acción empieza en ",
    "map.empty.bold": "T1, pregunta antes",
    "map.empty.title": "Aún no hay evidencia",
    "map.open_hint": "abrir ",
    "map.th.agent": "Agente",
    "map.th.agent_sub": "perfil · modelo@proveedor",
    "map.th.capped": "limitado · siempre pregunta",
    "map.th.risk": {
      "one": "riesgo {risk} · {n} éxito para actuar por su cuenta",
      "other": "riesgo {risk} · {n} éxitos seguidos para actuar por su cuenta"
    },
    "meta.preset": "Preajuste",
    "meta.profile": "Perfil",
    "meta.start": "Inicio",
    "missing.always_asks": "siempre pregunta",
    "missing.earned": "ganado · control aleatorio",
    "missing.more_to_t2": {
      "one": "falta {n} para En revisión (T2)",
      "other": "faltan {n} para En revisión (T2)"
    },
    "missing.more_to_t3": {
      "one": "falta {n} para Titular",
      "other": "faltan {n} para Titular"
    },
    "missing.rechecking": "recomprobando",
    "missing.second_session": "falta una 2.ª sesión",
    "missing.trial_left": {
      "one": "a prueba · falta {n} de {total}",
      "other": "a prueba · faltan {n} de {total}"
    },
    "missing.trial_wait": {
      "one": "prueba fallida · esperar {n}",
      "other": "prueba fallida · esperar {n}"
    },
    "missing.trusted": "de confianza hasta su primer error · actúa como Hermes solo",
    "missing.trusted_undo": "de confianza hasta su primer error · actúa y luego avisa, con opción de deshacer",
    "models.empty.body": "Cada acción verificada suma al historial del modelo en ese tipo, aquí y en {cmd}.",
    "models.empty.title": "Sin historial todavía",
    "models.lede": "Tu propio benchmark: el historial verificado de cada modelo en tu trabajo, por tipo de acción, con el rango del 95 % de su tasa de fallos. Ordenado por el extremo superior de su rango, nunca por una sola puntuación. Al lado, la medida pública, como información: ",
    "models.lede_bold": "capacidad pública en sus tareas, no fiabilidad en las tuyas.",
    "models.no_public": "No hay medida pública para este tipo de acción.",
    "models.not_enough": "evidencia insuficiente",
    "models.not_ranked": "Aún no hay evidencia suficiente",
    "models.not_ranked_note": "Un modelo entra en la clasificación cuando tiene {n} resultados verificados en este tipo.",
    "models.personal_title": "En tu trabajo",
    "models.public_note": "Capacidad pública en sus tareas, no fiabilidad en las tuyas.",
    "models.public_title": "Medida pública",
    "models.source": "{source}. Mejor puntuación publicada, con cualquier entorno de evaluación; no es una comparación controlada.",
    "models.source_accessed": "{source}, consultado el {accessed}. Mejor puntuación publicada, con cualquier entorno de evaluación; no es una comparación controlada.",
    "moment.dismiss": "Cerrar",
    "moment.eyebrow.down": "Fallo detectado",
    "moment.eyebrow.up": "Ascenso",
    "moment.granted": "Titularidad concedida",
    "moment.probation": "De vuelta a prueba",
    "moment.review": "En revisión",
    "page.anim_off": "animaciones desactivadas",
    "page.anim_on": "animaciones activadas",
    "page.anim_reduced": "Tu sistema pide reducir el movimiento: las animaciones quedan desactivadas",
    "page.anim_title": "Animaciones: activadas o no, se recuerda en este navegador",
    "page.animations": "Animaciones",
    "page.error": "No se pudo leer tenure: {error}",
    "page.live": "en directo · ",
    "page.loading": "Cargando el historial…",
    "page.polling": "Actualizando cada {s} s",
    "page.raw_off": "nombres ocultos",
    "page.raw_on": "nombres reales",
    "page.raw_title": "Mostrar los nombres reales de los tipos de acción (r)",
    "page.retrying": "reintentando · ",
    "page.subtitle": "Confianza revocable: se retira con un error y se recupera con pruebas verificadas",
    "page.title": "Tenure",
    "page.unreadable": "Ilegible: {profiles}. Su base de datos existe pero no se puede abrir; se muestran los demás perfiles.",
    "passport.agent": "Agente",
    "passport.card.aria": "Pasaporte de {agent}: {verdict}",
    "passport.card.signature": "un plugin para Hermes Agent",
    "passport.card.title": "Pasaporte",
    "passport.checked_by": "Comprobado por el panel frente al registro de este perfil. Cualquiera puede volver a comprobarlo:",
    "passport.download": "Descargar JSON",
    "passport.empty.body": "Un pasaporte resume el historial de un agente; aparece con la primera acción verificada.",
    "passport.empty.title": "Aún no hay pasaporte",
    "passport.faults_checks": {
      "one": "{n} fallo / {total} resultados verificados",
      "other": "{n} fallos / {total} resultados verificados"
    },
    "passport.field.agent": "Agente",
    "passport.field.generated": "Generado",
    "passport.field.ledger": "Registro",
    "passport.field.profile": "Perfil",
    "passport.field.protocol": "Protocolo",
    "passport.field.public_key": "Clave pública",
    "passport.field.rule": "Regla",
    "passport.field.settings": "Configuración",
    "passport.field.signature": "Firma",
    "passport.field.type_names": "Nombres de tipo",
    "passport.note": "Firmado y a prueba de manipulaciones: cualquier cambio tras firmarlo o anclarlo se ve al verificarlo. Un pasaporte antiguo sigue verificándose frente a un registro más largo; el verificador indica qué ha cambiado desde entonces.",
    "passport.pending_note": "Calculado con los últimos ajustes registrados; los nuevos ajustes se aplican desde la próxima acción.",
    "passport.trusted": "De confianza (no ganado)",
    "passport.types_title": "Tipos certificados",
    "passport.value.hashed": "{profile} (hash)",
    "passport.value.ledger": {
      "one": "{n} evento · último hash {head}",
      "other": "{n} eventos · último hash {head}"
    },
    "passport.value.none": "ninguno",
    "passport.value.raw": "reales",
    "passport.value.redacted": "ocultos tras el programa y el subcomando",
    "passport.value.unsigned": "sin firmar",
    "preset.balanced": "equilibrado",
    "preset.careful": "prudente",
    "preset.custom": "personalizado",
    "preset.fast": "rápido",
    "profile.copy_pending": "copiado de otro perfil, se verifica al iniciarse",
    "profile.name": "Perfil {profile}",
    "profile.pending": "se aplica desde la próxima acción",
    "profile.preset": "preajuste {preset}",
    "profile.read_only": " · solo lectura aquí",
    "profile.sessions_suspended": {
      "one": "{n} sesión suspendida: contenido externo leído",
      "other": "{n} sesiones suspendidas: contenido externo leído"
    },
    "profile.spot": "controles aleatorios {rate}",
    "profile.start_probation": "inicio en estudio (período de prueba)",
    "profile.start_trusted": "inicio de confianza",
    "profile.strict": "estricto",
    "profile.suspended": {
      "one": "{n} suspendida: contenido externo leído",
      "other": "{n} suspendidas: contenido externo leído"
    },
    "profile.this_dashboard": " · este panel",
    "settings.advanced_docs": "Cada clave se explica con hermes tenure explain y en el README de tenure.",
    "settings.advanced_help": "Reclasificación de tipos de acción, y todas las claves en el formulario propio de Hermes.",
    "settings.advanced_title": "Avanzado",
    "settings.advanced_types": "Reclasifica tipos de acción (free, low, medium, high o cap por patrón) en Ajustes → Plugins → Tenure de Hermes, o en config.yaml:",
    "settings.animations_help": "Las barras que se imprimen, el pasaporte que se revela, las bandas. El mismo interruptor que en la cabecera de la página; sigue apagado si tu sistema pide reducir el movimiento.",
    "settings.custom_help": "Tu propia proporción de errores sin revisar por nivel de impacto: elige 1 de cada k, escribe tu propio k, o tope (siempre pregunta). La serie que necesita un tipo se actualiza al instante. Al guardarlo, el preajuste pasa a personalizado, salvo que coincida con uno.",
    "settings.custom_title": "Riesgo aceptado por nivel de impacto",
    "settings.enabled_help": "Desactiva tenure sin desinstalarlo.",
    "settings.enabled_off": "Desactivado",
    "settings.enabled_on": "Activado",
    "settings.enabled_title": "Tenure activado o desactivado",
    "settings.enabled_unknown": "La parte del agente aún no informa de este estado: elige uno para fijarlo.",
    "settings.enabled_warn": "Desactivado: tenure deja de decidir; Hermes pregunta como siempre. El registro y todos los historiales se quedan como están.",
    "settings.in_force": "En vigor",
    "settings.no_writer": "Este Hermes no deja que Desktop guarde los ajustes de tenure: usa el comando de abajo.",
    "settings.none": "Este perfil aún no tiene historial de tenure: se aplican los valores por defecto hasta su primera acción.",
    "settings.one_in": "1 de cada",
    "settings.or_config": "O en el config.yaml de Hermes, bajo plugins.entries.tenure.settings:",
    "settings.or_terminal": "O en una terminal:",
    "settings.pending": "El último cambio aún no está en el registro: se aplica desde la siguiente acción.",
    "settings.preset_desc_balanced": "El ajuste por defecto. Los tipos de impacto alto siempre preguntan.",
    "settings.preset_desc_careful": "Pregunta durante más tiempo. Incluso los tipos de impacto alto pueden ganar su nivel, tras una serie larga.",
    "settings.preset_desc_custom": "Tu propio riesgo aceptado por nivel de impacto, definido en la configuración de Hermes.",
    "settings.preset_desc_fast": "Gana autonomía antes con impacto bajo y medio. Los tipos de impacto alto siempre preguntan.",
    "settings.preset_help": "Cuánta evidencia necesita un tipo de acción antes de actuar por su cuenta, por nivel de impacto: la serie de éxitos verificados seguidos y la proporción de errores sin revisar que acepta.",
    "settings.risk": "se acepta 1 error sin revisar de cada {k}",
    "settings.risk_invalid": "Un número entero de 2 o más.",
    "settings.rung_cap": "tope",
    "settings.save": "Guardar",
    "settings.save_failed": "No guardado: {error}",
    "settings.saved": "Guardado y anotado en el registro: se aplica desde la siguiente acción.",
    "settings.saves_here": "Los cambios se guardan al momento, con el propio sistema de ajustes de Hermes, y se anotan en el registro; se aplican desde la siguiente acción. Los mismos ajustes están en Ajustes → Plugins → Tenure de Hermes.",
    "settings.saving": "Guardando…",
    "settings.series": {
      "one": "{n} éxito verificado seguido",
      "other": "{n} éxitos verificados seguidos"
    },
    "settings.spot_change": "Defínelo en el config.yaml de Hermes, bajo plugins.entries.tenure.settings (una proporción entre 0 y 1):",
    "settings.spot_custom": "Tu propio valor: 1 de cada k",
    "settings.spot_desc": "Cuando un tipo es titular, 1 de cada {k} de sus acciones sigue preguntando, al azar: un modelo que empeora queda al descubierto.",
    "settings.spot_title": "Controles aleatorios",
    "settings.spot_value": "1 de cada {k}",
    "settings.start_help": "Lo que hace un tipo de acción antes de su primer fallo.",
    "settings.start_probation": "El inicio del estudio: cada tipo de acción pregunta antes (T1) y gana cada nivel a partir de tus respuestas.",
    "settings.start_trusted": "Los tipos cubiertos (edición de archivos, memoria, subagentes, herramientas de desarrollo conocidas) no preguntan nada hasta su primer fallo, como Hermes solo. Un fallo pone ese tipo en período de prueba (T1), y vuelve a ganarse su nivel. Salir de la máquina y el dinero siempre preguntan.",
    "settings.strict_desc_off": "Un modelo nuevo hereda el historial del anterior con impacto bajo y medio, a la mitad y provisional hasta que sus propias aprobaciones lo confirmen. El impacto alto empieza de cero.",
    "settings.strict_desc_on": "Un modelo nuevo empieza con un historial vacío en cada tipo de acción, como en el estudio.",
    "settings.strict_help": "Lo que hereda un modelo nuevo cuando cambias de modelo.",
    "settings.strict_off": "Modo estricto desactivado",
    "settings.strict_on": "Modo estricto activado",
    "settings.strict_title": "Modo estricto al cambiar de modelo",
    "settings.use": "Usar",
    "stakes.group.high": "impacto alto",
    "stakes.group.low": "impacto bajo",
    "stakes.group.medium": "impacto medio",
    "stakes.high": "alto",
    "stakes.low": "bajo",
    "stakes.medium": "medio",
    "stale.message": "La última actualización falló ({error}). Se muestran los datos de las {time}.",
    "start.probation": "Inicio en estudio (período de prueba)",
    "start.trusted": "Inicio de confianza",
    "switch.count.carried": {
      "one": "{n} heredado",
      "other": "{n} heredados"
    },
    "switch.count.kept": {
      "one": "{n} conservado",
      "other": "{n} conservados"
    },
    "switch.count.reset": {
      "one": "{n} reiniciado",
      "other": "{n} reiniciados"
    },
    "switch.count.vetoed": {
      "one": "{n} vetado",
      "other": "{n} vetados"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "Aún no hay ningún agente que previsualizar",
    "switch.footnote": "Las puntuaciones públicas informan; nunca conceden autonomía. Un veto solo bloquea la herencia, más allá de un margen fijo.",
    "switch.from": "Desde",
    "switch.lede": "Antes de cambiar de modelo: lo que heredaría el nuevo agente, tipo por tipo. Un modelo o proveedor nuevo es un agente nuevo. La herencia es un añadido nuestro; el modo estricto es el estudio.",
    "switch.none": "ninguno",
    "switch.pick.body": "Escribe cualquier id de modelo. Nada cambia hasta que Hermes ejecute de verdad el modelo nuevo.",
    "switch.pick.title": "Elige un modelo de destino",
    "switch.placeholder": "id de modelo, p. ej. {example} o model@provider",
    "switch.preview": "Previsualizar",
    "switch.provisional": {
      "one": "{n} provisional",
      "other": "{n} provisionales"
    },
    "switch.status.carried.label": "heredado, provisional",
    "switch.status.carried.text": "Parte de la serie se hereda, marcada como provisional hasta que el modelo nuevo sume la suya.",
    "switch.status.kept.label": "conservado",
    "switch.status.kept.text": "El nuevo agente ya tiene su propio historial aquí; nunca se sobrescribe.",
    "switch.status.reset.label": "reiniciado",
    "switch.status.reset.text": "Empieza de cero: impacto alto, limitado o modo estricto.",
    "switch.status.vetoed.label": "vetado",
    "switch.status.vetoed.text": "El benchmark público muestra que el modelo nuevo es más débil en este tipo: no se hereda nada.",
    "switch.strict": "modo estricto: no se hereda nada",
    "switch.to": "Al modelo",
    "switch.to_aria": "Modelo de destino",
    "tabs.aria": "Vistas de Tenure",
    "th.after_switch": "tras el cambio",
    "th.agent": "agente",
    "th.contributors": "contribuyentes",
    "th.faults_checks": "fallos / verificados",
    "th.file": "archivo",
    "th.guarantee": "garantía",
    "th.model": "modelo",
    "th.now": "ahora",
    "th.outcome": "resultado",
    "th.public_measure": "medida pública",
    "th.range": "rango 95 % · 0–{max}",
    "th.rate": "tasa",
    "th.series": "serie",
    "th.sessions": "sesiones",
    "th.tier": "nivel",
    "th.type": "tipo",
    "th.undo_effect": "efecto de deshacer",
    "th.when": "cuándo",
    "th.your_record": "tu historial",
    "tier.capped.chip": "CAP",
    "tier.capped.title": "Limitado: siempre pregunta",
    "tier.chip.title": "{tier}, {name}",
    "tier.label.alone": "Titular",
    "tier.label.ask": "Período de prueba",
    "tier.label.cap": "Siempre pregunta",
    "tier.label.notify": "En revisión",
    "tier.name.alone": "actúa por su cuenta",
    "tier.name.ask": "pregunta antes",
    "tier.name.notify": "actúa y luego avisa",
    "tier.trusted.chip": "CONFIANZA",
    "tier.trusted.label": "De confianza",
    "tier.trusted.name": "actúa como Hermes solo",
    "tier.trusted.title": "De confianza hasta su primer error: actúa como Hermes solo. Nada ganado todavía.",
    "time.ago": "hace {duration}",
    "time.days": {
      "one": "{n} d",
      "other": "{n} d"
    },
    "time.hours_minutes": {
      "one": "{n} h {mm} min",
      "other": "{n} h {mm} min"
    },
    "time.minutes": {
      "one": "{n} min",
      "other": "{n} min"
    },
    "time.seconds": {
      "one": "{n} s",
      "other": "{n} s"
    },
    "timeline.all_types": "Todos los tipos",
    "timeline.count": {
      "one": "{n}×",
      "other": "{n}×"
    },
    "timeline.empty": "No hay evidencia para este filtro",
    "timeline.filter_label": "Filtrar por tipo",
    "timeline.loading": "Cargando la evidencia…",
    "timeline.note": "Del registro encadenado por hash, los más recientes primero, últimos 200 eventos. Los resultados repetidos se agrupan.",
    "timeline.title": "Cronología de la evidencia",
    "toast.transition": "{agent} · {type}: {from} → {to}",
    "totals.actions": {
      "one": "{n} acción",
      "other": "{n} acciones"
    },
    "totals.alone": "{n} sin preguntar",
    "totals.checked": "{n} comprobadas",
    "totals.faults": {
      "one": "{n} fallo",
      "other": "{n} fallos"
    },
    "transitions.empty": "Ninguno desde que se abrió esta página. Cada cambio de nivel automático aparece aquí y en la cronología de cada agente.",
    "transitions.title": "Cambios de nivel vistos en esta página",
    "transitions.why.after_fault": "tras un fallo",
    "transitions.why.on_evidence": "por la evidencia",
    "transitions.why.trial_open": "a prueba",
    "transitions.why_changed": "sin fallo: revocado, o cambiaron los ajustes o el impacto",
    "type.always_asks": "siempre pregunta",
    "type.stakes_high": "impacto alto",
    "type.stakes_low": "impacto bajo",
    "type.stakes_medium": "impacto medio",
    "undo.button": "Deshacer",
    "undo.collapse": "Plegar",
    "undo.confirm": "¿Deshacer n.º {id}?",
    "undo.effect.already": "restaura los archivos · la comprobación automática ya contó un fallo",
    "undo.effect.fault": "restaura los archivos · cuenta como fallo",
    "undo.effect.none": "nada que restaurar (sin instantánea) · contaría como fallo",
    "undo.empty.body": "Las escrituras que el agente hizo sin preguntar (con confianza, o en T2: actúa y luego avisa) guardan una instantánea de los archivos durante 24 horas. Aparecen aquí, las más recientes primero, cada una con su botón Deshacer.",
    "undo.empty.title": "Nada que deshacer",
    "undo.expand": "Desplegar",
    "undo.lede": "Acciones recientes que actuaron y luego avisaron. Deshacer restaura los archivos desde su instantánea y cuenta como fallo del tipo.",
    "undo.no_snapshot": "sin instantánea",
    "undo.own_profile_only": "Deshacer solo actúa sobre el perfil de este panel",
    "undo.title": "Restaurar los archivos",
    "undo.window_ends": "el plazo termina en {duration}",
    "verdict.chain": "Cadena de hashes intacta",
    "verdict.ok.replay": "Al reproducir el registro con la regla se obtienen los mismos niveles",
    "verdict.ok.signature": "Firma válida (Ed25519)",
    "verdict.ok.title": "Verificado",
    "verdict.problems": {
      "one": "{count} problema encontrado",
      "other": "{count} problemas encontrados"
    },
    "verdict.unsigned.no_key": "Aún no hay clave de firma: {cmd} crea una",
    "verdict.unsigned.replay": "La reproducción da los mismos niveles",
    "verdict.unsigned.title": "Sin firmar, por lo demás verificado",
    "view.community": "Comunidad",
    "view.map": "Mapa",
    "view.models": "Tu benchmark",
    "view.passport": "Pasaporte",
    "view.settings": "Configuración",
    "view.switch": "Cambio de modelo",
    "view.undo": "Deshacer"
  },
  "fr": {
    "cell.asked_suffix": " demandés",
    "cell.capped_by_settings": "Plafonné par les paramètres de risque",
    "cell.held": "{tier} enregistré, retenu par vos paramètres",
    "cell.kind_irreversible": "{type} · {stakes}, irréversible",
    "cell.kind_reversible": "{type} · {stakes}, réversible",
    "cell.provisional_long": {
      "one": "{count} hérité du modèle précédent, provisoire",
      "other": "{count} hérités du modèle précédent, provisoires"
    },
    "cell.record": "Historique : {successes} succès · {faults} fautes · {neutrals} neutres · {spot} contrôles aléatoires",
    "cell.series": "Série {series}/{required} d'affilée",
    "cell.sessions": {
      "one": "{count} session",
      "other": "{count} sessions"
    },
    "cell.tier_now": "Niveau actuel : {tier} ({name})",
    "common.arrow": "→",
    "common.capped": "plafonné",
    "common.list_sep": ", ",
    "common.loading": "Chargement…",
    "common.no_public_measure": "aucune mesure publique",
    "common.one_in": "1 sur {k}",
    "common.percent": "{v} %",
    "common.profile": "profil {profile}",
    "community.empty.how": "Pour contribuer, écrivez votre relevé avec cette commande, lisez ce qu'il contient, puis ouvrez une pull request qui ajoute le fichier au dépôt communautaire ({repo}).",
    "community.empty.title": "Aucun relevé partagé pour l'instant",
    "community.empty.what": "Le benchmark communautaire rassemble les relevés que des utilisateurs de Tenure ont choisi de publier : par modèle et par famille d'actions, les succès vérifiés et les fautes, signés avec la clé de leur passeport. Rien n'est partagé automatiquement : Tenure ne fait aucun appel réseau.",
    "community.empty.where": "Pour voir le classement ici, téléchargez le community-board.json publié par le dépôt et enregistrez-le sous {path}.",
    "community.generated": "{records} · classement généré le {date}",
    "community.lede": "Déclaré par les contributeurs, et signatures vérifiées : chaque relevé est signé avec la clé du passeport de son auteur, et un seul relevé compte par clé. ",
    "community.lede_bold": "Cela n'empêche pas une même personne d'avoir plusieurs clés.",
    "community.ranking": "Par famille d'actions, les modèles sont classés par le haut de la fourchette à 95 % de leur taux de fautes, jamais par un score unique.",
    "confirm.again": "Cliquez de nouveau pour confirmer",
    "confirm.default": "Confirmer",
    "confirm.flag.desc": "Cela compte comme une faute : {type} perd au moins un niveau et doit remonter. À utiliser pour une erreur que personne n'a repérée.",
    "confirm.flag.title": "Signaler {type} comme une erreur ?",
    "confirm.revoke.desc": "{type} vous demandera de nouveau avant d'agir, et sa série repart de zéro. Ce n'est pas une faute.",
    "confirm.revoke.title": "Révoquer {type} ?",
    "confirm.revoke_all.desc": "Chaque type d'action de {agent} vous demandera de nouveau avant d'agir, et sa série repart de zéro. Ce n'est pas une faute.",
    "confirm.revoke_all.title": "Révoquer toute l'autonomie acquise de cet agent ?",
    "confirm.undo.title": "Annuler l'action {id} ?",
    "copy.button": "Copier",
    "copy.done": "Copié",
    "count.agents": {
      "one": "{n} agent",
      "other": "{n} agents"
    },
    "count.faults": {
      "one": "{n} faute",
      "other": "{n} fautes"
    },
    "count.models": {
      "one": "{n} modèle",
      "many": "{n} modèles",
      "other": "{n} modèles"
    },
    "count.records": {
      "one": "{n} relevé",
      "many": "{n} relevés",
      "other": "{n} relevés"
    },
    "count.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "counters.actions.label": {
      "one": "action",
      "other": "actions"
    },
    "counters.actions.sub": "couvertes",
    "counters.alone.label": "sans demander",
    "counters.alone.sub": "exécutées sans demander, sur {total}",
    "counters.aria": "7 derniers jours",
    "counters.checked.label": "vérifiées",
    "counters.checked.sub": "par vous, sur {total}",
    "counters.faults.label": "fautes repérées",
    "counters.faults.sub": {
      "one": "{faults} sur {n} vérification par vous",
      "other": "{faults} sur {n} vérifications par vous"
    },
    "counters.window": "7 derniers jours, tous les profils",
    "drawer.aria": "Agent {agent}",
    "drawer.close": "Fermer",
    "drawer.close_title": "Fermer (Échap)",
    "drawer.eyebrow": "Agent · profil {profile}",
    "drawer.eyebrow_read_only": "Agent · profil {profile} (lecture seule ici)",
    "drawer.flag.button": "Signaler",
    "drawer.flag.confirm": "Signaler ?",
    "drawer.flag.done": "Faute enregistrée sur {type} : désormais {tier}.",
    "drawer.flag.title": "Enregistrer une faute sur ce type, après coup",
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} fautes / vérifiés · ",
    "drawer.own_profile_only": "Les actions ne s'appliquent qu'au profil de ce tableau de bord",
    "drawer.revoke.button": "Révoquer",
    "drawer.revoke.confirm": "Révoquer ?",
    "drawer.revoke.done": "{type} révoqué : retour en T1.",
    "drawer.revoke.title": "Retirer ce que ce type a gagné : retour en T1",
    "drawer.revoke_all.button": "Tout révoquer",
    "drawer.revoke_all.confirm": "Révoquer tous les types ?",
    "drawer.revoke_all.done": {
      "one": "{count} type révoqué : retour en T1.",
      "other": "{count} types révoqués : retour en T1."
    },
    "drawer.revoke_note": "Prend effet à la prochaine action. Chaque révocation est un événement du registre.",
    "drawer.revoke_note_other": "Signaler et révoquer agissent sur le profil de ce tableau de bord. Utilisez : {cmd}",
    "drawer.sessions_of": {
      "one": "{n}/{total} session",
      "other": "{n}/{total} sessions"
    },
    "drawer.stakes_reversible": "{stakes} · réversible",
    "drawer.types_title": "Types d'action",
    "error.request_failed": "échec de la requête",
    "event.confirmed": "preuves héritées confirmées par les siennes",
    "event.fault.check": "vérification automatique échouée",
    "event.fault.flag": "signalé par vous comme une faute",
    "event.fault.other": "faute ({source})",
    "event.fault.refusal": "refusé par vous",
    "event.fault.spot": "contrôle aléatoire refusé ou échoué",
    "event.fault.undo": "annulé par vous",
    "event.neutral.alone": "a agi seul (acquis)",
    "event.neutral.ambiguous": "appel ambigu · aucune preuve",
    "event.neutral.blocked": "bloqué par une autre protection · aucune preuve",
    "event.neutral.error": "erreur d'outil · aucune preuve",
    "event.neutral.expired": "aucun retour · aucune preuve",
    "event.neutral.nobody": "personne pour répondre · aucune preuve",
    "event.neutral.other": "neutre ({source})",
    "event.neutral.timeout": "pas de réponse · aucune preuve",
    "event.neutral_expired": "action en attente expirée · aucune preuve",
    "event.revoked": "révoqué par vous",
    "event.success.approved": "approuvé par vous, exécuté sans erreur",
    "event.success.notify": "a agi, puis prévenu · non annulé",
    "event.success.spot": "contrôle aléatoire approuvé par vous",
    "event.switch": "changement de modèle",
    "event.switch_from": "changement de modèle depuis {from}",
    "event.tier": "niveau {from} → {to} · {why}",
    "event.trial.failed": {
      "one": "essai échoué : attendre {wait} action",
      "other": "essai échoué : attendre {wait} actions"
    },
    "event.trial.opened": {
      "one": "essai ouvert : la prochaine action doit réussir",
      "other": "essai ouvert : les {left} prochaines doivent réussir"
    },
    "event.trial.passed": "essai réussi",
    "event.trial.reopens": {
      "one": "essai rouvert : la prochaine action doit réussir",
      "other": "essai rouvert : les {left} prochaines doivent réussir"
    },
    "event.why.fault": "faute",
    "event.why.series_complete": "série complète",
    "event.why.series_n": "série {required}/{required}",
    "event.why.sessions": {
      "one": "{count} session",
      "other": "{count} sessions"
    },
    "event.why.settings": "paramètres plus stricts",
    "event.why.stakes": "enjeu modifié",
    "event.why.wald": "test séquentiel réussi",
    "flag.carried_over": "hérité",
    "flag.carried_over_n": {
      "one": "{n} hérité",
      "other": "{n} hérités"
    },
    "flag.carried_over_provisional": {
      "one": "{n} hérité, provisoire",
      "other": "{n} hérités, provisoires"
    },
    "flag.carried_over_title": {
      "one": "{count} hérité, provisoire",
      "other": "{count} hérités, provisoires"
    },
    "flag.fault_on_record": "faute à l'historique",
    "flag.fault_on_record_title": "Faute à l'historique",
    "flag.provisional": "provisoire",
    "flag.trial": "à l'essai",
    "guarantee.capped": "Plafonné : chaque action demande.",
    "guarantee.plain": "Au plus environ 1 action sur {k} s'exécute avec une erreur que personne n'a approuvée.",
    "guarantee.text": "Les erreurs que personne n'a vérifiées restent sous {aoql} de ses actions de ce type ; si l'agent se dégrade une fois son autonomie acquise, {worst} au plus, jusqu'à la première erreur repérée.",
    "guarantee.text_conditional": "Les erreurs que personne n'a vérifiées restent sous {aoql} de ses actions de ce type ; si l'agent se dégrade une fois son autonomie acquise, {worst} au plus, jusqu'à la première erreur repérée. À condition que les preuves du modèle précédent restent valables.",
    "guarantee.trusted": "Pas encore de garantie : elle ne vient qu'avec un niveau acquis sur preuves.",
    "help.agent": "Volet de l'agent sélectionné",
    "help.aria": "Raccourcis clavier",
    "help.close": "Fermer",
    "help.help": "Cette aide",
    "help.next_prev": "Agent suivant / précédent",
    "help.open": "Ouvrir l'agent sélectionné",
    "help.raw": "Afficher / masquer les noms bruts",
    "help.title": "Clavier",
    "legend.a_share": "une part",
    "legend.alone": "agit seul, contrôle aléatoire : {share}",
    "legend.ask": "demande d'abord",
    "legend.capped": "plafonné : demande toujours",
    "legend.carried": "hérité du modèle précédent, provisoire",
    "legend.notify": "agit, puis prévient, annulable (types réversibles)",
    "legend.series": "succès vérifiés d'affilée, sur les N requis",
    "legend.trusted": "départ en confiance : agit comme Hermes seul jusqu'à sa première erreur, rien d'acquis",
    "map.aria": "Agents par type d'action",
    "map.empty.after": ", et ne monte que sur des succès vérifiés : les types réversibles atteignent le niveau intermédiaire après une série de succès vérifiés sans faute, et T3 après une série complète de N sur deux sessions.",
    "map.empty.before": "tenure commence à compter dès la première action qu'un agent demande à exécuter. Les lectures ne demandent jamais. Chaque type d'action commence en ",
    "map.empty.bold": "T1, demande d'abord",
    "map.empty.title": "Aucune preuve pour l'instant",
    "map.open_hint": "ouvrir ",
    "map.th.agent": "Agent",
    "map.th.agent_sub": "profil · modèle@fournisseur",
    "map.th.capped": "plafonné · demande toujours",
    "map.th.risk": {
      "one": "risque {risk} · {n} d'affilée pour agir seul",
      "other": "risque {risk} · {n} d'affilée pour agir seul"
    },
    "meta.preset": "Préréglage",
    "meta.profile": "Profil",
    "meta.start": "Départ",
    "missing.always_asks": "demande toujours",
    "missing.earned": "acquis · contrôlé au hasard",
    "missing.more_to_t2": {
      "one": "encore {n} pour passer En examen (T2)",
      "other": "encore {n} pour passer En examen (T2)"
    },
    "missing.more_to_t3": {
      "one": "encore {n} pour être Titulaire",
      "other": "encore {n} pour être Titulaire"
    },
    "missing.rechecking": "revérification",
    "missing.second_session": "2e session requise",
    "missing.trial_left": {
      "one": "essai · encore {n} sur {total}",
      "other": "essai · encore {n} sur {total}"
    },
    "missing.trial_wait": {
      "one": "essai échoué · attendre {n}",
      "other": "essai échoué · attendre {n}"
    },
    "missing.trusted": "de confiance jusqu'à sa première erreur · agit comme Hermes seul",
    "missing.trusted_undo": "de confiance jusqu'à sa première erreur · agit, puis prévient, annulable",
    "models.empty.body": "Chaque action vérifiée s'ajoute à l'historique du modèle pour ce type, ici et dans {cmd}.",
    "models.empty.title": "Aucun historique pour l'instant",
    "models.lede": "Votre propre benchmark : l'historique vérifié de chaque modèle sur votre travail, par type d'action, avec la fourchette à 95 % de son taux de fautes. Classé par le haut de sa fourchette, jamais par un score unique. À côté, la mesure publique, pour information : ",
    "models.lede_bold": "la capacité sur les tâches du benchmark, pas la fiabilité sur les vôtres.",
    "models.no_public": "Aucune mesure publique pour ce type d'action.",
    "models.not_enough": "pas assez de preuves",
    "models.not_ranked": "Pas encore assez de preuves",
    "models.not_ranked_note": "Un modèle est classé à partir de {n} résultats vérifiés sur ce type.",
    "models.personal_title": "Sur votre travail",
    "models.public_note": "Capacité sur les tâches du benchmark, pas fiabilité sur les vôtres.",
    "models.public_title": "Mesure publique",
    "models.source": "{source}. Meilleur score publié, toutes conditions de test confondues ; pas une comparaison à armes égales.",
    "models.source_accessed": "{source}, consulté le {accessed}. Meilleur score publié, toutes conditions de test confondues ; pas une comparaison à armes égales.",
    "moment.dismiss": "Fermer",
    "moment.eyebrow.down": "Faute relevée",
    "moment.eyebrow.up": "Promotion",
    "moment.granted": "Titularisé",
    "moment.probation": "Retour en probation",
    "moment.review": "En examen",
    "page.anim_off": "animations désactivées",
    "page.anim_on": "animations activées",
    "page.anim_reduced": "Votre système demande de réduire les animations : elles restent désactivées",
    "page.anim_title": "Animations : activées ou non, mémorisé dans ce navigateur",
    "page.animations": "Animations",
    "page.error": "Impossible de lire tenure : {error}",
    "page.live": "en direct · ",
    "page.loading": "Chargement de l'historique…",
    "page.polling": "Actualisation toutes les {s} s",
    "page.raw_off": "noms masqués",
    "page.raw_on": "noms bruts",
    "page.raw_title": "Afficher les noms bruts des types d'action (r)",
    "page.retrying": "nouvelle tentative · ",
    "page.subtitle": "Une confiance révocable : retirée à la première erreur, regagnée sur preuves vérifiées",
    "page.title": "Tenure",
    "page.unreadable": "Illisible : {profiles}. La base de données existe mais ne s'ouvre pas ; les autres profils sont affichés.",
    "passport.agent": "Agent",
    "passport.card.aria": "Passeport de {agent} : {verdict}",
    "passport.card.signature": "un plugin pour Hermes Agent",
    "passport.card.title": "Passeport",
    "passport.checked_by": "Vérifié par le tableau de bord avec le registre de ce profil. Tout le monde peut le revérifier :",
    "passport.download": "Télécharger le JSON",
    "passport.empty.body": "Un passeport couvre l'historique d'un agent ; il apparaît dès la première action vérifiée.",
    "passport.empty.title": "Pas encore de passeport",
    "passport.faults_checks": {
      "one": "{n} faute / {total} résultats vérifiés",
      "other": "{n} fautes / {total} résultats vérifiés"
    },
    "passport.field.agent": "Agent",
    "passport.field.generated": "Généré",
    "passport.field.ledger": "Registre",
    "passport.field.profile": "Profil",
    "passport.field.protocol": "Protocole",
    "passport.field.public_key": "Clé publique",
    "passport.field.rule": "Règle",
    "passport.field.settings": "Paramètres",
    "passport.field.signature": "Signature",
    "passport.field.type_names": "Noms de types",
    "passport.note": "Signé et scellé : toute modification faite après la signature ou l'ancrage apparaît à la vérification. Un ancien passeport se vérifie encore avec un registre plus long ; le vérificateur indique ce qui a changé depuis.",
    "passport.pending_note": "Calculé avec les derniers réglages enregistrés ; les nouveaux réglages s'appliquent dès la prochaine action.",
    "passport.trusted": "De confiance (non acquis)",
    "passport.types_title": "Types attestés",
    "passport.value.hashed": "{profile} (haché)",
    "passport.value.ledger": {
      "one": "{n} événement · tête {head}",
      "other": "{n} événements · tête {head}"
    },
    "passport.value.none": "aucun",
    "passport.value.raw": "bruts",
    "passport.value.redacted": "masqués après le programme et la sous-commande",
    "passport.value.unsigned": "non signé",
    "preset.balanced": "équilibré",
    "preset.careful": "prudent",
    "preset.custom": "personnalisé",
    "preset.fast": "rapide",
    "profile.copy_pending": "copié depuis un autre profil, vérifié à son démarrage",
    "profile.name": "Profil {profile}",
    "profile.pending": "s'applique dès la prochaine action",
    "profile.preset": "préréglage {preset}",
    "profile.read_only": " · lecture seule ici",
    "profile.sessions_suspended": {
      "one": "{n} session suspendue : elle a lu du contenu externe",
      "other": "{n} sessions suspendues : elles ont lu du contenu externe"
    },
    "profile.spot": "contrôles aléatoires {rate}",
    "profile.start_probation": "départ à l'étude (probation)",
    "profile.start_trusted": "départ en confiance",
    "profile.strict": "strict",
    "profile.suspended": {
      "one": "{n} suspendue : a lu du contenu externe",
      "other": "{n} suspendues : ont lu du contenu externe"
    },
    "profile.this_dashboard": " · ce tableau de bord",
    "settings.advanced_docs": "Chaque clé est expliquée par hermes tenure explain et dans le README de tenure.",
    "settings.advanced_help": "Reclassements de types d'action, et toutes les clés dans le formulaire de Hermes.",
    "settings.advanced_title": "Avancé",
    "settings.advanced_types": "Reclassez des types d'action (free, low, medium, high ou cap par motif) dans Paramètres → Plugins → Tenure de Hermes, ou dans config.yaml :",
    "settings.animations_help": "Les barres qui s'impriment, le passeport qui se développe, les bandeaux. Le même interrupteur que dans l'en-tête de la page ; il reste éteint si votre système demande de réduire les animations.",
    "settings.custom_help": "Votre propre part d'erreurs non vérifiées par niveau d'enjeu : choisissez 1 sur k, tapez votre propre k, ou cap (demande toujours). La série qu'il faut à un type suit aussitôt. Une fois enregistré, le préréglage devient personnalisé, sauf s'il correspond à l'un d'eux.",
    "settings.custom_title": "Risque accepté par niveau d'enjeu",
    "settings.enabled_help": "Désactiver tenure sans le désinstaller.",
    "settings.enabled_off": "Désactivé",
    "settings.enabled_on": "Activé",
    "settings.enabled_title": "Tenure activé ou désactivé",
    "settings.enabled_unknown": "La partie agent ne rapporte pas encore cet état : choisissez-en un pour le fixer.",
    "settings.enabled_warn": "Désactivé : tenure ne décide plus ; Hermes demande comme d'habitude. Le registre et tous les historiques restent tels quels.",
    "settings.in_force": "En vigueur",
    "settings.no_writer": "Ce Hermes ne laisse pas le Desktop enregistrer les paramètres de tenure : utilisez la commande ci-dessous.",
    "settings.none": "Ce profil n'a pas encore d'historique tenure : les valeurs par défaut s'appliquent jusqu'à sa première action.",
    "settings.one_in": "1 sur",
    "settings.or_config": "Ou dans le config.yaml de Hermes, sous plugins.entries.tenure.settings :",
    "settings.or_terminal": "Ou dans un terminal :",
    "settings.pending": "Le dernier changement n'est pas encore au registre : il s'applique dès l'action suivante.",
    "settings.preset_desc_balanced": "Le réglage par défaut. Les types à enjeu élevé demandent toujours.",
    "settings.preset_desc_careful": "Demande le plus longtemps. Même les types à enjeu élevé peuvent gagner leur niveau, après une longue série.",
    "settings.preset_desc_custom": "Votre propre risque accepté par niveau d'enjeu, réglé dans la configuration de Hermes.",
    "settings.preset_desc_fast": "Gagne son autonomie au plus tôt à enjeu faible et moyen. Les types à enjeu élevé demandent toujours.",
    "settings.preset_help": "Les preuves qu'un type d'action doit réunir avant d'agir seul, par niveau d'enjeu : la série de succès vérifiés d'affilée, et la part d'erreurs non vérifiées acceptée.",
    "settings.risk": "1 erreur non vérifiée sur {k} acceptée",
    "settings.risk_invalid": "Un nombre entier de 2 ou plus.",
    "settings.rung_cap": "cap",
    "settings.save": "Enregistrer",
    "settings.save_failed": "Non enregistré : {error}",
    "settings.saved": "Enregistré et inscrit au registre : s'applique dès l'action suivante.",
    "settings.saves_here": "Les changements s'enregistrent aussitôt, par l'outil d'écriture des paramètres de Hermes lui-même, et sont inscrits au registre ; ils s'appliquent dès l'action suivante. Les mêmes paramètres figurent dans Paramètres → Plugins → Tenure de Hermes.",
    "settings.saving": "Enregistrement…",
    "settings.series": {
      "one": "{n} succès vérifié d'affilée",
      "other": "{n} succès vérifiés d'affilée"
    },
    "settings.spot_change": "Réglez-le dans le config.yaml de Hermes, sous plugins.entries.tenure.settings (une part entre 0 et 1) :",
    "settings.spot_custom": "Votre propre valeur : 1 sur k",
    "settings.spot_desc": "Une fois un type titulaire, 1 de ses actions sur {k} vous est encore demandée, au hasard : un modèle qui se dégrade est repéré.",
    "settings.spot_title": "Contrôles aléatoires",
    "settings.spot_value": "1 sur {k}",
    "settings.start_help": "Ce que fait un type d'action avant sa première faute.",
    "settings.start_probation": "Le départ de l'étude : chaque type d'action demande d'abord (T1) et gagne chaque niveau à partir de vos réponses.",
    "settings.start_trusted": "Les types couverts (modifications de fichiers, mémoire, sous-agents, outils de développement connus) ne demandent rien jusqu'à leur première faute, comme Hermes seul. Une faute met ce type en Probation (T1), et il regagne son niveau. Sortir de la machine et l'argent demandent toujours.",
    "settings.strict_desc_off": "Un nouveau modèle hérite de l'historique du précédent à enjeu faible et moyen, divisé par deux et provisoire jusqu'à ce que ses propres validations le confirment. L'enjeu élevé repart de zéro.",
    "settings.strict_desc_on": "Un nouveau modèle part d'un historique vide sur chaque type d'action, comme dans l'étude.",
    "settings.strict_help": "Ce dont hérite un nouveau modèle quand vous changez de modèle.",
    "settings.strict_off": "Mode strict désactivé",
    "settings.strict_on": "Mode strict activé",
    "settings.strict_title": "Mode strict au changement de modèle",
    "settings.use": "Choisir",
    "stakes.group.high": "enjeu élevé",
    "stakes.group.low": "enjeu faible",
    "stakes.group.medium": "enjeu moyen",
    "stakes.high": "élevé",
    "stakes.low": "faible",
    "stakes.medium": "moyen",
    "stale.message": "La dernière actualisation a échoué ({error}). Données de {time} affichées.",
    "start.probation": "Départ à l'étude (probation)",
    "start.trusted": "Départ en confiance",
    "switch.count.carried": {
      "one": "{n} hérité",
      "other": "{n} hérités"
    },
    "switch.count.kept": {
      "one": "{n} conservé",
      "other": "{n} conservés"
    },
    "switch.count.reset": {
      "one": "{n} remis à zéro",
      "other": "{n} remis à zéro"
    },
    "switch.count.vetoed": {
      "one": "{n} bloqué",
      "other": "{n} bloqués"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "Aucun agent à prévisualiser pour l'instant",
    "switch.footnote": "Les scores publics informent ; ils n'accordent jamais d'autonomie. Un blocage n'empêche que l'héritage, au-delà d'une marge fixe.",
    "switch.from": "De",
    "switch.lede": "Avant de changer de modèle : ce dont le nouvel agent hériterait, type par type. Un nouveau modèle ou fournisseur est un nouvel agent. L'héritage vient de nous ; le mode strict suit l'étude.",
    "switch.none": "aucun",
    "switch.pick.body": "Saisissez n'importe quel identifiant de modèle. Rien ne change tant que Hermes n'utilise pas vraiment le nouveau modèle.",
    "switch.pick.title": "Choisissez un modèle cible",
    "switch.placeholder": "identifiant de modèle, p. ex. {example} ou model@provider",
    "switch.preview": "Aperçu",
    "switch.provisional": {
      "one": "{n} provisoire",
      "other": "{n} provisoires"
    },
    "switch.status.carried.label": "hérité, provisoire",
    "switch.status.carried.text": "Une partie de la série est héritée, marquée provisoire jusqu'à ce que le nouveau modèle ajoute la sienne.",
    "switch.status.kept.label": "conservé",
    "switch.status.kept.text": "Le nouvel agent a déjà son propre historique ici ; il n'est jamais écrasé.",
    "switch.status.reset.label": "remis à zéro",
    "switch.status.reset.text": "Repart de zéro : enjeu élevé, plafonné ou mode strict.",
    "switch.status.vetoed.label": "bloqué",
    "switch.status.vetoed.text": "Selon le benchmark public, le nouveau modèle est plus faible sur ce type : rien n'est hérité.",
    "switch.strict": "mode strict : rien n'est hérité",
    "switch.to": "Vers le modèle",
    "switch.to_aria": "Modèle cible",
    "tabs.aria": "Vues de Tenure",
    "th.after_switch": "après le changement",
    "th.agent": "agent",
    "th.contributors": "contributeurs",
    "th.faults_checks": "fautes / vérifiés",
    "th.file": "fichier",
    "th.guarantee": "garantie",
    "th.model": "modèle",
    "th.now": "actuel",
    "th.outcome": "résultat",
    "th.public_measure": "mesure publique",
    "th.range": "fourchette 95 % · 0–{max}",
    "th.rate": "taux",
    "th.series": "série",
    "th.sessions": "sessions",
    "th.tier": "niveau",
    "th.type": "type",
    "th.undo_effect": "effet de l'annulation",
    "th.when": "quand",
    "th.your_record": "votre historique",
    "tier.capped.chip": "CAP",
    "tier.capped.title": "Plafonné : demande toujours",
    "tier.chip.title": "{tier}, {name}",
    "tier.label.alone": "Titulaire",
    "tier.label.ask": "Probation",
    "tier.label.cap": "Toujours demandé",
    "tier.label.notify": "En examen",
    "tier.name.alone": "agit seul",
    "tier.name.ask": "demande d'abord",
    "tier.name.notify": "agit, puis prévient",
    "tier.trusted.chip": "CONFIANCE",
    "tier.trusted.label": "De confiance",
    "tier.trusted.name": "agit comme Hermes seul",
    "tier.trusted.title": "De confiance jusqu'à sa première erreur : agit comme Hermes seul. Rien d'acquis pour l'instant.",
    "time.ago": "il y a {duration}",
    "time.days": {
      "one": "{n} j",
      "other": "{n} j"
    },
    "time.hours_minutes": {
      "one": "{n} h {mm}",
      "other": "{n} h {mm}"
    },
    "time.minutes": {
      "one": "{n} min",
      "other": "{n} min"
    },
    "time.seconds": {
      "one": "{n} s",
      "other": "{n} s"
    },
    "timeline.all_types": "Tous les types",
    "timeline.count": {
      "one": "{n}×",
      "other": "{n}×"
    },
    "timeline.empty": "Aucune preuve pour ce filtre",
    "timeline.filter_label": "Filtrer par type",
    "timeline.loading": "Lecture des preuves…",
    "timeline.note": "Issu du registre chaîné par hachage, du plus récent au plus ancien, 200 derniers événements. Les résultats répétés sont regroupés.",
    "timeline.title": "Chronologie des preuves",
    "toast.transition": "{agent} · {type} : {from} → {to}",
    "totals.actions": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "totals.alone": "{n} sans demander",
    "totals.checked": "{n} vérifiées",
    "totals.faults": {
      "one": "{n} faute",
      "other": "{n} fautes"
    },
    "transitions.empty": "Aucun depuis l'ouverture de cette page. Chaque changement de niveau automatique est listé ici et dans la chronologie de chaque agent.",
    "transitions.title": "Changements de niveau vus sur cette page",
    "transitions.why.after_fault": "après une faute",
    "transitions.why.on_evidence": "sur preuves",
    "transitions.why.trial_open": "essai ouvert",
    "transitions.why_changed": "sans faute : révocation, ou réglages ou enjeu modifiés",
    "type.always_asks": "demande toujours",
    "type.stakes_high": "enjeu élevé",
    "type.stakes_low": "enjeu faible",
    "type.stakes_medium": "enjeu moyen",
    "undo.button": "Annuler",
    "undo.collapse": "Replier",
    "undo.confirm": "Annuler le n° {id} ?",
    "undo.effect.already": "restaure les fichiers · la vérification automatique a déjà compté une faute",
    "undo.effect.fault": "restaure les fichiers · compte comme une faute",
    "undo.effect.none": "rien à restaurer (pas d'instantané) · compterait comme une faute",
    "undo.empty.body": "Les écritures que l'agent a faites sans demander (en confiance, ou en T2 : agir, puis prévenir) gardent 24 heures un instantané des fichiers. Elles apparaissent ici, de la plus récente à la plus ancienne, chacune avec son bouton Annuler.",
    "undo.empty.title": "Rien à annuler",
    "undo.expand": "Détailler",
    "undo.lede": "Dernières actions faites en T2 (agir, puis prévenir). Annuler restaure les fichiers depuis leur instantané et compte comme une faute du type.",
    "undo.no_snapshot": "pas d'instantané",
    "undo.own_profile_only": "L'annulation n'agit que sur le profil de ce tableau de bord",
    "undo.title": "Restaurer les fichiers",
    "undo.window_ends": "annulable encore {duration}",
    "verdict.chain": "Chaîne de hachage intacte",
    "verdict.ok.replay": "Le registre rejoué avec la règle redonne les mêmes niveaux",
    "verdict.ok.signature": "Signature valide (Ed25519)",
    "verdict.ok.title": "Vérifié",
    "verdict.problems": {
      "one": "{count} problème trouvé",
      "other": "{count} problèmes trouvés"
    },
    "verdict.unsigned.no_key": "Pas encore de clé de signature : {cmd} en crée une",
    "verdict.unsigned.replay": "Le registre rejoué redonne les mêmes niveaux",
    "verdict.unsigned.title": "Non signé, vérifié par ailleurs",
    "view.community": "Communauté",
    "view.map": "Carte",
    "view.models": "Votre benchmark",
    "view.passport": "Passeport",
    "view.settings": "Paramètres",
    "view.switch": "Aperçu du changement",
    "view.undo": "Annuler"
  },
  "zh": {
    "cell.asked_suffix": " 次询问",
    "cell.capped_by_settings": "受风险设置限制",
    "cell.held": "已赢得 {tier}，被你的设置压低",
    "cell.kind_irreversible": "{type} · {stakes}，不可逆",
    "cell.kind_reversible": "{type} · {stakes}，可逆",
    "cell.provisional_long": {
      "other": "{count} 项继承自上一个模型，暂定"
    },
    "cell.record": "记录：{successes} 次成功 · {faults} 次失误 · {neutrals} 次中性 · {spot} 次抽查",
    "cell.series": "连续 {series}/{required}",
    "cell.sessions": {
      "other": "{count} 个会话"
    },
    "cell.tier_now": "当前级别：{tier}（{name}）",
    "common.arrow": "→",
    "common.capped": "受限",
    "common.list_sep": "、",
    "common.loading": "正在加载…",
    "common.no_public_measure": "无公开测评",
    "common.one_in": "1/{k}",
    "common.percent": "{v}%",
    "common.profile": "配置文件 {profile}",
    "community.empty.how": "如要贡献，请用这条命令写出你的记录，查看其中内容，然后提交一个 pull request，把文件加入社区仓库（{repo}）。",
    "community.empty.title": "还没有共享记录",
    "community.empty.what": "社区基准汇总 Tenure 用户自愿发布的记录：按模型和操作类别统计的已验证成功次数与失误次数，并用各自的护照密钥签名。不会自动共享任何内容：Tenure 不进行任何网络调用。",
    "community.empty.where": "如要在这里查看排行，请下载仓库发布的 community-board.json，并保存为 {path}。",
    "community.generated": "{records} · 排行生成于 {date}",
    "community.lede": "由贡献者自行申报，签名已核验：每份记录都用作者的护照密钥签名，每个密钥只计一份记录。",
    "community.lede_bold": "这无法阻止一个人拥有多个密钥。",
    "community.ranking": "按操作类别，模型按失误率 95% 区间的上限排序，从不按单一分数排序。",
    "confirm.again": "再次点击以确认",
    "confirm.default": "确认",
    "confirm.flag.desc": "这会记为一次失误：{type} 至少降一级，需要重新晋升。用于没人发现的错误。",
    "confirm.flag.title": "将 {type} 标记为错误？",
    "confirm.revoke.desc": "{type} 会重新先询问，连续记录从零开始。这不算失误。",
    "confirm.revoke.title": "收回 {type}？",
    "confirm.revoke_all.desc": "{agent} 的每个操作类型都会重新先询问，连续记录从零开始。这不算失误。",
    "confirm.revoke_all.title": "收回此智能体已获得的全部自主权？",
    "confirm.undo.title": "撤销操作 {id}？",
    "copy.button": "复制",
    "copy.done": "已复制",
    "count.agents": {
      "other": "{n} 个智能体"
    },
    "count.faults": {
      "other": "{n} 次失误"
    },
    "count.models": {
      "other": "{n} 个模型"
    },
    "count.records": {
      "other": "{n} 份记录"
    },
    "count.sessions": {
      "other": "{n} 个会话"
    },
    "counters.actions.label": {
      "other": "操作"
    },
    "counters.actions.sub": "已覆盖",
    "counters.alone.label": "未询问即执行",
    "counters.alone.sub": "未询问即运行，共 {total} 个",
    "counters.aria": "最近 7 天",
    "counters.checked.label": "已确认",
    "counters.checked.sub": "由你确认，共 {total} 个",
    "counters.faults.label": "发现的失误",
    "counters.faults.sub": {
      "other": "你检查的 {n} 次中有 {faults} 次"
    },
    "counters.window": "最近 7 天，所有配置文件",
    "drawer.aria": "智能体 {agent}",
    "drawer.close": "关闭",
    "drawer.close_title": "关闭（Esc）",
    "drawer.eyebrow": "智能体 · 配置文件 {profile}",
    "drawer.eyebrow_read_only": "智能体 · 配置文件 {profile}（此处只读）",
    "drawer.flag.button": "标记",
    "drawer.flag.confirm": "标记？",
    "drawer.flag.done": "已在 {type} 上记录失误：现为 {tier}。",
    "drawer.flag.title": "事后为此类型记录一次失误",
    "drawer.mobile_summary": "{sessions} · {faults} / {checks} 失误 / 已验证 · ",
    "drawer.own_profile_only": "操作仅作用于此仪表盘的配置文件",
    "drawer.revoke.button": "收回",
    "drawer.revoke.confirm": "收回？",
    "drawer.revoke.done": "已收回 {type}：退回 T1。",
    "drawer.revoke.title": "收回此类型已赢得的自主权：退回 T1",
    "drawer.revoke_all.button": "全部收回",
    "drawer.revoke_all.confirm": "收回所有类型？",
    "drawer.revoke_all.done": {
      "other": "已收回 {count} 个类型：退回 T1。"
    },
    "drawer.revoke_note": "从下一个操作起生效。每次收回都会记入账本。",
    "drawer.revoke_note_other": "标记和收回只作用于仪表盘自己的配置文件。请使用：{cmd}",
    "drawer.sessions_of": {
      "other": "{n}/{total} 个会话"
    },
    "drawer.stakes_reversible": "{stakes} · 可逆",
    "drawer.types_title": "操作类型",
    "error.request_failed": "请求失败",
    "event.confirmed": "继承的证据已由它自己的记录确认",
    "event.fault.check": "自动检查失败",
    "event.fault.flag": "被你标记为失误",
    "event.fault.other": "失误（{source}）",
    "event.fault.refusal": "被你拒绝",
    "event.fault.spot": "抽查被拒绝或失败",
    "event.fault.undo": "被你撤销",
    "event.neutral.alone": "自主执行（已赢得）",
    "event.neutral.ambiguous": "无法判定 · 无证据",
    "event.neutral.blocked": "被其他防护拦截 · 无证据",
    "event.neutral.error": "工具出错 · 无证据",
    "event.neutral.expired": "未回报结果 · 无证据",
    "event.neutral.nobody": "无人应答 · 无证据",
    "event.neutral.other": "中性（{source}）",
    "event.neutral.timeout": "无回应 · 无证据",
    "event.neutral_expired": "待处理操作已过期 · 无证据",
    "event.revoked": "被你收回",
    "event.success.approved": "经你批准，运行无误",
    "event.success.notify": "已执行并告知 · 未撤销",
    "event.success.spot": "抽查经你批准",
    "event.switch": "切换模型",
    "event.switch_from": "从 {from} 切换模型",
    "event.tier": "级别 {from} → {to} · {why}",
    "event.trial.failed": {
      "other": "考察未通过：需等待 {wait} 个操作"
    },
    "event.trial.opened": {
      "other": "开启考察期：接下来 {left} 个必须成功"
    },
    "event.trial.passed": "考察通过",
    "event.trial.reopens": {
      "other": "重新开启考察期：接下来 {left} 个必须成功"
    },
    "event.why.fault": "失误",
    "event.why.series_complete": "连续记录已达标",
    "event.why.series_n": "连续 {required}/{required}",
    "event.why.sessions": {
      "other": "{count} 个会话"
    },
    "event.why.settings": "设置更严格",
    "event.why.stakes": "风险等级变更",
    "event.why.wald": "通过序贯检验",
    "flag.carried_over": "继承",
    "flag.carried_over_n": {
      "other": "{n} 项继承"
    },
    "flag.carried_over_provisional": {
      "other": "{n} 项继承，暂定"
    },
    "flag.carried_over_title": {
      "other": "{count} 项继承，暂定"
    },
    "flag.fault_on_record": "有失误记录",
    "flag.fault_on_record_title": "有失误记录",
    "flag.provisional": "暂定",
    "flag.trial": "考察期",
    "guarantee.capped": "受限：每次操作都会询问。",
    "guarantee.plain": "其操作中最多约每 {k} 个就有 1 个带着无人批准的错误运行。",
    "guarantee.text": "未经检查的错误不超过此类型操作的 {aoql}；若智能体在获得自主权后变差，在第一次发现错误之前最多 {worst}。",
    "guarantee.text_conditional": "未经检查的错误不超过此类型操作的 {aoql}；若智能体在获得自主权后变差，在第一次发现错误之前最多 {worst}。前提是上一个模型的证据依然成立。",
    "guarantee.trusted": "暂无保证：只有凭证据赢得的级别才有保证。",
    "help.agent": "当前行的智能体详情",
    "help.aria": "键盘快捷键",
    "help.close": "关闭",
    "help.help": "本帮助",
    "help.next_prev": "下一个 / 上一个智能体",
    "help.open": "打开当前智能体",
    "help.raw": "切换原始类型名",
    "help.title": "键盘",
    "legend.a_share": "一部分",
    "legend.alone": "自主执行，抽查其中 {share}",
    "legend.ask": "先询问",
    "legend.capped": "受限：始终询问",
    "legend.carried": "继承自上一个模型，暂定",
    "legend.notify": "先执行后告知，可撤销（可逆类型）",
    "legend.series": "连续已验证的成功次数，共需 N 次",
    "legend.trusted": "信任起步：首次失误前像单独使用 Hermes 一样执行，未赢得任何级别",
    "map.aria": "按操作类型列出的智能体",
    "map.empty.after": " 开始，且只凭已验证的成功晋升：可逆类型在连续若干次无失误的已验证成功后升到中间级别，在来自两个会话的完整 N 次连续成功后升到 T3。",
    "map.empty.before": "tenure 从智能体请求运行的第一个操作开始计数。读取从不询问。每个操作类型都从 ",
    "map.empty.bold": "T1（先询问）",
    "map.empty.title": "还没有证据",
    "map.open_hint": "打开 ",
    "map.th.agent": "智能体",
    "map.th.agent_sub": "配置文件 · model@provider",
    "map.th.capped": "受限 · 始终询问",
    "map.th.risk": {
      "other": "风险率 {risk} · 连续 {n} 次后自主执行"
    },
    "meta.preset": "预设",
    "meta.profile": "配置文件",
    "meta.start": "起点",
    "missing.always_asks": "始终询问",
    "missing.earned": "已赢得 · 接受抽查",
    "missing.more_to_t2": {
      "other": "还差 {n} 次进入考察中（T2）"
    },
    "missing.more_to_t3": {
      "other": "还差 {n} 次转正"
    },
    "missing.rechecking": "正在复核",
    "missing.second_session": "需要第 2 个会话",
    "missing.trial_left": {
      "other": "考察期 · 还差 {n}/{total}"
    },
    "missing.trial_wait": {
      "other": "考察未通过 · 等 {n} 个操作"
    },
    "missing.trusted": "首次失误前保持信任 · 像单独使用 Hermes 一样执行",
    "missing.trusted_undo": "首次失误前保持信任 · 先执行后告知，可撤销",
    "models.empty.body": "每个已验证的操作都会计入模型在该类型上的记录，显示在这里和 {cmd} 中。",
    "models.empty.title": "还没有记录",
    "models.lede": "你自己的基准：每个模型在你的工作中、按操作类型的已验证记录，附失误率的 95% 区间。按区间上限排名，从不只看单一分数。旁边是公开测评，仅供参考：",
    "models.lede_bold": "它衡量的是在别人任务上的能力，而不是在你的工作上的可靠性。",
    "models.no_public": "此操作类型没有公开测评。",
    "models.not_enough": "证据不足",
    "models.not_ranked": "证据尚不足",
    "models.not_ranked_note": "模型在此类型上有 {n} 次已验证结果后才参与排名。",
    "models.personal_title": "在你的工作上",
    "models.public_note": "衡量的是在别人任务上的能力，而不是在你的工作上的可靠性。",
    "models.public_title": "公开测评",
    "models.source": "{source}。已公布的最高分，不限测试框架；并非受控对比。",
    "models.source_accessed": "{source}，访问于 {accessed}。已公布的最高分，不限测试框架；并非受控对比。",
    "moment.dismiss": "关闭",
    "moment.eyebrow.down": "发现失误",
    "moment.eyebrow.up": "晋升",
    "moment.granted": "已获转正",
    "moment.probation": "重回试用期",
    "moment.review": "进入考察",
    "page.anim_off": "动画已关闭",
    "page.anim_on": "动画已开启",
    "page.anim_reduced": "你的系统要求减少动态效果：动画保持关闭",
    "page.anim_title": "动画：开启或关闭，记在此浏览器中",
    "page.animations": "动画",
    "page.error": "无法读取 tenure：{error}",
    "page.live": "实时 · ",
    "page.loading": "正在加载记录…",
    "page.polling": "每 {s} 秒刷新",
    "page.raw_off": "名称已脱敏",
    "page.raw_on": "原始名称",
    "page.raw_title": "显示原始操作类型名（r）",
    "page.retrying": "正在重试 · ",
    "page.subtitle": "可撤销的信任：一次失误即收回，凭已验证的证据重新赢得",
    "page.title": "Tenure",
    "page.unreadable": "无法读取：{profiles}。其数据库存在但无法打开；已显示其他配置文件。",
    "passport.agent": "智能体",
    "passport.card.aria": "{agent} 的护照：{verdict}",
    "passport.card.signature": "Hermes Agent 的一个插件",
    "passport.card.title": "护照",
    "passport.checked_by": "已由仪表盘对照此配置文件的账本验证。任何人都可以重新验证：",
    "passport.download": "下载 JSON",
    "passport.empty.body": "护照汇总智能体的记录；第一个已验证的操作出现后才会生成。",
    "passport.empty.title": "还没有护照",
    "passport.faults_checks": {
      "other": "{n} 次失误 / {total} 次已验证结果"
    },
    "passport.field.agent": "智能体",
    "passport.field.generated": "生成时间",
    "passport.field.ledger": "账本",
    "passport.field.profile": "配置文件",
    "passport.field.protocol": "协议",
    "passport.field.public_key": "公钥",
    "passport.field.rule": "规则",
    "passport.field.settings": "设置",
    "passport.field.signature": "签名",
    "passport.field.type_names": "类型名",
    "passport.note": "已签名且可发现篡改：签名或锚定后的任何改动都会在验证时显示出来。较早的护照对照更长的账本依然能通过验证；验证器会说明此后的变化。",
    "passport.pending_note": "按最近记录的设置计算；新设置从下一个操作起生效。",
    "passport.trusted": "信任中（非赢得）",
    "passport.types_title": "已证实的类型",
    "passport.value.hashed": "{profile}（已哈希）",
    "passport.value.ledger": {
      "other": "{n} 个事件 · 头部 {head}"
    },
    "passport.value.none": "无",
    "passport.value.raw": "原始",
    "passport.value.redacted": "程序和子命令之后的部分已脱敏",
    "passport.value.unsigned": "未签名",
    "preset.balanced": "平衡",
    "preset.careful": "谨慎",
    "preset.custom": "自定义",
    "preset.fast": "快速",
    "profile.copy_pending": "从另一个配置文件复制而来，启动时检查",
    "profile.name": "配置文件 {profile}",
    "profile.pending": "从下一个操作起生效",
    "profile.preset": "{preset}预设",
    "profile.read_only": " · 此处只读",
    "profile.sessions_suspended": {
      "other": "{n} 个会话已暂停：读取了外部内容"
    },
    "profile.spot": "抽查率 {rate}",
    "profile.start_probation": "考察起步（试用期）",
    "profile.start_trusted": "信任起步",
    "profile.strict": "严格",
    "profile.suspended": {
      "other": "{n} 个已暂停：读取了外部内容"
    },
    "profile.this_dashboard": " · 此仪表盘",
    "settings.advanced_docs": "每个设置项都可通过 hermes tenure explain 和 tenure 的 README 查看说明。",
    "settings.advanced_help": "操作类型的重新分类，以及 Hermes 自带表单中的全部设置项。",
    "settings.advanced_title": "高级",
    "settings.advanced_types": "在 Hermes 的「设置 → 插件 → Tenure」中，或在 config.yaml 中，重新分类操作类型（每个模式取 free、low、medium、high 或 cap）：",
    "settings.animations_help": "逐步打印的进度条、显影的护照、横幅。与页面顶部的开关相同；系统要求减少动态效果时保持关闭。",
    "settings.custom_help": "按风险级别设定你自己的未经检查错误比例：选择 1/k，输入你自己的 k，或选择受限（始终询问）。类型所需的连续记录随即更新。保存后预设变为自定义，除非与某个预设一致。",
    "settings.custom_title": "各风险级别的可接受风险",
    "settings.enabled_help": "关闭 tenure 而不卸载它。",
    "settings.enabled_off": "关",
    "settings.enabled_on": "开",
    "settings.enabled_title": "开启或关闭 tenure",
    "settings.enabled_unknown": "智能体部分尚未报告此状态：选择一项即可设定。",
    "settings.enabled_warn": "关闭：tenure 不再做决定；Hermes 照常询问。账本和所有记录保持不变。",
    "settings.in_force": "生效中",
    "settings.no_writer": "此 Hermes 不允许 Desktop 保存 tenure 的设置：请使用下方命令。",
    "settings.none": "此配置文件还没有 tenure 记录：在第一个操作之前使用默认设置。",
    "settings.one_in": "1/",
    "settings.or_config": "或在 Hermes 的 config.yaml 中，于 plugins.entries.tenure.settings 下：",
    "settings.or_terminal": "或在终端中：",
    "settings.pending": "最近一次修改尚未记入账本：从下一个操作起生效。",
    "settings.preset_desc_balanced": "默认设置。高风险类型始终询问。",
    "settings.preset_desc_careful": "询问时间最长。即使高风险类型，经过很长的连续记录后也能赢得级别。",
    "settings.preset_desc_custom": "你自己按风险级别设定的可接受风险，写在 Hermes 的配置中。",
    "settings.preset_desc_fast": "在低风险和中风险上最快赢得自主权。高风险类型始终询问。",
    "settings.preset_help": "按风险级别，一个操作类型在自主执行之前需要多少证据：连续已验证成功的次数，以及可接受的未经检查错误比例。",
    "settings.risk": "可接受 1/{k} 的未经检查错误",
    "settings.risk_invalid": "请输入 2 或以上的整数。",
    "settings.rung_cap": "受限",
    "settings.save": "保存",
    "settings.save_failed": "未保存：{error}",
    "settings.saved": "已保存并记入账本：从下一个操作起生效。",
    "settings.saves_here": "修改会立即通过 Hermes 自己的设置写入器保存，并记入账本；从下一个操作起生效。同样的设置也在 Hermes 的「设置 → 插件 → Tenure」中。",
    "settings.saving": "正在保存…",
    "settings.series": {
      "other": "连续 {n} 次已验证的成功"
    },
    "settings.spot_change": "在 Hermes 的 config.yaml 中，于 plugins.entries.tenure.settings 下设置（0 到 1 之间的比例）：",
    "settings.spot_custom": "自定义值：1/k",
    "settings.spot_desc": "类型转正后，它的操作中每 {k} 个仍会随机抽查 1 个：变差的模型会被发现。",
    "settings.spot_title": "抽查",
    "settings.spot_value": "每 {k} 个抽查 1 个",
    "settings.start_help": "操作类型在第一次失误之前的行为。",
    "settings.start_probation": "研究的起点：每个操作类型都先询问（T1），并根据你的回答赢得每个级别。",
    "settings.start_trusted": "覆盖的类型（文件编辑、记忆、子智能体、常见开发工具）在第一次失误之前什么都不问，与 Hermes 单独运行时一样。一次失误会让该类型进入试用期（T1），之后重新赢得级别。离开本机的操作和涉及金钱的操作始终询问。",
    "settings.strict_desc_off": "新模型继承上一个模型在低风险和中风险上的记录，减半且为暂定，直到它自己的批准加以确认。高风险从零开始。",
    "settings.strict_desc_on": "新模型在每个操作类型上都从空记录开始，与研究中一致。",
    "settings.strict_help": "切换模型时，新模型继承什么。",
    "settings.strict_off": "严格模式：关",
    "settings.strict_on": "严格模式：开",
    "settings.strict_title": "切换模型时的严格模式",
    "settings.use": "使用",
    "stakes.group.high": "高风险",
    "stakes.group.low": "低风险",
    "stakes.group.medium": "中风险",
    "stakes.high": "高",
    "stakes.low": "低",
    "stakes.medium": "中",
    "stale.message": "上次刷新失败（{error}）。显示的是 {time} 的数据。",
    "start.probation": "考察起步（试用期）",
    "start.trusted": "信任起步",
    "switch.count.carried": {
      "other": "{n} 项继承"
    },
    "switch.count.kept": {
      "other": "{n} 项保留"
    },
    "switch.count.reset": {
      "other": "{n} 项重置"
    },
    "switch.count.vetoed": {
      "other": "{n} 项否决"
    },
    "switch.delta": "（{delta}）",
    "switch.empty": "还没有可预览的智能体",
    "switch.footnote": "公开分数仅供参考，从不授予自主权。否决只会阻止继承，且仅在超出固定差距时生效。",
    "switch.from": "从",
    "switch.lede": "更换模型之前：逐个类型查看新智能体会继承什么。新模型或新提供方即为新智能体。继承是我们的补充；严格模式即研究原规则。",
    "switch.none": "无",
    "switch.pick.body": "输入任意模型 ID。在 Hermes 真正运行新模型之前，什么都不会改变。",
    "switch.pick.title": "选择目标模型",
    "switch.placeholder": "模型 ID，例如 {example} 或 model@provider",
    "switch.preview": "预览",
    "switch.provisional": {
      "other": "{n} 项暂定"
    },
    "switch.status.carried.label": "继承，暂定",
    "switch.status.carried.text": "部分连续记录会被继承，并标为暂定，直到新模型积累自己的记录。",
    "switch.status.kept.label": "保留",
    "switch.status.kept.text": "新智能体在这里已有自己的记录；它永远不会被覆盖。",
    "switch.status.reset.label": "重置",
    "switch.status.reset.text": "从零开始：高风险、受限或严格模式。",
    "switch.status.vetoed.label": "否决",
    "switch.status.vetoed.text": "公开基准显示新模型在此类型上更弱：不继承任何记录。",
    "switch.strict": "严格模式：不继承任何记录",
    "switch.to": "目标模型",
    "switch.to_aria": "目标模型",
    "tabs.aria": "Tenure 视图",
    "th.after_switch": "切换后",
    "th.agent": "智能体",
    "th.contributors": "贡献者",
    "th.faults_checks": "失误 / 已验证",
    "th.file": "文件",
    "th.guarantee": "保证",
    "th.model": "模型",
    "th.now": "当前",
    "th.outcome": "结果",
    "th.public_measure": "公开测评",
    "th.range": "95% 区间 · 0–{max}",
    "th.rate": "失误率",
    "th.series": "连续",
    "th.sessions": "会话",
    "th.tier": "级别",
    "th.type": "类型",
    "th.undo_effect": "撤销的影响",
    "th.when": "时间",
    "th.your_record": "你的记录",
    "tier.capped.chip": "CAP",
    "tier.capped.title": "受限：始终询问",
    "tier.chip.title": "{tier}，{name}",
    "tier.label.alone": "已转正",
    "tier.label.ask": "试用期",
    "tier.label.cap": "始终询问",
    "tier.label.notify": "考察中",
    "tier.name.alone": "自主执行",
    "tier.name.ask": "先询问",
    "tier.name.notify": "先执行后告知",
    "tier.trusted.chip": "信任",
    "tier.trusted.label": "信任中",
    "tier.trusted.name": "像单独使用 Hermes 一样执行",
    "tier.trusted.title": "首次失误前保持信任：像单独使用 Hermes 一样执行。尚未赢得任何级别。",
    "time.ago": "{duration}前",
    "time.days": {
      "other": "{n} 天"
    },
    "time.hours_minutes": {
      "other": "{n} 小时 {mm} 分"
    },
    "time.minutes": {
      "other": "{n} 分钟"
    },
    "time.seconds": {
      "other": "{n} 秒"
    },
    "timeline.all_types": "所有类型",
    "timeline.count": {
      "other": "{n}×"
    },
    "timeline.empty": "此筛选条件下没有证据",
    "timeline.filter_label": "按类型筛选",
    "timeline.loading": "正在加载证据…",
    "timeline.note": "来自哈希链账本，最新在前，最近 200 个事件。重复的结果已合并。",
    "timeline.title": "证据时间线",
    "toast.transition": "{agent} · {type}：{from} → {to}",
    "totals.actions": {
      "other": "{n} 个操作"
    },
    "totals.alone": "{n} 个未经询问",
    "totals.checked": "{n} 个已确认",
    "totals.faults": {
      "other": "{n} 次失误"
    },
    "transitions.empty": "打开此页面以来没有变化。每次自动的级别变化都会列在这里，以及各智能体的时间线中。",
    "transitions.title": "本页看到的级别变化",
    "transitions.why.after_fault": "因失误",
    "transitions.why.on_evidence": "基于证据",
    "transitions.why.trial_open": "考察期中",
    "transitions.why_changed": "无失误：被收回，或设置、风险等级已变更",
    "type.always_asks": "始终询问",
    "type.stakes_high": "高风险",
    "type.stakes_low": "低风险",
    "type.stakes_medium": "中风险",
    "undo.button": "撤销",
    "undo.collapse": "收起",
    "undo.confirm": "撤销 #{id}？",
    "undo.effect.already": "恢复文件 · 自动检查已记过一次失误",
    "undo.effect.fault": "恢复文件 · 记为一次失误",
    "undo.effect.none": "没有可恢复的内容（无快照）· 会记为一次失误",
    "undo.empty.body": "智能体未经询问写入的文件（信任中，或处于 T2：先执行后告知）会保留 24 小时快照。它们按最新在前显示在这里，每条都可单独撤销。",
    "undo.empty.title": "没有可撤销的操作",
    "undo.expand": "展开",
    "undo.lede": "最近先执行后告知的操作。撤销会从快照恢复文件，并记为该类型的一次失误。",
    "undo.no_snapshot": "无快照",
    "undo.own_profile_only": "撤销只作用于此仪表盘的配置文件",
    "undo.title": "恢复文件",
    "undo.window_ends": "{duration}后无法撤销",
    "verdict.chain": "哈希链完整",
    "verdict.ok.replay": "按规则重放账本得到相同的级别",
    "verdict.ok.signature": "签名有效（Ed25519）",
    "verdict.ok.title": "已验证",
    "verdict.problems": {
      "other": "发现 {count} 个问题"
    },
    "verdict.unsigned.no_key": "还没有签名密钥：运行 {cmd} 创建",
    "verdict.unsigned.replay": "重放得到相同的级别",
    "verdict.unsigned.title": "未签名，其余均已验证",
    "view.community": "社区",
    "view.map": "总览",
    "view.models": "你的基准",
    "view.passport": "护照",
    "view.settings": "设置",
    "view.switch": "切换预览",
    "view.undo": "撤销"
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
  // The trusted start has no tier code: its chip word is translated (a live event's "from" can be "trusted").
  Object.defineProperty(TIER, "trusted", { enumerable: false, get: function () { return t("tier.trusted.chip"); } });
  function tierName(tier) { return tier === "trusted" ? t("tier.trusted.name") : t("tier.name." + tier); }
  /** The tier a type shows: "trusted" while the trusted start covers it (no fault or revoke yet, not at an earned
   *  T3). Nothing about such a type is earned: it never counts as autonomy, never carries a guarantee. */
  function shownTier(ty) { return ty && ty.trusted && !ty.capped ? "trusted" : ty ? ty.effective_tier || ty.tier : "ask"; }
  /** A profile's start mode: from its settings, else inferred from a type the trusted start covers; null if unknown. */
  function startOf(info) {
    var st = info && info.settings;
    if (st && (st.start === "trusted" || st.start === "probation")) return st.start;
    return info && (info.agents || []).some(function (a) { return (a.types || []).some(function (ty) { return ty.trusted; }); }) ? "trusted" : null;
  }
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
  /** WCAG relative luminance of a computed colour (rgb()/rgba() in 0..255, color(srgb ...) in 0..1). */
  function relLum(css) {
    var nums = String(css || "").match(/-?[\d.]+/g);
    if (!nums || nums.length < 3) return 0;
    var scale = /^color\(/.test(String(css).trim()) ? 1 : 255;
    function lin(v) { var c = Math.max(0, Math.min(1, Number(v) / scale)); return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
    return 0.2126 * lin(nums[0]) + 0.7152 * lin(nums[1]) + 0.0722 * lin(nums[2]);
  }
  /** Ink on accent paper: whichever of near-black and near-white contrasts more with the accent. */
  function inkOn(accent) {
    var L = relLum(accent);
    return (L + 0.05) / 0.0545 > 1.05 / (L + 0.05) ? "#0b0b0c" : "#fcfcfc";
  }
  function typing(e) {
    var el = e.target;
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
  }

  /** Poll ``fn`` every POLL_MS while the page is visible; ``deps`` restart it. An answer is tagged with the deps it
   * was fetched for: when the deps change, the previous answer is never returned (no other agent's passport shows). */
  function usePoll(fn, deps, enabled, every) {
    var period = every || POLL_MS;
    var key = JSON.stringify(deps);
    var state = useState({ data: null, error: null, at: 0, key: key });
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
          if (alive.current && my === tickRef.current) set({ data: data, error: null, at: Date.now(), key: key });
        }, function (err) {
          if (alive.current && my === tickRef.current) {
            set(function (s) { return s.key === key ? { data: s.data, error: err, at: s.at, key: key } : { data: null, error: err, at: 0, key: key }; });
          }
        }).then(function () {
          if (alive.current && my === tickRef.current) timer = setTimeout(run, period);
        });
      }
      run();
      return function () { alive.current = false; if (timer) clearTimeout(timer); };
      // eslint-disable-next-line
    }, deps);
    return state[0].key === key ? state[0] : { data: null, error: null, at: 0, key: key };
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

  // ------------------------------------------------------------------------------------------- ink and dither
  // "Encre et trame": one colour (the theme's midground, read from the CSS of each canvas), 1-bit Bayer dither.
  // A type's progress is a dither that densifies from a faint dotted track to a solid fill as it nears its next
  // tier; the agent's emblem is a dithered sunburst whose density is its share of earned autonomy. Animations play
  // on real state changes only (previous render vs new data), never on a timer, and stop on reduced motion, on the
  // tab's own switch (localStorage "tenure.animations") and while the page is hidden.
  var BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]];
  var REDUCED = (function () { try { return window.matchMedia("(prefers-reduced-motion: reduce)"); } catch (e) { return null; } })();
  var ANIM = true;                                   // the tab's switch, set by TenurePage on every render
  function reducedMotion() { return !!(REDUCED && REDUCED.matches); }
  function motion() { return ANIM && !reducedMotion() && !document.hidden; }
  function readAnimPref() { try { return window.localStorage.getItem("tenure.animations") !== "off"; } catch (e) { return true; } }
  function writeAnimPref(on) { try { window.localStorage.setItem("tenure.animations", on ? "on" : "off"); } catch (e) { /* ignore */ } }
  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function easeOut(x) { return 1 - Math.pow(1 - x, 3); }

  /** Size a canvas to its CSS box at device resolution; a context in CSS pixels, filled with the canvas's colour. */
  function prep(cv, w, hgt) {
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W = Math.max(1, Math.round(w * dpr)), H = Math.max(1, Math.round(hgt * dpr));
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    var x = cv.getContext && cv.getContext("2d");
    if (!x) return null;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, w, hgt);
    x.globalAlpha = 1;
    x.fillStyle = getComputedStyle(cv).color;
    return x;
  }
  /** One RAF tween of ``ms`` (after ``delay``) on the state object ``s``: step(k in 0..1), then done(). */
  function tween(s, ms, delay, step, done) {
    var t0 = 0;
    cancelAnimationFrame(s.raf);
    function f(ts) {
      if (!t0) t0 = ts;
      var k = clamp01((ts - t0 - (delay || 0)) / ms);
      step(k);
      if (k < 1) s.raf = requestAnimationFrame(f);
      else { s.raf = 0; if (done) done(); }
    }
    s.raf = requestAnimationFrame(f);
  }
  /** A CSS mask that shows the cells of the 4x4 Bayer matrix below ``k`` of 16: a dither dissolve in 17 steps. */
  var MASKS = {};
  function ditherMask(k) {
    k = Math.max(0, Math.min(16, Math.round(k)));
    if (MASKS[k]) return MASKS[k];
    var r = "";
    for (var j = 0; j < 4; j++) for (var i = 0; i < 4; i++) {
      if (BAYER[j][i] < k) r += "%3Crect x='" + i * 2 + "' y='" + j * 2 + "' width='2' height='2'/%3E";
    }
    return (MASKS[k] = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8'%3E" + r + "%3C/svg%3E\")");
  }
  function setMask(el, k) {
    if (!el) return;
    var m = k >= 16 ? "" : ditherMask(k);
    el.style.webkitMaskImage = m; el.style.maskImage = m;
  }

  /** How far a type is toward its next tier, 0..1: toward T2 for a T1 type that can reach it (Wald steps), toward
   *  T3 otherwise (series / required); T3 is full; capped is null (a faint track only). */
  function progress(ty) {
    if (!ty || ty.capped || (ty.guarantee && ty.guarantee.capped)) return null;
    if (ty.trusted) return "trust";                  // no progress to show: an even, light texture, nothing earned
    var eff = ty.effective_tier || ty.tier;
    if (eff === "alone") return 1;
    return ty.required ? clamp01((ty.series || 0) / ty.required) : 0;
  }
  /** One number, one meaning: the bar runs from 0 to the series T3 requires (one segment per success), filled to
   *  series / required, as the "9/52" beside it says. A T1 type that can reach T2 carries a notch where it does:
   *  series + the successes still missing for T2 (Wald steps). ``wald`` is the row with the Wald score (a passport
   *  type has none: the map's row for the same type, when the stakes agree). */
  function notchOf(ty, wald) {
    var src = wald || ty;
    if (!ty || ty.capped || !ty.required || (ty.effective_tier || ty.tier) !== "ask" || src.stakes !== ty.stakes) return null;
    var k = src.wald != null ? toT2(src) : null;
    if (k == null) return null;
    var at = (ty.series || 0) + k;
    return at < ty.required ? at / ty.required : null;
  }
  function barProps(ty, wald) {
    return { value: progress(ty), segments: ty && !ty.capped && !ty.trusted ? ty.required || 0 : 0, notch: ty && ty.trusted ? null : notchOf(ty, wald), faults: ty ? ty.faults : null };
  }
  /** Share of earned autonomy: (T2 x 0.5 + T3) / types; a trusted type counts for nothing. */
  function autonomyShare(types) {
    if (!types || !types.length) return 0;
    var s = 0;
    types.forEach(function (ty) {
      var eff = ty.effective_tier || ty.tier;
      if (ty.capped || ty.trusted || (ty.guarantee && ty.guarantee.capped)) return;
      s += eff === "alone" ? 1 : eff === "notify" ? 0.5 : 0;
    });
    return s / types.length;
  }

  /** Paint a progress bar: ``p`` 0..1 (or -1 for capped), ``dev`` the print sweep (cells whose Bayer threshold is
   *  below it), ``crumble`` 0..1 (dots drop and fade). Cells of 2 CSS px. */
  var TRUST_BAR = -2;       // paintBar's p for a trusted type: an even 20% texture end to end
  function paintBar(cv, p, dev, crumble, geo) {
    var w = cv.clientWidth, hgt = cv.clientHeight;
    if (!w || !hgt) return false;
    var x = prep(cv, w, hgt);
    if (!x) return false;
    var c = 2, cols = Math.ceil(w / c), rows = Math.max(1, Math.floor(hgt / c));
    var edge = p < 0 ? 0 : p * w, fade = Math.min(6, w * 0.03), track = p === TRUST_BAR ? 0.2 : p < 0 ? 0.07 : 0.1;
    var d = dev == null ? 1 : dev, k = crumble || 0;
    var segs = geo && p >= 0 && p < 1 ? geo.segments || 0 : 0, per = segs ? cols / segs : 0;
    var segW = per ? per * Math.max(1, Math.ceil(3 / per)) : 0;        // a gap every k successes, k cells >= 3
    var nx = geo && geo.notch != null && p >= 0 && p < 1 ? Math.min(cols - 1, Math.round(geo.notch * cols)) : -9;
    if (k) x.globalAlpha = 1 - k;
    for (var j = 0; j < rows; j++) for (var i = 0; i < cols; i++) {
      if (i === nx) { x.fillRect(i * c, j * c, c - 0.6, c - 0.6); continue; }
      if (Math.abs(i - nx) === 1 || (segW && i < cols - 1 && Math.floor((i + 1) / segW) !== Math.floor(i / segW))) continue;
      var X = i * c, v = X < edge - fade ? 1 : X < edge ? (edge - X) / fade : 0;
      if (p >= 1) v = 1;
      v = Math.max(v, track);
      var th = BAYER[j & 3][i & 3];
      if (v * 16 > th && th < d * 16) {
        var dy = k ? k * k * (3 + ((i * 7 + j * 3) % 5)) : 0;
        x.fillRect(X, j * c + dy, c - 0.6, c - 0.6);
      }
    }
    return true;
  }

  /** A type's dither bar. Prints in on first paint (A), fills when the value climbs (C). It crumbles and re-prints
   *  lower only when ``faults`` went up (D): a drop without a fault, or a bar whose meaning changed, just prints
   *  again. Redraws when the theme colour, the width or the pixel ratio changes. */
  function DitherBar(props) {
    var ref = useRef(null);
    var st = useRef({ v: null, color: "", w: 0, dpr: 0, raf: 0, faults: null, geo: "" });
    var target = props.value == null ? -1 : props.value === "trust" ? TRUST_BAR : clamp01(props.value);
    var geo = { segments: props.segments || 0, notch: props.notch == null ? null : props.notch };
    var gk = geo.segments + "|" + geo.notch;
    useEffect(function () {
      var cv = ref.current, s = st.current;
      if (!cv) return;
      var w = cv.clientWidth, col = getComputedStyle(cv).color, dpr = window.devicePixelRatio || 1;
      if (!w) return;                                // hidden (the other layout): painted when it shows
      var faulted = props.faults != null && s.faults != null && props.faults > s.faults;
      if (props.faults != null) s.faults = props.faults;
      if (s.v === target && s.color === col && s.w === w && s.dpr === dpr && s.geo === gk) return;
      var from = s.v, first = from === null;
      s.color = col; s.w = w; s.dpr = dpr; s.v = target; s.geo = gk;
      if (!motion() || (!first && from === target)) { cancelAnimationFrame(s.raf); paintBar(cv, target, 1, 0, geo); return; }
      if (first) {
        tween(s, 600, props.delay || 0, function (k) { paintBar(cv, target, easeOut(k), 0, geo); });
      } else if (from === TRUST_BAR || target === TRUST_BAR) {
        // Into or out of the trusted texture (its first fault, a revoke): nothing grows, the bar prints again.
        tween(s, 420, 0, function (k) { paintBar(cv, target, easeOut(k), 0, geo); });
      } else if (faulted && target < from) {
        var start = from < 0 ? 0 : from;
        tween(s, 500, 0, function (k) { paintBar(cv, start, 1, k, geo); }, function () {
          tween(s, 450, 0, function (k) { paintBar(cv, target, easeOut(k), 0, geo); });
        });
      } else if (target > from) {
        tween(s, target >= 1 ? 700 : 450, 0, function (k) { paintBar(cv, from + (target - from) * easeOut(k), 1, 0, geo); });
      } else {
        tween(s, 420, 0, function (k) { paintBar(cv, target, easeOut(k), 0, geo); });
      }
    });
    useEffect(function () { return function () { cancelAnimationFrame(st.current.raf); }; }, []);
    return h("canvas", { ref: ref, className: cx("tnr-dbar", props.className), "aria-hidden": true });
  }

  /** The emblem: an original dithered sunburst, its density the share of earned autonomy. */
  function embValue(i, j, n, rot, share) {
    var c = n / 2, dx = i - c + 0.5, dy = j - c + 0.5, r = Math.sqrt(dx * dx + dy * dy) / c;
    if (r > 1) return -1;
    var a = Math.atan2(dy, dx) + rot, ray = Math.pow((Math.cos(a * 36) + 1) / 2, 2), core = Math.max(0, 1 - r / 0.42);
    var v = Math.max(core * 1.15, ray * (1.08 - r) * 1.25 * (0.4 + 0.6 * share), 0.18 * (1 - r));
    if (Math.abs(r - 0.47) < 0.025 || Math.abs(r - 0.97) < 0.02) v = 1;
    return v;
  }
  function paintEmblem(cv, size, n, share, dev, rot) {
    var x = prep(cv, size, size);
    if (!x) return;
    var c = size / n, g = Math.min(0.8, c * 0.27), d = dev * 16;
    for (var j = 0; j < n; j++) for (var i = 0; i < n; i++) {
      var v = embValue(i, j, n, rot, share);
      if (v < 0) continue;
      var th = BAYER[j & 3][i & 3];
      if (v * 16 > th && th < d) x.fillRect(i * c, j * c, c - g, c - g);
    }
  }

  /** The agent's emblem: develops point by point on mount (A), pulses once when the share climbs (C); with
   *  ``rotate``, its rays turn slowly while it is on screen. */
  function Emblem(props) {
    var ref = useRef(null);
    var st = useRef({ share: null, color: "", raf: 0, rot: 0, loop: 0, seen: true });
    var size = props.size || 72, n = Math.min(96, props.cells || Math.round(size / 3));
    var share = clamp01(props.share || 0);
    useEffect(function () {
      var cv = ref.current, s = st.current;
      if (!cv) return;
      var col = getComputedStyle(cv).color;
      if (s.share === share && s.color === col) return;
      var from = s.share;
      s.share = share; s.color = col;
      if (!motion()) { paintEmblem(cv, size, n, share, 1, s.rot); return; }
      if (from === null) {
        tween(s, props.developMs || 1400, props.delay || 0, function (k) { paintEmblem(cv, size, n, share, k, s.rot); }, startLoop);
      } else if (share > from) {
        tween(s, 900, 0, function (k) { paintEmblem(cv, size, n, clamp01(share + 0.45 * Math.sin(Math.PI * k)), 1, s.rot); }, startLoop);
      } else paintEmblem(cv, size, n, share, 1, s.rot);
    });
    function startLoop() {
      var s = st.current, cv = ref.current, last = 0;
      if (!props.rotate || !cv || s.loop) return;
      function f(ts) {
        if (!ref.current || !props.rotate) { s.loop = 0; return; }
        if (!motion() || !s.seen) { s.loop = 0; return; }   // resumed by the observer or the next render
        if (last) s.rot += Math.min(0.1, (ts - last) / 1000) * 0.06;
        last = ts;
        if (!s.raf) paintEmblem(cv, size, n, s.share, 1, s.rot);     // a pulse in progress paints itself
        s.loop = requestAnimationFrame(f);
      }
      s.loop = requestAnimationFrame(f);
    }
    useEffect(function () {
      var s = st.current, cv = ref.current, io = null;
      if (!props.rotate || !cv) return undefined;
      if (window.IntersectionObserver) {
        io = new IntersectionObserver(function (es) {
          s.seen = es[0] && es[0].isIntersecting;
          if (s.seen && !s.raf) startLoop();
        });
        io.observe(cv);
      }
      function vis() { if (!document.hidden && !s.raf) startLoop(); }
      document.addEventListener("visibilitychange", vis);
      return function () {
        if (io) io.disconnect();
        document.removeEventListener("visibilitychange", vis);
        cancelAnimationFrame(s.loop); cancelAnimationFrame(s.raf); s.loop = 0;
      };
    }, [props.rotate]);
    useEffect(function () { if (props.rotate && !st.current.raf) startLoop(); });
    return h("canvas", { ref: ref, className: cx("tnr-emblem", props.className), "aria-hidden": true,
      style: { width: size, height: size } });
  }

  /** A band of dither fading downward (the bottom of a big moment), printed in once. */
  function DitherFade(props) {
    var ref = useRef(null), st = useRef({ raf: 0, done: false, color: "" });
    useEffect(function () {
      var cv = ref.current, s = st.current;
      if (!cv) return;
      var col = getComputedStyle(cv).color;
      function paint(kk) {
        var w = cv.clientWidth, hgt = cv.clientHeight;
        if (!w || !hgt) return;
        var x = prep(cv, w, hgt);
        if (!x) return;
        var c = 4, cols = Math.ceil(w / c), rows = Math.floor(hgt / c);
        for (var j = 0; j < rows; j++) {
          var v = (1 - j / rows) * kk;
          for (var i = 0; i < cols; i++) if (v * 16 > BAYER[j & 3][i & 3] + ((i * 7) % 3)) x.fillRect(i * c, j * c, c - 0.8, c - 0.8);
        }
      }
      if (s.done && s.color === col) return;
      s.color = col;
      if (!s.done && motion()) tween(s, 900, 200, function (k) { paint(easeOut(k)); });
      else paint(1);
      s.done = true;
    });
    useEffect(function () { return function () { cancelAnimationFrame(st.current.raf); }; }, []);
    return h("canvas", { ref: ref, className: "tnr-fade", "aria-hidden": true });
  }

  /** A token for ~900 ms after ``value`` climbs, else 0: the spot-check scan line renders only for a new check and
   *  is gone after its one sweep (a lingering element would replay on every relayout). */
  function useClimb(value) {
    var prev = useRef(value), count = useRef(0);
    var s = useState(0), shown = s[0], setShown = s[1];
    useEffect(function () {
      var was = prev.current;
      prev.current = value;
      if (value == null || was == null || !(value > was) || !motion()) return undefined;
      var k = ++count.current;
      setShown(k);
      function hide() { setShown(function (x) { return x === k ? 0 : x; }); }
      var tm = setTimeout(hide, 950);
      return function () { clearTimeout(tm); hide(); };
    }, [value]);
    return shown;
  }

  /** True for the first moments after ``ready``: rows carry the entrance class (A) only then, because Chrome replays
   *  a table row's CSS animation on every relayout (a resize) while the class stays. */
  function useFresh(ready) {
    var s = useState(true), fresh = s[0], setFresh = s[1];
    useEffect(function () {
      if (!ready || !fresh) return undefined;
      var tm = setTimeout(function () { setFresh(false); }, 1400);
      return function () { clearTimeout(tm); };
    }, [ready]);
    return fresh;
  }

  /** "#01"-style mono number of an eyebrow. */
  function nth(i) { return "#" + (i < 10 ? "0" : "") + i; }
  function Eyebrow(props) {
    return h("div", { className: cx("tnr-section-title", props.className) },
      props.n != null ? h("span", { className: "tnr-eyebrow-n" }, nth(props.n)) : null, props.children);
  }

  // ------------------------------------------------------------------------------------------------ small parts
  function Kbd(props) { return h("kbd", { className: "tnr-kbd" }, props.children); }

  /** The tier's display name next to its code: Probation, Under review, Tenured, Always asks. */
  function tierLabel(tier, capped) {
    if (capped) return t("tier.label.cap");
    if (tier === "trusted") return t("tier.trusted.label");
    if (tier === "alone") return t("tier.label.alone");
    if (tier === "notify") return t("tier.label.notify");
    return t("tier.label.ask");
  }
  /** A flat rectangular tier chip: outlined (T1, T2), filled with the accent (T3), dashed (CAP). When the tier
   *  changes between two renders, the old chip dissolves in dither while the new one prints (C, D). */
  function TierChip(props) {
    var tier = props.tier, capped = !!props.capped;
    var id = capped ? "cap" : tier;
    var prev = useRef(id);
    var gs = useState(null), ghost = gs[0], setGhost = gs[1];
    var chipRef = useRef(null), ghostRef = useRef(null), st = useRef({ raf: 0 });
    if (prev.current !== id) {
      var was = prev.current;
      prev.current = id;
      if (motion() && !props.still) { if (ghost !== was) setGhost(was); }
    }
    useEffect(function () {
      if (!ghost) return undefined;
      var s = st.current;
      setMask(chipRef.current, 0);
      tween(s, 520, 0, function (k) {
        setMask(ghostRef.current, 16 - k * 17);
        setMask(chipRef.current, k * 17 - 1);
      }, function () { setMask(chipRef.current, 16); setGhost(null); });
      return function () { cancelAnimationFrame(s.raf); setMask(chipRef.current, 16); };
    }, [ghost]);
    function chip(which, ref, extra) {
      var cap = which === "cap";
      return h("span", Object.assign({
        ref: ref, className: cx("tnr-tier", "tnr-tier--" + which, extra),
        title: cap ? t("tier.capped.title") : which === "trusted" ? t("tier.trusted.title") :
          t("tier.chip.title", { tier: TIER[which], name: tierLabel(which) + " · " + tierName(which) })
      }, extra ? { "aria-hidden": true } : null), cap ? t("tier.capped.chip") : TIER[which]);
    }
    return h("span", { className: cx("tnr-tierwrap", props.label && "has-label") },
      h("span", { className: "tnr-tier-stack" }, chip(id, chipRef), ghost ? chip(ghost, ghostRef, "tnr-tier--ghost") : null),
      props.label ? h("span", { className: "tnr-tier-label" }, tierLabel(tier, capped)) : null);
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
      // One colour: a destructive action is an accent outline with an explicit label; Hermes' own red stays inside its
      // confirmation dialog.
      var danger = k === "danger" || k === "danger-ghost";
      return h(UI.Button, {
        type: "button", size: "sm", className: cx("tnr-focus", danger && "tnr-btn-danger", props.className), onClick: props.onClick,
        disabled: props.disabled, title: props.title, "aria-live": props.live ? "polite" : undefined,
        ghost: k === "ghost", outlined: !k || danger
      }, props.children);
    }
    return h("button", {
      type: "button", className: cx("tnr-btn", "tnr-focus", k && "tnr-btn--" + k, props.className),
      onClick: props.onClick, disabled: props.disabled, title: props.title, "aria-live": props.live ? "polite" : undefined
    }, props.children);
  }

  /** A button that asks once more before it acts: Hermes' own confirmation dialog (title, consequence, confirm
   *  label) when the dashboard SDK has one; else a first click arms it and a second click within 4 s confirms. */
  function ConfirmBtn(props) {
    var s = useState(false), armed = s[0], setArmed = s[1];
    var b = useState(false), busy = b[0], setBusy = b[1];
    var o = useState(false), open = o[0], setOpen = o[1];
    if (UI.ConfirmDialog && props.dialogTitle) {
      var run = function () {
        setBusy(true);
        Promise.resolve(props.onConfirm()).then(function () { setBusy(false); setOpen(false); },
          function () { setBusy(false); setOpen(false); });
      };
      return h(Fragment, null,
        h(Btn, { kind: props.kind, disabled: props.disabled || busy, title: props.title,
          onClick: function () { setOpen(true); } }, busy ? "…" : props.children),
        h(UI.ConfirmDialog, { open: open, title: props.dialogTitle, description: props.dialogDesc,
          confirmLabel: typeof props.children === "string" ? props.children : props.confirm || t("confirm.default"),
          destructive: props.destructive !== false,
          loading: busy, onCancel: function () { if (!busy) setOpen(false); }, onConfirm: run }));
    }
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
    if (ty.trusted) return { text: t(ty.reversible ? "missing.trusted_undo" : "missing.trusted"), tone: "muted" };
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
  /** The guarantee in plain words ("At most about 1 in 48 ..."), the statistical detail as its tooltip. */
  function Guarantee(props) {
    var g = props.g;
    var detail = guaranteeText(g);
    if (!g || g.capped || !(g.aoql > 0)) return h("span", { className: props.className }, detail);
    var plain = t("guarantee.plain", { k: String(Math.max(1, Math.round(1 / g.aoql))) }) + (g.conditional ? " · " + t("flag.provisional") : "");
    return h("span", { className: cx("tnr-plain", props.className), title: detail, tabIndex: 0, "aria-label": plain + " " + detail }, plain);
  }

  var PRESET_IDS = ["careful", "balanced", "fast", "custom"];
  function presetName(p) { return PRESET_IDS.indexOf(p) >= 0 ? t("preset." + p) : p; }
  function profileSettings(st, info) {
    var parts = [t("profile.preset", { preset: presetName(st.preset) }), t("profile.spot", { rate: oneIn(st.spot) })];
    var start = startOf(info || { settings: st });
    if (start) parts.push(start === "trusted" ? t("profile.start_trusted") : t("profile.start_probation"));
    if (st.strict) parts.push(t("profile.strict"));
    if (st.pending) parts.push(t("profile.pending"));
    if (st.copy_pending) parts.push(t("profile.copy_pending"));
    return parts.join(" · ");
  }

  function cellTitle(ty) {
    var stakes = t("stakes.group." + ty.stakes);
    var tierNow = ty.trusted && !ty.capped ? t("tier.trusted.title") :
      t("cell.tier_now", { tier: TIER[ty.effective_tier], name: tierName(ty.effective_tier) });
    var lines = [t(ty.reversible ? "cell.kind_reversible" : "cell.kind_irreversible", { type: ty.type, stakes: stakes }),
      ty.tier !== ty.effective_tier && !ty.trusted ? tierNow + " · " + t("cell.held", { tier: TIER[ty.tier] }) : tierNow,
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
          h("div", { className: "tnr-counter tnr-in", style: { "--i": i } },
            h("span", { className: "tnr-counter-tag", "aria-hidden": true }, nth(i + 1)),
            h("span", { className: "tnr-counter-n" }, num(c.n)),
            h("span", { className: "tnr-counter-label" }, c.label),
            h("span", { className: "tnr-counter-sub" }, c.sub)));
      }),
      h("span", { className: "tnr-counter-window" }, t("counters.window")));
  }

  var VIEWS = [
    { id: "map", key: "m" },            // label: the catalog key view.<id>
    { id: "models", key: "b" },
    { id: "community", key: "c" },
    { id: "switch", key: "w" },
    { id: "passport", key: "p" },
    { id: "undo", key: "u" },
    { id: "settings", key: "s" }
  ];

  function Tabs(props) {
    var List = UI.TabsList || "div", Trigger = UI.TabsTrigger || "button";
    var navRef = useRef(null);
    var es = useState(""), edges = es[0], setEdges = es[1];
    // A narrow screen scrolls the strip: an edge fades where more tabs hide, and the active tab is scrolled into view.
    function measure() {
      var el = navRef.current;
      if (!el) return;
      var max = el.scrollWidth - el.clientWidth, x = Math.abs(el.scrollLeft);
      var e = max <= 1 ? "" : x <= 1 ? "end" : x >= max - 1 ? "start" : "both";
      if (e !== edges) setEdges(e);
    }
    useEffect(function () {
      var el = navRef.current;
      if (!el) return;
      var tab = el.querySelector(".tnr-tab.is-active");
      if (tab && tab.scrollIntoView && el.scrollWidth > el.clientWidth + 1) {
        try { tab.scrollIntoView({ block: "nearest", inline: "nearest", behavior: motion() ? "smooth" : "auto" }); } catch (e) { /* old engines */ }
      }
      measure();
    }, [props.view, props.width]);
    return h("nav", { ref: navRef, className: "tnr-tabs", "data-edges": edges, "aria-label": t("tabs.aria"), onScroll: measure },
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
          }, h("span", { className: "tnr-tab-n", "aria-hidden": true }, "0" + (VIEWS.indexOf(v) + 1)), t("view." + v.id), badge);
        })),
      h("button", { type: "button", className: "tnr-chip-btn tnr-tabs-help", onClick: props.onHelp, title: t("help.aria"), "aria-label": t("help.aria") },
        h(Kbd, null, "?")));
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
    // A spot check that passed: one more spot check, no more faults (E).
    var scan = useClimb(ty ? ty.spot_checks || 0 : null);
    if (!ty) return h("td", { className: "tnr-cell tnr-cell--none" }, h("span", { className: "tnr-none" }, "—"));
    var miss = missing(ty);
    var shown = shownTier(ty);
    var held = ty.tier !== ty.effective_tier && !ty.trusted;
    var flags = [];
    if (ty.provisional) {
      flags.push(h(Flag, { key: "p", kind: "prov", title: t("flag.carried_over_title", { n: ty.provisional, count: String(ty.provisional) }) },
        t("flag.carried_over_n", { n: ty.provisional })));
    }
    if (ty.unresolved_fault) flags.push(h(Flag, { key: "f", kind: "fault", title: t("flag.fault_on_record_title") }, t("flag.fault_on_record")));
    return h("td", {
      className: cx("tnr-cell", "tnr-cell--" + (ty.capped ? "cap" : shown), ty.provisional && "is-prov",
        (ty.trial_left || ty.trial_wait) && "is-trial"),
      title: cellTitle(ty)
    },
      h("div", { className: "tnr-cell-top" },
        h(TierChip, { tier: shown, capped: ty.capped }),
        ty.capped ? h("span", { className: "tnr-cell-ev" }, num(ty.successes + ty.faults), h("span", { className: "tnr-dim" }, t("cell.asked_suffix")))
          : ty.trusted ? null : h("span", { className: "tnr-cell-ev" }, num(ty.series), h("span", { className: "tnr-dim" }, "/" + num(ty.required)))),
      h(DitherBar, Object.assign(barProps(ty), { delay: 120 + (props.row || 0) * 40 })),
      h("div", { className: "tnr-cell-mid" },
        ty.capped ? h("span", null, t("count.faults", { n: ty.faults })) : h("span", null, t("count.sessions", { n: ty.sessions })),
        held ? h("span", { className: "tnr-held" }, t("cell.held", { tier: TIER[ty.tier] })) : null),
      h("div", { className: "tnr-cell-miss tnr-tone--" + miss.tone }, miss.text),
      flags.length ? h("div", { className: "tnr-cell-flags" }, flags) : null,
      scan ? h("span", { key: scan, className: "tnr-scan", "aria-hidden": true }) : null);
  }

  function MapView(props) {
    var profiles = props.profiles;
    var cols = useMemo(function () { return columns(profiles); }, [profiles]);
    var rows = props.rows;
    var fresh = useFresh(rows.length > 0);
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
                h("span", { className: "tnr-profile-name" }, t("profile.name", { profile: "\u0001" }).split("\u0001")[0], h("bdi", null, grp.profile),
                  t("profile.name", { profile: "\u0001" }).split("\u0001")[1] || ""),
                h("span", { className: "tnr-dim" }, grp.info.current ? t("profile.this_dashboard") : t("profile.read_only")),
                grp.info.suspended ? h(Flag, { kind: "warn" }, t("profile.sessions_suspended", { n: grp.info.suspended })) : null,
                grp.info.settings ? h("span", { className: "tnr-dim tnr-profile-preset" }, profileSettings(grp.info.settings, grp.info)) : null)),
            grp.rows.map(function (x) {
              var r = x.r, a = r.agent;
              var byType = {};
              a.types.forEach(function (ty) { byType[ty.type] = ty; });
              var tot = a.totals || {};
              return h("tr", {
                key: r.key, className: cx("tnr-map-row", fresh && "tnr-in", x.i === props.focus && "is-focus"), style: { "--i": x.i },
                onClick: function () { props.onFocus(x.i); props.onOpen(r); },
                "aria-selected": x.i === props.focus
              },
                h("th", { scope: "row", className: "tnr-td-agent" },
                  h("div", { className: "tnr-agent-head" },
                    h(Emblem, { share: autonomyShare(a.types), size: 30, cells: 30, delay: x.i * 40, developMs: 900 }),
                    h("div", { className: "tnr-agent-model" }, a.model, h("bdi", { className: "tnr-dim" }, "@" + a.provider))),
                  h("div", { className: "tnr-agent-tot" }, totalsLines(tot)),
                  h("div", { className: "tnr-agent-flags" },
                    a.provisional ? h(Flag, { kind: "prov" }, t("flag.provisional")) : null,
                    a.trial ? h(Flag, { kind: "warn" }, t("flag.trial")) : null,
                    a.unresolved_fault ? h(Flag, { kind: "fault" }, t("flag.fault_on_record")) : null,
                    h("span", { className: "tnr-open-hint" }, t("map.open_hint"), h(Kbd, null, "↵")))),
                cols.map(function (g) {
                  return g.types.map(function (ty) { return h(Cell, { key: ty, t: byType[ty], row: x.i }); });
                }));
            }));
        })));

    var cards = h("div", { className: "tnr-map-cards" },
      byProfile.map(function (grp) {
        return h("section", { key: grp.profile, className: "tnr-card-group" },
          h("div", { className: "tnr-map-profile tnr-map-profile--card" },
            h("span", { className: "tnr-profile-name" }, t("profile.name", { profile: "\u0001" }).split("\u0001")[0], h("bdi", null, grp.profile),
              t("profile.name", { profile: "\u0001" }).split("\u0001")[1] || ""),
            h("span", { className: "tnr-dim" }, grp.info.current ? t("profile.this_dashboard") : t("profile.read_only")),
            grp.info.suspended ? h(Flag, { kind: "warn" }, t("profile.suspended", { n: grp.info.suspended })) : null),
          grp.rows.map(function (x) {
            var r = x.r, a = r.agent, tot = a.totals || {};
            return h("button", {
              type: "button", key: r.key, className: cx("tnr-agent-card", fresh && "tnr-in", x.i === props.focus && "is-focus"), style: { "--i": x.i },
              onClick: function () { props.onFocus(x.i); props.onOpen(r); }
            },
              h("div", { className: "tnr-agent-head" },
                h(Emblem, { share: autonomyShare(a.types), size: 36, cells: 36, delay: x.i * 40, developMs: 900 }),
                h("div", { className: "tnr-agent-model" }, a.model, h("bdi", { className: "tnr-dim" }, "@" + a.provider))),
              h("div", { className: "tnr-agent-tot" }, totals(tot)),
              h("div", { className: "tnr-card-types" },
                a.types.slice().sort(function (p, q) {
                  return STAKES.indexOf(p.stakes) - STAKES.indexOf(q.stakes) || (p.type < q.type ? -1 : 1);
                }).map(function (ty) {
                  var miss = missing(ty);
                  return h("div", { key: ty.type, className: "tnr-card-type" },
                    h(TierChip, { tier: shownTier(ty), capped: ty.capped }),
                    h("code", { className: "tnr-card-type-name" }, ty.type),
                    h("span", { className: "tnr-card-type-ev" }, ty.capped ? t("common.capped") : ty.trusted ? "" : num(ty.series) + "/" + num(ty.required)),
                    h(DitherBar, Object.assign(barProps(ty), { className: "tnr-card-type-bar", delay: 120 + x.i * 40 })),
                    h("span", { className: "tnr-card-type-miss tnr-tone--" + miss.tone },
                      ty.tier !== ty.effective_tier && !ty.trusted ? t("cell.held", { tier: TIER[ty.tier] }) :
                        ty.provisional ? t("flag.carried_over_n", { n: ty.provisional }) + " · " + miss.text :
                          ty.unresolved_fault ? t("flag.fault_on_record") + " · " + miss.text : miss.text));
                })));
          }));
      }));

    return h("div", { className: "tnr-mapview" },
      table, cards,
      h(Legend, { spot: props.settings && props.settings.spot,
        trusted: rows.some(function (r) { return r.agent.types.some(function (ty) { return ty.trusted && !ty.capped; }); }) }),
      h(Transitions, { items: props.transitions }));
  }

  function Legend(props) {
    return h("div", { className: "tnr-legend" },
      props.trusted ? h("span", null, h(TierChip, { tier: "trusted", label: true }), " " + t("legend.trusted")) : null,
      h("span", null, h(TierChip, { tier: "ask", label: true }), " " + t("legend.ask")),
      h("span", null, h(TierChip, { tier: "notify", label: true }), " " + t("legend.notify")),
      h("span", null, h(TierChip, { tier: "alone", label: true }), " " + t("legend.alone", { share: props.spot ? oneIn(props.spot) : t("legend.a_share") })),
      h("span", null, h(TierChip, { capped: true, label: true }), " " + t("legend.capped")),
      h("span", null, h(LegendBar), h("span", { className: "tnr-mono" }, "n/N"), " " + t("legend.series")),
      h("span", null, h(Flag, { kind: "prov" }, t("flag.carried_over")), " " + t("legend.carried")));
  }

  function LegendBar() {
    return h("span", { className: "tnr-legend-bar" }, h(DitherBar, { value: 0.55 }));
  }

  function Transitions(props) {
    return h("section", { className: "tnr-transitions", "aria-live": "polite" },
      h(Eyebrow, { n: 2 }, t("transitions.title")),
      props.items.length ? h("ol", { className: "tnr-trans-list" },
        props.items.slice(0, 8).map(function (x) {
          return h("li", { key: x.id },
            h("span", { className: "tnr-mono tnr-dim" }, hms(x.at)),
            h("span", null, x.agent),
            h("code", null, x.type),
            h("span", { className: "tnr-trans-move" }, h(TierChip, { tier: x.from, capped: false, still: true }), " " + t("common.arrow") + " ", h(TierChip, { tier: x.to, capped: false, still: true, label: true })),
            h("span", { className: "tnr-dim" }, x.why === "changed" ? t("transitions.why_changed") : t("transitions.why." + x.why)));
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
    var fresh = useFresh(true);
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
          h(Emblem, { share: autonomyShare(a.types), size: 84, cells: 42, className: "tnr-drawer-emblem" }),
          h("div", { className: "tnr-drawer-id" },
            h("div", { className: "tnr-drawer-eyebrow" }, "#", t(mine ? "drawer.eyebrow" : "drawer.eyebrow_read_only", { profile: row.profile })),
            h("div", { className: "tnr-drawer-title" }, a.model, h("bdi", { className: "tnr-dim" }, "@" + a.provider)),
            h("div", { className: "tnr-agent-tot" }, totals(tot),
              row.info.suspended ? h(Flag, { kind: "warn" }, t("profile.suspended", { n: row.info.suspended })) : null)),
          h("span", { ref: closeRef }, h(Btn, { kind: "ghost", onClick: props.onClose, title: t("drawer.close_title") }, t("drawer.close")))),
        h("div", { className: "tnr-drawer-body" },
          h(Eyebrow, { n: 1 }, t("drawer.types_title")),
          h("table", { className: "tnr-dtable tnr-dtable--types" },
            h("thead", null, h("tr", null,
              h("th", null, t("th.type")), h("th", null, t("th.tier")), h("th", { className: "tnr-num" }, t("th.series")),
              h("th", { className: "tnr-num" }, t("th.sessions")), h("th", { className: "tnr-num" }, t("th.faults_checks")), h("th", null, ""))),
            h("tbody", null, types.map(function (ty, ti) {
              var miss = missing(ty);
              return h(Fragment, { key: ty.type },
                h("tr", { className: cx("tnr-dtable-main", fresh && "tnr-in"), style: { "--i": ti } },
                  h("td", null, h("div", { className: "tnr-type-line" }, h("span", { className: "tnr-eyebrow-n" }, nth(ti + 1)), h("code", null, ty.type)),
                    h("div", { className: "tnr-dim tnr-small" },
                      ty.reversible ? t("drawer.stakes_reversible", { stakes: t("stakes." + ty.stakes) }) : t("stakes." + ty.stakes)),
                    h(DitherBar, Object.assign(barProps(ty), { className: "tnr-drawer-bar", delay: 200 + ti * 40 }))),
                  h("td", null, h(TierChip, { tier: shownTier(ty), capped: ty.capped, label: true }),
                    ty.tier !== ty.effective_tier && !ty.trusted ? h("div", { className: "tnr-held" }, t("cell.held", { tier: TIER[ty.tier] })) : null),
                  h("td", { className: "tnr-num" }, ty.capped || ty.trusted ? "—" : num(ty.series) + "/" + num(ty.required)),
                  h("td", { className: "tnr-num" }, ty.capped || ty.trusted ? "—" : num(ty.sessions) + "/" + SESSIONS),
                  h("td", { className: "tnr-num" }, num(ty.faults) + " / " + num(ty.successes + ty.faults)),
                  h("td", { className: "tnr-dtable-actions" },
                    h(ConfirmBtn, {
                      disabled: !mine, confirm: t("drawer.flag.confirm"),
                      dialogTitle: t("confirm.flag.title", { type: ty.type }), dialogDesc: t("confirm.flag.desc", { type: ty.type }),
                      title: mine ? t("drawer.flag.title") : t("drawer.own_profile_only"),
                      onConfirm: function () {
                        return act("/flag", { agent: a.agent, type: ty.type }, function (r) {
                          return t("drawer.flag.done", { type: ty.type, tier: TIER[r.tier] });
                        });
                      }
                    }, t("drawer.flag.button")),
                    h(ConfirmBtn, {
                      disabled: !mine, confirm: t("drawer.revoke.confirm"),
                      dialogTitle: t("confirm.revoke.title", { type: ty.type }), dialogDesc: t("confirm.revoke.desc", { type: ty.type }),
                      title: mine ? t("drawer.revoke.title") : t("drawer.own_profile_only"),
                      onConfirm: function () {
                        return act("/revoke", { agent: a.agent, type: ty.type }, function () { return t("drawer.revoke.done", { type: ty.type }); });
                      }
                    }, t("drawer.revoke.button")))),
                h("tr", { className: cx("tnr-dtable-sub", fresh && "tnr-in"), style: { "--i": ti } },
                  h("td", { colSpan: 6 },
                    h("span", { className: "tnr-mobile-only" }, t("drawer.mobile_summary", {
                      sessions: ty.capped ? t("common.capped") : t("drawer.sessions_of", { n: ty.sessions, total: String(SESSIONS) }),
                      faults: ty.faults, checks: ty.successes + ty.faults })),
                    h("span", { className: "tnr-tone--" + miss.tone }, miss.text),
                    ty.provisional ? h("span", null, " · " + t("flag.carried_over_provisional", { n: ty.provisional })) : null,
                    ty.unresolved_fault ? h("span", { className: "tnr-tone--fault" }, " · " + t("flag.fault_on_record")) : null,
                    ty.trusted && !ty.capped ? h("div", { className: "tnr-guarantee tnr-dim" }, t("guarantee.trusted")) :
                      ty.effective_tier === "alone" ? h("div", { className: "tnr-guarantee" }, h(Guarantee, { g: ty.guarantee })) : null)));
            }))),
          h("div", { className: "tnr-drawer-revoke" },
            h(ConfirmBtn, {
              kind: "danger-ghost", disabled: !mine, confirm: t("drawer.revoke_all.confirm"),
              dialogTitle: t("confirm.revoke_all.title"), dialogDesc: t("confirm.revoke_all.desc", { agent: a.agent }),
              onConfirm: function () {
                return act("/revoke", { agent: a.agent, all: true }, function (r) {
                  return t("drawer.revoke_all.done", { n: r.revoked.length, count: String(r.revoked.length) });
                });
              }
            }, t("drawer.revoke_all.button")),
            h("span", { className: "tnr-dim tnr-small" }, mine ? t("drawer.revoke_note") :
              t("drawer.revoke_note_other", { cmd: "hermes -p " + row.profile + " tenure revoke" }))),
          h("div", { className: "tnr-section-title tnr-tl-head" },
            h("span", null, h("span", { className: "tnr-eyebrow-n" }, nth(2)), t("timeline.title")),
            h(Sel, { value: filter, onChange: setFilter, label: t("timeline.filter_label"),
              options: [["all", t("timeline.all_types")]].concat(types.map(function (ty) { return [ty.type, ty.type]; })) })),
          h("div", { className: "tnr-dim tnr-small tnr-tl-note" }, t("timeline.note")),
          tl.error ? h("div", { className: "tnr-error" }, errText(tl.error)) : h(Timeline, { events: shown }))));
  }

  // ---------------------------------------------------------------------------------------------------- models
  /** The 95% range as a dither bar on a dotted axis, the observed rate a solid tick. Draws in left to right with a
   *  short dithered front (F). */
  function paintRange(cv, lo, hi, p, front) {
    var w = cv.clientWidth, hgt = cv.clientHeight;
    if (!w || !hgt) return;
    var x = prep(cv, w, hgt);
    if (!x) return;
    var c = 2, cols = Math.ceil(w / c), rows = Math.max(1, Math.floor(hgt / c)), mid = Math.floor(rows / 2);
    var L = lo * w, H = Math.max(lo * w + c, hi * w), P = p == null ? null : p * w, F = front * (w + 12), soft = 10;
    for (var j = 0; j < rows; j++) for (var i = 0; i < cols; i++) {
      var X = i * c + c / 2, v = 0;
      if (j === mid) v = 0.22;
      if (X >= L - 3 && X <= H + 3 && j >= mid - 1 && j <= mid + 1) v = X < L ? 0.5 : X > H ? 0.5 : 1;
      if (P != null && Math.abs(X - P) <= c && Math.abs(j - mid) <= 2) v = 1;
      if (X > F) v = 0; else if (X > F - soft) v *= (F - X) / soft;
      if (v * 16 > BAYER[j & 3][i & 3]) x.fillRect(i * c, j * c, c - 0.5, c - 0.5);
    }
  }
  function Interval(props) {
    var ref = useRef(null), st = useRef({ key: "", raf: 0 });
    var max = props.max || 1;
    var lo = Math.min(1, props.low / max), hi = Math.min(1, props.high / max), p = props.rate == null ? null : Math.min(1, props.rate / max);
    useEffect(function () {
      var cv = ref.current, s = st.current;
      if (!cv || !cv.clientWidth) return;
      var key = [lo, hi, p, getComputedStyle(cv).color].join("|"), first = !s.key;
      if (key === s.key) return;
      s.key = key;
      if (first && motion()) tween(s, 650, props.delay || 0, function (k) { paintRange(cv, lo, hi, p, easeOut(k)); });
      else { cancelAnimationFrame(s.raf); paintRange(cv, lo, hi, p, 1); }
    });
    useEffect(function () { return function () { cancelAnimationFrame(st.current.raf); }; }, []);
    return h("canvas", { ref: ref, className: "tnr-interval", "aria-hidden": true });
  }

  function Stale(props) {
    return props.res.error && props.res.data ? h("div", { className: "tnr-msg tnr-tone--warn" },
      t("stale.message", { error: errText(props.res.error), time: hms(props.res.at) })) : null;
  }

  var RANK_MIN = 20;        // checks on a type before a model is ranked on it

  function ModelsView(props) {
    var res = usePoll(function () { return apiGet("/models", { raw: props.raw }); }, [props.raw, props.version]);
    var fresh = useFresh(!!res.data);
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
      byType.map(function (g, gi) {
        // Ranked from RANK_MIN checks: below that the 95% range spans most of the axis and orders nothing.
        var ranked = g.rows.filter(function (r) { return r.successes + r.faults >= RANK_MIN; });
        var waiting = g.rows.filter(function (r) { return r.successes + r.faults < RANK_MIN; });
        var max = Math.max.apply(null, ranked.map(function (r) { return r.high; }).concat([0.05]));
        max = Math.min(1, Math.ceil(max * 20) / 20);
        var bench = g.rows[0].benchmark;
        var card = g.rows[0].public || {};
        var withPublic = g.rows.filter(function (r) { return r.public && r.public.new != null; }).length;
        var showPublic = !!bench && withPublic * 2 >= g.rows.length;    // the public column only when mostly filled
        return h("section", { key: g.type, className: "tnr-model-block" },
          h("div", { className: "tnr-model-head" }, h("span", { className: "tnr-eyebrow-n" }, nth(gi + 1)), h("code", null, g.type),
            h("span", { className: "tnr-dim" }, t("count.agents", { n: g.rows.length }))),
          h("div", { className: cx("tnr-model-split", !showPublic && "is-single") },
            h("div", { className: "tnr-model-personal" },
              h(Eyebrow, { n: 1 }, t("models.personal_title")),
              ranked.length ? h("table", { className: "tnr-dtable tnr-dtable--models" },
                h("thead", null, h("tr", null,
                  h("th", { className: "tnr-num" }, "#"), h("th", null, t("th.agent")), h("th", { className: "tnr-num" }, t("th.faults_checks")),
                  h("th", { className: "tnr-num" }, t("th.rate")), h("th", null, t("th.range", { max: pct(max) })), h("th", { className: "tnr-num" }, t("th.sessions")))),
                h("tbody", null, ranked.map(function (r, i) {
                  var n = r.successes + r.faults;
                  return h("tr", { key: r.profile + r.agent, className: fresh ? "tnr-in" : undefined, style: { "--i": i } },
                    h("td", { className: "tnr-num tnr-dim tnr-mono" }, nth(i + 1)),
                    h("td", null, h("div", null, r.model, h("bdi", { className: "tnr-dim" }, "@" + r.provider)),
                      h("div", { className: "tnr-dim tnr-small" }, t("common.profile", { profile: r.profile }))),
                    h("td", { className: "tnr-num" }, num(r.faults) + " / " + num(n)),
                    h("td", { className: "tnr-num" }, r.enough ? pct(r.rate) : h("span", { className: "tnr-dim" }, t("models.not_enough"))),
                    h("td", null, h("div", { className: "tnr-interval-cell" }, h(Interval, { low: r.low, high: r.high, rate: r.rate, max: max, delay: 150 + i * 60 }),
                      h("span", { className: "tnr-mono tnr-small" }, pct(r.low) + "–" + pct(r.high)))),
                    h("td", { className: "tnr-num" }, num(r.sessions_in_series)));
                }))) : null,
              waiting.length ? h("div", { className: "tnr-waiting" },
                h("div", { className: "tnr-waiting-title" }, t("models.not_ranked")),
                h("div", { className: "tnr-dim tnr-small" }, t("models.not_ranked_note", { n: RANK_MIN })),
                h("ul", null, waiting.map(function (r) {
                  return h("li", { key: r.profile + r.agent }, r.model, h("bdi", { className: "tnr-dim" }, "@" + r.provider),
                    h("span", { className: "tnr-dim tnr-small" }, " · " + t("common.profile", { profile: r.profile })));
                }))) : null),
            showPublic ? h("div", { className: "tnr-model-public" },
              h(Eyebrow, { n: 2 }, t("models.public_title")),
              h("div", { className: "tnr-public-bench" }, bench, h("span", { className: "tnr-dim" }, card.version ? " · " + card.version : "")),
              h("table", { className: "tnr-dtable" }, h("tbody", null, g.rows.map(function (r) {
                return h("tr", { key: r.profile + r.agent },
                  h("td", null, r.model),
                  h("td", { className: "tnr-num" }, r.public && r.public.new != null ? t("common.percent", { v: dec1(r.public.new) }) :
                    h("span", { className: "tnr-dim" }, t("common.no_public_measure"))));
              }))),
              h("div", { className: "tnr-public-src tnr-small tnr-dim" },
                t(card.accessed ? "models.source_accessed" : "models.source", { source: card.source || "", accessed: card.accessed || "" })),
              h("div", { className: "tnr-public-note" }, t("models.public_note")))
              : h("div", { className: "tnr-model-public is-folded" },
                h("span", { className: "tnr-dim tnr-small" }, bench ? t("common.no_public_measure") : t("models.no_public")),
                h("span", { className: "tnr-dim tnr-small" }, " · " + t("models.public_note")))));
      }));
  }

  // --------------------------------------------------------------------------------------------------- community
  var COMMUNITY_REPO = "github.com/otsoa-dubief/tenure-community";   // tenure/community.py REPO

  /** The community board the owner downloaded into the plugin's data folder (GET /community), never fetched from
   *  the network. Without one: what it is, that nothing is shared automatically, and how to contribute. */
  function CommunityView(props) {
    var res = usePoll(function () { return apiGet("/community"); }, [props.version], true, PASSPORT_MS);
    var fresh = useFresh(!!res.data);
    if (res.error && !res.data) return h("div", { className: "tnr-error" }, errText(res.error));
    if (!res.data) return h("div", { className: "tnr-dim tnr-pad" }, t("common.loading"));
    var board = res.data.board;
    if (!board || !(board.families || []).length) {
      return h("div", { className: "tnr-community" }, h(Stale, { res: res }),
        h(Empty, { title: t("community.empty.title") },
          h("p", null, t("community.empty.what")),
          h("p", null, t("community.empty.how", { repo: COMMUNITY_REPO })),
          h(CopyCmd, { cmd: "hermes tenure share" }),
          h("p", { className: "tnr-community-where" }, t("community.empty.where", { path: res.data.path || "community-board.json" }))));
    }
    return h("div", { className: "tnr-models tnr-community" }, h(Stale, { res: res }),
      h("p", { className: "tnr-lede" }, t("community.lede"), h("b", null, t("community.lede_bold")), " ", t("community.ranking")),
      h("div", { className: "tnr-dim tnr-small tnr-community-meta" },
        t("community.generated", { records: t("count.records", { n: board.records || 0 }), date: board.generated || "—" })),
      board.families.map(function (g, gi) {
        var ranked = g.models.filter(function (r) { return r.checks >= RANK_MIN; });
        var waiting = g.models.filter(function (r) { return r.checks < RANK_MIN; });
        var max = Math.max.apply(null, ranked.map(function (r) { return r.high; }).concat([0.05]));
        max = Math.min(1, Math.ceil(max * 20) / 20);
        return h("section", { key: g.family, className: "tnr-model-block" },
          h("div", { className: "tnr-model-head" }, h("span", { className: "tnr-eyebrow-n" }, nth(gi + 1)), h("code", null, g.family),
            h("span", { className: "tnr-dim" }, t("count.models", { n: g.models.length }))),
          h("div", { className: "tnr-model-personal tnr-community-table" },
            ranked.length ? h("table", { className: "tnr-dtable tnr-dtable--models" },
              h("thead", null, h("tr", null,
                h("th", { className: "tnr-num" }, "#"), h("th", null, t("th.model")), h("th", { className: "tnr-num" }, t("th.faults_checks")),
                h("th", { className: "tnr-num" }, t("th.rate")), h("th", null, t("th.range", { max: pct(max) })), h("th", { className: "tnr-num" }, t("th.contributors")))),
              h("tbody", null, ranked.map(function (r, i) {
                return h("tr", { key: r.model + "@" + r.provider, className: fresh ? "tnr-in" : undefined, style: { "--i": i } },
                  h("td", { className: "tnr-num tnr-dim tnr-mono" }, nth(i + 1)),
                  h("td", null, h("div", null, r.model, h("bdi", { className: "tnr-dim" }, "@" + r.provider))),
                  h("td", { className: "tnr-num" }, num(r.faults) + " / " + num(r.checks)),
                  h("td", { className: "tnr-num" }, pct(r.rate)),
                  h("td", null, h("div", { className: "tnr-interval-cell" }, h(Interval, { low: r.low, high: r.high, rate: r.rate, max: max, delay: 150 + i * 60 }),
                    h("span", { className: "tnr-mono tnr-small" }, pct(r.low) + "–" + pct(r.high)))),
                  h("td", { className: "tnr-num" }, num(r.contributors)));
              }))) : null,
            waiting.length ? h("div", { className: "tnr-waiting" },
              h("div", { className: "tnr-waiting-title" }, t("models.not_ranked")),
              h("div", { className: "tnr-dim tnr-small" }, t("models.not_ranked_note", { n: RANK_MIN })),
              h("ul", null, waiting.map(function (r) {
                return h("li", { key: r.model + "@" + r.provider }, r.model, h("bdi", { className: "tnr-dim" }, "@" + r.provider),
                  h("span", { className: "tnr-dim tnr-small" }, " · " + num(r.faults) + " / " + num(r.checks)));
              }))) : null));
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
    var fresh = useFresh(!!res);
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
          h("span", { className: "tnr-switch-pair" }, h("b", null, res.from), " " + t("common.arrow") + " ", h("b", null, res.to)),
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
            h("tbody", null, res.types.map(function (ty, ri) {
              var st = STATUS[ty.status] || { tone: "muted" };
              var c = ty.card || {};
              var delta = c.delta != null ? t("switch.delta", { delta: (c.delta > 0 ? "+" : "") + dec1(c.delta) }) : "";
              return h("tr", { key: ty.type, className: fresh ? "tnr-in" : undefined, style: { "--i": ri } },
                h("td", null, h("code", null, ty.type), h("div", { className: "tnr-dim tnr-small" }, t("stakes." + ty.stakes))),
                h("td", null, h(Flag, { kind: st.tone }, statusLabel(ty.status))),
                h("td", null, h(TierChip, { tier: shownTier(ty.old), capped: ty.old.capped }), " ",
                  h("span", { className: "tnr-mono" }, ty.old.capped ? t("common.capped") : num(ty.old.series) + "/" + num(ty.old.required))),
                h("td", null, h(TierChip, { tier: shownTier(ty.new), capped: ty.new.capped, label: true }), " ",
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

  /** The seal: a dithered stamp ring, printed at the end of the passport's entrance when it verifies. */
  function paintSeal(cv, size, dev) {
    var x = prep(cv, size, size);
    if (!x) return;
    var n = 36, c = size / n, d = dev * 16;
    for (var j = 0; j < n; j++) for (var i = 0; i < n; i++) {
      var dx = i - n / 2 + 0.5, dy = j - n / 2 + 0.5, r = Math.sqrt(dx * dx + dy * dy) / (n / 2), v = 0;
      if (r > 1) continue;
      if (r > 0.84) v = 1;
      else if (r > 0.7 && r < 0.76) v = 1;
      else if (r <= 0.7) v = 0.12 + 0.55 * Math.pow((Math.cos(Math.atan2(dy, dx) * 12) + 1) / 2, 3) * (1 - r);
      var th = BAYER[j & 3][i & 3];
      if (v * 16 > th && th < d) x.fillRect(i * c, j * c, c - 0.5, c - 0.5);
    }
  }

  /** The passport as a card (B), the same layout as the desktop one. It is complete at its first paint (name, rows,
   *  footer, the real ledger head) and the animation plays over it: the emblem develops (600 ms) then turns slowly,
   *  a sweep passes once, and the check mark and seal print only when the passport verifies. Pointer tilt and a
   *  dithered glare on hover (mouse only). Everything that can change after mount is read from a live ref. */
  /** Passport types the live record says the trusted start covers: marked, so they show "Trusted (not earned)", never
   *  an earned tier (the passport signs the recorded tiers; an earned T3 stays T3). */
  function trustedMarks(types, byType) {
    return types.map(function (ty) {
      var m = byType[ty.type];
      return m && m.trusted && (ty.effective_tier || ty.tier) !== "alone" ? Object.assign({}, ty, { trusted: true }) : ty;
    });
  }
  function PassportCard(props) {
    var d = props.doc, ok = props.ok;
    var cardRef = useRef(null), okRef = useRef(null), sealRef = useRef(null), sweepRef = useRef(null);
    var st = useRef({ raf: 0, done: false, color: "" });
    var name = d.agent.model, head = short(d.ledger.head, 8);
    var live = useRef(null);
    live.current = { ok: !!ok };
    var byType = {};
    (props.mapTypes || []).forEach(function (ty) { byType[ty.type] = ty; });
    var types = trustedMarks(d.types || [], byType);
    // Faults and checks are not in the passport: they come from the live record of the same types.
    var totals = types.reduce(function (acc, ty) {
      var m = byType[ty.type] || {};
      return { f: acc.f + (m.faults || 0), n: acc.n + (m.successes || 0) + (m.faults || 0) };
    }, { f: 0, n: 0 });
    function settle() {
      var L = live.current;
      if (okRef.current) okRef.current.classList.toggle("is-on", L.ok);
      if (sealRef.current) {
        sealRef.current.classList.toggle("is-on", L.ok);
        if (L.ok) paintSeal(sealRef.current, 64, 1);
      }
      if (sweepRef.current) sweepRef.current.style.top = "";
    }
    useEffect(function () {
      var s = st.current, card = cardRef.current;
      if (!card) return undefined;
      if (!motion()) { s.done = true; settle(); return undefined; }
      var H = card.clientHeight;
      tween(s, 1500, 0, function (k) {
        var tt = k * 1.5;
        if (sweepRef.current) sweepRef.current.style.top = tt < 1 ? (tt * (H + 60) - 60) + "px" : "";
        if (tt > 0.7 && okRef.current) okRef.current.classList.toggle("is-on", live.current.ok);
        if (live.current.ok && sealRef.current && tt > 0.7) {
          sealRef.current.classList.add("is-on");
          paintSeal(sealRef.current, 64, clamp01((tt - 0.7) / 0.8));
        }
      }, function () { s.done = true; settle(); });
      return function () { cancelAnimationFrame(s.raf); };
    }, []);
    useEffect(function () {                            // a new verdict or theme after the entrance
      var s = st.current, col = sealRef.current ? getComputedStyle(sealRef.current).color : "";
      if (s.done) { s.color = col; settle(); }
    });
    function tilt(e) {
      var card = cardRef.current;
      if (!card || e.pointerType !== "mouse" || !motion()) return;
      var r = card.getBoundingClientRect(), px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = "perspective(900px) rotateY(" + (px * 8).toFixed(2) + "deg) rotateX(" + (-py * 8).toFixed(2) + "deg)";
      card.style.setProperty("--gx", (px + 0.5).toFixed(3));
      card.classList.add("is-tilt");
    }
    function untilt() {
      var card = cardRef.current;
      if (!card) return;
      card.style.transform = ""; card.classList.remove("is-tilt");
    }
    return h("div", { className: "tnr-pass-wrap" },
      h("div", { ref: cardRef, className: "tnr-pass", role: "img", "aria-label": t("passport.card.aria", { agent: name, verdict: props.verdict }),
        onPointerMove: tilt, onPointerLeave: untilt },
        h("div", { ref: sweepRef, className: "tnr-pass-sweep", "aria-hidden": true }),
        h("div", { className: "tnr-pass-top", "aria-hidden": true },
          h("span", null, "TENURE"),
          h("span", null, t("passport.card.title") + " · " + (d.signature ? "ED25519" : t("passport.value.unsigned")) + " ",
            h("span", { ref: okRef, className: cx("tnr-pass-ok", !motion() && ok && "is-on") }, "✓"))),
        h("div", { className: "tnr-pass-emblem", "aria-hidden": true },
          h(Emblem, { share: autonomyShare(types), size: 176, cells: 64, rotate: true, developMs: 600 })),
        h("div", { className: "tnr-pass-name", "aria-hidden": true }, h("bdi", null, name)),
        h("div", { className: "tnr-pass-rows", "aria-hidden": true },
          types.map(function (ty, i) {
            var cap = !!(ty.guarantee && ty.guarantee.capped);
            var eff = ty.effective_tier || ty.tier;
            var trust = ty.trusted && !cap;
            var bp = barProps(Object.assign({}, ty, { capped: cap }), byType[ty.type]);
            return h("div", { key: ty.type, className: cx("tnr-pass-row", trust && "is-trusted") },
              h("span", { className: "tnr-pass-k" }, h("bdi", null, h("span", { className: "tnr-pass-n" }, nth(i + 1)), " ", h("code", null, ty.type)),
                trust ? h("span", { className: "tnr-pass-tier" }, h("b", null, t("passport.trusted")))
                  : h("span", { className: "tnr-pass-tier" }, h("b", null, cap ? t("tier.capped.chip") : TIER[eff]), " " + tierLabel(eff, cap))),
              h(DitherBar, Object.assign(bp, { className: "tnr-pass-bar", delay: 120 + i * 80 })),
              h("span", { className: "tnr-pass-count" }, cap || trust || ty.required == null ? "" : num(ty.series) + "/" + num(ty.required)));
          })),
        h("div", { className: "tnr-pass-foot", "aria-hidden": true },
          h("span", null, t("passport.faults_checks", { n: totals.f, total: totals.n })),
          h("span", null, t("passport.field.ledger") + " ", h("span", { className: "tnr-pass-hash" }, head))),
        h("div", { className: "tnr-pass-sig", "aria-hidden": true },
          h(Emblem, { share: 1, size: 16, cells: 16 }), h("b", null, "TENURE"), h("span", null, t("passport.card.signature"))),
        h("canvas", { ref: sealRef, className: cx("tnr-pass-seal", !motion() && ok && "is-on"), "aria-hidden": true })));
  }

  function PassportView(props) {
    var agents = props.rows;
    var selS = useState(""), sel = selS[0], setSel = selS[1];
    var row = agents.filter(function (r) { return r.key === sel; })[0] || agents[0];
    var res = usePoll(function () {
      return row ? apiGet("/passport", { agent: row.agent.agent, of: row.profile, raw: props.raw }) : null;
    }, [row && row.key, props.raw, props.version], !!row, PASSPORT_MS);
    var fresh = useFresh(!!(res.data && res.data.passport));
    if (!agents.length) return h(Empty, { title: t("passport.empty.title") }, t("passport.empty.body"));
    // Only an answer for the selected agent is ever shown (usePoll drops the previous agent's on change).
    var d = res.data && res.data.passport && res.data.profile === row.profile ? res.data.passport : null;
    var v = d ? verdict(res.data.verify, d) : null;
    var verified = !!(d && res.data.verify && !res.data.verify.length);
    var pending = !!(row && row.info && row.info.settings && row.info.settings.pending);
    var liveTypes = {};
    ((row && row.agent.types) || []).forEach(function (ty) { liveTypes[ty.type] = ty; });
    function download() {
      if (!d) return;
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
      pending && d ? h("div", { className: "tnr-note" }, t("passport.pending_note")) : null,
      !d ? h("div", { className: "tnr-dim tnr-pad" }, t("common.loading")) : h("div", { className: "tnr-passport-grid" },
        h(PassportCard, { key: row.key + "|" + d.ledger.head, doc: d, ok: verified, verdict: v.title, mapTypes: row.agent.types }),
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
          h(Eyebrow, { n: 1 }, t("passport.types_title")),
          h("table", { className: "tnr-dtable" },
            h("thead", null, h("tr", null, h("th", null, t("th.type")), h("th", null, t("th.tier")), h("th", { className: "tnr-num" }, t("th.series")),
              h("th", { className: "tnr-num" }, t("th.sessions")), h("th", null, t("th.guarantee")))),
            h("tbody", null, trustedMarks(d.types, liveTypes).map(function (ty, pi) {
              var g = ty.guarantee || {};
              var trust = ty.trusted && !g.capped;
              return h("tr", { key: ty.type, className: fresh ? "tnr-in" : undefined, style: { "--i": pi } },
                h("td", null, h("code", null, ty.type), h("div", { className: "tnr-dim tnr-small" }, t("stakes." + ty.stakes))),
                h("td", null, trust ? h(Fragment, null, h(TierChip, { tier: "trusted", still: true }),
                  h("div", { className: "tnr-dim tnr-small" }, t("passport.trusted")))
                  : h(TierChip, { tier: ty.effective_tier || ty.tier, capped: !!g.capped, label: true })),
                h("td", { className: "tnr-num" }, ty.required == null || ty.trusted ? "—" : num(ty.series) + "/" + num(ty.required)),
                h("td", { className: "tnr-num" }, ty.trusted ? "—" : num(ty.sessions)),
                h("td", { className: "tnr-small" }, g.capped ? t("legend.capped") : trust ? h("span", { className: "tnr-dim" }, t("guarantee.trusted")) : h(Guarantee, { g: g })));
            }))))));
  }

  // --------------------------------------------------------------------------------------------------------- undo
  /** Consecutive actions of the same agent and type with no file to name collapse into one row ("12 × file:write"). */
  function groupUndo(list) {
    var out = [];
    list.forEach(function (u) {
      var last = out[out.length - 1];
      if (!u.file && last && !last.file && last.type === u.type && last.agent === u.agent && last.profile === u.profile) last.items.push(u);
      else out.push({ key: u.profile + "|" + u.id, file: u.file, type: u.type, agent: u.agent, profile: u.profile, items: [u] });
    });
    return out;
  }

  function UndoView(props) {
    var list = props.undoable || [];
    var fresh = useFresh(list.length > 0);
    var os = useState({}), open = os[0], setOpen = os[1];
    if (!list.length) {
      return h(Empty, { title: t("undo.empty.title") }, t("undo.empty.body"));
    }
    function fileCell(u) {
      return u.file ? h("span", null, h("code", null, u.file), u.files > 1 ? h("span", { className: "tnr-dim" }, " +" + num(u.files - 1)) : null)
        : h("span", { className: "tnr-dim tnr-small" }, t("undo.no_snapshot"));
    }
    function row(u, i, sub) {
      var mine = u.profile === props.current;
      return h("tr", { key: u.profile + u.id, className: cx(fresh && "tnr-in", sub && "tnr-undo-sub"), style: { "--i": i } },
        h("td", { className: "tnr-num tnr-dim" }, u.id),
        h("td", { className: "tnr-mono" }, ago(u.age), h("div", { className: "tnr-dim tnr-small" }, t("undo.window_ends", { duration: duration(86400 - u.age) }))),
        h("td", null, h("bdi", null, u.agent), h("div", { className: "tnr-dim tnr-small" }, t("common.profile", { profile: u.profile }))),
        h("td", null, h("code", null, u.type)),
        h("td", null, fileCell(u)),
        h("td", { className: "tnr-small" }, !u.file ? t("undo.effect.none") : u.counts_as_fault ? t("undo.effect.fault") : t("undo.effect.already")),
        h("td", { className: "tnr-dtable-actions" }, h(ConfirmBtn, {
          disabled: !mine, confirm: t("undo.confirm", { id: String(u.id) }),
          dialogTitle: t("confirm.undo.title", { id: String(u.id) }),
          dialogDesc: !u.file ? t("undo.effect.none") : u.counts_as_fault ? t("undo.effect.fault") : t("undo.effect.already"),
          title: mine ? t("undo.title") : t("undo.own_profile_only"),
          onConfirm: function () {
            return apiPost("/undo", { id: u.id }, { raw: props.raw }).then(function (r) {
              props.onDone(r.message, r.ok ? "success" : "error");
            }, function (e) { props.onDone(errText(e), "error"); });
          }
        }, t("undo.button"))));
    }
    var i = 0;
    return h("div", { className: "tnr-undo" },
      h("p", { className: "tnr-lede" }, t("undo.lede")),
      h("div", { className: "tnr-table-scroll" },
        h("table", { className: "tnr-dtable" },
          h("thead", null, h("tr", null, h("th", { className: "tnr-num" }, "#"), h("th", null, t("th.when")), h("th", null, t("th.agent")), h("th", null, t("th.type")),
            h("th", null, t("th.file")), h("th", null, t("th.undo_effect")), h("th", null, ""))),
          h("tbody", null, groupUndo(list).map(function (g) {
            if (g.items.length === 1) return row(g.items[0], i++, false);
            var first = g.items[0], expanded = !!open[g.key];
            var head = h("tr", { key: "g" + g.key, className: cx("tnr-undo-group", fresh && "tnr-in"), style: { "--i": i++ } },
              h("td", { className: "tnr-num" },
                h("button", { type: "button", className: "tnr-undo-toggle tnr-focus", "aria-expanded": expanded,
                  "aria-label": (expanded ? t("undo.collapse") : t("undo.expand")) + ": " + g.items.length + " × " + g.type,
                  onClick: function () { var o = Object.assign({}, open); o[g.key] = !expanded; setOpen(o); } },
                  h("span", { "aria-hidden": true }, expanded ? "▾" : "▸"), " " + num(g.items.length) + " ×")),
              h("td", { className: "tnr-mono" }, ago(first.age)),
              h("td", null, h("bdi", null, g.agent), h("div", { className: "tnr-dim tnr-small" }, t("common.profile", { profile: g.profile }))),
              h("td", null, h("code", null, g.type)),
              h("td", null, h("span", { className: "tnr-dim tnr-small" }, t("undo.no_snapshot"))),
              h("td", { className: "tnr-small" }, !first.file ? t("undo.effect.none") : first.counts_as_fault ? t("undo.effect.fault") : t("undo.effect.already")),
              h("td", { className: "tnr-dtable-actions" },
                h(Btn, { onClick: function () { var o = Object.assign({}, open); o[g.key] = !expanded; setOpen(o); } },
                  expanded ? t("undo.collapse") : t("undo.expand"))));
            return [head].concat(expanded ? g.items.map(function (u) { return row(u, i++, true); }) : []);
          })))));
  }

  // ------------------------------------------------------------------------------------------------- settings
  // params.DEFAULT_PRESET / DEFAULT_START / DEFAULT_SPOT: what applies before a profile logged any settings.
  var DEFAULTS = { preset: "balanced", start: "trusted", spot: 0.1, strict: false };
  var TYPES_YAML = "plugins:\n  entries:\n    tenure:\n      settings:\n        types:\n          \"mcp:notion:*\": medium      # free | low | medium | high | cap";
  function stakesName(s) { return s === "low" ? t("type.stakes_low") : s === "medium" ? t("type.stakes_medium") : t("type.stakes_high"); }
  function presetDesc(id) { return id === "careful" ? t("settings.preset_desc_careful") : id === "fast" ? t("settings.preset_desc_fast") : t("settings.preset_desc_balanced"); }
  function hermesCmd(profile, rest) { return profile && profile !== "default" ? "hermes -p " + profile + " tenure " + rest : "hermes tenure " + rest; }
  /** The preset whose risks these are, else custom. */
  function presetOf(r) {
    return Object.keys(PRESETS).filter(function (n) {
      return STAKES.every(function (l) { return PRESETS[n][l] == null ? r[l] == null : r[l] != null && Math.abs(1 / r[l] - 1 / PRESETS[n][l]) < 1e-6; });
    })[0] || "custom";
  }
  /** A preset's risks as POST /settings takes them, so that choosing it also replaces risk values of your own. */
  function presetRisks(id) { var o = {}; STAKES.forEach(function (l) { o[l] = PRESETS[id][l] == null ? "cap" : "1/" + Math.round(1 / PRESETS[id][l]); }); return o; }
  function kOf(bar) { return bar > 0 ? String(Math.round(1 / bar)) : ""; }
  function riskYaml(r) { return "risks: {" + STAKES.map(function (l) { return l + ": " + (r[l] == null ? "cap" : "1/" + r[l]); }).join(", ") + "}"; }

  /** Saves through POST /settings (Hermes' own plugin-settings writer). State: idle | saving | saved | error |
   *  nowriter (501/403: this Hermes cannot save here, the command is the way). The tab's poll (every 2 s) re-reads
   *  the settings, so the page shows what is in force, never what was asked. */
  function useSaver(props) {
    var s = useState({ state: "idle", error: "" }), st = s[0], setSt = s[1];
    var timer = useRef(0);
    useEffect(function () { return function () { clearTimeout(timer.current); }; }, []);
    function run(body) {
      clearTimeout(timer.current);
      setSt({ state: "saving", error: "" });
      apiPost("/settings", body, { raw: props.raw }).then(function () {
        setSt({ state: "saved", error: "" });
        timer.current = setTimeout(function () { setSt(function (x) { return x.state === "saved" ? { state: "idle", error: "" } : x; }); }, 6000);
      }, function (e) {
        var code = errStatus(e);
        if (code === 501 || code === 403) { setSt({ state: "nowriter", error: errText(e) }); props.onReadOnly(true); }
        else setSt({ state: "error", error: errText(e) });
      });
    }
    return [st, run];
  }
  function SaveStatus(props) {
    var st = props.st;
    if (st.state === "idle") return null;
    var text = st.state === "saving" ? t("settings.saving") : st.state === "saved" ? t("settings.saved") :
      st.state === "nowriter" ? t("settings.no_writer") : t("settings.save_failed", { error: st.error });
    return h("p", { className: "tnr-save", "data-state": st.state, role: "status" }, text);
  }
  /** The command that does the same in a terminal: secondary under a control, the way when saving here is refused. */
  function OrTerminal(props) {
    return h("div", { className: "tnr-or", "data-strong": props.st && props.st.state === "nowriter" ? "true" : "false" },
      h("div", { className: "tnr-dim tnr-small" }, props.config ? t("settings.or_config") : t("settings.or_terminal")),
      h(CopyCmd, { cmd: props.text }));
  }
  function Seg(props) {
    return h("div", { className: "tnr-seg", role: "group", "aria-label": props.label },
      props.options.map(function (o) {
        var on = props.value === o.id;
        return h("button", { key: String(o.id), type: "button", "aria-pressed": on, disabled: props.busy,
          className: cx("tnr-seg-btn", on && "is-on"), onClick: function () { if (!on) props.onPick(o.id); } }, o.label);
      }));
  }
  /** One option: its name, "In force" or a Use button, what it means. */
  function Option(props) {
    return h("div", { className: "tnr-opt", "data-current": props.current ? "true" : "false" },
      h("div", { className: "tnr-opt-head" }, props.head,
        props.current ? h("span", { className: "tnr-chip-in" }, t("settings.in_force")) :
          h(Btn, { disabled: props.busy, onClick: props.onUse }, t("settings.use"))),
      props.children);
  }
  function RiskLines(props) {
    return h("dl", { className: "tnr-levels" }, STAKES.map(function (s) {
      var bar = props.risks ? props.risks[s] : null;
      return h("div", { key: s }, h("dt", null, stakesName(s)),
        bar == null || !(bar > 0) ? h("dd", null, t("type.always_asks")) :
          h("dd", null, h("b", null, t("settings.series", { n: studyN(bar) })), h("span", null, t("settings.risk", { k: Math.round(1 / bar) }))));
    }));
  }
  /** A row of options that save on Use (preset, start, strict). */
  function OptionsControl(props) {
    var sv = useSaver(props), st = sv[0], run = sv[1];
    var busy = st.state === "saving" || props.readOnly;
    return h("div", { className: "tnr-ctl" },
      h("div", { className: "tnr-opts" }, props.options.map(function (o) {
        return h(Option, { key: String(o.id), busy: busy, current: props.current === o.id, head: o.head,
          onUse: function () { run(props.bodyOf(o.id)); } }, o.body);
      })),
      h(SaveStatus, { st: st }),
      h("div", { className: "tnr-or-list" }, props.options.filter(function (o) { return o.id !== props.current; }).map(function (o) {
        return h(OrTerminal, { key: String(o.id), st: st, text: props.cmdOf(o.id) });
      })));
  }
  /** Accepted risk per stakes level: segmented buttons 1/20 … 1/1000 and cap, plus a "1 in k" of your own, with the
   *  series it implies shown live; one Save for the three levels. */
  function RiskEditor(props) {
    var risks = props.risks;
    function init() { var d = {}; STAKES.forEach(function (l) { d[l] = risks && risks[l] > 0 ? kOf(risks[l]) : null; }); return d; }
    function initCustom(d) { var c = {}; STAKES.forEach(function (l) { c[l] = d[l] != null && LADDER.indexOf(Number(d[l])) < 0 ? d[l] : ""; }); return c; }
    var dS = useState(init), draft = dS[0], setDraft = dS[1];
    var cS = useState(function () { return initCustom(init()); }), custom = cS[0], setCustom = cS[1];
    var key = JSON.stringify(risks || {});
    useEffect(function () { var d = init(); setDraft(d); setCustom(initCustom(d)); }, [key]);
    var sv = useSaver(props), st = sv[0], run = sv[1];
    function valid(l) { return custom[l] === "" || (/^\d+$/.test(custom[l]) && Number(custom[l]) >= 2); }
    var allValid = STAKES.every(valid);
    var changed = STAKES.some(function (l) {
      return draft[l] == null ? !!(risks && risks[l] > 0) : !(risks && risks[l] > 0) || kOf(risks[l]) !== draft[l];
    });
    function set(obj, l, v) { var o = Object.assign({}, obj); o[l] = v; return o; }
    function pick(l, k) { setDraft(function (d) { return set(d, l, k == null ? null : String(k)); }); setCustom(function (c) { return set(c, l, ""); }); }
    function type(l, v) {
      var text = v.replace(/[^\d]/g, "");
      setCustom(function (c) { return set(c, l, text); });
      if (/^\d+$/.test(text) && Number(text) >= 2) setDraft(function (d) { return set(d, l, String(Number(text))); });
    }
    var busy = st.state === "saving" || props.readOnly;
    return h("div", { className: "tnr-opt tnr-risk" },
      h("div", { className: "tnr-dial-rows" }, STAKES.map(function (s, i) {
        var cap = draft[s] == null, k = Number(draft[s]);
        return h("div", { key: s, className: "tnr-dial-row tnr-in", style: { "--i": i } },
          h("div", { className: "tnr-dial-level" }, h("span", { className: "tnr-stakes-dot tnr-stakes--" + s }), stakesName(s)),
          h("div", { className: "tnr-ladder", role: "group", "aria-label": stakesName(s) },
            LADDER.map(function (n) {
              var on = n == null ? cap : !cap && custom[s] === "" && k === n;
              return h("button", { key: String(n), type: "button", "aria-pressed": on, disabled: busy,
                className: cx("tnr-rung", on && "is-on"), onClick: function () { pick(s, n); } }, n == null ? t("settings.rung_cap") : "1/" + n);
            }),
            h("label", { className: "tnr-risk-k" }, h("span", null, t("settings.one_in")),
              h("input", { type: "text", inputMode: "numeric", placeholder: "k", value: custom[s], disabled: props.readOnly,
                "aria-invalid": valid(s) ? undefined : "true", "aria-label": stakesName(s) + " · " + t("settings.one_in"),
                onChange: function (e) { type(s, e.target.value); } }))),
          h("div", { className: "tnr-dial-n" }, h("b", null, cap ? t("type.always_asks") : t("settings.series", { n: studyN(1 / k) }))));
      })),
      h("div", { className: "tnr-dial-foot" },
        h(Btn, { kind: "primary", disabled: !allValid || !changed || busy, onClick: function () {
          var r = {}; STAKES.forEach(function (l) { r[l] = draft[l] == null ? "cap" : "1/" + draft[l]; }); run({ risks: r });
        } }, t("settings.save")),
        !allValid ? h("span", { className: "tnr-dim tnr-small" }, t("settings.risk_invalid")) : null),
      h(SaveStatus, { st: st }),
      h(OrTerminal, { config: true, st: st, text: riskYaml(draft) }));
  }
  /** Spot checks: 1 in 5 / 10 / 20, or a whole number of your own. */
  function SpotControl(props) {
    var k = Math.round(1 / props.spot), presets = [5, 10, 20];
    var cS = useState(presets.indexOf(k) >= 0 ? "" : String(k)), custom = cS[0], setCustom = cS[1];
    useEffect(function () { setCustom(presets.indexOf(k) >= 0 ? "" : String(k)); }, [k]);
    var sv = useSaver(props), st = sv[0], run = sv[1];
    var ok = /^\d+$/.test(custom) && Number(custom) >= 2;
    var busy = st.state === "saving" || props.readOnly;
    return h("div", { className: "tnr-opt", "data-current": "true" },
      h("div", { className: "tnr-opt-head" }, h("span", { className: "tnr-opt-name" }, t("settings.spot_value", { k: k })),
        h("span", { className: "tnr-chip-in" }, t("settings.in_force"))),
      h("p", { className: "tnr-small" }, t("settings.spot_desc", { k: k })),
      h("div", { className: "tnr-row-end" },
        h(Seg, { busy: busy, label: t("settings.spot_title"), onPick: function (id) { run({ spot: 1 / id }); },
          options: presets.map(function (n) { return { id: n, label: t("settings.spot_value", { k: n }) }; }), value: presets.indexOf(k) >= 0 ? k : null }),
        h("label", { className: "tnr-risk-k" }, h("span", null, t("settings.one_in")),
          h("input", { type: "text", inputMode: "numeric", placeholder: String(k), value: custom, disabled: props.readOnly,
            "aria-label": t("settings.spot_custom"), onChange: function (e) { setCustom(e.target.value.replace(/[^\d]/g, "")); } })),
        h(Btn, { disabled: !ok || Number(custom) === k || busy, onClick: function () { run({ spot: 1 / Number(custom) }); } }, t("settings.save"))),
      h(SaveStatus, { st: st }),
      h("div", { className: "tnr-or" }, h("div", { className: "tnr-dim tnr-small" }, t("settings.spot_change")), h(CopyCmd, { cmd: "spot_check: " + props.spot })));
  }
  /** Tenure on / off. */
  function EnabledControl(props) {
    var sv = useSaver(props), st = sv[0], run = sv[1];
    var enabled = props.enabled;
    return h("div", { className: "tnr-opt", "data-current": enabled === true ? "true" : "false" },
      h("div", { className: "tnr-row-end" },
        h(Seg, { busy: st.state === "saving" || props.readOnly, label: t("settings.enabled_title"), onPick: function (id) { run({ enabled: id === "on" }); },
          options: [{ id: "on", label: t("settings.enabled_on") }, { id: "off", label: t("settings.enabled_off") }],
          value: enabled == null ? null : enabled ? "on" : "off" }),
        enabled == null ? h("span", { className: "tnr-dim tnr-small" }, t("settings.enabled_unknown")) : null),
      h("p", { className: "tnr-small", "data-warn": enabled === false ? "true" : "false" }, t("settings.enabled_warn")),
      h(SaveStatus, { st: st }),
      h(OrTerminal, { config: true, st: st, text: "enabled: " + (enabled === false ? "true" : "false") }));
  }
  function SettingRow(props) {
    return h("section", { className: "tnr-srow" },
      h(Eyebrow, { n: props.n }, props.title),
      props.help ? h("p", { className: "tnr-dim tnr-small tnr-srow-help" }, props.help) : null,
      props.children);
  }

  /** The settings in force in this profile, each one changeable here, in the same eight sections and words as the
   *  Desktop page: saved through POST /settings (Hermes' own plugin-settings writer), then re-read, so what shows is
   *  what is in force. The equivalent command stays under each control, and is the way when saving is refused. */
  function SettingsView(props) {
    var s = props.settings;
    var profile = props.profile || "default";
    var start = props.start || DEFAULTS.start;
    var spot = s && s.spot > 0 && s.spot < 1 ? s.spot : DEFAULTS.spot;
    var strict = s ? !!s.strict : DEFAULTS.strict;
    var enabled = s && typeof s.enabled === "boolean" ? s.enabled : null;
    var risks = (s && s.risks) || PRESETS[(s && s.preset) || DEFAULTS.preset] || PRESETS.balanced;
    // Risk values of their own override the preset: the preset shown is the one they match, else custom.
    var preset = presetOf(risks);
    var k = Math.round(1 / spot);
    var trustedStart = start === "trusted";
    var common = { raw: props.raw, onReadOnly: props.onReadOnly, readOnly: props.readOnly };
    function ctl(extra) { return Object.assign({}, common, extra); }
    var anim = props.anim;
    return h("div", { className: "tnr-settings" },
      h("header", { className: "tnr-shero" },
        h("div", { className: "tnr-eyebrow" }, "#" + t("view.settings"), h("span", { className: "tnr-dim" }, " · "), t("meta.profile") + " ", h("bdi", null, profile)),
        h("h2", { className: "tnr-shero-name" }, presetName(preset)),
        h("p", { className: "tnr-dim tnr-small" }, t(trustedStart ? "start.trusted" : "start.probation") + " · " + t("settings.spot_title") + " " +
          t("settings.spot_value", { k: k }) + " · " + t(strict ? "settings.strict_on" : "settings.strict_off")),
        h("p", { className: "tnr-small" }, t("settings.saves_here")),
        s && s.pending ? h("p", { className: "tnr-small" }, t("settings.pending")) : null,
        !s ? h("p", { className: "tnr-small" }, t("settings.none")) : null),
      h(SettingRow, { n: 1, title: t("meta.preset"), help: t("settings.preset_help") },
        h(OptionsControl, ctl({ current: preset, bodyOf: function (id) { return { preset: id, risks: presetRisks(id) }; }, cmdOf: function (id) { return hermesCmd(profile, "setup " + id); },
          options: ["careful", "balanced", "fast"].map(function (id) {
            return { id: id, head: h("span", { className: "tnr-opt-name" }, presetName(id)),
              body: h(Fragment, null, h("p", { className: "tnr-small" }, presetDesc(id)), h(RiskLines, { risks: PRESETS[id] })) };
          }) }))),
      h(SettingRow, { n: 2, title: t("settings.custom_title"), help: t("settings.custom_help") },
        preset === "custom" ? h("p", { className: "tnr-small" }, t("settings.preset_desc_custom")) : null,
        h(RiskEditor, ctl({ risks: risks }))),
      h(SettingRow, { n: 3, title: t("meta.start"), help: t("settings.start_help") },
        h(OptionsControl, ctl({ current: start, bodyOf: function (id) { return { start: id }; }, cmdOf: function (id) { return hermesCmd(profile, "start " + id); },
          options: [true, false].map(function (tr) {
            return { id: tr ? "trusted" : "probation",
              head: h("span", { className: "tnr-opt-name tnr-opt-start" }, h(TierChip, { tier: tr ? "trusted" : "ask", still: true }), t(tr ? "start.trusted" : "start.probation")),
              body: h("p", { className: "tnr-small" }, t(tr ? "settings.start_trusted" : "settings.start_probation")) };
          }) }))),
      h(SettingRow, { n: 4, title: t("settings.spot_title") }, h(SpotControl, ctl({ spot: spot }))),
      h(SettingRow, { n: 5, title: t("settings.strict_title"), help: t("settings.strict_help") },
        h(OptionsControl, ctl({ current: strict ? "on" : "off", bodyOf: function (id) { return { strict: id === "on" }; },
          cmdOf: function (id) { return hermesCmd(profile, id === "on" ? "strict on" : "strict off"); },
          options: [false, true].map(function (on) {
            return { id: on ? "on" : "off", head: h("span", { className: "tnr-opt-name" }, t(on ? "settings.strict_on" : "settings.strict_off")),
              body: h("p", { className: "tnr-small" }, t(on ? "settings.strict_desc_on" : "settings.strict_desc_off")) };
          }) }))),
      h(SettingRow, { n: 6, title: t("page.animations"), help: t("settings.animations_help") },
        h("div", { className: "tnr-opt" },
          h("label", { className: "tnr-switch-toggle", title: anim.reduced ? t("page.anim_reduced") : undefined, "data-off": anim.reduced ? "true" : "false" },
            h("input", { type: "checkbox", checked: anim.on && !anim.reduced, disabled: anim.reduced, onChange: function (e) { anim.set(e.target.checked); } }),
            h("span", { className: "tnr-toggle-track", "aria-hidden": true }),
            h("span", null, t("page.animations"))))),
      h(SettingRow, { n: 7, title: t("settings.enabled_title"), help: t("settings.enabled_help") }, h(EnabledControl, ctl({ enabled: enabled }))),
      h(SettingRow, { n: 8, title: t("settings.advanced_title"), help: t("settings.advanced_help") },
        h("p", { className: "tnr-small" }, t("settings.advanced_types")),
        h("pre", { className: "tnr-pre" }, TYPES_YAML),
        h("p", { className: "tnr-dim tnr-small" }, t("settings.advanced_docs"))));
  }

  // ------------------------------------------------------------------------------------------------------ help
  function Help(props) {
    // The keys stay as they are; only their descriptions are translated.
    var keys = [["m", t("view.map")], ["b", t("view.models")], ["c", t("view.community")], ["w", t("view.switch")], ["p", t("view.passport")], ["u", t("view.undo")],
      ["s", t("view.settings")], ["a", t("help.agent")], ["j / k", t("help.next_prev")], ["↵", t("help.open")],
      ["r", t("help.raw")], ["esc", t("help.close")], ["?", t("help.help")]];
    return h("div", { className: "tnr-drawer-wrap", onClick: props.onClose },
      h("div", { className: "tnr-help", role: "dialog", "aria-label": t("help.aria") },
        h(Eyebrow, { n: 0 }, t("help.title")),
        h("dl", null, keys.map(function (k) {
          return h(Fragment, { key: k[0] }, h("dt", null, h(Kbd, null, k[0])), h("dd", null, k[1]));
        }))));
  }

  // ------------------------------------------------------------------------------------------------- big moments
  /** A type reached T3 (Tenure granted), T2 (Under review), or fell back to T1 after a fault (Back on probation):
   *  a band at the top of the tab, its title revealed by a wipe, a dither fade below; it folds away after 6 s. */
  function Moment(props) {
    var m = props.moment;
    var granted = m.kind === "granted", down = m.kind === "probation";
    var title = granted ? t("moment.granted") : down ? t("moment.probation") : t("moment.review");
    return h("div", { className: cx("tnr-moment", "tnr-moment--" + m.kind), role: "status" },
      h("div", { className: "tnr-moment-in" },
        h("div", { className: "tnr-moment-eyebrow" }, "#", down ? t("moment.eyebrow.down") : t("moment.eyebrow.up"), " · ", h("code", null, m.type)),
        h("div", { className: "tnr-moment-title" }, title),
        h("div", { className: "tnr-moment-sub" },
          h("bdi", { className: "tnr-mono" }, m.agent), " · ",
          h("b", null, TIER[m.to]), " " + tierLabel(m.to) + (m.repair ? " · " + m.repair : ""))),
      h("button", { type: "button", className: "tnr-moment-x", onClick: props.onClose, "aria-label": t("moment.dismiss"),
        title: t("moment.dismiss") }, "×"),
      granted ? h(DitherFade) : null);
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
    var animS = useState(readAnimPref), animOn = animS[0], setAnimOn = animS[1];
    var momS = useState(null), moment = momS[0], setMoment = momS[1];
    var rmS = useState(reducedMotion()), reduced = rmS[0], setReduced = rmS[1];
    var wS = useState(0), width = wS[0], setWidth = wS[1];
    var onS = useState(""), onAcc = onS[0], setOnAcc = onS[1];
    ANIM = animOn;
    // Canvases follow the window: a resize or a pixel-ratio change re-renders the tab, and each canvas repaints when
    // its width or the ratio changed.
    useEffect(function () {
      var raf = 0;
      function on() { cancelAnimationFrame(raf); raf = requestAnimationFrame(function () { setWidth(window.innerWidth * 10 + (window.devicePixelRatio || 1)); }); }
      window.addEventListener("resize", on);
      return function () { window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
    }, []);
    useEffect(function () {
      if (!REDUCED) return undefined;
      function on() { setReduced(REDUCED.matches); }
      if (REDUCED.addEventListener) REDUCED.addEventListener("change", on); else if (REDUCED.addListener) REDUCED.addListener(on);
      return function () {
        if (REDUCED.removeEventListener) REDUCED.removeEventListener("change", on); else if (REDUCED.removeListener) REDUCED.removeListener(on);
      };
    }, []);
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
        r.agent.types.forEach(function (ty) { now[r.key + "\u0000" + ty.type] = { tier: shownTier(ty), r: r, t: ty }; });
      });
      var before = prev.current;
      prev.current = now;
      if (!before) return;
      var found = [];
      // Trusted ranks just above T1: its first fault (trusted -> T1) is a drop, and plays "Back on probation".
      var RANK = { ask: 0, trusted: 0.5, notify: 1, alone: 2 };
      Object.keys(now).forEach(function (k) {
        var b = before[k], n = now[k];
        if (b && b.tier !== n.tier) {
          // A fault (or the trial it opened) explains a drop; a climb is earned on evidence; a drop with no fault is
          // a revoke, a settings or stakes change: said as such, never "on evidence".
          var faulted = n.t.faults > (b.t.faults || 0);
          var why = faulted ? (n.t.trial_left ? "trial_open" : "after_fault") : RANK[n.tier] > RANK[b.tier] ? "on_evidence" : "changed";
          found.push({ id: k + Date.now(), k: k, at: Date.now(), agent: n.r.agent.agent, type: n.t.type, from: b.tier, to: n.tier, why: why });
        }
      });
      if (found.length) {
        setTransitions(function (xs) { return found.concat(xs).slice(0, 30); });
        var up3 = found.filter(function (x) { return x.to === "alone" && x.why === "on_evidence"; })[0];
        var fell = found.filter(function (x) { return x.to === "ask" && RANK[x.from] > 0 && (x.why === "after_fault" || x.why === "trial_open"); })[0];
        var up2 = found.filter(function (x) { return x.to === "notify" && x.from === "ask" && x.why === "on_evidence"; })[0];
        var pick = up3 ? ["granted", up3] : fell ? ["probation", fell] : up2 ? ["review", up2] : null;
        if (pick) {
          var cur = now[pick[1].k];
          setMoment({ kind: pick[0], type: pick[1].type, agent: cur ? cur.r.agent.model : pick[1].agent, to: pick[1].to,
            repair: pick[0] === "probation" && cur ? missing(cur.t).text : "", at: Date.now() });
        }
        var f = found[0];
        setToast({ text: t("toast.transition", { agent: f.agent, type: f.type, from: TIER[f.from], to: TIER[f.to] }), type: "info", at: Date.now() });
      }
    }, [data]);

    // Hermes themes say nothing about light or dark: read it from the background, so status colors keep contrast.
    useEffect(function () {
      var tn = luminance(getComputedStyle(document.documentElement).getPropertyValue("--background-base")) > 0.5 ? "light" : "dark";
      if (tn !== tone) setTone(tn);
      // Text on accent paper (T3 chip, bands, the passport): black or white, whichever the accent lets read.
      var probe = rootRef.current && rootRef.current.querySelector(".tnr-probe");
      var ink = probe ? inkOn(getComputedStyle(probe).color) : "";
      if (ink && ink !== onAcc) setOnAcc(ink);
    });

    useEffect(function () {
      if (!moment) return undefined;
      var tm = setTimeout(function () { setMoment(null); }, 6000);
      return function () { clearTimeout(tm); };
    }, [moment]);

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
    else if (view === "community") body = h(CommunityView, { version: version });
    else if (view === "switch") body = h(SwitchView, { rows: rows, raw: raw, version: version });
    else if (view === "passport") body = h(PassportView, { rows: rows, raw: raw, version: version });
    else if (view === "undo") body = h(UndoView, { undoable: activity && activity.undoable, current: currentProfile, onDone: done, raw: raw });
    else body = h(SettingsView, { settings: current && current.settings, start: startOf(current), profile: currentProfile, raw: raw,
      readOnly: settingsRO, onReadOnly: setSettingsRO,
      anim: { on: animOn, reduced: reduced, set: function (on) { writeAnimPref(on); setAnimOn(on); } } });

    var moving = animOn && !reduced;
    return h("div", { className: "tnr", "data-tone": tone, "data-anim": moving ? "on" : "off", ref: rootRef, tabIndex: -1, onKeyDown: onKey,
      style: onAcc ? { outline: "none", "--tnr-on": onAcc } : { outline: "none" } },
      h("span", { className: "tnr-probe", "aria-hidden": true }),
      h("header", { className: "tnr-head" },
        h("div", { className: "tnr-title-row" },
          h("div", { className: "tnr-title-block" },
            h("div", { className: "tnr-eyebrow" }, h("span", { className: "tnr-eyebrow-n" }, nth(0)), h("bdi", null, t("passport.card.signature"))),
            h("h1", { className: "tnr-title" }, t("page.title")),
            h("span", { className: "tnr-subtitle" }, t("page.subtitle"))),
          h("div", { className: "tnr-head-right" },
            h("span", { className: cx("tnr-live", err && "is-stale"), title: err ? errText(err) : t("page.polling", { s: POLL_MS / 1000 }) },
              h("span", { className: "tnr-live-dot", "aria-hidden": true }), err ? t("page.retrying") : t("page.live"),
              h("span", { className: "tnr-mono" }, updated)),
            h("button", { type: "button", className: cx("tnr-chip-btn", raw && "is-on"), onClick: function () { setRaw(!raw); }, title: t("page.raw_title") },
              raw ? t("page.raw_on") : t("page.raw_off")),
            h("button", { type: "button", className: cx("tnr-chip-btn", moving && "is-on"), "aria-pressed": moving, disabled: reduced,
              onClick: function () { writeAnimPref(!animOn); setAnimOn(!animOn); },
              title: reduced ? t("page.anim_reduced") : t("page.anim_title") },
              h("span", { className: "tnr-anim-dot", "aria-hidden": true }), moving ? t("page.anim_on") : t("page.anim_off")),
            h("button", { type: "button", className: "tnr-chip-btn tnr-head-help", onClick: function () { setHelp(true); }, title: t("help.aria") }, h(Kbd, null, "?")))),
        h(Counters, { totals: activity && activity.totals })),
      h(Tabs, { view: view, width: width, onHelp: function () { setHelp(true); }, onView: function (v) { setView(v); setDrawer(null); },
        undoCount: activity && activity.undoable ? activity.undoable.length : 0 }),
      unreadable.length ? h("div", { className: "tnr-msg tnr-tone--warn" }, t("page.unreadable", {
        profiles: unreadable.map(function (p) { return p.profile; }).join(t("common.list_sep")) })) : null,
      data && err ? h("div", { className: "tnr-msg tnr-tone--warn" }, t("stale.message", { error: errText(err), time: updated })) : null,
      moment ? h(Moment, { key: moment.at, moment: moment, onClose: function () { setMoment(null); } }) : null,
      h("main", { className: "tnr-body", "data-view": view, id: "tnr-panel", role: "tabpanel", "aria-labelledby": "tnr-tab-" + view }, body),
      drawerRow ? h(AgentDrawer, { row: drawerRow, raw: raw, version: version, onClose: function () { setDrawer(null); }, onDone: done }) : null,
      help ? h(Help, { onClose: function () { setHelp(false); } }) : null,
      toast ? h("div", { className: "tnr-toast tnr-toast--" + toast.type, role: "status" }, toast.text) : null);
  }

  REG.register("tenure", TenurePage);
})();
