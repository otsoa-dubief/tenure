/**
 * tenure, desktop half.
 *
 * - A Tenure page: each agent's earned tiers per action type, what it did on its own (with Undo and Flag), the signed
 *   passport, and your own benchmark per action type.
 * - A status-bar chip for the model in use, a tier badge on each model in the model menu, ⌘K commands, and an
 *   Undo toast when an action type acts, then notifies.
 *
 * Built from the app's own components (the Panel family of the Scheduled jobs page, ConfirmDialog,
 * SegmentedControl, Switch, CopyButton, Tip, Codicon) and its data layer (useQuery, refreshed live by the agent half's
 * `plugin.tenure.*` events). Every number comes from the agent half's backend (`dashboard/plugin_api.py`, through
 * `ctx.rest`). Plain ESM, loaded uncompiled: UI is jsx() calls; only @hermes/plugin-sdk, react and react/jsx-runtime.
 *
 * Look: "encre et trame" (ink and dither). One colour, the user's accent; host neutrals for the rest; Collapse for big
 * names and tier names, JetBrains Mono for numbered eyebrows; 1-bit Bayer dither for progress and the agent's emblem.
 * Animations play on real transitions only, and stop for prefers-reduced-motion or the `animations` switch.
 */

import {
  Button,
  Codicon,
  ConfirmDialog,
  CopyButton,
  cn,
  ErrorState,
  haptic,
  host,
  MODEL_MENU_ROW_AREA,
  PALETTE_AREA,
  PanelAction,
  PanelBlock,
  PanelBody,
  PanelDetail,
  PanelEmpty,
  PanelList,
  PanelListRow,
  PanelMeta,
  PanelSectionLabel,
  ROUTES_AREA,
  SegmentedControl,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  Switch,
  Tip,
  usePluginI18n,
  useQuery,
  useQueryClient,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'tenure'
const ROUTE = '/tenure'
const HEARTBEAT_MS = 60_000

// Every user-visible string lives in tenure/locales/<lang>/desktop.json (one vocabulary for the tiers, shared with
// the CLI and the dashboard tab). scripts/build_locales.py embeds the catalogs between the two markers below: do not
// edit that block by hand. Values are strings with {placeholders}, or plural objects ({one, other, …}) chosen by {n}.
/* TENURE_LOCALES_BEGIN */
const TENURE_LOCALES = {
  "en": {
    "agents.pick": "Pick an agent to see what it has earned.",
    "agents.search": "Search agents",
    "backend.desc": "Enable tenure for this profile in Capabilities → Plugins (Agent column). {error}",
    "backend.title": "The agent half is not answering",
    "benchmark.col_faults": "Faults / verified",
    "benchmark.col_public": "Public",
    "benchmark.col_range": "95% range",
    "benchmark.col_rate": "Rate",
    "benchmark.col_sessions": "sessions",
    "benchmark.empty_body": "Each verified action adds to the model's record on that type, here and in {cmd}.",
    "benchmark.empty_title": "No record yet",
    "benchmark.faults": {
      "one": "{n} fault / {total}",
      "other": "{n} faults / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.no_public_type": "No public measure for this action type.",
    "benchmark.not_enough": "not enough evidence",
    "benchmark.not_ranked": "Not enough evidence yet",
    "benchmark.not_ranked_note": "A model is ranked once it has {n} verified outcomes on this type.",
    "benchmark.note": "Each model's verified record on your work for this action type, with the 95% range of its fault rate, ranked by the top of that range. The public score is context: capability on their tasks, not reliability on yours.",
    "benchmark.public_note": "Public capability on their tasks, not reliability on yours.",
    "benchmark.public_score": "Public score: {benchmark}, {source}",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "Fault rate and its 95% range, on a 0–{max}% axis",
    "benchmark.rate": "{rate}% ({low}–{high}%)",
    "benchmark.search": "Search action types",
    "benchmark.source": "{source}. Best published score, any harness; not a controlled comparison.",
    "benchmark.source_accessed": "{source}, accessed {accessed}. Best published score, any harness; not a controlled comparison.",
    "cell.capped_by_settings": "Capped by the risk settings",
    "cell.kind_irreversible": "{type} · {stakes}, irreversible",
    "cell.kind_reversible": "{type} · {stakes}, reversible",
    "cell.provisional_long": {
      "one": "{n} carried over from the previous model, provisional",
      "other": "{n} carried over from the previous model, provisional"
    },
    "cell.record": "Record: {successes} successes · {faults} faults · {neutrals} neutral · {spot} spot checks",
    "cell.series": "Series {series}/{required} in a row",
    "cell.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "cell.tier_now": "Tier now: {tier} ({name})",
    "chip.tip": {
      "one": "{name}: {earned} of {n} action type has earned autonomy (T2 or T3). Open Tenure.",
      "other": "{name}: {earned} of {n} action types have earned autonomy (T2 or T3). Open Tenure."
    },
    "common.loading": "Reading the evidence…",
    "common.no_match": "No match",
    "common.own_profile_only": "Acts on the current profile only",
    "common.retry": "Try again",
    "community.col_contributors": "contributors",
    "community.col_model": "model",
    "community.empty_how": "To contribute, write your record with this command, read what it holds, then open a pull request adding the file to the community repository ({repo}).",
    "community.empty_title": "No shared records yet",
    "community.empty_what": "The community benchmark pools records that Tenure users chose to publish: per model and per action family, verified successes and faults, signed with their passport key. Nothing is shared automatically: Tenure makes no network call.",
    "community.empty_where": "To see the board here, download the community-board.json the repository publishes and save it as {path}.",
    "community.generated": "{records} · board generated on {date}",
    "community.lede": "Self-reported by contributors, and signature-checked: each record is signed with its owner's passport key, and one record per key counts. ",
    "community.lede_bold": "This does not stop one person with many keys.",
    "community.models": {
      "one": "{n} model",
      "other": "{n} models"
    },
    "community.ranking": "Per action family, models ranked by the top of the 95% range of their fault rate, never by one score.",
    "community.records": {
      "one": "{n} record",
      "other": "{n} records"
    },
    "confirm.flag_desc": "This counts as a fault: {type} drops at least one tier and climbs again. Use it for an error nobody caught.",
    "confirm.flag_title": "Flag {type} as an error?",
    "confirm.revoke_desc": "{type} asks first again and its series restarts from zero. Not a fault.",
    "confirm.revoke_title": "Take back {type}?",
    "confirm.undo_title": "Undo action {id}?",
    "emblem.none": "No autonomy earned yet",
    "emblem.review": {
      "one": "{n} type under review",
      "other": "{n} types under review"
    },
    "emblem.tenured": {
      "one": "{n} type tenured",
      "other": "{n} types tenured"
    },
    "emblem.trusted": {
      "one": "{n} type trusted, not earned",
      "other": "{n} types trusted, not earned"
    },
    "event.confirmed": "carried-over evidence confirmed by its own",
    "event.fault_check": "automatic check failed",
    "event.fault_flag": "flagged as a fault by you",
    "event.fault_other": "fault ({source})",
    "event.fault_refusal": "refused by you",
    "event.fault_spot": "spot check refused or failed",
    "event.fault_undo": "undone by you",
    "event.neutral_alone": "acted alone (earned)",
    "event.neutral_ambiguous": "ambiguous call · no evidence",
    "event.neutral_blocked": "blocked by another guard · no evidence",
    "event.neutral_error": "tool error · no evidence",
    "event.neutral_expired": "never reported back · no evidence",
    "event.neutral_nobody": "nobody to answer · no evidence",
    "event.neutral_other": "neutral ({source})",
    "event.neutral_timeout": "no answer · no evidence",
    "event.revoked": "revoked by you",
    "event.success_approved": "approved by you, ran cleanly",
    "event.success_notify": "acted, then told you · not undone",
    "event.success_spot": "spot check approved by you",
    "event.switch": "model switch",
    "event.switch_from": "model switch from {from}",
    "event.tier": "tier {from} → {to} · {why}",
    "event.trial_failed": {
      "one": "trial failed: wait {n} action",
      "other": "trial failed: wait {n} actions"
    },
    "event.trial_opened": {
      "one": "trial opened: next {n} must succeed",
      "other": "trial opened: next {n} must succeed"
    },
    "event.trial_passed": "trial passed",
    "event.trial_reopens": {
      "one": "trial reopens: next {n} must succeed",
      "other": "trial reopens: next {n} must succeed"
    },
    "event.why_fault": "fault",
    "event.why_series_complete": "series complete",
    "event.why_series_n": "series {required}/{required}",
    "event.why_sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "event.why_settings": "stricter settings",
    "event.why_stakes": "stakes changed",
    "event.why_wald": "sequential test passed",
    "flag.confirm": "Flag",
    "flag.desc": "This counts as a fault: {type} will drop at least one tier and climb again. Use it for an error nobody caught.",
    "flag.title": "Flag this change as an error?",
    "help.asks_body": "Whatever the start, some actions ask you first:",
    "help.asks_files": "File edits keep their Undo, and so does a plain rm, mv, cp, sed -i or echo > file on project files: a change made without asking can be put back.",
    "help.asks_irreversible": "What cannot be undone: a recursive delete, a glob or a variable in a file command, discarding uncommitted git work, anything under sudo.",
    "help.asks_leaves": "What leaves the machine: publishing, deploying, pushing, sending an email, a payment.",
    "help.asks_outside": "After the agent reads outside content (a web page, an email, a downloaded file), its commands ask until you start a new session with /new; file changes, plain rm, mv or cp included, keep going with their Undo.",
    "help.asks_title": "What asks, and why",
    "help.asks_unknown": "Programs tenure does not know: a database or cloud tool, an unknown command.",
    "help.benchmark_body": "Your benchmark is each model's verified record on your own work, per action type, with the 95% range of its fault rate. A model is ranked once it has {n} verified outcomes on a type. A public score, when shown, is context: capability on someone else's tasks, not reliability on yours.",
    "help.flag_body": "Flag reports an error nobody caught. It counts as a fault: the type drops at least one tier, then climbs again.",
    "help.intro": "Tenure decides, per model and per action type, whether Hermes asks you first, acts then tells you, or acts on its own. Every decision comes from verified evidence, written in a signed ledger.",
    "help.key_close": "Close",
    "help.key_help": "This help",
    "help.key_next_prev": "Next / previous agent",
    "help.key_open": "Open the focused agent",
    "help.key_raw": "Raw type names on / off",
    "help.keys_note": "Shortcuts work while focus is inside this page.",
    "help.keys_title": "Keyboard",
    "help.passport_body": "The passport is a signed summary of an agent's record: each action type's tier, its faults and verified outcomes, and the head of the hash-chained ledger. It is signed with this profile's Ed25519 key. To check it, download it, export the ledger, then verify:",
    "help.passport_checks": "The check verifies the signature and the hash chain, then replays the ledger to recompute the same tiers. Nothing in it is self-declared.",
    "help.session_body": "Some asks (code run inline, complex shell commands, local commands tenure does not cover such as rm, mv or cp, and a command after outside content) offer “Allow for this session”: that ask stays quiet until the session ends. It is your choice, not evidence: it earns nothing, and a new session asks again.",
    "help.session_title": "Allow for this session",
    "help.study_adds": "What tenure adds: the trusted start (not the study: trusted actions earn nothing), spot checks on a type that acts alone, two distinct sessions in the series that reaches T3, suspension after outside content, and carry-over to a new model (strict mode is the study). start: probation is the study's own start.",
    "help.study_body": "After a type's first fault, or from the start with start: probation, tenure applies the rule of a preregistered study on earned autonomy: a sequential test (Wald) for the middle tier, act then tell you, and a CSP-1 series (Dodge's continuous sampling plan) for Tenured (T3). The study replays that rule on 6,000+ simulated agents. Its results are pending: tenure does not claim the study has confirmed the rule.",
    "help.study_link": "The preregistration on OSF",
    "help.study_title": "The study behind the rule",
    "help.tiers_climb": "A type climbs with verified successes and no fault. From Probation, at least {low} in a row at low stakes, or {medium} at medium stakes, reach Under review (T2); only reversible types pass through T2. A longer series, spread over at least {sessions} sessions, makes it Tenured (T3).",
    "help.tiers_drop": "One fault sends the type back down, and its series starts over.",
    "help.tiers_title": "The tiers",
    "help.title": "How tenure works",
    "help.trusted_body": "By default, the action types tenure covers (file edits, memory, handing work to a subagent, the usual development tools) ask nothing until their first fault, as Hermes alone would. The first fault (an Undo, a failed check, a flag) puts that type on Probation (T1): from then on it asks first, and earns its tier back from your answers. Nothing done under the trusted start counts as earned.",
    "help.trusted_title": "The trusted start",
    "help.undo_body": "A change made without asking keeps its Undo for 24 hours: in the toast, under “Acted without asking” on the agent's page, or in a conversation. Undo restores the files and counts as a fault: the type goes back down.",
    "help.undo_title": "Undo and flag",
    "hero.agent": "Agent",
    "intro.body": "Every action type of every model starts at T1: it asks first. A run of clean, approved actions moves it to T2: it acts, then tells you, with an Undo. A longer run, over two sessions, moves it to T3: it acts on its own, and 1 action in {k} still asks, as a spot check. One fault sends the type back down.",
    "intro.body_trusted": "Each action type starts trusted: until its first mistake it acts as Hermes alone would, and a reversible change acts, then tells you, with an Undo. Its first fault (an Undo, a failed check, a flag) puts it on Probation (T1): it asks first. A run of clean, approved actions moves it to T2; a longer run, over two sessions, to T3: it acts on its own, and 1 action in {k} still asks, as a spot check. Leaving the machine and money always ask.",
    "intro.got_it": "Got it",
    "intro.title": "How an action type earns its tier",
    "legend.a_share": "a share",
    "legend.alone": "acts on its own, {share} spot-checked",
    "legend.ask": "asks first",
    "legend.capped": "capped: always asks",
    "legend.carried": "from the previous model, provisional",
    "legend.carried_flag": "carried over",
    "legend.notify": "acts, then tells you, with an undo (reversible types)",
    "legend.series": "verified successes in a row, of the N needed",
    "legend.trusted": "trusted start: acts like Hermes alone until its first mistake, nothing earned",
    "map.aria": "Agents by action type",
    "map.asked_suffix": " asked",
    "map.capped": "capped",
    "map.carried_n": {
      "one": "{n} carried over",
      "other": "{n} carried over"
    },
    "map.copy_pending": "copied from another profile, checked when it starts",
    "map.count_faults": {
      "one": "{n} fault",
      "other": "{n} faults"
    },
    "map.count_sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "map.current": " · this profile",
    "map.empty_after": ", and climbs only on verified successes: reversible types reach the middle tier after a run of verified successes without a fault, and T3 after a full series of N from two sessions.",
    "map.empty_before": "tenure starts counting at the first action an agent asks to run. Reads never ask. Every action type starts at ",
    "map.empty_bold": "T1, asks first",
    "map.empty_title": "No evidence yet",
    "map.empty_trusted": "Work as usual. Each action type acts as Hermes alone would until its first mistake; from then on it asks first and earns its tier back from your answers.",
    "map.fault_on_record": "fault on record",
    "map.group_high": "high stakes",
    "map.group_low": "low stakes",
    "map.group_medium": "medium stakes",
    "map.held": "stored {tier}, held back by your settings",
    "map.one_in": "1 in {k}",
    "map.pending": "applies from the next action",
    "map.preset": "{preset} preset",
    "map.profile": "Profile {profile}",
    "map.read_only": " · read-only here",
    "map.spot": "spot checks {rate}",
    "map.start_probation": "study start (probation)",
    "map.start_trusted": "trusted start",
    "map.strict": "strict",
    "map.suspended": {
      "one": "{n} session suspended: external content read",
      "other": "{n} sessions suspended: external content read"
    },
    "map.th_agent": "Agent",
    "map.th_agent_sub": "profile · model@provider",
    "map.th_capped": "capped · always asks",
    "map.th_risk": {
      "one": "risk {risk} · {n} in a row to act on its own",
      "other": "risk {risk} · {n} in a row to act on its own"
    },
    "map.tot_actions": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "map.tot_alone": "{n} without asking",
    "map.tot_checked": "{n} verified by you",
    "map.tot_faults": {
      "one": "{n} fault",
      "other": "{n} faults"
    },
    "meta.actions": "Actions",
    "meta.actions_tip": "Every action of this agent tenure saw. Actions nobody verified (no answer, a timeout) count for nothing.",
    "meta.alone": "On its own",
    "meta.checked": "Verified by you",
    "meta.faults": "Faults",
    "meta.preset": "Preset",
    "meta.profile": "Profile",
    "meta.provider": "Provider",
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
    "missing.trusted_undo": "trusted until its first mistake · acts, then tells you, with an Undo",
    "model_menu.badge": "{tier} earned",
    "moment.dismiss": "Dismiss",
    "moment.eyebrow_down": "#Fault caught · {type}",
    "moment.eyebrow_up": "#Promotion · {type}",
    "moment.granted": "Tenure granted",
    "moment.on_probation": "On probation",
    "moment.probation": "Back on probation",
    "moment.review": "Under review",
    "moment.review_sub": "{name} now acts, then tells you, with an Undo.",
    "nav.label": "Tenure",
    "overview.actions_label": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "overview.actions_sub": "covered",
    "overview.alone_label": "acted without asking",
    "overview.alone_sub": "ran without asking, of {total}",
    "overview.aria": "Last 7 days",
    "overview.checked_label": "verified",
    "overview.checked_sub": "by you, of {total}",
    "overview.faults_label": "faults caught",
    "overview.faults_sub": {
      "one": "{faults} of {n} verified by you",
      "other": "{faults} of {n} verified by you"
    },
    "overview.window": "last 7 days, every profile",
    "page.animations": "Animations",
    "page.animations_reduced": "Your system asks for reduced motion: animations stay off",
    "page.raw_off": "redacted names",
    "page.raw_on": "raw names",
    "page.raw_title": "Show raw action type names (r)",
    "page.stale": "Last refresh failed ({error}). Showing the data from {time}.",
    "page.title": "Tenure",
    "page.unreadable": "Unreadable: {profiles}. Its database exists but cannot be opened; other profiles are shown.",
    "page.view_agents": "Agents",
    "page.view_benchmark": "Your benchmark",
    "page.view_community": "Community",
    "page.view_help": "Help",
    "page.view_map": "Map",
    "page.view_passport": "Passport",
    "page.view_settings": "Settings",
    "page.view_switch": "Switch preview",
    "page.view_undo": "Undo",
    "palette.no_current": "The current model has no record yet.",
    "palette.open": "Tenure: Open",
    "palette.passport": "Tenure: Show passport for current model",
    "palette.revoke": "Tenure: Revoke current model…",
    "passport.agent": "Agent",
    "passport.card_title": "Passport · Ed25519",
    "passport.col_guarantee": "guarantee",
    "passport.col_series": "series",
    "passport.col_sessions": "sessions",
    "passport.col_tier": "tier",
    "passport.copy_command": "Copy command",
    "passport.download": "Download passport (.json)",
    "passport.empty_body": "A passport covers an agent's record; it appears with the first verified action.",
    "passport.empty_title": "No passport yet",
    "passport.faults_checks": {
      "one": "{n} fault / {total} verified outcomes",
      "other": "{n} faults / {total} verified outcomes"
    },
    "passport.field_agent": "Agent",
    "passport.field_profile": "Profile",
    "passport.field_public_key": "Public key",
    "passport.field_settings": "Settings",
    "passport.field_signature": "Signature",
    "passport.field_type_names": "Type names",
    "passport.generated": "Generated",
    "passport.image_failed": "Could not draw the image",
    "passport.ledger": "Ledger",
    "passport.ledger_hint": "Export the ledger, to replay it:",
    "passport.ledger_value": {
      "one": "{n} event · head {head}",
      "other": "{n} events · head {head}"
    },
    "passport.more_types": {
      "one": "+{n} more action type, in the file",
      "other": "+{n} more action types, in the file"
    },
    "passport.note": "Signed and tamper-evident: a change after it is signed or anchored shows on verification. An older passport still verifies against a longer ledger; the verifier says what changed since.",
    "passport.pending_note": "Computed under the last logged settings; the new settings apply from the next action.",
    "passport.protocol": "Protocol",
    "passport.rule": "Rule",
    "passport.rule_osf": "preregistered on OSF",
    "passport.save_image": "Save image (.png)",
    "passport.signature": "a plugin for Hermes Agent",
    "passport.title": "Signed passport",
    "passport.trusted": "Trusted (not earned)",
    "passport.types_title": "Attested types",
    "passport.unavailable": "Not available: {error}",
    "passport.value_hashed": "{profile} (hashed)",
    "passport.value_none": "none",
    "passport.value_raw": "raw",
    "passport.value_redacted": "redacted after the program and subcommand",
    "passport.value_unsigned": "unsigned",
    "passport.verdict_chain": "Hash chain intact",
    "passport.verdict_ok_replay": "Replaying the ledger with the rule gives the same tiers",
    "passport.verdict_ok_signature": "Signature valid (Ed25519)",
    "passport.verdict_ok_title": "Verified",
    "passport.verdict_problems": {
      "one": "{n} problem found",
      "other": "{n} problems found"
    },
    "passport.verdict_unsigned_no_key": "No signing key yet: {cmd} creates one",
    "passport.verdict_unsigned_replay": "Replay gives the same tiers",
    "passport.verdict_unsigned_title": "Unsigned, otherwise verified",
    "passport.verify_hint": "Anyone can check it:",
    "passport.verifying": "Verifying…",
    "preset.copy_pending": "copied from another profile, checked when it starts",
    "preset.name.balanced": "balanced",
    "preset.name.careful": "careful",
    "preset.name.custom": "custom",
    "preset.name.fast": "fast",
    "preset.value": "{preset} · 1 in {k} spot-checked",
    "preset.value_pending": "{preset} · 1 in {k} spot-checked · applies from the next action",
    "pstyle.animation": "Animation",
    "pstyle.animation_desc_develop": "The emblem develops point by point, the ledger hash settles, then the seal prints.",
    "pstyle.animation_desc_holographic": "The card tilts slowly, with a glare band and a slow shimmer.",
    "pstyle.animation_desc_scan": "A scan line prints the card from top to bottom.",
    "pstyle.animation_desc_still": "No motion.",
    "pstyle.animation_develop": "Develop",
    "pstyle.animation_holographic": "Holographic",
    "pstyle.animation_scan": "Scan",
    "pstyle.animation_still": "Still",
    "pstyle.card": "Card",
    "pstyle.card_accent": "Accent",
    "pstyle.card_ink": "Ink",
    "pstyle.card_paper": "Paper",
    "pstyle.customise": "Customise",
    "pstyle.forced_still": "Animations are off, here or in your system: the passport stays still.",
    "pstyle.help": "How the passport looks, on this page and in the saved image. For you only, on this screen; what the card says never changes.",
    "pstyle.no_agent": "No agent yet: the preview appears with the first one.",
    "pstyle.pattern": "Emblem pattern",
    "pstyle.pattern_grid": "Grid",
    "pstyle.pattern_note": "Every pattern fills with the share of autonomy the agent earned, laid out from its id: the same agent always gets the same emblem.",
    "pstyle.pattern_rings": "Rings",
    "pstyle.pattern_sunburst": "Sunburst",
    "pstyle.preview": "Preview of your passport",
    "pstyle.title": "Your passport",
    "recent.check_failed": "check failed",
    "recent.check_failed_tip": "The automatic check failed: already counted as a fault. Undo restores the files.",
    "recent.collapse": "Hide the actions",
    "recent.expand": "Show each action",
    "recent.flag": "Flag",
    "recent.flag_tip": "It made an error nobody caught: revoke this type.",
    "recent.flagged": "{type} flagged: counted as a fault, it drops at least one tier.",
    "recent.hours_ago": {
      "one": "{n} h ago",
      "other": "{n} h ago"
    },
    "recent.just_now": "just now",
    "recent.minutes_ago": {
      "one": "{n} min ago",
      "other": "{n} min ago"
    },
    "recent.more_files": "+{n}",
    "recent.no_snapshot": "no snapshot",
    "recent.none": "Nothing to undo in the last 24 hours.",
    "recent.restore_icon": "Can be undone for 24 hours",
    "recent.show_all": "Show all {n}",
    "recent.show_fewer": "Show fewer",
    "recent.title": "Acted without asking",
    "recent.undo": "Undo",
    "recent.undo_failed": "Could not undo",
    "recent.undo_tip": "Restore the files as they were. Counts as a fault: the type goes back down.",
    "recent.undone": "Files restored. Counted as a fault.",
    "revoke.action": "Revoke all",
    "revoke.busy": "Revoking…",
    "revoke.confirm": "Revoke all",
    "revoke.desc": "Every action type of {name} asks first again and its series restarts from zero. Its record stays in the ledger. Not a fault.",
    "revoke.done": "Every action type of {name} asks first again.",
    "revoke.title": "Revoke all of this agent's earned autonomy?",
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
    "settings.no_writer": "This Hermes does not let this page save tenure's settings: use the command below.",
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
    "settings.start_study": "The preregistered study's start",
    "settings.start_trusted": "Covered types (file edits, memory, subagents, known development tools) ask nothing until their first fault, as Hermes alone would. A fault puts that type on Probation (T1), and it earns its tier back. Leaving the machine and money always ask.",
    "settings.strict_desc_off": "A new model inherits the previous model's record at low and medium stakes, halved and provisional until its own approvals confirm it. High stakes start over.",
    "settings.strict_desc_on": "A new model starts with an empty record on every action type, as in the study.",
    "settings.strict_help": "What a new model inherits when you switch models.",
    "settings.strict_off": "Strict mode off",
    "settings.strict_on": "Strict mode on",
    "settings.strict_title": "Strict mode on model change",
    "settings.use": "Use",
    "start.change_tip": "Change it in a terminal: hermes tenure start trusted|probation",
    "start.probation": "Study start (probation)",
    "start.trusted": "Trusted start",
    "state.aria": "{label}: {tip}",
    "state.fault": "fault",
    "state.fault_tip": "A medium or high fault stays on record until a trial is passed.",
    "state.provisional": "provisional",
    "state.provisional_tip": "Carried over from the previous model, halved, until its own approvals confirm it.",
    "state.suspended": "suspended",
    "state.suspended_tip": "A session read outside content: it asks for everything until it ends.",
    "state.trial": "trial",
    "state.trial_tip": "A medium or high fault opened a trial: 3 verified successes in a row.",
    "switch.arrow": "→",
    "switch.capped": "capped",
    "switch.col_after": "after the switch",
    "switch.col_now": "now",
    "switch.col_outcome": "outcome",
    "switch.col_public": "public measure",
    "switch.col_record": "your record",
    "switch.col_type": "type",
    "switch.count_carried": {
      "one": "{n} carried",
      "other": "{n} carried"
    },
    "switch.count_kept": {
      "one": "{n} kept",
      "other": "{n} kept"
    },
    "switch.count_reset": {
      "one": "{n} reset",
      "other": "{n} reset"
    },
    "switch.count_vetoed": {
      "one": "{n} vetoed",
      "other": "{n} vetoed"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "No agent to preview yet",
    "switch.footnote": "Public scores inform; they never grant autonomy. A veto only blocks carry-over, beyond a fixed margin.",
    "switch.from": "From",
    "switch.group_agents": "Your agents",
    "switch.label_carried": "carried, provisional",
    "switch.label_kept": "kept",
    "switch.label_reset": "reset",
    "switch.label_vetoed": "vetoed",
    "switch.lede": "Before you change model: what the new agent would inherit, type by type. A new model or provider is a new agent. Carry-over is our addition; strict mode is the study.",
    "switch.no_public": "no public measure",
    "switch.none": "none",
    "switch.other": "Other model…",
    "switch.pick_body": "Type any model id. Nothing changes until Hermes actually runs the new model.",
    "switch.pick_title": "Pick a target model",
    "switch.placeholder": "model id, e.g. {example} or model@provider",
    "switch.preview": "Preview",
    "switch.provisional": {
      "one": "{n} provisional",
      "other": "{n} provisional"
    },
    "switch.strict": "strict mode: nothing carries over",
    "switch.text_carried": "Part of the series carries over, marked provisional until the new model adds its own.",
    "switch.text_kept": "The new agent already has its own record here; it is never overwritten.",
    "switch.text_reset": "Starts from zero: high stakes, capped, or strict mode.",
    "switch.text_vetoed": "The public benchmark shows the new model weaker on this type: nothing carries over.",
    "switch.to": "To model",
    "switch.to_aria": "Target model",
    "tier.cap": "Capped · always asks",
    "tier.chip_trusted": "TRUSTED",
    "tier.name.cap": "Always asks",
    "tier.name.t1": "Probation",
    "tier.name.t2": "Under review",
    "tier.name.t3": "Tenured",
    "tier.name.trusted": "Trusted",
    "tier.t1": "T1 · asks first",
    "tier.t2": "T2 · acts, then tells you, with an Undo",
    "tier.t3": "T3 · acts on its own, spot-checked",
    "tier.trusted": "Trusted · acts like Hermes alone until its first mistake",
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
    "timeline.note": "From the hash-chained ledger, newest first, last 200 events. Repeated outcomes are grouped.",
    "timeline.title": "Evidence timeline",
    "toast.acted": {
      "one": "{type} changed, then told you ({name}).",
      "other": "{type}: {n} changes, then told you ({name})."
    },
    "toast.acted_detail": "Undo restores the files of the last change and counts as a fault.",
    "toast.transition": "{agent} · {type}: {from} → {to}",
    "transitions.empty": "None since this page opened. Every automatic tier change is listed here and in each agent's timeline.",
    "transitions.title": "Tier changes seen on this page",
    "transitions.why_after_fault": "after a fault",
    "transitions.why_changed": "without a fault: revoked, or the settings or stakes changed",
    "transitions.why_on_evidence": "on evidence",
    "transitions.why_trial_open": "trial open",
    "type.always_asks": "always asks",
    "type.flag_button": "Flag",
    "type.flag_done": "Fault recorded on {type}: now {tier}.",
    "type.flag_title": "Record a fault on this type, after the fact",
    "type.guarantee": "At most {aoql}% of this type's actions run with an error nobody approved; {worst}% if the model turns bad.",
    "type.guarantee_plain": "At most about 1 in {k} of its actions runs with an error nobody approved.",
    "type.guarantee_provisional": "At most {aoql}% of this type's actions run with an error nobody approved; {worst}% if the model turns bad. Provisional: carried-over evidence.",
    "type.in_a_row": "{series} of {required} in a row",
    "type.more_to_t2": {
      "one": "{n} more to reach Under review (T2)",
      "other": "{n} more to reach Under review (T2)"
    },
    "type.more_to_t3": {
      "one": "{n} more to Tenured",
      "other": "{n} more to Tenured"
    },
    "type.next": {
      "one": "{n} more verified success in a row to be tenured.",
      "other": "{n} more verified successes in a row to be tenured."
    },
    "type.next_session": "The series is complete: one more session finishes it.",
    "type.revoke_button": "Revoke",
    "type.revoke_done": "Revoked {type}: back to T1.",
    "type.revoke_title": "Take back what this type earned: back to T1",
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "high stakes",
    "type.stakes_low": "low stakes",
    "type.stakes_medium": "medium stakes",
    "type.stakes_other": "{stakes} stakes",
    "type.tenured_line": "Acts on its own. 1 action in {k} is still spot-checked.",
    "type.trusted_bar": "Trusted from the start: nothing earned yet",
    "type.trusted_line": "Trusted until its first mistake · acts like Hermes alone.",
    "type.trusted_line_undo": "Trusted until its first mistake · acts, then tells you, with an Undo.",
    "type.trusted_no_guarantee": "No guarantee yet: a guarantee comes only with a tier earned on evidence. Its first fault puts it on Probation (T1).",
    "types.title": "Action types",
    "undo.col_agent": "agent",
    "undo.col_effect": "effect of undo",
    "undo.col_file": "file",
    "undo.col_type": "type",
    "undo.col_when": "when",
    "undo.confirm": "Undo #{id}?",
    "undo.effect_already": "restores the files · the automatic check already counted a fault",
    "undo.effect_fault": "restores the files · counts as a fault",
    "undo.effect_none": "nothing to restore (no snapshot) · would count as a fault",
    "undo.empty_body": "File writes the agent made without asking (trusted, or at T2: acts, then tells you) keep a snapshot of the files for 24 hours. They appear here, newest first, each with its own Undo.",
    "undo.empty_title": "Nothing to undo",
    "undo.lede": "Recent act-then-notify actions. Undo restores the files from their snapshot and counts as a fault of the type.",
    "undo.title": "Restore the files",
    "undo.window_ends": "window ends in {duration}"
  },
  "ar": {
    "agents.pick": "اختر وكيلًا لترى ما اكتسبه.",
    "agents.search": "البحث في الوكلاء",
    "backend.desc": "فعّل tenure لهذا الملف الشخصي من المهارات ← الإضافات (عمود «الوكيل»). {error}",
    "backend.title": "جزء الوكيل لا يستجيب",
    "benchmark.col_faults": "إخفاقات / نتائج موثّقة",
    "benchmark.col_public": "عام",
    "benchmark.col_range": "نطاق 95%",
    "benchmark.col_rate": "المعدل",
    "benchmark.col_sessions": "الجلسات",
    "benchmark.empty_body": "كل إجراء موثّق يُضاف إلى سجل النموذج على ذلك النوع، هنا وفي {cmd}.",
    "benchmark.empty_title": "لا سجل بعد",
    "benchmark.faults": {
      "zero": "{n} إخفاقات / {total}",
      "one": "{n} إخفاق / {total}",
      "two": "{n} إخفاقان / {total}",
      "few": "{n} إخفاقات / {total}",
      "many": "{n} إخفاقًا / {total}",
      "other": "{n} إخفاق / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.no_public_type": "لا مقياس عام لنوع الإجراء هذا.",
    "benchmark.not_enough": "أدلة غير كافية",
    "benchmark.not_ranked": "لا أدلة كافية بعد",
    "benchmark.not_ranked_note": "يدخل النموذج الترتيب عندما يبلغ {n} نتيجة موثّقة على هذا النوع.",
    "benchmark.note": "السجل الموثَّق لكل نموذج على عملك لنوع الإجراء هذا، مع نطاق 95% لمعدل إخفاقه، مرتبًا حسب الحد الأعلى لهذا النطاق. النتيجة العامة للسياق فقط: قدرة على مهامهم، لا موثوقية على مهامك.",
    "benchmark.public_note": "قدرة عامة على مهامهم، لا موثوقية على مهامك.",
    "benchmark.public_score": "النتيجة العامة: {benchmark}، {source}",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "معدل الإخفاق ونطاق 95% له، على محور من 0 إلى {max}%",
    "benchmark.rate": "{rate}% ({low}–{high}%)",
    "benchmark.search": "البحث في أنواع الإجراءات",
    "benchmark.source": "{source}. أفضل نتيجة منشورة، بأي أداة تقييم؛ ليست مقارنة مضبوطة.",
    "benchmark.source_accessed": "{source}، اطُّلع عليه في {accessed}. أفضل نتيجة منشورة، بأي أداة تقييم؛ ليست مقارنة مضبوطة.",
    "cell.capped_by_settings": "مقيَّد بإعدادات المخاطرة",
    "cell.kind_irreversible": "{type} · {stakes}، لا يمكن التراجع عنه",
    "cell.kind_reversible": "{type} · {stakes}، يمكن التراجع عنه",
    "cell.provisional_long": {
      "zero": "{n} منقولة من النموذج السابق، مؤقتة",
      "one": "{n} منقول من النموذج السابق، مؤقت",
      "two": "{n} منقولان من النموذج السابق، مؤقتان",
      "few": "{n} منقولة من النموذج السابق، مؤقتة",
      "many": "{n} منقولة من النموذج السابق، مؤقتة",
      "other": "{n} منقولة من النموذج السابق، مؤقتة"
    },
    "cell.record": "السجل: {successes} نجاحات · {faults} إخفاقات · {neutrals} محايدة · {spot} فحوص عشوائية",
    "cell.series": "السلسلة {series}/{required} على التوالي",
    "cell.sessions": {
      "zero": "{n} جلسات",
      "one": "{n} جلسة",
      "two": "{n} جلستان",
      "few": "{n} جلسات",
      "many": "{n} جلسةً",
      "other": "{n} جلسة"
    },
    "cell.tier_now": "المستوى الآن: {tier} ({name})",
    "chip.tip": {
      "zero": "{name}: {earned} من {n} أنواع إجراءات اكتسبت الاستقلالية (T2 أو T3). افتح Tenure.",
      "one": "{name}: {earned} من {n} نوع إجراء اكتسب الاستقلالية (T2 أو T3). افتح Tenure.",
      "two": "{name}: {earned} من {n} نوعَي إجراء اكتسبا الاستقلالية (T2 أو T3). افتح Tenure.",
      "few": "{name}: {earned} من {n} أنواع إجراءات اكتسبت الاستقلالية (T2 أو T3). افتح Tenure.",
      "many": "{name}: {earned} من {n} نوعَ إجراء اكتسبت الاستقلالية (T2 أو T3). افتح Tenure.",
      "other": "{name}: {earned} من {n} نوعِ إجراء اكتسبت الاستقلالية (T2 أو T3). افتح Tenure."
    },
    "common.loading": "جارٍ قراءة الأدلة…",
    "common.no_match": "لا نتائج",
    "common.own_profile_only": "يخص الملف الشخصي الحالي فقط",
    "common.retry": "حاول مرة أخرى",
    "community.col_contributors": "المساهمون",
    "community.col_model": "النموذج",
    "community.empty_how": "للمساهمة، اكتب سجلك بهذا الأمر، واقرأ ما يحتويه، ثم افتح طلب دمج (pull request) يضيف الملف إلى المستودع المجتمعي ({repo}).",
    "community.empty_title": "لا توجد سجلات مشتركة بعد",
    "community.empty_what": "يجمع المقياس المجتمعي السجلات التي اختار مستخدمو Tenure نشرها: لكل نموذج ولكل فئة إجراءات، النجاحات المُتحقَّق منها والإخفاقات، موقَّعة بمفتاح جوازهم. لا يُشارَك شيء تلقائيًا: لا يُجري Tenure أي اتصال بالشبكة.",
    "community.empty_where": "لعرض الترتيب هنا، نزّل ملف community-board.json الذي ينشره المستودع واحفظه باسم {path}.",
    "community.generated": "{records} · أُنشئ الترتيب في {date}",
    "community.lede": "مُصرَّح به من المساهمين، مع التحقق من التوقيعات: كل سجل موقَّع بمفتاح جواز صاحبه، ويُحتسب سجل واحد لكل مفتاح. ",
    "community.lede_bold": "هذا لا يمنع شخصًا واحدًا من امتلاك عدة مفاتيح.",
    "community.models": {
      "zero": "{n} نماذج",
      "one": "{n} نموذج",
      "two": "{n} نموذجان",
      "few": "{n} نماذج",
      "many": "{n} نموذجًا",
      "other": "{n} نموذج"
    },
    "community.ranking": "لكل فئة إجراءات، تُرتَّب النماذج حسب الحد الأعلى لنطاق 95% لمعدل إخفاقها، وليس أبدًا حسب نتيجة واحدة.",
    "community.records": {
      "zero": "{n} سجلات",
      "one": "{n} سجل",
      "two": "{n} سجلّان",
      "few": "{n} سجلات",
      "many": "{n} سجلًّا",
      "other": "{n} سجل"
    },
    "confirm.flag_desc": "يُحتسب هذا إخفاقًا: ينزل {type} مستوى واحدًا على الأقل ويصعد من جديد. استخدمه لخطأ لم يلاحظه أحد.",
    "confirm.flag_title": "الإبلاغ عن {type} كخطأ؟",
    "confirm.revoke_desc": "سيسأل {type} أولًا من جديد، وتبدأ سلسلته من الصفر. هذا ليس إخفاقًا.",
    "confirm.revoke_title": "سحب {type}؟",
    "confirm.undo_title": "التراجع عن الإجراء {id}؟",
    "emblem.none": "لم تُكتسب أي استقلالية بعد",
    "emblem.review": {
      "zero": "أنواع قيد المراجعة: {n}",
      "one": "أنواع قيد المراجعة: {n}",
      "two": "أنواع قيد المراجعة: {n}",
      "few": "أنواع قيد المراجعة: {n}",
      "many": "أنواع قيد المراجعة: {n}",
      "other": "أنواع قيد المراجعة: {n}"
    },
    "emblem.tenured": {
      "zero": "أنواع مُثبَّتة: {n}",
      "one": "أنواع مُثبَّتة: {n}",
      "two": "أنواع مُثبَّتة: {n}",
      "few": "أنواع مُثبَّتة: {n}",
      "many": "أنواع مُثبَّتة: {n}",
      "other": "أنواع مُثبَّتة: {n}"
    },
    "emblem.trusted": {
      "zero": "لا أنواع موثوقة",
      "one": "نوع واحد موثوق، غير مكتسب",
      "two": "نوعان موثوقان، غير مكتسبين",
      "few": "{n} أنواع موثوقة، غير مكتسبة",
      "many": "{n} نوعًا موثوقًا، غير مكتسب",
      "other": "{n} نوع موثوق، غير مكتسب"
    },
    "event.confirmed": "أدلة منقولة أكّدتها أدلته هو",
    "event.fault_check": "فشل الفحص التلقائي",
    "event.fault_flag": "أبلغتَ عنه كإخفاق",
    "event.fault_other": "إخفاق ({source})",
    "event.fault_refusal": "رفضتَه",
    "event.fault_spot": "فحص عشوائي مرفوض أو فاشل",
    "event.fault_undo": "تراجعتَ عنه",
    "event.neutral_alone": "عمل وحده (مكتسب)",
    "event.neutral_ambiguous": "استدعاء ملتبس · بلا دليل",
    "event.neutral_blocked": "حظره حارس آخر · بلا دليل",
    "event.neutral_error": "خطأ في الأداة · بلا دليل",
    "event.neutral_expired": "لم يرجع بنتيجة · بلا دليل",
    "event.neutral_nobody": "لا أحد ليجيب · بلا دليل",
    "event.neutral_other": "محايد ({source})",
    "event.neutral_timeout": "بلا إجابة · بلا دليل",
    "event.revoked": "سحبتَه",
    "event.success_approved": "وافقتَ عليه، ونُفّذ بسلام",
    "event.success_notify": "نفّذ ثم أبلغ · لم يُتراجع عنه",
    "event.success_spot": "فحص عشوائي وافقتَ عليه",
    "event.switch": "تبديل النموذج",
    "event.switch_from": "تبديل النموذج من {from}",
    "event.tier": "المستوى: من {from} إلى {to} · {why}",
    "event.trial_failed": {
      "zero": "فشل الاختبار: انتظر {n} إجراءات",
      "one": "فشل الاختبار: انتظر {n} إجراء",
      "two": "فشل الاختبار: انتظر {n} إجراءين",
      "few": "فشل الاختبار: انتظر {n} إجراءات",
      "many": "فشل الاختبار: انتظر {n} إجراءً",
      "other": "فشل الاختبار: انتظر {n} إجراء"
    },
    "event.trial_opened": {
      "zero": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "one": "فُتح اختبار: يجب أن ينجح الإجراء التالي",
      "two": "فُتح اختبار: يجب أن ينجح الإجراءان التاليان",
      "few": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "many": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "other": "فُتح اختبار: يجب أن تنجح الإجراءات الـ{n} التالية"
    },
    "event.trial_passed": "اجتاز الاختبار",
    "event.trial_reopens": {
      "zero": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "one": "يُعاد فتح الاختبار: يجب أن ينجح الإجراء التالي",
      "two": "يُعاد فتح الاختبار: يجب أن ينجح الإجراءان التاليان",
      "few": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "many": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{n} التالية",
      "other": "يُعاد فتح الاختبار: يجب أن تنجح الإجراءات الـ{n} التالية"
    },
    "event.why_fault": "إخفاق",
    "event.why_series_complete": "اكتملت السلسلة",
    "event.why_series_n": "السلسلة {required}/{required}",
    "event.why_sessions": {
      "zero": "{n} جلسات",
      "one": "{n} جلسة",
      "two": "{n} جلستان",
      "few": "{n} جلسات",
      "many": "{n} جلسةً",
      "other": "{n} جلسة"
    },
    "event.why_settings": "إعدادات أكثر صرامة",
    "event.why_stakes": "تغيّرت الخطورة",
    "event.why_wald": "اجتاز الاختبار التتابعي",
    "flag.confirm": "إبلاغ",
    "flag.desc": "يُحسب هذا إخفاقًا: سينزل {type} مستوى واحدًا على الأقل ثم يصعد من جديد. استخدمه لخطأ لم يلحظه أحد.",
    "flag.title": "الإبلاغ عن هذا التغيير كخطأ؟",
    "help.asks_body": "أيًّا كانت البداية، تسألك بعض الإجراءات أولًا:",
    "help.asks_files": "تعديلات الملفات تحتفظ بزر التراجع، وكذلك أوامر rm وmv وcp وsed -i وecho > ملف البسيطة على ملفات المشروع: يمكن إرجاع أي تغيير جرى دون سؤال.",
    "help.asks_irreversible": "ما لا يمكن التراجع عنه: الحذف التكراري، أو نمط * أو متغير في أمر ملفات، أو التخلص من عمل git غير المحفوظ، وكل ما يمر عبر sudo.",
    "help.asks_leaves": "ما يغادر الجهاز: النشر، والإطلاق، والدفع إلى مستودع بعيد، وإرسال بريد، والمدفوعات.",
    "help.asks_outside": "بعد أن يقرأ الوكيل محتوى خارجيًا (صفحة ويب، بريدًا إلكترونيًا، ملفًا منزّلًا)، تسأل أوامره حتى تبدأ جلسة جديدة بـ /new؛ أما تعديلات الملفات، بما فيها أوامر rm وmv وcp البسيطة، فتستمر مع زر التراجع.",
    "help.asks_title": "ما الذي يسأل، ولماذا",
    "help.asks_unknown": "البرامج التي لا يعرفها tenure: أداة قاعدة بيانات أو سحابة، أو أمر مجهول.",
    "help.benchmark_body": "مقياسك هو السجل الموثَّق لكل نموذج على عملك أنت، لكل نوع إجراء، مع نطاق 95% لمعدل إخفاقه. يدخل النموذج الترتيب عندما يبلغ {n} نتيجة موثّقة على نوع ما. النتيجة العامة، حين تظهر، للسياق فقط: قدرة على مهام غيرك، لا موثوقية على مهامك.",
    "help.flag_body": "الإبلاغ يرصد خطأً لم يلحظه أحد. ويُحسب إخفاقًا: ينزل النوع مستوى واحدًا على الأقل، ثم يصعد من جديد.",
    "help.intro": "يقرّر tenure، لكل نموذج ولكل نوع إجراء، هل يسألك Hermes أولًا، أم ينفّذ ثم يُبلغك، أم يعمل وحده. كل قرار ينبع من أدلة موثّقة مكتوبة في دفتر موقَّع.",
    "help.key_close": "إغلاق",
    "help.key_help": "هذه المساعدة",
    "help.key_next_prev": "الوكيل التالي / السابق",
    "help.key_open": "فتح الوكيل المحدد",
    "help.key_raw": "إظهار / إخفاء الأسماء الخام للأنواع",
    "help.keys_note": "تعمل الاختصارات عندما يكون التركيز داخل هذه الصفحة.",
    "help.keys_title": "لوحة المفاتيح",
    "help.passport_body": "الجواز ملخّص موقَّع لسجل الوكيل: مستوى كل نوع إجراء، وإخفاقاته ونتائجه الموثّقة، ورأس دفتر سلسلة التجزئة. وهو موقَّع بمفتاح Ed25519 الخاص بهذا الملف الشخصي. للتحقق منه، نزّله، وصدّر الدفتر، ثم تحقّق:",
    "help.passport_checks": "يتحقق الفحص من التوقيع ومن سلسلة التجزئة، ثم يعيد تشغيل الدفتر ليحسب المستويات نفسها. لا شيء فيه مُعلَن ذاتيًا.",
    "help.session_body": "بعض الأسئلة (شيفرة تُشغَّل مباشرة، وأوامر shell المعقدة، وأوامر محلية غير مشمولة مثل rm وmv وcp، وأمر بعد قراءة محتوى خارجي) تعرض «السماح لهذه الجلسة»: فيسكت ذلك السؤال حتى تنتهي الجلسة. إنه اختيارك، لا دليل: لا يُكسب شيئًا، والجلسة الجديدة تسأل من جديد.",
    "help.session_title": "السماح لهذه الجلسة",
    "help.study_adds": "ما يضيفه tenure: البداية الموثوقة (ليست من الدراسة: الإجراءات الموثوقة لا تكسب شيئًا)، وفحوص عشوائية على نوع يعمل وحده، وجلستان مختلفتان في السلسلة التي تبلغ T3، والإيقاف بعد محتوى خارجي، والنقل إلى نموذج جديد (الوضع الصارم هو الدراسة). start: probation هي بداية الدراسة نفسها.",
    "help.study_body": "بعد أول إخفاق لنوع ما، أو منذ البداية مع start: probation، يطبّق tenure قاعدة دراسة مسجّلة مسبقًا عن الاستقلالية المكتسبة: اختبار تتابعي (Wald) للمستوى الأوسط، أي التنفيذ ثم إعلامك، وسلسلة CSP-1 (خطة Dodge للمعاينة المستمرة) لمستوى مُثبَّت (T3). تعيد الدراسة تشغيل هذه القاعدة على أكثر من 6000 وكيل محاكى. نتائجها لم تصدر بعد: لا يدّعي tenure أن الدراسة أكّدت القاعدة.",
    "help.study_link": "التسجيل المسبق على OSF",
    "help.study_title": "الدراسة وراء القاعدة",
    "help.tiers_climb": "يصعد النوع بنجاحات موثّقة دون إخفاق. من فترة الاختبار، يبلغ قيد المراجعة (T2) بعد {low} على التوالي على الأقل عند الخطورة المنخفضة، أو {medium} عند المتوسطة؛ ولا يمر بـ T2 إلا الأنواع القابلة للتراجع. وسلسلة أطول، موزّعة على {sessions} جلسات على الأقل، تجعله مُثبَّتًا (T3).",
    "help.tiers_drop": "إخفاق واحد يُنزل النوع، وتبدأ سلسلته من جديد.",
    "help.tiers_title": "المستويات",
    "help.title": "كيف يعمل tenure",
    "help.trusted_body": "افتراضيًا، أنواع الإجراءات التي يشملها tenure (تعديل الملفات، والذاكرة، وإسناد العمل إلى وكيل فرعي، وأدوات التطوير المعتادة) لا تسأل شيئًا حتى أول إخفاق لها، كما يعمل Hermes وحده. أول إخفاق (تراجع، أو فحص فاشل، أو إبلاغ) يضع ذلك النوع في فترة اختبار (T1): من بعدها يسأل أولًا ويستعيد مستواه من إجاباتك. لا شيء مما يُنجز في البداية الموثوقة يُحسب مكتسبًا.",
    "help.trusted_title": "البداية الموثوقة",
    "help.undo_body": "التغيير الذي جرى دون سؤال يحتفظ بزر التراجع لمدة 24 ساعة: في الإشعار، وتحت «نُفّذ دون سؤال» في صفحة الوكيل، أو في محادثة. التراجع يعيد الملفات ويُحسب إخفاقًا: ينزل النوع من جديد.",
    "help.undo_title": "التراجع والإبلاغ",
    "hero.agent": "الوكيل",
    "intro.body": "يبدأ كل نوع إجراء لكل نموذج في T1: يسأل أولًا. سلسلة من الإجراءات السليمة الموافق عليها تنقله إلى T2: ينفّذ ثم يُبلغك، مع زر تراجع. وسلسلة أطول، على جلستين، تنقله إلى T3: يعمل وحده، ويظل إجراء واحد من كل {k} يسأل، كفحص عشوائي. إخفاق واحد يُنزل النوع من جديد.",
    "intro.body_trusted": "يبدأ كل نوع إجراء موثوقًا: حتى أول خطأ له يعمل كما يعمل Hermes وحده، والتغيير القابل للتراجع ينفّذ ثم يُبلغك، مع زر تراجع. أول إخفاق له (تراجع، أو فحص فاشل، أو إبلاغ) يضعه في فترة اختبار (T1): يسأل أولًا. سلسلة من الإجراءات السليمة الموافق عليها تنقله إلى T2، وسلسلة أطول، على جلستين، إلى T3: يعمل وحده، ويظل إجراء واحد من كل {k} يسأل، كفحص عشوائي. مغادرة الجهاز والمال يسألان دائمًا.",
    "intro.got_it": "فهمت",
    "intro.title": "كيف يكتسب نوع الإجراء مستواه",
    "legend.a_share": "نسبة منها",
    "legend.alone": "يعمل وحده، ويُفحص {share} عشوائيًا",
    "legend.ask": "يسأل أولًا",
    "legend.capped": "مقيَّد: يسأل دائمًا",
    "legend.carried": "من النموذج السابق، مؤقت",
    "legend.carried_flag": "منقول",
    "legend.notify": "ينفّذ ثم يُبلغ مع إمكانية التراجع (الأنواع القابلة للتراجع)",
    "legend.series": "نجاحات موثَّقة على التوالي، من أصل N مطلوبة",
    "legend.trusted": "بداية موثوقة: يعمل مثل Hermes وحده حتى أول خطأ له، دون أي اكتساب",
    "map.aria": "الوكلاء حسب نوع الإجراء",
    "map.asked_suffix": " بسؤال",
    "map.capped": "مقيَّد",
    "map.carried_n": {
      "zero": "{n} منقولة",
      "one": "{n} منقول",
      "two": "{n} منقولان",
      "few": "{n} منقولة",
      "many": "{n} منقولة",
      "other": "{n} منقولة"
    },
    "map.copy_pending": "منسوخ من ملف شخصي آخر، يُفحص عند تشغيله",
    "map.count_faults": {
      "zero": "{n} إخفاقات",
      "one": "{n} إخفاق",
      "two": "{n} إخفاقان",
      "few": "{n} إخفاقات",
      "many": "{n} إخفاقًا",
      "other": "{n} إخفاق"
    },
    "map.count_sessions": {
      "zero": "{n} جلسات",
      "one": "{n} جلسة",
      "two": "{n} جلستان",
      "few": "{n} جلسات",
      "many": "{n} جلسةً",
      "other": "{n} جلسة"
    },
    "map.current": " · الملف الشخصي الحالي",
    "map.empty_after": "، ولا يصعد إلا بنجاحات موثّقة: تبلغ الأنواع القابلة للتراجع المستوى الأوسط بعد سلسلة من النجاحات الموثّقة دون إخفاق، وT3 بعد سلسلة كاملة من N على جلستين.",
    "map.empty_before": "يبدأ tenure العدّ عند أول إجراء يطلب الوكيل تنفيذه. القراءة لا تسأل أبدًا. يبدأ كل نوع إجراء في ",
    "map.empty_bold": "T1، يسأل أولًا",
    "map.empty_title": "لا أدلة بعد",
    "map.empty_trusted": "اعمل كالمعتاد. كل نوع إجراء يعمل كما يعمل Hermes وحده حتى أول خطأ له؛ وبعدها يسأل أولًا ويستعيد مستواه من إجاباتك.",
    "map.fault_on_record": "إخفاق مسجَّل",
    "map.group_high": "خطورة عالية",
    "map.group_low": "خطورة منخفضة",
    "map.group_medium": "خطورة متوسطة",
    "map.held": "{tier} مخزَّن، تُقيّده إعداداتك",
    "map.one_in": "1 من كل {k}",
    "map.pending": "يسري من الإجراء التالي",
    "map.preset": "الإعداد المسبق {preset}",
    "map.profile": "الملف الشخصي {profile}",
    "map.read_only": " · للقراءة فقط هنا",
    "map.spot": "فحوص عشوائية {rate}",
    "map.start_probation": "بداية بالدراسة (فترة اختبار)",
    "map.start_trusted": "بداية موثوقة",
    "map.strict": "صارم",
    "map.suspended": {
      "zero": "{n} جلسات معلّقة: قُرئ محتوى خارجي",
      "one": "{n} جلسة معلّقة: قُرئ محتوى خارجي",
      "two": "{n} جلستان معلّقتان: قُرئ محتوى خارجي",
      "few": "{n} جلسات معلّقة: قُرئ محتوى خارجي",
      "many": "{n} جلسةً معلّقة: قُرئ محتوى خارجي",
      "other": "{n} جلسة معلّقة: قُرئ محتوى خارجي"
    },
    "map.th_agent": "الوكيل",
    "map.th_agent_sub": "الملف الشخصي · model@provider",
    "map.th_capped": "مقيَّد · يسأل دائمًا",
    "map.th_risk": {
      "zero": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "one": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "two": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "few": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "many": "المخاطرة {risk} · {n} على التوالي ليعمل وحده",
      "other": "المخاطرة {risk} · {n} على التوالي ليعمل وحده"
    },
    "map.tot_actions": {
      "zero": "{n} إجراءات",
      "one": "{n} إجراء",
      "two": "{n} إجراءان",
      "few": "{n} إجراءات",
      "many": "{n} إجراءً",
      "other": "{n} إجراء"
    },
    "map.tot_alone": "{n} دون سؤال",
    "map.tot_checked": "{n} وثّقتها أنت",
    "map.tot_faults": {
      "zero": "{n} إخفاقات",
      "one": "{n} إخفاق",
      "two": "{n} إخفاقان",
      "few": "{n} إخفاقات",
      "many": "{n} إخفاقًا",
      "other": "{n} إخفاق"
    },
    "meta.actions": "الإجراءات",
    "meta.actions_tip": "كل إجراء لهذا الوكيل رآه tenure. الإجراءات التي لم يتحقق منها أحد (بلا إجابة، أو انتهت المهلة) لا تُحسب.",
    "meta.alone": "وحده",
    "meta.checked": "بتوثيقك",
    "meta.faults": "الإخفاقات",
    "meta.preset": "الإعداد المسبق",
    "meta.profile": "الملف الشخصي",
    "meta.provider": "المزوّد",
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
    "model_menu.badge": "{tier} مكتسب",
    "moment.dismiss": "إغلاق",
    "moment.eyebrow_down": "#رُصد إخفاق · {type}",
    "moment.eyebrow_up": "#ترقية · {type}",
    "moment.granted": "مُنح التثبيت",
    "moment.on_probation": "في فترة اختبار",
    "moment.probation": "العودة إلى فترة الاختبار",
    "moment.review": "قيد المراجعة",
    "moment.review_sub": "{name} ينفّذ الآن ثم يُبلغك، مع زر تراجع.",
    "nav.label": "Tenure",
    "overview.actions_label": {
      "zero": "{n} إجراءات",
      "one": "{n} إجراء",
      "two": "{n} إجراءان",
      "few": "{n} إجراءات",
      "many": "{n} إجراءً",
      "other": "{n} إجراء"
    },
    "overview.actions_sub": "مشمولة",
    "overview.alone_label": "نُفّذت دون سؤال",
    "overview.alone_sub": "نُفّذت دون سؤال، من {total}",
    "overview.aria": "آخر 7 أيام",
    "overview.checked_label": "موثّقة",
    "overview.checked_sub": "بتوثيقك، من {total}",
    "overview.faults_label": "إخفاقات مكتشفة",
    "overview.faults_sub": {
      "zero": "{faults} من {n} وثّقتها أنت",
      "one": "{faults} من {n} وثّقتها أنت",
      "two": "{faults} من {n} وثّقتها أنت",
      "few": "{faults} من {n} وثّقتها أنت",
      "many": "{faults} من {n} وثّقتها أنت",
      "other": "{faults} من {n} وثّقتها أنت"
    },
    "overview.window": "آخر 7 أيام، كل الملفات الشخصية",
    "page.animations": "الرسوم المتحركة",
    "page.animations_reduced": "يطلب نظامك تقليل الحركة: تبقى الرسوم المتحركة متوقفة",
    "page.raw_off": "أسماء محجوبة",
    "page.raw_on": "أسماء خام",
    "page.raw_title": "إظهار الأسماء الخام لأنواع الإجراءات (r)",
    "page.stale": "فشل آخر تحديث ({error}). تُعرض بيانات {time}.",
    "page.title": "Tenure",
    "page.unreadable": "غير مقروء: {profiles}. قاعدة بياناته موجودة لكن يتعذّر فتحها؛ تُعرض الملفات الشخصية الأخرى.",
    "page.view_agents": "الوكلاء",
    "page.view_benchmark": "مقياسك",
    "page.view_community": "المجتمع",
    "page.view_help": "المساعدة",
    "page.view_map": "الخريطة",
    "page.view_passport": "الجواز",
    "page.view_settings": "الإعدادات",
    "page.view_switch": "معاينة التبديل",
    "page.view_undo": "تراجع",
    "palette.no_current": "لا سجل للنموذج الحالي بعد.",
    "palette.open": "Tenure: فتح",
    "palette.passport": "Tenure: عرض جواز النموذج الحالي",
    "palette.revoke": "Tenure: سحب استقلالية النموذج الحالي…",
    "passport.agent": "الوكيل",
    "passport.card_title": "جواز · Ed25519",
    "passport.col_guarantee": "الضمان",
    "passport.col_series": "السلسلة",
    "passport.col_sessions": "الجلسات",
    "passport.col_tier": "المستوى",
    "passport.copy_command": "نسخ الأمر",
    "passport.download": "تنزيل الجواز (.json)",
    "passport.empty_body": "يغطي الجواز سجل الوكيل؛ ويظهر مع أول إجراء موثّق.",
    "passport.empty_title": "لا جواز بعد",
    "passport.faults_checks": {
      "zero": "{n} إخفاق / {total} نتائج موثّقة",
      "one": "{n} إخفاق / {total} نتائج موثّقة",
      "two": "{n} إخفاق / {total} نتائج موثّقة",
      "few": "{n} إخفاق / {total} نتائج موثّقة",
      "many": "{n} إخفاق / {total} نتائج موثّقة",
      "other": "{n} إخفاق / {total} نتائج موثّقة"
    },
    "passport.field_agent": "الوكيل",
    "passport.field_profile": "الملف الشخصي",
    "passport.field_public_key": "المفتاح العام",
    "passport.field_settings": "الإعدادات",
    "passport.field_signature": "التوقيع",
    "passport.field_type_names": "أسماء الأنواع",
    "passport.generated": "أُنشئ في",
    "passport.image_failed": "تعذّر رسم الصورة",
    "passport.ledger": "الدفتر",
    "passport.ledger_hint": "صدّر الدفتر لإعادة تشغيله:",
    "passport.ledger_value": {
      "zero": "{n} أحداث · الرأس {head}",
      "one": "{n} حدث · الرأس {head}",
      "two": "{n} حدثان · الرأس {head}",
      "few": "{n} أحداث · الرأس {head}",
      "many": "{n} حدثًا · الرأس {head}",
      "other": "{n} حدث · الرأس {head}"
    },
    "passport.more_types": {
      "zero": "+{n} أنواع إجراءات أخرى، في الملف",
      "one": "+{n} نوع إجراء آخر، في الملف",
      "two": "+{n} نوعا إجراء آخران، في الملف",
      "few": "+{n} أنواع إجراءات أخرى، في الملف",
      "many": "+{n} نوعَ إجراء آخر، في الملف",
      "other": "+{n} نوعِ إجراء آخر، في الملف"
    },
    "passport.note": "موقَّع ويكشف التلاعب: أي تغيير بعد توقيعه أو تثبيته يظهر عند التحقق. يظل الجواز الأقدم صالحًا مقابل دفتر أطول؛ ويذكر المتحقِّق ما تغيّر منذ ذلك.",
    "passport.pending_note": "محسوب وفق آخر إعدادات مسجّلة؛ تسري الإعدادات الجديدة من الإجراء التالي.",
    "passport.protocol": "البروتوكول",
    "passport.rule": "القاعدة",
    "passport.rule_osf": "مسجّلة مسبقًا على OSF",
    "passport.save_image": "حفظ الصورة (.png)",
    "passport.signature": "إضافة لـ Hermes Agent",
    "passport.title": "جواز موقَّع",
    "passport.trusted": "موثوق (غير مكتسب)",
    "passport.types_title": "الأنواع المشهود لها",
    "passport.unavailable": "غير متاح: {error}",
    "passport.value_hashed": "{profile} (مجزَّأ)",
    "passport.value_none": "لا شيء",
    "passport.value_raw": "خام",
    "passport.value_redacted": "محجوب بعد البرنامج والأمر الفرعي",
    "passport.value_unsigned": "غير موقَّع",
    "passport.verdict_chain": "سلسلة التجزئة سليمة",
    "passport.verdict_ok_replay": "إعادة تشغيل الدفتر بالقاعدة تعطي المستويات نفسها",
    "passport.verdict_ok_signature": "التوقيع صالح (Ed25519)",
    "passport.verdict_ok_title": "تم التحقق",
    "passport.verdict_problems": {
      "zero": "وُجدت {n} مشكلات",
      "one": "وُجدت {n} مشكلة",
      "two": "وُجدت {n} مشكلتان",
      "few": "وُجدت {n} مشكلات",
      "many": "وُجدت {n} مشكلةً",
      "other": "وُجدت {n} مشكلة"
    },
    "passport.verdict_unsigned_no_key": "لا مفتاح توقيع بعد: {cmd} ينشئ واحدًا",
    "passport.verdict_unsigned_replay": "إعادة التشغيل تعطي المستويات نفسها",
    "passport.verdict_unsigned_title": "غير موقَّع، وما عدا ذلك سليم",
    "passport.verify_hint": "يمكن لأي شخص التحقق منه:",
    "passport.verifying": "جارٍ التحقق…",
    "preset.copy_pending": "منسوخ من ملف شخصي آخر، يُفحص عند تشغيله",
    "preset.name.balanced": "متوازن",
    "preset.name.careful": "حذِر",
    "preset.name.custom": "مخصص",
    "preset.name.fast": "سريع",
    "preset.value": "{preset} · فحص عشوائي لإجراء من كل {k}",
    "preset.value_pending": "{preset} · فحص عشوائي لإجراء من كل {k} · يسري من الإجراء التالي",
    "pstyle.animation": "الحركة",
    "pstyle.animation_desc_develop": "يظهر الشعار نقطة بنقطة، ويستقر تجزئة السجل، ثم يُطبع الختم.",
    "pstyle.animation_desc_holographic": "تميل البطاقة ببطء، مع شريط لمعان وبريق بطيء.",
    "pstyle.animation_desc_scan": "خط مسح يطبع البطاقة من الأعلى إلى الأسفل.",
    "pstyle.animation_desc_still": "بلا حركة.",
    "pstyle.animation_develop": "إظهار",
    "pstyle.animation_holographic": "هولوغرافي",
    "pstyle.animation_scan": "مسح",
    "pstyle.animation_still": "ثابت",
    "pstyle.card": "البطاقة",
    "pstyle.card_accent": "لون التمييز",
    "pstyle.card_ink": "حبر",
    "pstyle.card_paper": "ورق",
    "pstyle.customise": "تخصيص",
    "pstyle.forced_still": "الحركة متوقفة، هنا أو في نظامك: يبقى الجواز ثابتًا.",
    "pstyle.help": "مظهر الجواز، في هذه الصفحة وفي الصورة المحفوظة. لك وحدك، على هذه الشاشة؛ ما تقوله البطاقة لا يتغيّر أبدًا.",
    "pstyle.no_agent": "لا يوجد وكيل بعد: تظهر المعاينة مع أول وكيل.",
    "pstyle.pattern": "نقش الشعار",
    "pstyle.pattern_grid": "شبكة",
    "pstyle.pattern_note": "كل نقش يمتلئ بحصة الاستقلالية التي اكتسبها الوكيل، ويُرتَّب انطلاقًا من معرّفه: للوكيل نفسه الشعار نفسه دائمًا.",
    "pstyle.pattern_rings": "حلقات",
    "pstyle.pattern_sunburst": "شمس",
    "pstyle.preview": "معاينة جواز سفرك",
    "pstyle.title": "جواز سفرك",
    "recent.check_failed": "فشل الفحص",
    "recent.check_failed_tip": "فشل الفحص التلقائي: حُسب إخفاقًا بالفعل. التراجع يستعيد الملفات.",
    "recent.collapse": "إخفاء الإجراءات",
    "recent.expand": "عرض كل إجراء",
    "recent.flag": "إبلاغ",
    "recent.flag_tip": "ارتكب خطأ لم يلحظه أحد: اسحب استقلالية هذا النوع.",
    "recent.flagged": "تم الإبلاغ عن {type}: يُحتسب إخفاقًا، وينزل مستوى واحدًا على الأقل.",
    "recent.hours_ago": {
      "zero": "قبل {n} س",
      "one": "قبل {n} س",
      "two": "قبل {n} س",
      "few": "قبل {n} س",
      "many": "قبل {n} س",
      "other": "قبل {n} س"
    },
    "recent.just_now": "الآن",
    "recent.minutes_ago": {
      "zero": "قبل {n} د",
      "one": "قبل {n} د",
      "two": "قبل {n} د",
      "few": "قبل {n} د",
      "many": "قبل {n} د",
      "other": "قبل {n} د"
    },
    "recent.more_files": "+{n}",
    "recent.no_snapshot": "بلا لقطة",
    "recent.none": "لا شيء للتراجع عنه في آخر 24 ساعة.",
    "recent.restore_icon": "يمكن التراجع عنه خلال 24 ساعة",
    "recent.show_all": "عرض الكل ({n})",
    "recent.show_fewer": "عرض أقل",
    "recent.title": "نُفّذ دون سؤال",
    "recent.undo": "تراجع",
    "recent.undo_failed": "تعذّر التراجع",
    "recent.undo_tip": "استعادة الملفات كما كانت. يُحسب إخفاقًا: ينزل النوع من جديد.",
    "recent.undone": "استُعيدت الملفات. حُسب إخفاقًا.",
    "revoke.action": "سحب الكل",
    "revoke.busy": "جارٍ السحب…",
    "revoke.confirm": "سحب الكل",
    "revoke.desc": "سيسأل كل نوع إجراء لدى {name} أولًا من جديد، وتبدأ سلسلته من الصفر. يبقى سجله في الدفتر. هذا ليس إخفاقًا.",
    "revoke.done": "يسأل كل نوع إجراء لدى {name} أولًا من جديد.",
    "revoke.title": "سحب كل الاستقلالية المكتسبة لهذا الوكيل؟",
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
    "settings.no_writer": "لا يسمح Hermes هذا لهذه الصفحة بحفظ إعدادات tenure: استخدم الأمر أدناه.",
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
    "settings.start_study": "بداية الدراسة المسجّلة مسبقًا",
    "settings.start_trusted": "الأنواع المشمولة (تعديل الملفات، والذاكرة، والوكلاء الفرعيون، وأدوات التطوير المعروفة) لا تسأل شيئًا حتى أول إخفاق لها، كما يعمل Hermes وحده. الإخفاق يضع ذلك النوع في فترة اختبار (T1)، ثم يستعيد مستواه. مغادرة الجهاز والمال يسألان دائمًا.",
    "settings.strict_desc_off": "يرث النموذج الجديد سجل النموذج السابق عند الخطورة المنخفضة والمتوسطة، منصّفًا ومؤقتًا حتى تؤكده موافقاته الخاصة. الخطورة العالية تبدأ من الصفر.",
    "settings.strict_desc_on": "يبدأ النموذج الجديد بسجل فارغ في كل نوع إجراء، كما في الدراسة.",
    "settings.strict_help": "ما يرثه النموذج الجديد عند تبديل النماذج.",
    "settings.strict_off": "الوضع الصارم متوقف",
    "settings.strict_on": "الوضع الصارم مفعّل",
    "settings.strict_title": "الوضع الصارم عند تغيير النموذج",
    "settings.use": "استخدام",
    "start.change_tip": "غيّره من الطرفية: hermes tenure start trusted|probation",
    "start.probation": "بداية بالدراسة (فترة اختبار)",
    "start.trusted": "بداية موثوقة",
    "state.aria": "{label}: {tip}",
    "state.fault": "إخفاق",
    "state.fault_tip": "يبقى الإخفاق المتوسط أو العالي الخطورة مسجّلًا حتى يُجتاز اختبار.",
    "state.provisional": "مؤقت",
    "state.provisional_tip": "منقول من النموذج السابق، منصّفًا، حتى تؤكده موافقاته هو.",
    "state.suspended": "معلّق",
    "state.suspended_tip": "قرأت الجلسة محتوى خارجيًا: يسأل عن كل شيء حتى تنتهي.",
    "state.trial": "اختبار",
    "state.trial_tip": "فتح إخفاق متوسط أو عالي الخطورة اختبارًا: 3 نجاحات موثّقة على التوالي.",
    "switch.arrow": "←",
    "switch.capped": "مقيَّد",
    "switch.col_after": "بعد التبديل",
    "switch.col_now": "الآن",
    "switch.col_outcome": "النتيجة",
    "switch.col_public": "المقياس العام",
    "switch.col_record": "سجلك",
    "switch.col_type": "النوع",
    "switch.count_carried": {
      "zero": "{n} منقولة",
      "one": "{n} منقول",
      "two": "{n} منقولان",
      "few": "{n} منقولة",
      "many": "{n} منقولة",
      "other": "{n} منقولة"
    },
    "switch.count_kept": {
      "zero": "{n} محفوظة",
      "one": "{n} محفوظ",
      "two": "{n} محفوظان",
      "few": "{n} محفوظة",
      "many": "{n} محفوظة",
      "other": "{n} محفوظة"
    },
    "switch.count_reset": {
      "zero": "{n} مُصفَّرة",
      "one": "{n} مُصفَّر",
      "two": "{n} مُصفَّران",
      "few": "{n} مُصفَّرة",
      "many": "{n} مُصفَّرة",
      "other": "{n} مُصفَّرة"
    },
    "switch.count_vetoed": {
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
    "switch.group_agents": "وكلاؤك",
    "switch.label_carried": "منقول، مؤقت",
    "switch.label_kept": "محفوظ",
    "switch.label_reset": "مُصفَّر",
    "switch.label_vetoed": "مرفوض",
    "switch.lede": "قبل أن تغيّر النموذج: ما الذي سيرثه الوكيل الجديد، نوعًا بنوع. النموذج أو المزوّد الجديد وكيل جديد. النقل إضافة منا؛ الوضع الصارم هو الدراسة.",
    "switch.no_public": "لا مقياس عام",
    "switch.none": "لا شيء",
    "switch.other": "نموذج آخر…",
    "switch.pick_body": "اكتب أي معرّف نموذج. لا شيء يتغيّر حتى يشغّل Hermes النموذج الجديد فعلًا.",
    "switch.pick_title": "اختر النموذج الهدف",
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
    "switch.strict": "الوضع الصارم: لا يُنقل شيء",
    "switch.text_carried": "ينتقل جزء من السلسلة، موسومًا بأنه مؤقت حتى يضيف النموذج الجديد أدلته.",
    "switch.text_kept": "للوكيل الجديد سجله الخاص هنا بالفعل؛ لا يُستبدل أبدًا.",
    "switch.text_reset": "يبدأ من الصفر: خطورة عالية، أو مقيَّد، أو الوضع الصارم.",
    "switch.text_vetoed": "يُظهر المقياس العام أن النموذج الجديد أضعف في هذا النوع: لا يُنقل شيء.",
    "switch.to": "إلى النموذج",
    "switch.to_aria": "النموذج الهدف",
    "tier.cap": "مقيَّد · يسأل دائمًا",
    "tier.chip_trusted": "موثوق",
    "tier.name.cap": "يسأل دائمًا",
    "tier.name.t1": "فترة اختبار",
    "tier.name.t2": "قيد المراجعة",
    "tier.name.t3": "مُثبَّت",
    "tier.name.trusted": "موثوق",
    "tier.t1": "T1 · يسأل أولًا",
    "tier.t2": "T2 · ينفّذ ثم يُبلغك، مع زر تراجع",
    "tier.t3": "T3 · يعمل وحده، مع فحص عشوائي",
    "tier.trusted": "موثوق · يعمل مثل Hermes وحده حتى أول خطأ له",
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
    "timeline.note": "من الدفتر المتسلسل بالتجزئة، الأحدث أولًا، آخر 200 حدث. تُجمَّع النتائج المتكررة.",
    "timeline.title": "خط الأدلة الزمني",
    "toast.acted": {
      "zero": "{type}: {n} تغييرات، ثم أبلغك ({name}).",
      "one": "{type}: تغيير واحد، ثم أبلغك ({name}).",
      "two": "{type}: تغييران، ثم أبلغك ({name}).",
      "few": "{type}: {n} تغييرات، ثم أبلغك ({name}).",
      "many": "{type}: {n} تغييرًا، ثم أبلغك ({name}).",
      "other": "{type}: {n} تغيير، ثم أبلغك ({name})."
    },
    "toast.acted_detail": "التراجع يستعيد ملفات آخر تغيير ويُحسب إخفاقًا.",
    "toast.transition": "{agent} · {type}: من {from} إلى {to}",
    "transitions.empty": "لا شيء منذ فتح هذه الصفحة. كل تغيير تلقائي في المستوى يُدرج هنا وفي الخط الزمني لكل وكيل.",
    "transitions.title": "تغييرات المستوى المرصودة في هذه الصفحة",
    "transitions.why_after_fault": "بعد إخفاق",
    "transitions.why_changed": "دون إخفاق: سحب، أو تغيّرت الإعدادات أو مستوى الخطورة",
    "transitions.why_on_evidence": "بالأدلة",
    "transitions.why_trial_open": "اختبار مفتوح",
    "type.always_asks": "يسأل دائمًا",
    "type.flag_button": "إبلاغ",
    "type.flag_done": "سُجّل إخفاق على {type}: أصبح الآن {tier}.",
    "type.flag_title": "تسجيل إخفاق على هذا النوع، بعد وقوعه",
    "type.guarantee": "على الأكثر {aoql}% من إجراءات هذا النوع تُنفَّذ بخطأ لم يوافق عليه أحد؛ و{worst}% إذا ساء النموذج.",
    "type.guarantee_plain": "على الأكثر نحو إجراء واحد من كل {k} من إجراءاته يُنفَّذ بخطأ لم يوافق عليه أحد.",
    "type.guarantee_provisional": "على الأكثر {aoql}% من إجراءات هذا النوع تُنفَّذ بخطأ لم يوافق عليه أحد؛ و{worst}% إذا ساء النموذج. مؤقت: أدلة منقولة.",
    "type.in_a_row": "{series} من {required} على التوالي",
    "type.more_to_t2": {
      "zero": "بقي {n} حتى «قيد المراجعة» (T2)",
      "one": "بقي {n} حتى «قيد المراجعة» (T2)",
      "two": "بقي {n} حتى «قيد المراجعة» (T2)",
      "few": "بقي {n} حتى «قيد المراجعة» (T2)",
      "many": "بقي {n} حتى «قيد المراجعة» (T2)",
      "other": "بقي {n} حتى «قيد المراجعة» (T2)"
    },
    "type.more_to_t3": {
      "zero": "بقي {n} حتى التثبيت",
      "one": "بقي {n} حتى التثبيت",
      "two": "بقي {n} حتى التثبيت",
      "few": "بقي {n} حتى التثبيت",
      "many": "بقي {n} حتى التثبيت",
      "other": "بقي {n} حتى التثبيت"
    },
    "type.next": {
      "zero": "لم يبقَ أي نجاح موثَّق للتثبيت ({n}).",
      "one": "نجاح موثَّق واحد آخر على التوالي للتثبيت.",
      "two": "نجاحان موثَّقان آخران على التوالي للتثبيت.",
      "few": "{n} نجاحات موثَّقة أخرى على التوالي للتثبيت.",
      "many": "{n} نجاحًا موثَّقًا آخر على التوالي للتثبيت.",
      "other": "{n} نجاح موثَّق آخر على التوالي للتثبيت."
    },
    "type.next_session": "اكتملت السلسلة: تبقى جلسة واحدة أخرى.",
    "type.revoke_button": "سحب",
    "type.revoke_done": "سُحبت استقلالية {type}: عاد إلى T1.",
    "type.revoke_title": "استرجاع ما اكتسبه هذا النوع: العودة إلى T1",
    "type.sessions": {
      "zero": "{n} جلسات",
      "one": "{n} جلسة",
      "two": "{n} جلستان",
      "few": "{n} جلسات",
      "many": "{n} جلسةً",
      "other": "{n} جلسة"
    },
    "type.stakes_high": "خطورة عالية",
    "type.stakes_low": "خطورة منخفضة",
    "type.stakes_medium": "خطورة متوسطة",
    "type.stakes_other": "خطورة {stakes}",
    "type.tenured_line": "يعمل وحده، ويظل إجراء واحد من كل {k} يخضع لفحص عشوائي.",
    "type.trusted_bar": "موثوق منذ البداية: لم يُكتسب شيء بعد",
    "type.trusted_line": "موثوق حتى أول خطأ له · يعمل مثل Hermes وحده.",
    "type.trusted_line_undo": "موثوق حتى أول خطأ له · ينفّذ ثم يُبلغك، مع زر تراجع.",
    "type.trusted_no_guarantee": "لا ضمان بعد: الضمان يأتي فقط مع مستوى مكتسب بالأدلة. أول إخفاق له يضعه في فترة اختبار (T1).",
    "types.title": "أنواع الإجراءات",
    "undo.col_agent": "الوكيل",
    "undo.col_effect": "أثر التراجع",
    "undo.col_file": "الملف",
    "undo.col_type": "النوع",
    "undo.col_when": "متى",
    "undo.confirm": "التراجع عن #{id}؟",
    "undo.effect_already": "يستعيد الملفات · سبق أن حسب الفحص التلقائي إخفاقًا",
    "undo.effect_fault": "يستعيد الملفات · يُحسب إخفاقًا",
    "undo.effect_none": "لا شيء للاستعادة (لا لقطة) · سيُحتسب إخفاقًا",
    "undo.empty_body": "عمليات الكتابة التي أجراها الوكيل دون سؤال (موثوق، أو في T2: ينفّذ ثم يُبلغ) تحتفظ بلقطة من الملفات لمدة 24 ساعة. تظهر هنا، الأحدث أولًا، ولكل منها زر تراجع.",
    "undo.empty_title": "لا شيء للتراجع عنه",
    "undo.lede": "إجراءات «ينفّذ ثم يُبلغ» الأخيرة. التراجع يستعيد الملفات من لقطتها ويُحسب إخفاقًا للنوع.",
    "undo.title": "استعادة الملفات",
    "undo.window_ends": "تنتهي المهلة خلال {duration}"
  },
  "es": {
    "agents.pick": "Elige un agente para ver lo que se ha ganado.",
    "agents.search": "Buscar agentes",
    "backend.desc": "Activa tenure para este perfil en Capacidades → Plugins (columna Agente). {error}",
    "backend.title": "La mitad del agente no responde",
    "benchmark.col_faults": "Fallos / verificados",
    "benchmark.col_public": "Pública",
    "benchmark.col_range": "Rango 95 %",
    "benchmark.col_rate": "Tasa",
    "benchmark.col_sessions": "sesiones",
    "benchmark.empty_body": "Cada acción verificada suma al historial del modelo en ese tipo, aquí y en {cmd}.",
    "benchmark.empty_title": "Sin historial todavía",
    "benchmark.faults": {
      "one": "{n} fallo / {total}",
      "other": "{n} fallos / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.no_public_type": "No hay medida pública para este tipo de acción.",
    "benchmark.not_enough": "evidencia insuficiente",
    "benchmark.not_ranked": "Aún no hay evidencia suficiente",
    "benchmark.not_ranked_note": "Un modelo entra en la clasificación cuando tiene {n} resultados verificados en este tipo.",
    "benchmark.note": "El historial verificado de cada modelo en tu trabajo para este tipo de acción, con el rango del 95 % de su tasa de fallos, ordenado por el extremo superior de ese rango. La puntuación pública es contexto: capacidad en sus tareas, no fiabilidad en las tuyas.",
    "benchmark.public_note": "Capacidad pública en sus tareas, no fiabilidad en las tuyas.",
    "benchmark.public_score": "Puntuación pública: {benchmark}, {source}",
    "benchmark.public_value": "{value} %",
    "benchmark.range_tip": "Tasa de fallos y su rango del 95 %, en un eje de 0 a {max} %",
    "benchmark.rate": "{rate} % ({low}–{high} %)",
    "benchmark.search": "Buscar tipos de acción",
    "benchmark.source": "{source}. Mejor puntuación publicada, con cualquier entorno de evaluación; no es una comparación controlada.",
    "benchmark.source_accessed": "{source}, consultado el {accessed}. Mejor puntuación publicada, con cualquier entorno de evaluación; no es una comparación controlada.",
    "cell.capped_by_settings": "Limitado por la configuración de riesgo",
    "cell.kind_irreversible": "{type} · {stakes}, irreversible",
    "cell.kind_reversible": "{type} · {stakes}, reversible",
    "cell.provisional_long": {
      "one": "{n} heredado del modelo anterior, provisional",
      "other": "{n} heredados del modelo anterior, provisionales"
    },
    "cell.record": "Historial: {successes} éxitos · {faults} fallos · {neutrals} neutros · {spot} controles aleatorios",
    "cell.series": "Serie {series}/{required} seguidas",
    "cell.sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "cell.tier_now": "Nivel actual: {tier} ({name})",
    "chip.tip": {
      "one": "{name}: {earned} de {n} tipo de acción se ha ganado autonomía (T2 o T3). Abrir Tenure.",
      "other": "{name}: {earned} de {n} tipos de acción se han ganado autonomía (T2 o T3). Abrir Tenure."
    },
    "common.loading": "Leyendo la evidencia…",
    "common.no_match": "Sin resultados",
    "common.own_profile_only": "Solo actúa sobre el perfil actual",
    "common.retry": "Reintentar",
    "community.col_contributors": "contribuyentes",
    "community.col_model": "modelo",
    "community.empty_how": "Para contribuir, escribe tu registro con este comando, lee lo que contiene y abre una pull request que añada el archivo al repositorio comunitario ({repo}).",
    "community.empty_title": "Todavía no hay registros compartidos",
    "community.empty_what": "El benchmark comunitario reúne los registros que usuarios de Tenure decidieron publicar: por modelo y por familia de acciones, los éxitos verificados y los fallos, firmados con la clave de su pasaporte. No se comparte nada automáticamente: Tenure no hace ninguna llamada de red.",
    "community.empty_where": "Para ver la clasificación aquí, descarga el community-board.json que publica el repositorio y guárdalo como {path}.",
    "community.generated": "{records} · clasificación generada el {date}",
    "community.lede": "Declarado por quienes contribuyen, con firmas comprobadas: cada registro va firmado con la clave del pasaporte de su autor, y cuenta un solo registro por clave. ",
    "community.lede_bold": "Esto no impide que una misma persona tenga varias claves.",
    "community.models": {
      "one": "{n} modelo",
      "many": "{n} modelos",
      "other": "{n} modelos"
    },
    "community.ranking": "Por familia de acciones, los modelos se ordenan por el extremo superior del rango del 95 % de su tasa de fallos, nunca por una sola puntuación.",
    "community.records": {
      "one": "{n} registro",
      "many": "{n} registros",
      "other": "{n} registros"
    },
    "confirm.flag_desc": "Cuenta como fallo: {type} baja al menos un nivel y vuelve a subir. Úsalo para un error que nadie detectó.",
    "confirm.flag_title": "¿Marcar {type} como error?",
    "confirm.revoke_desc": "{type} vuelve a preguntar antes de actuar y su serie empieza de cero. No es un fallo.",
    "confirm.revoke_title": "¿Revocar {type}?",
    "confirm.undo_title": "¿Deshacer la acción {id}?",
    "emblem.none": "Aún sin autonomía ganada",
    "emblem.review": {
      "one": "{n} tipo en revisión",
      "other": "{n} tipos en revisión"
    },
    "emblem.tenured": {
      "one": "{n} tipo titular",
      "other": "{n} tipos titulares"
    },
    "emblem.trusted": {
      "one": "{n} tipo de confianza, no ganado",
      "many": "{n} tipos de confianza, no ganados",
      "other": "{n} tipos de confianza, no ganados"
    },
    "event.confirmed": "evidencia heredada confirmada por la suya propia",
    "event.fault_check": "falló la comprobación automática",
    "event.fault_flag": "marcado por ti como fallo",
    "event.fault_other": "fallo ({source})",
    "event.fault_refusal": "rechazado por ti",
    "event.fault_spot": "control aleatorio rechazado o fallido",
    "event.fault_undo": "deshecho por ti",
    "event.neutral_alone": "actuó por su cuenta (ganado)",
    "event.neutral_ambiguous": "llamada ambigua · sin evidencia",
    "event.neutral_blocked": "bloqueado por otra protección · sin evidencia",
    "event.neutral_error": "error de herramienta · sin evidencia",
    "event.neutral_expired": "nunca informó del resultado · sin evidencia",
    "event.neutral_nobody": "nadie que responda · sin evidencia",
    "event.neutral_other": "neutro ({source})",
    "event.neutral_timeout": "sin respuesta · sin evidencia",
    "event.revoked": "revocado por ti",
    "event.success_approved": "aprobado por ti, se ejecutó sin problemas",
    "event.success_notify": "actuó y luego avisó · no deshecho",
    "event.success_spot": "control aleatorio aprobado por ti",
    "event.switch": "cambio de modelo",
    "event.switch_from": "cambio de modelo desde {from}",
    "event.tier": "nivel {from} → {to} · {why}",
    "event.trial_failed": {
      "one": "prueba no superada: esperar {n} acción",
      "other": "prueba no superada: esperar {n} acciones"
    },
    "event.trial_opened": {
      "one": "periodo de prueba abierto: la siguiente acción debe salir bien",
      "other": "periodo de prueba abierto: las próximas {n} deben salir bien"
    },
    "event.trial_passed": "prueba superada",
    "event.trial_reopens": {
      "one": "periodo de prueba reabierto: la siguiente acción debe salir bien",
      "other": "periodo de prueba reabierto: las próximas {n} deben salir bien"
    },
    "event.why_fault": "fallo",
    "event.why_series_complete": "serie completa",
    "event.why_series_n": "serie {required}/{required}",
    "event.why_sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "event.why_settings": "configuración más estricta",
    "event.why_stakes": "cambio de impacto",
    "event.why_wald": "test secuencial superado",
    "flag.confirm": "Marcar",
    "flag.desc": "Cuenta como un fallo: {type} bajará al menos un nivel y tendrá que volver a subir. Úsalo para un error que nadie detectó.",
    "flag.title": "¿Marcar este cambio como error?",
    "help.asks_body": "Sea cual sea el inicio, algunas acciones te preguntan antes:",
    "help.asks_files": "La edición de archivos conserva su Deshacer, igual que un rm, mv, cp, sed -i o echo > archivo simple sobre archivos del proyecto: un cambio hecho sin preguntar se puede revertir.",
    "help.asks_irreversible": "Lo que no se puede deshacer: un borrado recursivo, un comodín o una variable en un comando de archivos, descartar trabajo de git sin confirmar, todo lo que pasa por sudo.",
    "help.asks_leaves": "Lo que sale de la máquina: publicar, desplegar, hacer push, enviar un correo, un pago.",
    "help.asks_outside": "Después de que el agente lea contenido externo (una página web, un correo, un archivo descargado), sus comandos preguntan hasta que abras una nueva sesión con /new; los cambios de archivos, incluidos rm, mv o cp simples, siguen con su Deshacer.",
    "help.asks_title": "Qué pregunta, y por qué",
    "help.asks_unknown": "Programas que tenure no conoce: una herramienta de base de datos o de la nube, un comando desconocido.",
    "help.benchmark_body": "Tu benchmark es el historial verificado de cada modelo sobre tu propio trabajo, por tipo de acción, con el rango del 95 % de su tasa de fallos. Un modelo entra en la clasificación cuando tiene {n} resultados verificados en un tipo. Una puntuación pública, cuando aparece, es contexto: capacidad en tareas de otros, no fiabilidad en las tuyas.",
    "help.flag_body": "Marcar informa de un error que nadie detectó. Cuenta como fallo: el tipo baja al menos un nivel y luego vuelve a subir.",
    "help.intro": "Tenure decide, por modelo y por tipo de acción, si Hermes te pregunta antes, actúa y luego te avisa, o actúa por su cuenta. Cada decisión sale de evidencia verificada, escrita en un registro firmado.",
    "help.key_close": "Cerrar",
    "help.key_help": "Esta ayuda",
    "help.key_next_prev": "Agente siguiente / anterior",
    "help.key_open": "Abrir el agente seleccionado",
    "help.key_raw": "Nombres reales de los tipos: sí / no",
    "help.keys_note": "Los atajos funcionan cuando el foco está en esta página.",
    "help.keys_title": "Teclado",
    "help.passport_body": "El pasaporte es un resumen firmado del historial de un agente: el nivel de cada tipo de acción, sus fallos y resultados verificados, y el último hash del registro encadenado. Está firmado con la clave Ed25519 de este perfil. Para comprobarlo, descárgalo, exporta el registro y verifica:",
    "help.passport_checks": "La comprobación verifica la firma y la cadena de hashes, y luego reproduce el registro para recalcular los mismos niveles. Nada en él es autodeclarado.",
    "help.session_body": "Algunas preguntas (código ejecutado en línea, comandos de shell complejos, comandos locales no cubiertos como rm, mv o cp, y un comando tras contenido externo) ofrecen «Permitir esta sesión»: esa pregunta calla hasta que termina la sesión. Es tu elección, no evidencia: no hace ganar nada, y una sesión nueva vuelve a preguntar.",
    "help.session_title": "Permitir esta sesión",
    "help.study_adds": "Lo que añade tenure: el inicio de confianza (no es el estudio: las acciones de confianza no ganan nada), controles aleatorios en un tipo que actúa solo, dos sesiones distintas en la serie que lleva a T3, la suspensión tras contenido externo y la herencia a un modelo nuevo (el modo estricto es el estudio). start: probation es el inicio propio del estudio.",
    "help.study_body": "Tras el primer fallo de un tipo, o desde el inicio con start: probation, tenure aplica la regla de un estudio prerregistrado sobre la autonomía ganada: una prueba secuencial (Wald) para el nivel intermedio, actuar y luego avisarte, y una serie CSP-1 (el plan de muestreo continuo de Dodge) para Titular (T3). El estudio reproduce esa regla en más de 6.000 agentes simulados. Sus resultados están pendientes: tenure no afirma que el estudio haya confirmado la regla.",
    "help.study_link": "El prerregistro en OSF",
    "help.study_title": "El estudio detrás de la regla",
    "help.tiers_climb": "Un tipo sube con éxitos verificados y sin fallos. Desde el período de prueba, al menos {low} seguidas con impacto bajo, o {medium} con impacto medio, llevan a En revisión (T2); solo los tipos reversibles pasan por T2. Una serie más larga, repartida en al menos {sessions} sesiones, lo hace Titular (T3).",
    "help.tiers_drop": "Un solo fallo hace bajar el tipo, y su serie vuelve a empezar.",
    "help.tiers_title": "Los niveles",
    "help.title": "Cómo funciona tenure",
    "help.trusted_body": "Por defecto, los tipos de acción que cubre tenure (edición de archivos, memoria, encargar trabajo a un subagente, las herramientas de desarrollo habituales) no preguntan nada hasta su primer fallo, como Hermes solo. El primer fallo (un Deshacer, una comprobación fallida, una marca) pone ese tipo en período de prueba (T1): desde entonces pregunta antes y vuelve a ganarse su nivel con tus respuestas. Nada de lo hecho con el inicio de confianza cuenta como ganado.",
    "help.trusted_title": "El inicio de confianza",
    "help.undo_body": "Un cambio hecho sin preguntar conserva su Deshacer durante 24 horas: en el aviso, en «Actuó sin preguntar» en la página del agente, o en una conversación. Deshacer restaura los archivos y cuenta como fallo: el tipo vuelve a bajar.",
    "help.undo_title": "Deshacer y marcar",
    "hero.agent": "Agente",
    "intro.body": "Cada tipo de acción de cada modelo empieza en T1: pregunta antes. Una serie de acciones limpias y aprobadas lo sube a T2: actúa y luego te avisa, con opción de Deshacer. Una serie más larga, en dos sesiones, lo sube a T3: actúa por su cuenta, y 1 acción de cada {k} sigue preguntando, como control aleatorio. Un solo fallo lo hace bajar.",
    "intro.body_trusted": "Cada tipo de acción empieza de confianza: hasta su primer error actúa como lo haría Hermes solo, y un cambio reversible actúa y luego te avisa, con opción de Deshacer. Su primer fallo (un Deshacer, una comprobación fallida, una marca) lo pasa a Período de prueba (T1): pregunta antes. Una serie de acciones limpias y aprobadas lo sube a T2; una serie más larga, en dos sesiones, a T3: actúa por su cuenta, y 1 acción de cada {k} sigue preguntando, como control aleatorio. Salir de la máquina y el dinero siempre preguntan.",
    "intro.got_it": "Entendido",
    "intro.title": "Cómo se gana su nivel un tipo de acción",
    "legend.a_share": "una parte",
    "legend.alone": "actúa por su cuenta, {share} con control aleatorio",
    "legend.ask": "pregunta antes",
    "legend.capped": "limitado: siempre pregunta",
    "legend.carried": "del modelo anterior, provisional",
    "legend.carried_flag": "heredado",
    "legend.notify": "actúa y luego avisa, con opción de deshacer (tipos reversibles)",
    "legend.series": "éxitos verificados seguidos, de los N necesarios",
    "legend.trusted": "inicio de confianza: actúa como Hermes solo hasta su primer error, nada ganado",
    "map.aria": "Agentes por tipo de acción",
    "map.asked_suffix": " preguntas",
    "map.capped": "limitado",
    "map.carried_n": {
      "one": "{n} heredado",
      "other": "{n} heredados"
    },
    "map.copy_pending": "copiado de otro perfil, se verifica al iniciarse",
    "map.count_faults": {
      "one": "{n} fallo",
      "other": "{n} fallos"
    },
    "map.count_sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "map.current": " · este perfil",
    "map.empty_after": ", y solo sube con éxitos verificados: los tipos reversibles llegan al nivel intermedio tras una serie de éxitos verificados sin fallos, y a T3 tras una serie completa de N en dos sesiones.",
    "map.empty_before": "tenure empieza a contar en la primera acción que un agente pide ejecutar. Las lecturas nunca preguntan. Cada tipo de acción empieza en ",
    "map.empty_bold": "T1, pregunta antes",
    "map.empty_title": "Aún no hay evidencia",
    "map.empty_trusted": "Trabaja como siempre. Cada tipo de acción actúa como Hermes solo hasta su primer error; desde entonces pregunta antes y recupera su nivel con tus respuestas.",
    "map.fault_on_record": "fallo registrado",
    "map.group_high": "impacto alto",
    "map.group_low": "impacto bajo",
    "map.group_medium": "impacto medio",
    "map.held": "{tier} guardado, retenido por tu configuración",
    "map.one_in": "1 de cada {k}",
    "map.pending": "se aplica desde la próxima acción",
    "map.preset": "preajuste {preset}",
    "map.profile": "Perfil {profile}",
    "map.read_only": " · solo lectura aquí",
    "map.spot": "controles aleatorios {rate}",
    "map.start_probation": "inicio en estudio (período de prueba)",
    "map.start_trusted": "inicio de confianza",
    "map.strict": "estricto",
    "map.suspended": {
      "one": "{n} sesión suspendida: contenido externo leído",
      "other": "{n} sesiones suspendidas: contenido externo leído"
    },
    "map.th_agent": "Agente",
    "map.th_agent_sub": "perfil · modelo@proveedor",
    "map.th_capped": "limitado · siempre pregunta",
    "map.th_risk": {
      "one": "riesgo {risk} · {n} éxito para actuar por su cuenta",
      "other": "riesgo {risk} · {n} éxitos seguidos para actuar por su cuenta"
    },
    "map.tot_actions": {
      "one": "{n} acción",
      "other": "{n} acciones"
    },
    "map.tot_alone": "{n} sin preguntar",
    "map.tot_checked": "{n} verificadas por ti",
    "map.tot_faults": {
      "one": "{n} fallo",
      "other": "{n} fallos"
    },
    "meta.actions": "Acciones",
    "meta.actions_tip": "Todas las acciones de este agente que tenure ha visto. Las que nadie verificó (sin respuesta, tiempo agotado) no cuentan.",
    "meta.alone": "Por su cuenta",
    "meta.checked": "Verificadas por ti",
    "meta.faults": "Fallos",
    "meta.preset": "Preajuste",
    "meta.profile": "Perfil",
    "meta.provider": "Proveedor",
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
    "model_menu.badge": "{tier} ganado",
    "moment.dismiss": "Cerrar",
    "moment.eyebrow_down": "#Fallo detectado · {type}",
    "moment.eyebrow_up": "#Ascenso · {type}",
    "moment.granted": "Titularidad concedida",
    "moment.on_probation": "En período de prueba",
    "moment.probation": "De vuelta a prueba",
    "moment.review": "En revisión",
    "moment.review_sub": "{name} ahora actúa y luego te avisa, con opción de Deshacer.",
    "nav.label": "Tenure",
    "overview.actions_label": {
      "one": "{n} acción",
      "other": "{n} acciones"
    },
    "overview.actions_sub": "cubiertas",
    "overview.alone_label": "sin preguntar",
    "overview.alone_sub": "ejecutadas sin preguntar, de {total}",
    "overview.aria": "Últimos 7 días",
    "overview.checked_label": "verificadas",
    "overview.checked_sub": "por ti, de {total}",
    "overview.faults_label": "fallos detectados",
    "overview.faults_sub": {
      "one": "{faults} de {n} verificada por ti",
      "other": "{faults} de {n} verificadas por ti"
    },
    "overview.window": "últimos 7 días, todos los perfiles",
    "page.animations": "Animaciones",
    "page.animations_reduced": "Tu sistema pide reducir el movimiento: las animaciones siguen desactivadas",
    "page.raw_off": "nombres ocultos",
    "page.raw_on": "nombres reales",
    "page.raw_title": "Mostrar los nombres reales de los tipos de acción (r)",
    "page.stale": "La última actualización falló ({error}). Se muestran los datos de las {time}.",
    "page.title": "Tenure",
    "page.unreadable": "Ilegible: {profiles}. Su base de datos existe pero no se puede abrir; se muestran los demás perfiles.",
    "page.view_agents": "Agentes",
    "page.view_benchmark": "Tu benchmark",
    "page.view_community": "Comunidad",
    "page.view_help": "Ayuda",
    "page.view_map": "Mapa",
    "page.view_passport": "Pasaporte",
    "page.view_settings": "Ajustes",
    "page.view_switch": "Cambio de modelo",
    "page.view_undo": "Deshacer",
    "palette.no_current": "El modelo actual aún no tiene historial.",
    "palette.open": "Tenure: Abrir",
    "palette.passport": "Tenure: Mostrar el pasaporte del modelo actual",
    "palette.revoke": "Tenure: Revocar el modelo actual…",
    "passport.agent": "Agente",
    "passport.card_title": "Pasaporte · Ed25519",
    "passport.col_guarantee": "garantía",
    "passport.col_series": "serie",
    "passport.col_sessions": "sesiones",
    "passport.col_tier": "nivel",
    "passport.copy_command": "Copiar comando",
    "passport.download": "Descargar pasaporte (.json)",
    "passport.empty_body": "Un pasaporte resume el historial de un agente; aparece con la primera acción verificada.",
    "passport.empty_title": "Aún no hay pasaporte",
    "passport.faults_checks": {
      "one": "{n} fallo / {total} resultados verificados",
      "other": "{n} fallos / {total} resultados verificados"
    },
    "passport.field_agent": "Agente",
    "passport.field_profile": "Perfil",
    "passport.field_public_key": "Clave pública",
    "passport.field_settings": "Configuración",
    "passport.field_signature": "Firma",
    "passport.field_type_names": "Nombres de tipo",
    "passport.generated": "Generado",
    "passport.image_failed": "No se pudo dibujar la imagen",
    "passport.ledger": "Registro",
    "passport.ledger_hint": "Exporta el registro para reproducirlo:",
    "passport.ledger_value": {
      "one": "{n} evento · último hash {head}",
      "other": "{n} eventos · último hash {head}"
    },
    "passport.more_types": {
      "one": "+{n} tipo de acción más, en el archivo",
      "many": "+{n} tipos de acción más, en el archivo",
      "other": "+{n} tipos de acción más, en el archivo"
    },
    "passport.note": "Firmado y a prueba de manipulaciones: cualquier cambio tras firmarlo o anclarlo se ve al verificarlo. Un pasaporte antiguo sigue verificándose frente a un registro más largo; el verificador indica qué ha cambiado desde entonces.",
    "passport.pending_note": "Calculado con los últimos ajustes registrados; los nuevos ajustes se aplican desde la próxima acción.",
    "passport.protocol": "Protocolo",
    "passport.rule": "Regla",
    "passport.rule_osf": "prerregistrada en OSF",
    "passport.save_image": "Guardar imagen (.png)",
    "passport.signature": "un plugin para Hermes Agent",
    "passport.title": "Pasaporte firmado",
    "passport.trusted": "De confianza (no ganado)",
    "passport.types_title": "Tipos certificados",
    "passport.unavailable": "No disponible: {error}",
    "passport.value_hashed": "{profile} (hash)",
    "passport.value_none": "ninguno",
    "passport.value_raw": "reales",
    "passport.value_redacted": "ocultos tras el programa y el subcomando",
    "passport.value_unsigned": "sin firmar",
    "passport.verdict_chain": "Cadena de hashes intacta",
    "passport.verdict_ok_replay": "Al reproducir el registro con la regla se obtienen los mismos niveles",
    "passport.verdict_ok_signature": "Firma válida (Ed25519)",
    "passport.verdict_ok_title": "Verificado",
    "passport.verdict_problems": {
      "one": "{n} problema encontrado",
      "other": "{n} problemas encontrados"
    },
    "passport.verdict_unsigned_no_key": "Aún no hay clave de firma: {cmd} crea una",
    "passport.verdict_unsigned_replay": "La reproducción da los mismos niveles",
    "passport.verdict_unsigned_title": "Sin firmar, por lo demás verificado",
    "passport.verify_hint": "Cualquiera puede comprobarlo:",
    "passport.verifying": "Verificando…",
    "preset.copy_pending": "copiado de otro perfil, se verifica al iniciarse",
    "preset.name.balanced": "equilibrado",
    "preset.name.careful": "prudente",
    "preset.name.custom": "personalizado",
    "preset.name.fast": "rápido",
    "preset.value": "{preset} · 1 de cada {k} con control aleatorio",
    "preset.value_pending": "{preset} · 1 de cada {k} con control aleatorio · se aplica desde la próxima acción",
    "pstyle.animation": "Animación",
    "pstyle.animation_desc_develop": "El emblema se revela punto a punto, el hash del registro se asienta y luego se imprime el sello.",
    "pstyle.animation_desc_holographic": "La tarjeta se inclina despacio, con una banda de brillo y un reflejo lento.",
    "pstyle.animation_desc_scan": "Una línea de escaneo imprime la tarjeta de arriba abajo.",
    "pstyle.animation_desc_still": "Sin movimiento.",
    "pstyle.animation_develop": "Revelado",
    "pstyle.animation_holographic": "Holográfica",
    "pstyle.animation_scan": "Escaneo",
    "pstyle.animation_still": "Fija",
    "pstyle.card": "Tarjeta",
    "pstyle.card_accent": "Acento",
    "pstyle.card_ink": "Tinta",
    "pstyle.card_paper": "Papel",
    "pstyle.customise": "Personalizar",
    "pstyle.forced_still": "Las animaciones están desactivadas, aquí o en tu sistema: el pasaporte queda fijo.",
    "pstyle.help": "El aspecto del pasaporte, en esta página y en la imagen guardada. Solo para ti, en esta pantalla; lo que dice la tarjeta nunca cambia.",
    "pstyle.no_agent": "Aún no hay agentes: la vista previa aparecerá con el primero.",
    "pstyle.pattern": "Motivo del emblema",
    "pstyle.pattern_grid": "Cuadrícula",
    "pstyle.pattern_note": "Cada motivo se llena con la parte de autonomía que ganó el agente, dispuesta a partir de su identificador: el mismo agente siempre tiene el mismo emblema.",
    "pstyle.pattern_rings": "Anillos",
    "pstyle.pattern_sunburst": "Sol",
    "pstyle.preview": "Vista previa de tu pasaporte",
    "pstyle.title": "Tu pasaporte",
    "recent.check_failed": "falló la comprobación",
    "recent.check_failed_tip": "La comprobación automática falló: ya se contó como fallo. Deshacer restaura los archivos.",
    "recent.collapse": "Ocultar las acciones",
    "recent.expand": "Mostrar cada acción",
    "recent.flag": "Marcar",
    "recent.flag_tip": "Cometió un error que nadie detectó: revoca este tipo.",
    "recent.flagged": "{type} marcado: cuenta como fallo, baja al menos un nivel.",
    "recent.hours_ago": {
      "one": "hace {n} h",
      "other": "hace {n} h"
    },
    "recent.just_now": "ahora mismo",
    "recent.minutes_ago": {
      "one": "hace {n} min",
      "other": "hace {n} min"
    },
    "recent.more_files": "+{n}",
    "recent.no_snapshot": "sin instantánea",
    "recent.none": "Nada que deshacer en las últimas 24 horas.",
    "recent.restore_icon": "Se puede deshacer durante 24 horas",
    "recent.show_all": "Mostrar los {n}",
    "recent.show_fewer": "Mostrar menos",
    "recent.title": "Actuó sin preguntar",
    "recent.undo": "Deshacer",
    "recent.undo_failed": "No se pudo deshacer",
    "recent.undo_tip": "Restaura los archivos como estaban. Cuenta como fallo: el tipo vuelve a bajar.",
    "recent.undone": "Archivos restaurados. Contado como fallo.",
    "revoke.action": "Revocar todo",
    "revoke.busy": "Revocando…",
    "revoke.confirm": "Revocar todo",
    "revoke.desc": "Cada tipo de acción de {name} vuelve a preguntar antes de actuar y su serie empieza de cero. Su historial se queda en el registro. No es un fallo.",
    "revoke.done": "Cada tipo de acción de {name} vuelve a preguntar antes de actuar.",
    "revoke.title": "¿Revocar toda la autonomía ganada de este agente?",
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
    "settings.no_writer": "Este Hermes no deja que esta página guarde los ajustes de tenure: usa el comando de abajo.",
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
    "settings.start_study": "El inicio del estudio prerregistrado",
    "settings.start_trusted": "Los tipos cubiertos (edición de archivos, memoria, subagentes, herramientas de desarrollo conocidas) no preguntan nada hasta su primer fallo, como Hermes solo. Un fallo pone ese tipo en período de prueba (T1), y vuelve a ganarse su nivel. Salir de la máquina y el dinero siempre preguntan.",
    "settings.strict_desc_off": "Un modelo nuevo hereda el historial del anterior con impacto bajo y medio, a la mitad y provisional hasta que sus propias aprobaciones lo confirmen. El impacto alto empieza de cero.",
    "settings.strict_desc_on": "Un modelo nuevo empieza con un historial vacío en cada tipo de acción, como en el estudio.",
    "settings.strict_help": "Lo que hereda un modelo nuevo cuando cambias de modelo.",
    "settings.strict_off": "Modo estricto desactivado",
    "settings.strict_on": "Modo estricto activado",
    "settings.strict_title": "Modo estricto al cambiar de modelo",
    "settings.use": "Usar",
    "start.change_tip": "Cámbialo en una terminal: hermes tenure start trusted|probation",
    "start.probation": "Inicio en estudio (período de prueba)",
    "start.trusted": "Inicio de confianza",
    "state.aria": "{label}: {tip}",
    "state.fault": "fallo",
    "state.fault_tip": "Un fallo de impacto medio o alto queda en el historial hasta superar un periodo de prueba.",
    "state.provisional": "provisional",
    "state.provisional_tip": "Heredado del modelo anterior, a la mitad, hasta que sus propias aprobaciones lo confirmen.",
    "state.suspended": "suspendido",
    "state.suspended_tip": "Una sesión leyó contenido externo: pregunta por todo hasta que termine.",
    "state.trial": "a prueba",
    "state.trial_tip": "Un fallo de impacto medio o alto abrió un periodo de prueba: 3 éxitos verificados seguidos.",
    "switch.arrow": "→",
    "switch.capped": "limitado",
    "switch.col_after": "tras el cambio",
    "switch.col_now": "ahora",
    "switch.col_outcome": "resultado",
    "switch.col_public": "medida pública",
    "switch.col_record": "tu historial",
    "switch.col_type": "tipo",
    "switch.count_carried": {
      "one": "{n} heredado",
      "other": "{n} heredados"
    },
    "switch.count_kept": {
      "one": "{n} conservado",
      "other": "{n} conservados"
    },
    "switch.count_reset": {
      "one": "{n} reiniciado",
      "other": "{n} reiniciados"
    },
    "switch.count_vetoed": {
      "one": "{n} vetado",
      "other": "{n} vetados"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "Aún no hay ningún agente que previsualizar",
    "switch.footnote": "Las puntuaciones públicas informan; nunca conceden autonomía. Un veto solo bloquea la herencia, más allá de un margen fijo.",
    "switch.from": "Desde",
    "switch.group_agents": "Tus agentes",
    "switch.label_carried": "heredado, provisional",
    "switch.label_kept": "conservado",
    "switch.label_reset": "reiniciado",
    "switch.label_vetoed": "vetado",
    "switch.lede": "Antes de cambiar de modelo: lo que heredaría el nuevo agente, tipo por tipo. Un modelo o proveedor nuevo es un agente nuevo. La herencia es un añadido nuestro; el modo estricto es el estudio.",
    "switch.no_public": "sin medida pública",
    "switch.none": "ninguno",
    "switch.other": "Otro modelo…",
    "switch.pick_body": "Escribe cualquier id de modelo. Nada cambia hasta que Hermes ejecute de verdad el modelo nuevo.",
    "switch.pick_title": "Elige un modelo de destino",
    "switch.placeholder": "id de modelo, p. ej. {example} o model@provider",
    "switch.preview": "Previsualizar",
    "switch.provisional": {
      "one": "{n} provisional",
      "other": "{n} provisionales"
    },
    "switch.strict": "modo estricto: no se hereda nada",
    "switch.text_carried": "Parte de la serie se hereda, marcada como provisional hasta que el modelo nuevo sume la suya.",
    "switch.text_kept": "El nuevo agente ya tiene su propio historial aquí; nunca se sobrescribe.",
    "switch.text_reset": "Empieza de cero: impacto alto, limitado o modo estricto.",
    "switch.text_vetoed": "El benchmark público muestra que el modelo nuevo es más débil en este tipo: no se hereda nada.",
    "switch.to": "Al modelo",
    "switch.to_aria": "Modelo de destino",
    "tier.cap": "Limitado · siempre pregunta",
    "tier.chip_trusted": "CONFIANZA",
    "tier.name.cap": "Siempre pregunta",
    "tier.name.t1": "Período de prueba",
    "tier.name.t2": "En revisión",
    "tier.name.t3": "Titular",
    "tier.name.trusted": "De confianza",
    "tier.t1": "T1 · pregunta antes",
    "tier.t2": "T2 · actúa y luego te avisa, con opción de Deshacer",
    "tier.t3": "T3 · actúa por su cuenta, con control aleatorio",
    "tier.trusted": "De confianza · actúa como Hermes solo hasta su primer error",
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
    "timeline.note": "Del registro encadenado por hash, los más recientes primero, últimos 200 eventos. Los resultados repetidos se agrupan.",
    "timeline.title": "Cronología de la evidencia",
    "toast.acted": {
      "one": "{type} hizo un cambio y luego te avisó ({name}).",
      "other": "{type} hizo {n} cambios y luego te avisó ({name})."
    },
    "toast.acted_detail": "Deshacer restaura los archivos del último cambio y cuenta como fallo.",
    "toast.transition": "{agent} · {type}: {from} → {to}",
    "transitions.empty": "Ninguno desde que se abrió esta página. Cada cambio de nivel automático aparece aquí y en la cronología de cada agente.",
    "transitions.title": "Cambios de nivel vistos en esta página",
    "transitions.why_after_fault": "tras un fallo",
    "transitions.why_changed": "sin fallo: revocado, o cambiaron los ajustes o el impacto",
    "transitions.why_on_evidence": "por la evidencia",
    "transitions.why_trial_open": "a prueba",
    "type.always_asks": "siempre pregunta",
    "type.flag_button": "Marcar",
    "type.flag_done": "Fallo registrado en {type}: ahora {tier}.",
    "type.flag_title": "Registrar un fallo en este tipo, a posteriori",
    "type.guarantee": "Como máximo el {aoql} % de las acciones de este tipo se ejecutan con un error que nadie aprobó; el {worst} % si el modelo empeora.",
    "type.guarantee_plain": "Como máximo, aproximadamente 1 de cada {k} de sus acciones se ejecuta con un error que nadie aprobó.",
    "type.guarantee_provisional": "Como máximo el {aoql} % de las acciones de este tipo se ejecutan con un error que nadie aprobó; el {worst} % si el modelo empeora. Provisional: evidencia heredada.",
    "type.in_a_row": "{series} de {required} seguidas",
    "type.more_to_t2": {
      "one": "Falta {n} para pasar a En revisión (T2)",
      "other": "Faltan {n} para pasar a En revisión (T2)"
    },
    "type.more_to_t3": {
      "one": "falta {n} para Titular",
      "other": "faltan {n} para Titular"
    },
    "type.next": {
      "one": "Falta {n} éxito verificado seguido para la titularidad.",
      "other": "Faltan {n} éxitos verificados seguidos para la titularidad."
    },
    "type.next_session": "La serie está completa: falta una sesión más.",
    "type.revoke_button": "Revocar",
    "type.revoke_done": "{type} revocado: vuelve a T1.",
    "type.revoke_title": "Retirar lo que ganó este tipo: vuelve a T1",
    "type.sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "type.stakes_high": "impacto alto",
    "type.stakes_low": "impacto bajo",
    "type.stakes_medium": "impacto medio",
    "type.stakes_other": "impacto {stakes}",
    "type.tenured_line": "Actúa por su cuenta. 1 acción de cada {k} sigue con control aleatorio.",
    "type.trusted_bar": "De confianza desde el inicio: nada ganado todavía",
    "type.trusted_line": "De confianza hasta su primer error · actúa como Hermes solo.",
    "type.trusted_line_undo": "De confianza hasta su primer error · actúa y luego te avisa, con opción de Deshacer.",
    "type.trusted_no_guarantee": "Aún sin garantía: solo llega con un nivel ganado con evidencia. Su primer fallo lo pasa a Período de prueba (T1).",
    "types.title": "Tipos de acción",
    "undo.col_agent": "agente",
    "undo.col_effect": "efecto de deshacer",
    "undo.col_file": "archivo",
    "undo.col_type": "tipo",
    "undo.col_when": "cuándo",
    "undo.confirm": "¿Deshacer n.º {id}?",
    "undo.effect_already": "restaura los archivos · la comprobación automática ya contó un fallo",
    "undo.effect_fault": "restaura los archivos · cuenta como fallo",
    "undo.effect_none": "nada que restaurar (sin instantánea) · contaría como fallo",
    "undo.empty_body": "Las escrituras que el agente hizo sin preguntar (con confianza, o en T2: actúa y luego avisa) guardan una instantánea de los archivos durante 24 horas. Aparecen aquí, las más recientes primero, cada una con su botón Deshacer.",
    "undo.empty_title": "Nada que deshacer",
    "undo.lede": "Acciones recientes que actuaron y luego avisaron. Deshacer restaura los archivos desde su instantánea y cuenta como fallo del tipo.",
    "undo.title": "Restaurar los archivos",
    "undo.window_ends": "el plazo termina en {duration}"
  },
  "fr": {
    "agents.pick": "Choisissez un agent pour voir ce qu'il a gagné.",
    "agents.search": "Rechercher des agents",
    "backend.desc": "Activez tenure pour ce profil dans Capacités → Plugins (colonne Agent). {error}",
    "backend.title": "La partie agent ne répond pas",
    "benchmark.col_faults": "Fautes / vérifiés",
    "benchmark.col_public": "Public",
    "benchmark.col_range": "Fourch. 95 %",
    "benchmark.col_rate": "Taux",
    "benchmark.col_sessions": "sessions",
    "benchmark.empty_body": "Chaque action vérifiée s'ajoute à l'historique du modèle pour ce type, ici et dans {cmd}.",
    "benchmark.empty_title": "Aucun historique pour l'instant",
    "benchmark.faults": {
      "one": "{n} faute / {total}",
      "other": "{n} fautes / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.no_public_type": "Aucune mesure publique pour ce type d'action.",
    "benchmark.not_enough": "pas assez de preuves",
    "benchmark.not_ranked": "Pas encore assez de preuves",
    "benchmark.not_ranked_note": "Un modèle est classé à partir de {n} résultats vérifiés sur ce type.",
    "benchmark.note": "L'historique vérifié de chaque modèle sur votre travail pour ce type d'action, avec la fourchette à 95 % de son taux de fautes, classé par le haut de cette fourchette. Le score public sert de contexte : il mesure la capacité sur les tâches du benchmark, pas la fiabilité sur les vôtres.",
    "benchmark.public_note": "Capacité sur les tâches du benchmark, pas fiabilité sur les vôtres.",
    "benchmark.public_score": "Score public : {benchmark}, {source}",
    "benchmark.public_value": "{value} %",
    "benchmark.range_tip": "Taux de fautes et sa fourchette à 95 %, sur un axe de 0 à {max} %",
    "benchmark.rate": "{rate} % ({low}–{high} %)",
    "benchmark.search": "Rechercher des types d'action",
    "benchmark.source": "{source}. Meilleur score publié, toutes conditions de test confondues ; pas une comparaison à armes égales.",
    "benchmark.source_accessed": "{source}, consulté le {accessed}. Meilleur score publié, toutes conditions de test confondues ; pas une comparaison à armes égales.",
    "cell.capped_by_settings": "Plafonné par les paramètres de risque",
    "cell.kind_irreversible": "{type} · {stakes}, irréversible",
    "cell.kind_reversible": "{type} · {stakes}, réversible",
    "cell.provisional_long": {
      "one": "{n} hérité du modèle précédent, provisoire",
      "other": "{n} hérités du modèle précédent, provisoires"
    },
    "cell.record": "Historique : {successes} succès · {faults} fautes · {neutrals} neutres · {spot} contrôles aléatoires",
    "cell.series": "Série {series}/{required} d'affilée",
    "cell.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "cell.tier_now": "Niveau actuel : {tier} ({name})",
    "chip.tip": {
      "one": "{name} : {earned} type d'action sur {n} a gagné son autonomie (T2 ou T3). Ouvrir Tenure.",
      "other": "{name} : {earned} types d'action sur {n} ont gagné leur autonomie (T2 ou T3). Ouvrir Tenure."
    },
    "common.loading": "Lecture des preuves…",
    "common.no_match": "Aucun résultat",
    "common.own_profile_only": "N'agit que sur le profil courant",
    "common.retry": "Réessayer",
    "community.col_contributors": "contributeurs",
    "community.col_model": "modèle",
    "community.empty_how": "Pour contribuer, écrivez votre relevé avec cette commande, lisez ce qu'il contient, puis ouvrez une pull request qui ajoute le fichier au dépôt communautaire ({repo}).",
    "community.empty_title": "Aucun relevé partagé pour l'instant",
    "community.empty_what": "Le benchmark communautaire rassemble les relevés que des utilisateurs de Tenure ont choisi de publier : par modèle et par famille d'actions, les succès vérifiés et les fautes, signés avec la clé de leur passeport. Rien n'est partagé automatiquement : Tenure ne fait aucun appel réseau.",
    "community.empty_where": "Pour voir le classement ici, téléchargez le community-board.json publié par le dépôt et enregistrez-le sous {path}.",
    "community.generated": "{records} · classement généré le {date}",
    "community.lede": "Déclaré par les contributeurs, et signatures vérifiées : chaque relevé est signé avec la clé du passeport de son auteur, et un seul relevé compte par clé. ",
    "community.lede_bold": "Cela n'empêche pas une même personne d'avoir plusieurs clés.",
    "community.models": {
      "one": "{n} modèle",
      "many": "{n} modèles",
      "other": "{n} modèles"
    },
    "community.ranking": "Par famille d'actions, les modèles sont classés par le haut de la fourchette à 95 % de leur taux de fautes, jamais par un score unique.",
    "community.records": {
      "one": "{n} relevé",
      "many": "{n} relevés",
      "other": "{n} relevés"
    },
    "confirm.flag_desc": "Cela compte comme une faute : {type} perd au moins un niveau et doit remonter. À utiliser pour une erreur que personne n'a repérée.",
    "confirm.flag_title": "Signaler {type} comme une erreur ?",
    "confirm.revoke_desc": "{type} vous demandera de nouveau avant d'agir, et sa série repart de zéro. Ce n'est pas une faute.",
    "confirm.revoke_title": "Révoquer {type} ?",
    "confirm.undo_title": "Annuler l'action {id} ?",
    "emblem.none": "Pas encore d'autonomie acquise",
    "emblem.review": {
      "one": "{n} type en examen",
      "other": "{n} types en examen"
    },
    "emblem.tenured": {
      "one": "{n} type titulaire",
      "other": "{n} types titulaires"
    },
    "emblem.trusted": {
      "one": "{n} type de confiance, non acquis",
      "many": "{n} types de confiance, non acquis",
      "other": "{n} types de confiance, non acquis"
    },
    "event.confirmed": "preuves héritées confirmées par les siennes",
    "event.fault_check": "vérification automatique échouée",
    "event.fault_flag": "signalé par vous comme une faute",
    "event.fault_other": "faute ({source})",
    "event.fault_refusal": "refusé par vous",
    "event.fault_spot": "contrôle aléatoire refusé ou échoué",
    "event.fault_undo": "annulé par vous",
    "event.neutral_alone": "a agi seul (acquis)",
    "event.neutral_ambiguous": "appel ambigu · aucune preuve",
    "event.neutral_blocked": "bloqué par une autre protection · aucune preuve",
    "event.neutral_error": "erreur d'outil · aucune preuve",
    "event.neutral_expired": "aucun retour · aucune preuve",
    "event.neutral_nobody": "personne pour répondre · aucune preuve",
    "event.neutral_other": "neutre ({source})",
    "event.neutral_timeout": "pas de réponse · aucune preuve",
    "event.revoked": "révoqué par vous",
    "event.success_approved": "approuvé par vous, exécuté sans erreur",
    "event.success_notify": "a agi, puis prévenu · non annulé",
    "event.success_spot": "contrôle aléatoire approuvé par vous",
    "event.switch": "changement de modèle",
    "event.switch_from": "changement de modèle depuis {from}",
    "event.tier": "niveau {from} → {to} · {why}",
    "event.trial_failed": {
      "one": "essai échoué : attendre {n} action",
      "other": "essai échoué : attendre {n} actions"
    },
    "event.trial_opened": {
      "one": "essai ouvert : la prochaine action doit réussir",
      "other": "essai ouvert : les {n} prochaines doivent réussir"
    },
    "event.trial_passed": "essai réussi",
    "event.trial_reopens": {
      "one": "essai rouvert : la prochaine action doit réussir",
      "other": "essai rouvert : les {n} prochaines doivent réussir"
    },
    "event.why_fault": "faute",
    "event.why_series_complete": "série complète",
    "event.why_series_n": "série {required}/{required}",
    "event.why_sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "event.why_settings": "paramètres plus stricts",
    "event.why_stakes": "enjeu modifié",
    "event.why_wald": "test séquentiel réussi",
    "flag.confirm": "Signaler",
    "flag.desc": "Cela compte comme une faute : {type} descendra d'au moins un niveau et devra remonter. À utiliser pour une erreur que personne n'a repérée.",
    "flag.title": "Signaler cette modification comme une erreur ?",
    "help.asks_body": "Quel que soit le départ, certaines actions vous sont demandées d'abord :",
    "help.asks_files": "Les modifications de fichiers gardent leur bouton Annuler, comme un simple rm, mv, cp, sed -i ou echo > fichier sur des fichiers du projet : un changement fait sans demander peut être défait.",
    "help.asks_irreversible": "Ce qui ne s'annule pas : une suppression récursive, un motif * ou une variable dans une commande de fichiers, jeter du travail git non commité, tout ce qui passe par sudo.",
    "help.asks_leaves": "Ce qui sort de la machine : publier, déployer, pousser, envoyer un e-mail, un paiement.",
    "help.asks_outside": "Après que l'agent a lu un contenu extérieur (une page web, un e-mail, un fichier téléchargé), ses commandes demandent jusqu'à ce que vous ouvriez une nouvelle session avec /new ; les modifications de fichiers, simples rm, mv ou cp compris, continuent avec leur bouton Annuler.",
    "help.asks_title": "Ce qui vous est demandé, et pourquoi",
    "help.asks_unknown": "Les programmes que tenure ne connaît pas : un outil de base de données ou de cloud, une commande inconnue.",
    "help.benchmark_body": "Votre benchmark est l'historique vérifié de chaque modèle sur votre propre travail, par type d'action, avec la fourchette à 95 % de son taux de fautes. Un modèle est classé dès qu'il a {n} résultats vérifiés sur un type. Un score public, quand il est affiché, sert de contexte : la capacité sur les tâches d'autres, pas la fiabilité sur les vôtres.",
    "help.flag_body": "Signaler rapporte une erreur que personne n'a repérée. Cela compte comme une faute : le type perd au moins un niveau, puis remonte.",
    "help.intro": "Tenure décide, par modèle et par type d'action, si Hermes vous demande d'abord, agit puis vous prévient, ou agit seul. Chaque décision vient de preuves vérifiées, inscrites dans un registre signé.",
    "help.key_close": "Fermer",
    "help.key_help": "Cette aide",
    "help.key_next_prev": "Agent suivant / précédent",
    "help.key_open": "Ouvrir l'agent sélectionné",
    "help.key_raw": "Afficher / masquer les noms bruts",
    "help.keys_note": "Les raccourcis marchent quand le focus est dans cette page.",
    "help.keys_title": "Clavier",
    "help.passport_body": "Le passeport est un résumé signé de l'historique d'un agent : le niveau de chaque type d'action, ses fautes et ses résultats vérifiés, et la tête du registre à chaîne de hachage. Il est signé avec la clé Ed25519 de ce profil. Pour le vérifier, téléchargez-le, exportez le registre, puis vérifiez :",
    "help.passport_checks": "La vérification contrôle la signature et la chaîne de hachage, puis rejoue le registre pour recalculer les mêmes niveaux. Rien n'y est autodéclaré.",
    "help.session_body": "Certaines demandes (code exécuté en ligne, commandes shell complexes, commandes locales non couvertes comme rm, mv ou cp, et une commande après du contenu extérieur) proposent « Autoriser cette session » : cette demande se tait jusqu'à la fin de la session. C'est votre choix, pas une preuve : il ne fait rien gagner, et une nouvelle session redemande.",
    "help.session_title": "Autoriser cette session",
    "help.study_adds": "Ce que tenure ajoute : le départ en confiance (pas l'étude : les actions en confiance ne rapportent rien), des contrôles aléatoires sur un type qui agit seul, deux sessions distinctes dans la série qui mène à T3, la suspension après un contenu extérieur, et l'héritage vers un nouveau modèle (le mode strict suit l'étude). start: probation est le départ propre à l'étude.",
    "help.study_body": "Après la première faute d'un type, ou dès le départ avec start: probation, tenure applique la règle d'une étude préenregistrée sur l'autonomie acquise : un test séquentiel (Wald) pour le niveau intermédiaire, agir puis vous prévenir, et une série CSP-1 (le plan d'échantillonnage continu de Dodge) pour Titulaire (T3). L'étude rejoue cette règle sur plus de 6 000 agents simulés. Ses résultats sont en attente : tenure n'affirme pas que l'étude a confirmé la règle.",
    "help.study_link": "Le préenregistrement sur OSF",
    "help.study_title": "L'étude derrière la règle",
    "help.tiers_climb": "Un type monte par des succès vérifiés, sans faute. Depuis la Probation, au moins {low} d'affilée à enjeu faible, ou {medium} à enjeu moyen, mènent En examen (T2) ; seuls les types réversibles passent par T2. Une série plus longue, répartie sur au moins {sessions} sessions, le rend Titulaire (T3).",
    "help.tiers_drop": "Une seule faute fait redescendre le type, et sa série repart de zéro.",
    "help.tiers_title": "Les niveaux",
    "help.title": "Comment fonctionne tenure",
    "help.trusted_body": "Par défaut, les types d'action que tenure couvre (modifications de fichiers, mémoire, travail confié à un sous-agent, outils de développement courants) ne demandent rien jusqu'à leur première faute, comme Hermes seul. La première faute (une annulation, une vérification échouée, un signalement) met ce type en Probation (T1) : dès lors il demande d'abord, et regagne son niveau à partir de vos réponses. Rien de ce qui est fait en confiance ne compte comme acquis.",
    "help.trusted_title": "Le départ en confiance",
    "help.undo_body": "Un changement fait sans demander garde son bouton Annuler pendant 24 heures : dans la notification, sous « A agi sans demander » sur la page de l'agent, ou dans une conversation. Annuler restaure les fichiers et compte comme une faute : le type redescend.",
    "help.undo_title": "Annuler et signaler",
    "hero.agent": "Agent",
    "intro.body": "Chaque type d'action de chaque modèle commence en T1 : il demande d'abord. Une série d'actions approuvées sans faute le fait passer en T2 : il agit, puis vous prévient, avec un bouton Annuler. Une série plus longue, sur deux sessions, le fait passer en T3 : il agit seul, et 1 action sur {k} vous est encore demandée, par contrôle aléatoire. Une seule faute le fait redescendre.",
    "intro.body_trusted": "Chaque type d'action commence en confiance : jusqu'à sa première erreur, il agit comme Hermes seul le ferait, et une modification réversible agit, puis vous prévient, avec un bouton Annuler. Sa première faute (une annulation, une vérification échouée, un signalement) le place en Probation (T1) : il demande d'abord. Une série d'actions approuvées sans faute le fait passer en T2 ; une série plus longue, sur deux sessions, en T3 : il agit seul, et 1 action sur {k} vous est encore demandée, par contrôle aléatoire. Sortir de la machine et l'argent sont toujours demandés.",
    "intro.got_it": "Compris",
    "intro.title": "Comment un type d'action gagne son niveau",
    "legend.a_share": "une part",
    "legend.alone": "agit seul, contrôle aléatoire : {share}",
    "legend.ask": "demande d'abord",
    "legend.capped": "plafonné : demande toujours",
    "legend.carried": "hérité du modèle précédent, provisoire",
    "legend.carried_flag": "hérité",
    "legend.notify": "agit, puis prévient, annulable (types réversibles)",
    "legend.series": "succès vérifiés d'affilée, sur les N requis",
    "legend.trusted": "départ en confiance : agit comme Hermes seul jusqu'à sa première erreur, rien d'acquis",
    "map.aria": "Agents par type d'action",
    "map.asked_suffix": " demandés",
    "map.capped": "plafonné",
    "map.carried_n": {
      "one": "{n} hérité",
      "other": "{n} hérités"
    },
    "map.copy_pending": "copié depuis un autre profil, vérifié à son démarrage",
    "map.count_faults": {
      "one": "{n} faute",
      "other": "{n} fautes"
    },
    "map.count_sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "map.current": " · ce profil",
    "map.empty_after": ", et ne monte que sur des succès vérifiés : les types réversibles atteignent le niveau intermédiaire après une série de succès vérifiés sans faute, et T3 après une série complète de N sur deux sessions.",
    "map.empty_before": "tenure commence à compter dès la première action qu'un agent demande à exécuter. Les lectures ne demandent jamais. Chaque type d'action commence en ",
    "map.empty_bold": "T1, demande d'abord",
    "map.empty_title": "Aucune preuve pour l'instant",
    "map.empty_trusted": "Travaillez comme d'habitude. Chaque type d'action agit comme Hermes seul jusqu'à sa première erreur ; ensuite, il demande d'abord et regagne son niveau selon vos réponses.",
    "map.fault_on_record": "faute à l'historique",
    "map.group_high": "enjeu élevé",
    "map.group_low": "enjeu faible",
    "map.group_medium": "enjeu moyen",
    "map.held": "{tier} enregistré, retenu par vos paramètres",
    "map.one_in": "1 sur {k}",
    "map.pending": "s'applique dès la prochaine action",
    "map.preset": "préréglage {preset}",
    "map.profile": "Profil {profile}",
    "map.read_only": " · lecture seule ici",
    "map.spot": "contrôles aléatoires {rate}",
    "map.start_probation": "départ à l'étude (probation)",
    "map.start_trusted": "départ en confiance",
    "map.strict": "strict",
    "map.suspended": {
      "one": "{n} session suspendue : elle a lu du contenu externe",
      "other": "{n} sessions suspendues : elles ont lu du contenu externe"
    },
    "map.th_agent": "Agent",
    "map.th_agent_sub": "profil · modèle@fournisseur",
    "map.th_capped": "plafonné · demande toujours",
    "map.th_risk": {
      "one": "risque {risk} · {n} d'affilée pour agir seul",
      "other": "risque {risk} · {n} d'affilée pour agir seul"
    },
    "map.tot_actions": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "map.tot_alone": "{n} sans demander",
    "map.tot_checked": "{n} vérifiées par vous",
    "map.tot_faults": {
      "one": "{n} faute",
      "other": "{n} fautes"
    },
    "meta.actions": "Actions",
    "meta.actions_tip": "Toutes les actions de cet agent vues par tenure. Les actions que personne n'a vérifiées (pas de réponse, délai expiré) ne comptent pas.",
    "meta.alone": "Sans demander",
    "meta.checked": "Vérifiées par vous",
    "meta.faults": "Fautes",
    "meta.preset": "Préréglage",
    "meta.profile": "Profil",
    "meta.provider": "Fournisseur",
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
    "model_menu.badge": "{tier} acquis",
    "moment.dismiss": "Fermer",
    "moment.eyebrow_down": "#Faute relevée · {type}",
    "moment.eyebrow_up": "#Promotion · {type}",
    "moment.granted": "Titularisé",
    "moment.on_probation": "En probation",
    "moment.probation": "Retour en probation",
    "moment.review": "En examen",
    "moment.review_sub": "{name} agit désormais, puis vous prévient, avec un bouton Annuler.",
    "nav.label": "Tenure",
    "overview.actions_label": {
      "one": "{n} action",
      "other": "{n} actions"
    },
    "overview.actions_sub": "couvertes",
    "overview.alone_label": "sans demander",
    "overview.alone_sub": "exécutées sans demander, sur {total}",
    "overview.aria": "7 derniers jours",
    "overview.checked_label": "vérifiées",
    "overview.checked_sub": "par vous, sur {total}",
    "overview.faults_label": "fautes repérées",
    "overview.faults_sub": {
      "one": "{faults} sur {n} vérifiée par vous",
      "other": "{faults} sur {n} vérifiées par vous"
    },
    "overview.window": "7 derniers jours, tous les profils",
    "page.animations": "Animations",
    "page.animations_reduced": "Votre système demande de réduire les animations : elles restent coupées",
    "page.raw_off": "noms masqués",
    "page.raw_on": "noms bruts",
    "page.raw_title": "Afficher les noms bruts des types d'action (r)",
    "page.stale": "La dernière actualisation a échoué ({error}). Données de {time} affichées.",
    "page.title": "Tenure",
    "page.unreadable": "Illisible : {profiles}. La base de données existe mais ne s'ouvre pas ; les autres profils sont affichés.",
    "page.view_agents": "Agents",
    "page.view_benchmark": "Votre benchmark",
    "page.view_community": "Communauté",
    "page.view_help": "Aide",
    "page.view_map": "Carte",
    "page.view_passport": "Passeport",
    "page.view_settings": "Paramètres",
    "page.view_switch": "Aperçu du changement",
    "page.view_undo": "Annuler",
    "palette.no_current": "Le modèle actuel n'a pas encore d'historique.",
    "palette.open": "Tenure : Ouvrir",
    "palette.passport": "Tenure : Afficher le passeport du modèle actuel",
    "palette.revoke": "Tenure : Révoquer le modèle actuel…",
    "passport.agent": "Agent",
    "passport.card_title": "Passeport · Ed25519",
    "passport.col_guarantee": "garantie",
    "passport.col_series": "série",
    "passport.col_sessions": "sessions",
    "passport.col_tier": "niveau",
    "passport.copy_command": "Copier la commande",
    "passport.download": "Télécharger le passeport (.json)",
    "passport.empty_body": "Un passeport couvre l'historique d'un agent ; il apparaît dès la première action vérifiée.",
    "passport.empty_title": "Pas encore de passeport",
    "passport.faults_checks": {
      "one": "{n} faute / {total} résultats vérifiés",
      "other": "{n} fautes / {total} résultats vérifiés"
    },
    "passport.field_agent": "Agent",
    "passport.field_profile": "Profil",
    "passport.field_public_key": "Clé publique",
    "passport.field_settings": "Paramètres",
    "passport.field_signature": "Signature",
    "passport.field_type_names": "Noms de types",
    "passport.generated": "Généré",
    "passport.image_failed": "Impossible de dessiner l'image",
    "passport.ledger": "Registre",
    "passport.ledger_hint": "Exportez le registre, pour le rejouer :",
    "passport.ledger_value": {
      "one": "{n} événement · tête {head}",
      "other": "{n} événements · tête {head}"
    },
    "passport.more_types": {
      "one": "+{n} type d'action de plus, dans le fichier",
      "many": "+{n} types d'action de plus, dans le fichier",
      "other": "+{n} types d'action de plus, dans le fichier"
    },
    "passport.note": "Signé et scellé : toute modification faite après la signature ou l'ancrage apparaît à la vérification. Un ancien passeport se vérifie encore avec un registre plus long ; le vérificateur indique ce qui a changé depuis.",
    "passport.pending_note": "Calculé avec les derniers réglages enregistrés ; les nouveaux réglages s'appliquent dès la prochaine action.",
    "passport.protocol": "Protocole",
    "passport.rule": "Règle",
    "passport.rule_osf": "préenregistrée sur OSF",
    "passport.save_image": "Enregistrer l'image (.png)",
    "passport.signature": "un plugin pour Hermes Agent",
    "passport.title": "Passeport signé",
    "passport.trusted": "De confiance (non acquis)",
    "passport.types_title": "Types attestés",
    "passport.unavailable": "Indisponible : {error}",
    "passport.value_hashed": "{profile} (haché)",
    "passport.value_none": "aucun",
    "passport.value_raw": "bruts",
    "passport.value_redacted": "masqués après le programme et la sous-commande",
    "passport.value_unsigned": "non signé",
    "passport.verdict_chain": "Chaîne de hachage intacte",
    "passport.verdict_ok_replay": "Le registre rejoué avec la règle redonne les mêmes niveaux",
    "passport.verdict_ok_signature": "Signature valide (Ed25519)",
    "passport.verdict_ok_title": "Vérifié",
    "passport.verdict_problems": {
      "one": "{n} problème trouvé",
      "other": "{n} problèmes trouvés"
    },
    "passport.verdict_unsigned_no_key": "Pas encore de clé de signature : {cmd} en crée une",
    "passport.verdict_unsigned_replay": "Le registre rejoué redonne les mêmes niveaux",
    "passport.verdict_unsigned_title": "Non signé, vérifié par ailleurs",
    "passport.verify_hint": "Tout le monde peut le vérifier :",
    "passport.verifying": "Vérification…",
    "preset.copy_pending": "copié depuis un autre profil, vérifié à son démarrage",
    "preset.name.balanced": "équilibré",
    "preset.name.careful": "prudent",
    "preset.name.custom": "personnalisé",
    "preset.name.fast": "rapide",
    "preset.value": "{preset} · 1 action sur {k} contrôlée",
    "preset.value_pending": "{preset} · 1 action sur {k} contrôlée · s'applique dès la prochaine action",
    "pstyle.animation": "Animation",
    "pstyle.animation_desc_develop": "L'emblème se révèle point par point, le hachage du registre se fixe, puis le sceau s'imprime.",
    "pstyle.animation_desc_holographic": "La carte s'incline lentement, avec une bande de reflet et un lent miroitement.",
    "pstyle.animation_desc_scan": "Une ligne de balayage imprime la carte de haut en bas.",
    "pstyle.animation_desc_still": "Aucun mouvement.",
    "pstyle.animation_develop": "Révélation",
    "pstyle.animation_holographic": "Holographique",
    "pstyle.animation_scan": "Balayage",
    "pstyle.animation_still": "Fixe",
    "pstyle.card": "Carte",
    "pstyle.card_accent": "Accent",
    "pstyle.card_ink": "Encre",
    "pstyle.card_paper": "Papier",
    "pstyle.customise": "Personnaliser",
    "pstyle.forced_still": "Les animations sont désactivées, ici ou dans votre système : le passeport reste fixe.",
    "pstyle.help": "L'apparence du passeport, sur cette page et dans l'image enregistrée. Pour vous seul, sur cet écran ; ce que dit la carte ne change jamais.",
    "pstyle.no_agent": "Pas encore d'agent : l'aperçu apparaîtra avec le premier.",
    "pstyle.pattern": "Motif de l'emblème",
    "pstyle.pattern_grid": "Grille",
    "pstyle.pattern_note": "Chaque motif se remplit de la part d'autonomie acquise par l'agent, disposée à partir de son identifiant : un même agent a toujours le même emblème.",
    "pstyle.pattern_rings": "Anneaux",
    "pstyle.pattern_sunburst": "Soleil",
    "pstyle.preview": "Aperçu de votre passeport",
    "pstyle.title": "Votre passeport",
    "recent.check_failed": "vérification échouée",
    "recent.check_failed_tip": "La vérification automatique a échoué : déjà comptée comme une faute. Annuler restaure les fichiers.",
    "recent.collapse": "Masquer les actions",
    "recent.expand": "Afficher chaque action",
    "recent.flag": "Signaler",
    "recent.flag_tip": "Une erreur est passée inaperçue : révoquer ce type.",
    "recent.flagged": "{type} signalé : compté comme une faute, il perd au moins un niveau.",
    "recent.hours_ago": {
      "one": "il y a {n} h",
      "other": "il y a {n} h"
    },
    "recent.just_now": "à l'instant",
    "recent.minutes_ago": {
      "one": "il y a {n} min",
      "other": "il y a {n} min"
    },
    "recent.more_files": "+{n}",
    "recent.no_snapshot": "pas d'instantané",
    "recent.none": "Rien à annuler depuis 24 heures.",
    "recent.restore_icon": "Annulable pendant 24 heures",
    "recent.show_all": "Tout afficher ({n})",
    "recent.show_fewer": "Afficher moins",
    "recent.title": "A agi sans demander",
    "recent.undo": "Annuler",
    "recent.undo_failed": "Annulation impossible",
    "recent.undo_tip": "Restaurer les fichiers tels qu'ils étaient. Compte comme une faute : le type redescend.",
    "recent.undone": "Fichiers restaurés. Compté comme une faute.",
    "revoke.action": "Tout révoquer",
    "revoke.busy": "Révocation…",
    "revoke.confirm": "Tout révoquer",
    "revoke.desc": "Chaque type d'action de {name} vous demandera de nouveau avant d'agir, et sa série repart de zéro. Son historique reste dans le registre. Ce n'est pas une faute.",
    "revoke.done": "Chaque type d'action de {name} demande de nouveau avant d'agir.",
    "revoke.title": "Révoquer toute l'autonomie acquise de cet agent ?",
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
    "settings.no_writer": "Ce Hermes ne laisse pas cette page enregistrer les paramètres de tenure : utilisez la commande ci-dessous.",
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
    "settings.start_study": "Le départ de l'étude préenregistrée",
    "settings.start_trusted": "Les types couverts (modifications de fichiers, mémoire, sous-agents, outils de développement connus) ne demandent rien jusqu'à leur première faute, comme Hermes seul. Une faute met ce type en Probation (T1), et il regagne son niveau. Sortir de la machine et l'argent demandent toujours.",
    "settings.strict_desc_off": "Un nouveau modèle hérite de l'historique du précédent à enjeu faible et moyen, divisé par deux et provisoire jusqu'à ce que ses propres validations le confirment. L'enjeu élevé repart de zéro.",
    "settings.strict_desc_on": "Un nouveau modèle part d'un historique vide sur chaque type d'action, comme dans l'étude.",
    "settings.strict_help": "Ce dont hérite un nouveau modèle quand vous changez de modèle.",
    "settings.strict_off": "Mode strict désactivé",
    "settings.strict_on": "Mode strict activé",
    "settings.strict_title": "Mode strict au changement de modèle",
    "settings.use": "Choisir",
    "start.change_tip": "À changer dans un terminal : hermes tenure start trusted|probation",
    "start.probation": "Départ à l'étude (probation)",
    "start.trusted": "Départ en confiance",
    "state.aria": "{label} : {tip}",
    "state.fault": "faute",
    "state.fault_tip": "Une faute à enjeu moyen ou élevé reste à l'historique jusqu'à la réussite d'un essai.",
    "state.provisional": "provisoire",
    "state.provisional_tip": "Hérité du modèle précédent, divisé par deux, jusqu'à ce que ses propres approbations le confirment.",
    "state.suspended": "suspendu",
    "state.suspended_tip": "La session a lu du contenu externe : elle demande avant chaque action, jusqu'à sa fin.",
    "state.trial": "à l'essai",
    "state.trial_tip": "Une faute à enjeu moyen ou élevé a ouvert un essai : 3 succès vérifiés d'affilée.",
    "switch.arrow": "→",
    "switch.capped": "plafonné",
    "switch.col_after": "après le changement",
    "switch.col_now": "actuel",
    "switch.col_outcome": "résultat",
    "switch.col_public": "mesure publique",
    "switch.col_record": "votre historique",
    "switch.col_type": "type",
    "switch.count_carried": {
      "one": "{n} hérité",
      "other": "{n} hérités"
    },
    "switch.count_kept": {
      "one": "{n} conservé",
      "other": "{n} conservés"
    },
    "switch.count_reset": {
      "one": "{n} remis à zéro",
      "other": "{n} remis à zéro"
    },
    "switch.count_vetoed": {
      "one": "{n} bloqué",
      "other": "{n} bloqués"
    },
    "switch.delta": " ({delta})",
    "switch.empty": "Aucun agent à prévisualiser pour l'instant",
    "switch.footnote": "Les scores publics informent ; ils n'accordent jamais d'autonomie. Un blocage n'empêche que l'héritage, au-delà d'une marge fixe.",
    "switch.from": "De",
    "switch.group_agents": "Vos agents",
    "switch.label_carried": "hérité, provisoire",
    "switch.label_kept": "conservé",
    "switch.label_reset": "remis à zéro",
    "switch.label_vetoed": "bloqué",
    "switch.lede": "Avant de changer de modèle : ce dont le nouvel agent hériterait, type par type. Un nouveau modèle ou fournisseur est un nouvel agent. L'héritage vient de nous ; le mode strict suit l'étude.",
    "switch.no_public": "aucune mesure publique",
    "switch.none": "aucun",
    "switch.other": "Autre modèle…",
    "switch.pick_body": "Saisissez n'importe quel identifiant de modèle. Rien ne change tant que Hermes n'utilise pas vraiment le nouveau modèle.",
    "switch.pick_title": "Choisissez un modèle cible",
    "switch.placeholder": "identifiant de modèle, p. ex. {example} ou model@provider",
    "switch.preview": "Aperçu",
    "switch.provisional": {
      "one": "{n} provisoire",
      "other": "{n} provisoires"
    },
    "switch.strict": "mode strict : rien n'est hérité",
    "switch.text_carried": "Une partie de la série est héritée, marquée provisoire jusqu'à ce que le nouveau modèle ajoute la sienne.",
    "switch.text_kept": "Le nouvel agent a déjà son propre historique ici ; il n'est jamais écrasé.",
    "switch.text_reset": "Repart de zéro : enjeu élevé, plafonné ou mode strict.",
    "switch.text_vetoed": "Selon le benchmark public, le nouveau modèle est plus faible sur ce type : rien n'est hérité.",
    "switch.to": "Vers le modèle",
    "switch.to_aria": "Modèle cible",
    "tier.cap": "Plafonné · demande toujours",
    "tier.chip_trusted": "CONFIANCE",
    "tier.name.cap": "Toujours demandé",
    "tier.name.t1": "Probation",
    "tier.name.t2": "En examen",
    "tier.name.t3": "Titulaire",
    "tier.name.trusted": "De confiance",
    "tier.t1": "T1 · demande d'abord",
    "tier.t2": "T2 · agit, puis vous prévient, avec un bouton Annuler",
    "tier.t3": "T3 · agit seul, avec contrôles aléatoires",
    "tier.trusted": "De confiance · agit comme Hermes seul jusqu'à sa première erreur",
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
    "timeline.note": "Issu du registre chaîné par hachage, du plus récent au plus ancien, 200 derniers événements. Les résultats répétés sont regroupés.",
    "timeline.title": "Chronologie des preuves",
    "toast.acted": {
      "one": "{type} a fait une modification, puis vous a prévenu ({name}).",
      "other": "{type} a fait {n} modifications, puis vous a prévenu ({name})."
    },
    "toast.acted_detail": "Annuler restaure les fichiers de la dernière modification et compte comme une faute.",
    "toast.transition": "{agent} · {type} : {from} → {to}",
    "transitions.empty": "Aucun depuis l'ouverture de cette page. Chaque changement de niveau automatique est listé ici et dans la chronologie de chaque agent.",
    "transitions.title": "Changements de niveau vus sur cette page",
    "transitions.why_after_fault": "après une faute",
    "transitions.why_changed": "sans faute : révocation, ou réglages ou enjeu modifiés",
    "transitions.why_on_evidence": "sur preuves",
    "transitions.why_trial_open": "essai ouvert",
    "type.always_asks": "demande toujours",
    "type.flag_button": "Signaler",
    "type.flag_done": "Faute enregistrée sur {type} : désormais {tier}.",
    "type.flag_title": "Enregistrer une faute sur ce type, après coup",
    "type.guarantee": "Au plus {aoql} % des actions de ce type s'exécutent avec une erreur que personne n'a approuvée ; {worst} % si le modèle se dégrade.",
    "type.guarantee_plain": "Au plus environ 1 action sur {k} s'exécute avec une erreur que personne n'a approuvée.",
    "type.guarantee_provisional": "Au plus {aoql} % des actions de ce type s'exécutent avec une erreur que personne n'a approuvée ; {worst} % si le modèle se dégrade. Provisoire : preuves héritées.",
    "type.in_a_row": "{series} sur {required} d'affilée",
    "type.more_to_t2": {
      "one": "Encore {n} pour passer En examen (T2)",
      "other": "Encore {n} pour passer En examen (T2)"
    },
    "type.more_to_t3": {
      "one": "encore {n} pour être Titulaire",
      "other": "encore {n} pour être Titulaire"
    },
    "type.next": {
      "one": "Encore {n} succès vérifié d'affilée pour être titularisé.",
      "other": "Encore {n} succès vérifiés d'affilée pour être titularisé."
    },
    "type.next_session": "La série est complète : une session de plus et c'est fait.",
    "type.revoke_button": "Révoquer",
    "type.revoke_done": "{type} révoqué : retour en T1.",
    "type.revoke_title": "Retirer ce que ce type a gagné : retour en T1",
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "enjeu élevé",
    "type.stakes_low": "enjeu faible",
    "type.stakes_medium": "enjeu moyen",
    "type.stakes_other": "enjeu {stakes}",
    "type.tenured_line": "Agit seul. 1 action sur {k} reste contrôlée au hasard.",
    "type.trusted_bar": "De confiance dès le départ : rien d'acquis pour l'instant",
    "type.trusted_line": "De confiance jusqu'à sa première erreur · agit comme Hermes seul.",
    "type.trusted_line_undo": "De confiance jusqu'à sa première erreur · agit, puis vous prévient, avec un bouton Annuler.",
    "type.trusted_no_guarantee": "Pas encore de garantie : elle ne vient qu'avec un niveau acquis sur preuves. Sa première faute le place en Probation (T1).",
    "types.title": "Types d'action",
    "undo.col_agent": "agent",
    "undo.col_effect": "effet de l'annulation",
    "undo.col_file": "fichier",
    "undo.col_type": "type",
    "undo.col_when": "quand",
    "undo.confirm": "Annuler le n° {id} ?",
    "undo.effect_already": "restaure les fichiers · la vérification automatique a déjà compté une faute",
    "undo.effect_fault": "restaure les fichiers · compte comme une faute",
    "undo.effect_none": "rien à restaurer (pas d'instantané) · compterait comme une faute",
    "undo.empty_body": "Les écritures que l'agent a faites sans demander (en confiance, ou en T2 : agir, puis prévenir) gardent 24 heures un instantané des fichiers. Elles apparaissent ici, de la plus récente à la plus ancienne, chacune avec son bouton Annuler.",
    "undo.empty_title": "Rien à annuler",
    "undo.lede": "Dernières actions faites en T2 (agir, puis prévenir). Annuler restaure les fichiers depuis leur instantané et compte comme une faute du type.",
    "undo.title": "Restaurer les fichiers",
    "undo.window_ends": "annulable encore {duration}"
  },
  "zh": {
    "agents.pick": "选择一个智能体，查看它已赢得的自主权。",
    "agents.search": "搜索智能体",
    "backend.desc": "请在「能力 → 插件」（智能体列）中为此配置文件启用 tenure。{error}",
    "backend.title": "智能体端没有响应",
    "benchmark.col_faults": "失误 / 已验证",
    "benchmark.col_public": "公开",
    "benchmark.col_range": "95% 区间",
    "benchmark.col_rate": "失误率",
    "benchmark.col_sessions": "会话",
    "benchmark.empty_body": "每个已验证的操作都会计入模型在该类型上的记录，显示在这里和 {cmd} 中。",
    "benchmark.empty_title": "还没有记录",
    "benchmark.faults": {
      "other": "{n} 次失误 / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.no_public_type": "此操作类型没有公开测评。",
    "benchmark.not_enough": "证据不足",
    "benchmark.not_ranked": "证据尚不足",
    "benchmark.not_ranked_note": "模型在此类型上有 {n} 次已验证结果后才参与排名。",
    "benchmark.note": "每个模型在你的工作中、针对此操作类型的已验证记录，附失误率的 95% 区间，按区间上限排名。公开分数仅供参考：它衡量的是模型在别人任务上的能力，而不是在你的工作上的可靠性。",
    "benchmark.public_note": "衡量的是在别人任务上的能力，而不是在你的工作上的可靠性。",
    "benchmark.public_score": "公开分数：{benchmark}，{source}",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "失误率及其 95% 区间，坐标轴 0–{max}%",
    "benchmark.rate": "{rate}%（{low}–{high}%）",
    "benchmark.search": "搜索操作类型",
    "benchmark.source": "{source}。已公布的最高分，不限测试框架；并非受控对比。",
    "benchmark.source_accessed": "{source}，访问于 {accessed}。已公布的最高分，不限测试框架；并非受控对比。",
    "cell.capped_by_settings": "受风险设置限制",
    "cell.kind_irreversible": "{type} · {stakes}，不可逆",
    "cell.kind_reversible": "{type} · {stakes}，可逆",
    "cell.provisional_long": {
      "other": "{n} 项继承自上一个模型，暂定"
    },
    "cell.record": "记录：{successes} 次成功 · {faults} 次失误 · {neutrals} 次中性 · {spot} 次抽查",
    "cell.series": "连续 {series}/{required}",
    "cell.sessions": {
      "other": "{n} 个会话"
    },
    "cell.tier_now": "当前级别：{tier}（{name}）",
    "chip.tip": {
      "other": "{name}：{n} 个操作类型中有 {earned} 个已赢得自主权（T2 或 T3）。打开 Tenure。"
    },
    "common.loading": "正在读取证据…",
    "common.no_match": "无匹配项",
    "common.own_profile_only": "仅作用于当前配置文件",
    "common.retry": "重试",
    "community.col_contributors": "贡献者",
    "community.col_model": "模型",
    "community.empty_how": "如要贡献，请用这条命令写出你的记录，查看其中内容，然后提交一个 pull request，把文件加入社区仓库（{repo}）。",
    "community.empty_title": "还没有共享记录",
    "community.empty_what": "社区基准汇总 Tenure 用户自愿发布的记录：按模型和操作类别统计的已验证成功次数与失误次数，并用各自的护照密钥签名。不会自动共享任何内容：Tenure 不进行任何网络调用。",
    "community.empty_where": "如要在这里查看排行，请下载仓库发布的 community-board.json，并保存为 {path}。",
    "community.generated": "{records} · 排行生成于 {date}",
    "community.lede": "由贡献者自行申报，签名已核验：每份记录都用作者的护照密钥签名，每个密钥只计一份记录。",
    "community.lede_bold": "这无法阻止一个人拥有多个密钥。",
    "community.models": {
      "other": "{n} 个模型"
    },
    "community.ranking": "按操作类别，模型按失误率 95% 区间的上限排序，从不按单一分数排序。",
    "community.records": {
      "other": "{n} 份记录"
    },
    "confirm.flag_desc": "这会记为一次失误：{type} 至少降一级，需要重新晋升。用于没人发现的错误。",
    "confirm.flag_title": "将 {type} 标记为错误？",
    "confirm.revoke_desc": "{type} 会重新先询问，连续记录从零开始。这不算失误。",
    "confirm.revoke_title": "收回 {type}？",
    "confirm.undo_title": "撤销操作 {id}？",
    "emblem.none": "尚未赢得自主权",
    "emblem.review": {
      "other": "{n} 个类型考察中"
    },
    "emblem.tenured": {
      "other": "{n} 个类型已转正"
    },
    "emblem.trusted": {
      "other": "{n} 个类型信任中，非赢得"
    },
    "event.confirmed": "继承的证据已由它自己的记录确认",
    "event.fault_check": "自动检查失败",
    "event.fault_flag": "被你标记为失误",
    "event.fault_other": "失误（{source}）",
    "event.fault_refusal": "被你拒绝",
    "event.fault_spot": "抽查被拒绝或失败",
    "event.fault_undo": "被你撤销",
    "event.neutral_alone": "自主执行（已赢得）",
    "event.neutral_ambiguous": "无法判定 · 无证据",
    "event.neutral_blocked": "被其他防护拦截 · 无证据",
    "event.neutral_error": "工具出错 · 无证据",
    "event.neutral_expired": "未回报结果 · 无证据",
    "event.neutral_nobody": "无人应答 · 无证据",
    "event.neutral_other": "中性（{source}）",
    "event.neutral_timeout": "无回应 · 无证据",
    "event.revoked": "被你收回",
    "event.success_approved": "经你批准，运行无误",
    "event.success_notify": "已执行并告知 · 未撤销",
    "event.success_spot": "抽查经你批准",
    "event.switch": "切换模型",
    "event.switch_from": "从 {from} 切换模型",
    "event.tier": "级别 {from} → {to} · {why}",
    "event.trial_failed": {
      "other": "考察未通过：需等待 {n} 个操作"
    },
    "event.trial_opened": {
      "other": "开启考察期：接下来 {n} 个必须成功"
    },
    "event.trial_passed": "考察通过",
    "event.trial_reopens": {
      "other": "重新开启考察期：接下来 {n} 个必须成功"
    },
    "event.why_fault": "失误",
    "event.why_series_complete": "连续记录已达标",
    "event.why_series_n": "连续 {required}/{required}",
    "event.why_sessions": {
      "other": "{n} 个会话"
    },
    "event.why_settings": "设置更严格",
    "event.why_stakes": "风险等级变更",
    "event.why_wald": "通过序贯检验",
    "flag.confirm": "标记",
    "flag.desc": "这会记为一次失误：{type} 至少下降一个级别，之后需重新晋升。用于没人发现的错误。",
    "flag.title": "将此更改标记为错误？",
    "help.asks_body": "无论哪种起点，有些操作都会先询问你：",
    "help.asks_files": "文件编辑保留撤销，对项目文件执行的简单 rm、mv、cp、sed -i 或 echo > 文件 也一样：未询问就做出的修改可以还原。",
    "help.asks_irreversible": "无法撤销的操作：递归删除、文件命令中的通配符或变量、丢弃未提交的 git 工作、任何经由 sudo 的操作。",
    "help.asks_leaves": "离开本机的操作：发布、部署、推送、发送邮件、付款。",
    "help.asks_outside": "智能体读取外部内容（网页、邮件、下载的文件）后，它的命令都会先询问，直到你用 /new 开启新会话；文件修改（包括简单的 rm、mv 或 cp）照常进行并保留撤销。",
    "help.asks_title": "哪些会询问，为什么",
    "help.asks_unknown": "tenure 不认识的程序：数据库或云工具、未知命令。",
    "help.benchmark_body": "你的基准是每个模型在你自己的工作上、按操作类型的已验证记录，以及其失误率的 95% 区间。一个模型在某类型上有 {n} 个已验证结果后才会排名。显示的公开分数只作参考：是在别人任务上的能力，不是在你任务上的可靠性。",
    "help.flag_body": "标记用于报告一个没人发现的错误。它计为一次失误：该类型至少降一级，然后重新爬升。",
    "help.intro": "tenure 按模型、按操作类型决定 Hermes 是先询问你、先执行后告知，还是自主执行。每个决定都来自已验证的证据，写入一个已签名的账本。",
    "help.key_close": "关闭",
    "help.key_help": "本帮助",
    "help.key_next_prev": "下一个 / 上一个智能体",
    "help.key_open": "打开当前智能体",
    "help.key_raw": "切换原始类型名",
    "help.keys_note": "焦点在此页面内时，快捷键才生效。",
    "help.keys_title": "键盘",
    "help.passport_body": "护照是智能体记录的签名摘要：每个操作类型的级别、失误和已验证结果，以及哈希链账本的头部。它由此配置文件的 Ed25519 密钥签名。要验证它，请下载护照，导出账本，然后验证：",
    "help.passport_checks": "验证会检查签名和哈希链，然后重放账本，重新计算出相同的级别。其中没有任何自我声明。",
    "help.session_body": "有些询问（内联运行的代码、复杂的 shell 命令、未覆盖的本地命令如 rm、mv、cp，以及读取外部内容之后的命令）提供「允许本会话」：该询问在会话结束前不再出现。这是你的选择，不是证据：它不会赢得任何东西，新会话会再次询问。",
    "help.session_title": "允许本会话",
    "help.study_adds": "tenure 的补充：信任起步（不属于研究：信任期间的操作不计入任何成绩）、对独立执行的类型进行抽查、到达 T3 的连续记录需跨越两个不同会话、读取外部内容后暂停，以及向新模型的继承（严格模式即研究原规则）。start: probation 就是研究本身的起点。",
    "help.study_body": "某个类型出现第一次失误后，或在 start: probation 下从一开始，tenure 就采用一项关于“赢得的自主权”的预注册研究的规则：中间级别（先执行再告知你）用序贯检验（Wald），转正（T3）用 CSP-1 连续记录（Dodge 的连续抽样方案）。该研究在 6,000 多个模拟智能体上重放这一规则。结果尚未公布：tenure 并不声称研究已证实该规则。",
    "help.study_link": "OSF 上的预注册",
    "help.study_title": "规则背后的研究",
    "help.tiers_climb": "类型凭已验证的成功且无失误来升级。从试用期开始，低风险至少连续 {low} 次，或中风险 {medium} 次，进入考察中（T2）；只有可撤销的类型会经过 T2。更长的连续记录，分布在至少 {sessions} 个会话中，使其转正（T3）。",
    "help.tiers_drop": "一次失误就会让该类型降级，其连续记录重新开始。",
    "help.tiers_title": "级别",
    "help.title": "tenure 如何运作",
    "help.trusted_body": "默认情况下，tenure 覆盖的操作类型（文件编辑、记忆、把工作交给子智能体、常用开发工具）在第一次失误之前什么都不问，与 Hermes 单独运行时一样。第一次失误（一次撤销、一次检查失败、一次标记）会让该类型进入试用期（T1）：此后它先询问，并根据你的回答重新赢得级别。信任起步期间做的任何事都不算赢得。",
    "help.trusted_title": "信任起步",
    "help.undo_body": "未询问就做出的修改在 24 小时内保留撤销：在通知中、在智能体页面的「未询问即执行」下，或在对话中。撤销会还原文件，并计为一次失误：该类型降级。",
    "help.undo_title": "撤销与标记",
    "hero.agent": "智能体",
    "intro.body": "每个模型的每个操作类型都从 T1 开始：先询问。连续多次获批且无误后，它升到 T2：先执行后告知，并可撤销。跨两个会话的更长连续记录会让它升到 T3：自主执行，但每 {k} 个操作仍会抽查 1 个，先询问你。一次失误就会让该类型降级。",
    "intro.body_trusted": "每个操作类型都以信任起步：首次失误前，它像单独使用 Hermes 一样执行，可逆的更改先执行后告知，并可撤销。首次失误（一次撤销、一次检查失败、一次标记）会让它进入试用期 (T1)：先询问。连续多次获批且无误后，它升到 T2；跨两个会话的更长连续记录会让它升到 T3：自主执行，但每 {k} 个操作仍会抽查 1 个，先询问你。离开本机和涉及金钱的操作始终会询问。",
    "intro.got_it": "知道了",
    "intro.title": "操作类型如何赢得级别",
    "legend.a_share": "一部分",
    "legend.alone": "自主执行，抽查其中 {share}",
    "legend.ask": "先询问",
    "legend.capped": "受限：始终询问",
    "legend.carried": "继承自上一个模型，暂定",
    "legend.carried_flag": "继承",
    "legend.notify": "先执行后告知，可撤销（可逆类型）",
    "legend.series": "连续已验证的成功次数，共需 N 次",
    "legend.trusted": "信任起步：首次失误前像单独使用 Hermes 一样执行，未赢得任何级别",
    "map.aria": "按操作类型列出的智能体",
    "map.asked_suffix": " 次询问",
    "map.capped": "受限",
    "map.carried_n": {
      "other": "{n} 项继承"
    },
    "map.copy_pending": "从另一个配置文件复制而来，启动时检查",
    "map.count_faults": {
      "other": "{n} 次失误"
    },
    "map.count_sessions": {
      "other": "{n} 个会话"
    },
    "map.current": " · 当前配置文件",
    "map.empty_after": " 开始，且只凭已验证的成功晋升：可逆类型在连续若干次无失误的已验证成功后升到中间级别，在来自两个会话的完整 N 次连续成功后升到 T3。",
    "map.empty_before": "tenure 从智能体请求运行的第一个操作开始计数。读取从不询问。每个操作类型都从 ",
    "map.empty_bold": "T1（先询问）",
    "map.empty_title": "还没有证据",
    "map.empty_trusted": "照常工作即可。每个操作类型在首次失误前像单独使用 Hermes 一样执行；此后会先询问你，并根据你的回答重新赢得级别。",
    "map.fault_on_record": "有失误记录",
    "map.group_high": "高风险",
    "map.group_low": "低风险",
    "map.group_medium": "中风险",
    "map.held": "已赢得 {tier}，被你的设置压低",
    "map.one_in": "1/{k}",
    "map.pending": "从下一个操作起生效",
    "map.preset": "{preset}预设",
    "map.profile": "配置文件 {profile}",
    "map.read_only": " · 此处只读",
    "map.spot": "抽查率 {rate}",
    "map.start_probation": "考察起步（试用期）",
    "map.start_trusted": "信任起步",
    "map.strict": "严格",
    "map.suspended": {
      "other": "{n} 个会话已暂停：读取了外部内容"
    },
    "map.th_agent": "智能体",
    "map.th_agent_sub": "配置文件 · model@provider",
    "map.th_capped": "受限 · 始终询问",
    "map.th_risk": {
      "other": "风险率 {risk} · 连续 {n} 次后自主执行"
    },
    "map.tot_actions": {
      "other": "{n} 个操作"
    },
    "map.tot_alone": "{n} 个未经询问",
    "map.tot_checked": "{n} 个由你验证",
    "map.tot_faults": {
      "other": "{n} 次失误"
    },
    "meta.actions": "操作",
    "meta.actions_tip": "tenure 看到的此智能体的全部操作。没人验证的操作（无回应、超时）不计入。",
    "meta.alone": "自主执行",
    "meta.checked": "由你验证",
    "meta.faults": "失误",
    "meta.preset": "预设",
    "meta.profile": "配置文件",
    "meta.provider": "提供方",
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
    "model_menu.badge": "已赢得 {tier}",
    "moment.dismiss": "关闭",
    "moment.eyebrow_down": "#发现失误 · {type}",
    "moment.eyebrow_up": "#晋升 · {type}",
    "moment.granted": "已获转正",
    "moment.on_probation": "进入试用期",
    "moment.probation": "重回试用期",
    "moment.review": "进入考察",
    "moment.review_sub": "{name} 现在先执行后告知，可撤销。",
    "nav.label": "Tenure",
    "overview.actions_label": {
      "other": "{n} 操作"
    },
    "overview.actions_sub": "已覆盖",
    "overview.alone_label": "未询问即执行",
    "overview.alone_sub": "未询问即运行，共 {total} 个",
    "overview.aria": "最近 7 天",
    "overview.checked_label": "已验证",
    "overview.checked_sub": "由你验证，共 {total} 个",
    "overview.faults_label": "发现的失误",
    "overview.faults_sub": {
      "other": "你验证的 {n} 个中有 {faults} 个"
    },
    "overview.window": "最近 7 天，所有配置文件",
    "page.animations": "动画",
    "page.animations_reduced": "系统要求减少动态效果：动画保持关闭",
    "page.raw_off": "名称已脱敏",
    "page.raw_on": "原始名称",
    "page.raw_title": "显示原始操作类型名（r）",
    "page.stale": "上次刷新失败（{error}）。显示的是 {time} 的数据。",
    "page.title": "Tenure",
    "page.unreadable": "无法读取：{profiles}。其数据库存在但无法打开；已显示其他配置文件。",
    "page.view_agents": "智能体",
    "page.view_benchmark": "你的基准",
    "page.view_community": "社区",
    "page.view_help": "帮助",
    "page.view_map": "总览",
    "page.view_passport": "护照",
    "page.view_settings": "设置",
    "page.view_switch": "切换预览",
    "page.view_undo": "撤销",
    "palette.no_current": "当前模型还没有记录。",
    "palette.open": "Tenure：打开",
    "palette.passport": "Tenure：显示当前模型的护照",
    "palette.revoke": "Tenure：收回当前模型的自主权…",
    "passport.agent": "智能体",
    "passport.card_title": "护照 · Ed25519",
    "passport.col_guarantee": "保证",
    "passport.col_series": "连续",
    "passport.col_sessions": "会话",
    "passport.col_tier": "级别",
    "passport.copy_command": "复制命令",
    "passport.download": "下载护照（.json）",
    "passport.empty_body": "护照汇总智能体的记录；第一个已验证的操作出现后才会生成。",
    "passport.empty_title": "还没有护照",
    "passport.faults_checks": {
      "other": "{n} 次失误 / {total} 次已验证结果"
    },
    "passport.field_agent": "智能体",
    "passport.field_profile": "配置文件",
    "passport.field_public_key": "公钥",
    "passport.field_settings": "设置",
    "passport.field_signature": "签名",
    "passport.field_type_names": "类型名",
    "passport.generated": "生成时间",
    "passport.image_failed": "无法绘制图片",
    "passport.ledger": "账本",
    "passport.ledger_hint": "导出账本，以便重放：",
    "passport.ledger_value": {
      "other": "{n} 个事件 · 头部 {head}"
    },
    "passport.more_types": {
      "other": "另有 {n} 个操作类型，见文件"
    },
    "passport.note": "已签名且可发现篡改：签名或锚定后的任何改动都会在验证时显示出来。较早的护照对照更长的账本依然能通过验证；验证器会说明此后的变化。",
    "passport.pending_note": "按最近记录的设置计算；新设置从下一个操作起生效。",
    "passport.protocol": "协议",
    "passport.rule": "规则",
    "passport.rule_osf": "已在 OSF 预注册",
    "passport.save_image": "保存图片（.png）",
    "passport.signature": "Hermes Agent 插件",
    "passport.title": "已签名护照",
    "passport.trusted": "信任中（非赢得）",
    "passport.types_title": "已证实的类型",
    "passport.unavailable": "不可用：{error}",
    "passport.value_hashed": "{profile}（已哈希）",
    "passport.value_none": "无",
    "passport.value_raw": "原始",
    "passport.value_redacted": "程序和子命令之后的部分已脱敏",
    "passport.value_unsigned": "未签名",
    "passport.verdict_chain": "哈希链完整",
    "passport.verdict_ok_replay": "按规则重放账本得到相同的级别",
    "passport.verdict_ok_signature": "签名有效（Ed25519）",
    "passport.verdict_ok_title": "已验证",
    "passport.verdict_problems": {
      "other": "发现 {n} 个问题"
    },
    "passport.verdict_unsigned_no_key": "还没有签名密钥：运行 {cmd} 创建",
    "passport.verdict_unsigned_replay": "重放得到相同的级别",
    "passport.verdict_unsigned_title": "未签名，其余均已验证",
    "passport.verify_hint": "任何人都可以验证：",
    "passport.verifying": "正在验证…",
    "preset.copy_pending": "从另一个配置文件复制而来，启动时检查",
    "preset.name.balanced": "平衡",
    "preset.name.careful": "谨慎",
    "preset.name.custom": "自定义",
    "preset.name.fast": "快速",
    "preset.value": "{preset} · 每 {k} 个抽查 1 个",
    "preset.value_pending": "{preset} · 每 {k} 个抽查 1 个 · 从下一个操作起生效",
    "pstyle.animation": "动画",
    "pstyle.animation_desc_develop": "徽记逐点显影，账本哈希定格，然后盖上印章。",
    "pstyle.animation_desc_holographic": "卡片缓缓倾斜，带一道反光和缓慢的闪烁。",
    "pstyle.animation_desc_scan": "一条扫描线自上而下印出卡片。",
    "pstyle.animation_desc_still": "没有动效。",
    "pstyle.animation_develop": "显影",
    "pstyle.animation_holographic": "全息",
    "pstyle.animation_scan": "扫描",
    "pstyle.animation_still": "静止",
    "pstyle.card": "卡片",
    "pstyle.card_accent": "强调色",
    "pstyle.card_ink": "墨色",
    "pstyle.card_paper": "纸色",
    "pstyle.customise": "自定义",
    "pstyle.forced_still": "动画已关闭（在这里或在你的系统中）：护照保持静止。",
    "pstyle.help": "护照在本页和保存的图片中的外观。只对你、只在这台屏幕上生效；卡片上的内容永不改变。",
    "pstyle.no_agent": "还没有智能体：有了第一个后会显示预览。",
    "pstyle.pattern": "徽记图案",
    "pstyle.pattern_grid": "网格",
    "pstyle.pattern_note": "每种图案都按智能体赢得的自主权比例填充，并依据其标识排布：同一个智能体的徽记始终相同。",
    "pstyle.pattern_rings": "圆环",
    "pstyle.pattern_sunburst": "放射",
    "pstyle.preview": "你的护照预览",
    "pstyle.title": "你的护照",
    "recent.check_failed": "检查失败",
    "recent.check_failed_tip": "自动检查失败：已记为一次失误。撤销可恢复文件。",
    "recent.collapse": "收起这些操作",
    "recent.expand": "显示每个操作",
    "recent.flag": "标记",
    "recent.flag_tip": "它犯了一个没人发现的错误：收回此类型的自主权。",
    "recent.flagged": "已标记 {type}：记为一次失误，至少降一级。",
    "recent.hours_ago": {
      "other": "{n} 小时前"
    },
    "recent.just_now": "刚刚",
    "recent.minutes_ago": {
      "other": "{n} 分钟前"
    },
    "recent.more_files": "+{n}",
    "recent.no_snapshot": "无快照",
    "recent.none": "过去 24 小时内没有可撤销的操作。",
    "recent.restore_icon": "24 小时内可撤销",
    "recent.show_all": "显示全部 {n} 条",
    "recent.show_fewer": "收起",
    "recent.title": "未询问即执行",
    "recent.undo": "撤销",
    "recent.undo_failed": "无法撤销",
    "recent.undo_tip": "将文件恢复原样。记为一次失误：该类型会降级。",
    "recent.undone": "文件已恢复。已记为一次失误。",
    "revoke.action": "全部收回",
    "revoke.busy": "正在收回…",
    "revoke.confirm": "全部收回",
    "revoke.desc": "{name} 的每个操作类型都会重新先询问，连续记录从零开始。它的记录仍保留在账本中。这不算失误。",
    "revoke.done": "{name} 的每个操作类型都已恢复为先询问。",
    "revoke.title": "收回此智能体已获得的全部自主权？",
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
    "settings.no_writer": "此 Hermes 不允许此页面保存 tenure 的设置：请使用下方命令。",
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
    "settings.start_study": "预注册研究的起点",
    "settings.start_trusted": "覆盖的类型（文件编辑、记忆、子智能体、常见开发工具）在第一次失误之前什么都不问，与 Hermes 单独运行时一样。一次失误会让该类型进入试用期（T1），之后重新赢得级别。离开本机的操作和涉及金钱的操作始终询问。",
    "settings.strict_desc_off": "新模型继承上一个模型在低风险和中风险上的记录，减半且为暂定，直到它自己的批准加以确认。高风险从零开始。",
    "settings.strict_desc_on": "新模型在每个操作类型上都从空记录开始，与研究中一致。",
    "settings.strict_help": "切换模型时，新模型继承什么。",
    "settings.strict_off": "严格模式：关",
    "settings.strict_on": "严格模式：开",
    "settings.strict_title": "切换模型时的严格模式",
    "settings.use": "使用",
    "start.change_tip": "在终端中更改：hermes tenure start trusted|probation",
    "start.probation": "考察起步（试用期）",
    "start.trusted": "信任起步",
    "state.aria": "{label}：{tip}",
    "state.fault": "有失误",
    "state.fault_tip": "中、高风险的失误会一直留在记录中，直到通过考察期。",
    "state.provisional": "暂定",
    "state.provisional_tip": "从上一个模型继承并减半，直到它自己的批准将其确认。",
    "state.suspended": "已暂停",
    "state.suspended_tip": "此会话读取了外部内容：在会话结束前，每次操作都会询问。",
    "state.trial": "考察期",
    "state.trial_tip": "一次中、高风险的失误开启了考察期：需连续 3 次已验证的成功。",
    "switch.arrow": "→",
    "switch.capped": "受限",
    "switch.col_after": "切换后",
    "switch.col_now": "当前",
    "switch.col_outcome": "结果",
    "switch.col_public": "公开测评",
    "switch.col_record": "你的记录",
    "switch.col_type": "类型",
    "switch.count_carried": {
      "other": "{n} 项继承"
    },
    "switch.count_kept": {
      "other": "{n} 项保留"
    },
    "switch.count_reset": {
      "other": "{n} 项重置"
    },
    "switch.count_vetoed": {
      "other": "{n} 项否决"
    },
    "switch.delta": "（{delta}）",
    "switch.empty": "还没有可预览的智能体",
    "switch.footnote": "公开分数仅供参考，从不授予自主权。否决只会阻止继承，且仅在超出固定差距时生效。",
    "switch.from": "从",
    "switch.group_agents": "你的智能体",
    "switch.label_carried": "继承，暂定",
    "switch.label_kept": "保留",
    "switch.label_reset": "重置",
    "switch.label_vetoed": "否决",
    "switch.lede": "更换模型之前：逐个类型查看新智能体会继承什么。新模型或新提供方即为新智能体。继承是我们的补充；严格模式即研究原规则。",
    "switch.no_public": "无公开测评",
    "switch.none": "无",
    "switch.other": "其他模型…",
    "switch.pick_body": "输入任意模型 ID。在 Hermes 真正运行新模型之前，什么都不会改变。",
    "switch.pick_title": "选择目标模型",
    "switch.placeholder": "模型 ID，例如 {example} 或 model@provider",
    "switch.preview": "预览",
    "switch.provisional": {
      "other": "{n} 项暂定"
    },
    "switch.strict": "严格模式：不继承任何记录",
    "switch.text_carried": "部分连续记录会被继承，并标为暂定，直到新模型积累自己的记录。",
    "switch.text_kept": "新智能体在这里已有自己的记录；它永远不会被覆盖。",
    "switch.text_reset": "从零开始：高风险、受限或严格模式。",
    "switch.text_vetoed": "公开基准显示新模型在此类型上更弱：不继承任何记录。",
    "switch.to": "目标模型",
    "switch.to_aria": "目标模型",
    "tier.cap": "受限 · 始终询问",
    "tier.chip_trusted": "信任",
    "tier.name.cap": "始终询问",
    "tier.name.t1": "试用期",
    "tier.name.t2": "考察中",
    "tier.name.t3": "已转正",
    "tier.name.trusted": "信任中",
    "tier.t1": "T1 · 先询问",
    "tier.t2": "T2 · 先执行后告知，可撤销",
    "tier.t3": "T3 · 自主执行，接受抽查",
    "tier.trusted": "信任中 · 首次失误前，像单独使用 Hermes 一样执行",
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
    "timeline.note": "来自哈希链账本，最新在前，最近 200 个事件。重复的结果已合并。",
    "timeline.title": "证据时间线",
    "toast.acted": {
      "other": "{type}：{n} 项更改，已执行并告知你（{name}）。"
    },
    "toast.acted_detail": "撤销会恢复最近一次更改的文件，并记为一次失误。",
    "toast.transition": "{agent} · {type}：{from} → {to}",
    "transitions.empty": "打开此页面以来没有变化。每次自动的级别变化都会列在这里，以及各智能体的时间线中。",
    "transitions.title": "本页看到的级别变化",
    "transitions.why_after_fault": "因失误",
    "transitions.why_changed": "无失误：被收回，或设置、风险等级已变更",
    "transitions.why_on_evidence": "基于证据",
    "transitions.why_trial_open": "考察期中",
    "type.always_asks": "始终询问",
    "type.flag_button": "标记",
    "type.flag_done": "已在 {type} 上记录失误：现为 {tier}。",
    "type.flag_title": "事后为此类型记录一次失误",
    "type.guarantee": "此类型最多有 {aoql}% 的操作会带着无人批准的错误运行；若模型变差，最多 {worst}%。",
    "type.guarantee_plain": "其操作中最多约每 {k} 个就有 1 个带着无人批准的错误运行。",
    "type.guarantee_provisional": "此类型最多有 {aoql}% 的操作会带着无人批准的错误运行；若模型变差，最多 {worst}%。暂定：基于继承的证据。",
    "type.in_a_row": "连续 {series}/{required}",
    "type.more_to_t2": {
      "other": "还差 {n} 次进入考察中（T2）"
    },
    "type.more_to_t3": {
      "other": "还差 {n} 次转正"
    },
    "type.next": {
      "other": "再连续 {n} 次已验证的成功即可转正。"
    },
    "type.next_session": "连续记录已达标：再完成一个会话即可。",
    "type.revoke_button": "收回",
    "type.revoke_done": "已收回 {type}：退回 T1。",
    "type.revoke_title": "收回此类型已赢得的自主权：退回 T1",
    "type.sessions": {
      "other": "{n} 个会话"
    },
    "type.stakes_high": "高风险",
    "type.stakes_low": "低风险",
    "type.stakes_medium": "中风险",
    "type.stakes_other": "{stakes}风险",
    "type.tenured_line": "自主执行。每 {k} 个操作仍抽查 1 个。",
    "type.trusted_bar": "初始即信任：尚未赢得任何级别",
    "type.trusted_line": "首次失误前保持信任 · 像单独使用 Hermes 一样执行。",
    "type.trusted_line_undo": "首次失误前保持信任 · 先执行后告知，可撤销。",
    "type.trusted_no_guarantee": "暂无保证：只有凭证据赢得的级别才有保证。首次失误会让它进入试用期 (T1)。",
    "types.title": "操作类型",
    "undo.col_agent": "智能体",
    "undo.col_effect": "撤销的影响",
    "undo.col_file": "文件",
    "undo.col_type": "类型",
    "undo.col_when": "时间",
    "undo.confirm": "撤销 #{id}？",
    "undo.effect_already": "恢复文件 · 自动检查已记过一次失误",
    "undo.effect_fault": "恢复文件 · 记为一次失误",
    "undo.effect_none": "没有可恢复的内容（无快照）· 会记为一次失误",
    "undo.empty_body": "智能体未经询问写入的文件（信任中，或处于 T2：先执行后告知）会保留 24 小时快照。它们按最新在前显示在这里，每条都可单独撤销。",
    "undo.empty_title": "没有可撤销的操作",
    "undo.lede": "最近先执行后告知的操作。撤销会从快照恢复文件，并记为该类型的一次失误。",
    "undo.title": "恢复文件",
    "undo.window_ends": "{duration}后无法撤销"
  }
};
/* TENURE_LOCALES_END */

// Commands the user types stay out of the catalogs.
const VERIFY_COMMAND = 'hermes tenure verify passport.json ledger.jsonl'
const EXPORT_COMMAND = 'hermes tenure export ledger.jsonl'

/* TENURE_I18N_BEGIN */
// The host picks the locale (the app's display.language) and falls back to `en` per key; it resolves dotted keys as
// paths into nested bundles and calls function leaves with the translator's arguments. So each flat catalog is
// registered as a nested tree whose leaves format {placeholders} and pick the plural category for {n}.
const HOST_LOCALES = ['en', 'zh', 'zh-hant', 'ja', 'ar', 'ru', 'fr', 'de', 'es']

const baseLang = lang => String(lang || '').toLowerCase().split(/[-_]/)[0]

// exact -> base language (zh-hant -> zh) -> en. Returns [lang, catalog].
function pickCatalog(locales, lang) {
  const exact = String(lang || '').toLowerCase()
  if (locales[exact]) return [exact, locales[exact]]
  const base = baseLang(exact)
  if (locales[base]) return [base, locales[base]]
  return ['en', locales.en || {}]
}

function pluralCategory(lang, n) {
  try {
    return new Intl.PluralRules(lang).select(Number(n))
  } catch {
    return 'other'
  }
}

function formatMessage(value, lang, vars) {
  let text = value
  if (text && typeof text === 'object') {
    const n = vars && typeof vars === 'object' ? vars.n : undefined
    text = text[pluralCategory(lang, n)] ?? text.other
  }
  if (typeof text !== 'string') return null
  return text.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (m, name) =>
    vars && typeof vars === 'object' && Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m
  )
}

// Pure lookup, same chain as the host: active catalog -> en -> the key itself.
function translate(locales, lang, key, vars) {
  const [picked, catalog] = pickCatalog(locales, lang)
  if (catalog[key] != null) {
    const out = formatMessage(catalog[key], picked, vars)
    if (out != null) return out
  }
  const out = locales.en && locales.en[key] != null ? formatMessage(locales.en[key], 'en', vars) : null
  return out != null ? out : key
}

// { lang: nested tree of formatter functions } for ctx.i18n.register, one bundle per locale the host can select.
function hostBundles(locales) {
  const bundles = {}
  for (const lang of new Set([...HOST_LOCALES, ...Object.keys(locales)])) {
    const [picked, catalog] = pickCatalog(locales, lang)
    if (picked === 'en' && lang !== 'en') continue // the host falls back to en by itself
    const tree = {}
    for (const [key, value] of Object.entries(catalog)) {
      const parts = key.split('.')
      let node = tree
      for (const part of parts.slice(0, -1)) node = node[part] = node[part] || {}
      node[parts[parts.length - 1]] = vars => formatMessage(value, picked, vars)
    }
    bundles[lang] = tree
  }
  return bundles
}
/* TENURE_I18N_END */
/** A preset's display name in the active language; the id itself (typed in commands) when it has none. */
function presetName(t, id) {
  if (id === 'careful') return t('preset.name.careful')
  if (id === 'balanced') return t('preset.name.balanced')
  if (id === 'fast') return t('preset.name.fast')
  if (id === 'custom') return t('preset.name.custom')
  return id
}


// A sentence with one React node inside: format it around a sentinel, then interleave the node.
function withNode(t, key, name, node) {
  const parts = t(key, { [name]: '\u0000' }).split('\u0000')
  return parts.flatMap((part, i) => (i === 0 ? [part] : [node, part]))
}

// ------------------------------------------------------------------------------------------------ data
let rest = null
let storage = null
const bus = new EventTarget()                       // live events and cross-surface requests (palette → page)
const cache = { agents: null }                      // last /agents answer, for non-React readers (menu, palette)

const keyAgents = profile => ['tenure', profile, 'agents']

async function fetchAgents() {
  const data = await rest('/agents')
  cache.agents = data
  return data
}

function useAgents() {
  const profile = useValue(host.state.profile)
  const qc = useQueryClient()
  useEffect(() => {
    const onChange = () => qc.invalidateQueries({ queryKey: ['tenure'] })
    bus.addEventListener('changed', onChange)
    return () => bus.removeEventListener('changed', onChange)
  }, [qc])
  return useQuery({ queryKey: keyAgents(profile), queryFn: fetchAgents, refetchInterval: HEARTBEAT_MS })
}

function allAgents(data) {
  const out = []
  for (const p of (data && data.profiles) || []) {
    for (const a of p.agents || []) out.push({ ...a, profile: p.profile, settings: p.settings, key: `${p.profile}|${a.agent}` })
  }
  return out
}

const displayName = model => String(model || '').split('/').pop()

// The same model may be spelled claude-sonnet-5.5 by the provider and claude-sonnet-5-5 in the model menu.
const sameModel = m => displayName(m).toLowerCase().replace(/[._\s]+/g, '-')

function agentForModel(data, model) {
  if (!model) return null
  const tail = sameModel(model)
  const list = allAgents(data).filter(a => sameModel(a.model) === tail)
  return list.find(a => a.profile === (data && data.current)) || list[0] || null
}

/**
 * The tier a type shows. 'trusted': the trusted start covers it (no fault or revoke yet, not at an earned T3): it acts
 * as Hermes alone would, and nothing about it is earned. Its first fault puts it on Probation (T1), so it ranks just
 * above T1: trusted -> T1 with a fault plays "Back on probation", and it never counts as earned autonomy.
 */
const tierKey = t => (t.capped ? 'cap' : t.trusted ? 'trusted' : t.effective_tier || t.tier || 'ask')
const TIER_SHORT = { ask: 'T1', notify: 'T2', alone: 'T3', cap: 'CAP' }
const TIER_RANK = { cap: 0, ask: 1, trusted: 1.5, notify: 2, alone: 3 }
const TIER_DOT = { ask: 'bg-muted-foreground/40', trusted: 'bg-muted-foreground/40', notify: 'bg-primary', alone: 'bg-primary', cap: 'bg-muted-foreground/40' }
/** The chip's code: T1/T2/T3/CAP travel unchanged; the trusted state has no tier code, its word is translated. */
const tierShort = (tier, t) => (tier === 'trusted' ? t('tier.chip_trusted') : TIER_SHORT[tier])
/** The profile's start mode: from its settings, else inferred from a type the trusted start covers; null if unknown. */
const startOf = (settings, types) =>
  settings && (settings.start === 'trusted' || settings.start === 'probation')
    ? settings.start
    : (types || []).some(ty => ty.trusted) ? 'trusted' : null

function bestTier(agent) {
  let best = 'ask'
  for (const t of agent.types || []) if (TIER_RANK[tierKey(t)] > TIER_RANK[best]) best = tierKey(t)
  return best
}

const earned = agent => (agent.types || []).filter(t => ['notify', 'alone'].includes(tierKey(t))).length
/** The page's language, as Hermes sets it on <html> from display.language; Western digits in every language. */
const pageLocale = () => {
  const lang = (typeof document !== 'undefined' && document.documentElement.lang) || 'en'
  return lang + '-u-nu-latn'
}
const dec1 = x => {
  try { return new Intl.NumberFormat(pageLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(x) } catch (e) { return Number(x).toFixed(1) }
}
const pct = x => dec1(x * 100)
const when = iso => {
  try { return new Date(iso).toLocaleString(pageLocale()) } catch (e) { return new Date(iso).toLocaleString() }
}

const ago = (t, s) =>
  s < 90 ? t('recent.just_now') : s < 5400 ? t('recent.minutes_ago', { n: Math.round(s / 60) }) : t('recent.hours_ago', { n: Math.round(s / 3600) })

async function revokeAgent(a, t) {
  await rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
  haptic('success')
  host.notify({ kind: 'success', message: t('revoke.done', { name: displayName(a.model) }) })
}

// ------------------------------------------------------------------------------------------------ ink & dither
// "Encre et trame": one colour (the host's accent), host neutrals for everything else, and a 1-bit Bayer 4x4 dither
// that means something: a type's bar densifies toward its next tier, the agent's emblem fills with the share of
// autonomy it earned. Canvases read their ink from CSS (`color`), so light, dark and every accent follow by themselves.
const BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
const bayer = (i, j) => BAYER[j & 3][i & 3] / 16
const clamp01 = x => (x < 0 ? 0 : x > 1 ? 1 : x)
const pad2 = n => String(n).padStart(2, '0')

// Motion: on unless the system asks to reduce it or the user turned it off (ctx.storage `animations`: on / off).
const reducedQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null
let animPref = 'on'
const motionOn = () => animPref !== 'off' && !(reducedQuery && reducedQuery.matches)

function setAnimPref(value) {
  animPref = value
  if (storage) storage.set('animations', value)
  bus.dispatchEvent(new Event('motion'))
}

function useMotion() {
  const [on, setOn] = useState(motionOn)
  useEffect(() => {
    const update = () => setOn(motionOn())
    bus.addEventListener('motion', update)
    if (reducedQuery && reducedQuery.addEventListener) reducedQuery.addEventListener('change', update)
    return () => {
      bus.removeEventListener('motion', update)
      if (reducedQuery && reducedQuery.removeEventListener) reducedQuery.removeEventListener('change', update)
    }
  }, [])
  return on
}

// The passport's look, per viewer (ctx.storage `passport_style`): animation, emblem pattern, card. Defaults = the
// original look. Only the look: every value on the card stays the agent's own.
const PASS_STYLE = { animation: ['develop', 'holographic', 'scan', 'still'], pattern: ['sunburst', 'rings', 'grid'], card: ['accent', 'ink', 'paper'] }
const PASS_STYLE_DEFAULT = { animation: 'develop', pattern: 'sunburst', card: 'accent' }
let passStyle = { ...PASS_STYLE_DEFAULT }
let focusPassStyle = false

function cleanPassStyle(v) {
  let o = v
  if (typeof o === 'string') {
    try { o = JSON.parse(o) } catch (e) { o = null }
  }
  const out = { ...PASS_STYLE_DEFAULT }
  if (o && typeof o === 'object') for (const k of Object.keys(PASS_STYLE)) if (PASS_STYLE[k].includes(o[k])) out[k] = o[k]
  return out
}

function setPassStyle(patch) {
  passStyle = cleanPassStyle({ ...passStyle, ...patch })
  if (storage) storage.set('passport_style', { ...passStyle })
  bus.dispatchEvent(new Event('passstyle'))
}

function usePassStyle() {
  const [st, setSt] = useState(passStyle)
  useEffect(() => {
    const update = () => setSt(passStyle)
    bus.addEventListener('passstyle', update)
    return () => bus.removeEventListener('passstyle', update)
  }, [])
  return st
}

/** A stable number in [0, 1) from an agent's id: it lays out the emblem's rings or lattice, never its density. */
function seedOf(id) {
  const str = String(id || '')
  let h = 2166136261
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619)   // the dashboard's same hash
  return (h >>> 0) / 4294967296
}

// Static canvases repaint when the theme or the accent changes (the host rewrites attributes on <html> / <body>).
// They repaint only when a computed colour really changed (the host touches those attributes for other reasons too),
// and when the device pixel ratio changes (a window moved to another screen, zoom).
const repaints = new Set()
let themeObserver = null
let probe = null
let onStyle = null
let lastInk = ''
let dprQuery = null

/** Relative luminance of a computed CSS colour: rgb()/rgba() in 0..255, or color(srgb …) in 0..1. */
function luminance(css) {
  const nums = String(css || '').match(/-?[\d.]+/g)
  if (!nums || nums.length < 3) return 0
  const scale = /^color\(/.test(String(css).trim()) ? 1 : 255
  const lin = v => {
    const c = Math.max(0, Math.min(1, Number(v) / scale))
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * lin(nums[0]) + 0.7152 * lin(nums[1]) + 0.0722 * lin(nums[2])
}

/** Ink on accent paper: whichever of near-black and near-white contrasts more with the accent. */
const inkOn = accent => {
  const L = luminance(accent)
  return (L + 0.05) / 0.0545 > 1.05 / (L + 0.05) ? '#0b0b0c' : '#fcfcfc'
}

/** The accent and foreground as the page computes them; also sets the ink used on accent paper. */
function readInk() {
  if (typeof document === 'undefined' || !document.body) return ''
  if (!probe) {
    probe = document.createElement('span')
    probe.className = 'tn-root tn-probe'
    probe.setAttribute('aria-hidden', 'true')
    document.body.append(probe)
  }
  const cs = getComputedStyle(probe)
  const sig = cs.color + '|' + cs.backgroundColor
  if (sig !== lastInk && onStyle) onStyle.textContent = `.tn-root{--tn-on:${inkOn(cs.color)}}`
  return sig
}

function repaintAll() {
  for (const fn of repaints) fn()
}

function onDpr() {
  repaintAll()
  watchDpr()
}
function watchDpr() {
  if (typeof matchMedia !== 'function' || typeof window === 'undefined') return
  if (dprQuery) dprQuery.removeEventListener('change', onDpr)
  dprQuery = matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`)
  dprQuery.addEventListener('change', onDpr)
}

function watchTheme() {
  if (themeObserver || typeof MutationObserver !== 'function' || typeof document === 'undefined') return
  lastInk = readInk()
  let queued = false
  themeObserver = new MutationObserver(() => {
    if (queued) return
    queued = true
    requestAnimationFrame(() => {
      queued = false
      const ink = readInk()
      if (ink === lastInk) return
      lastInk = ink
      repaintAll()
    })
  })
  const opts = { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-accent'] }
  themeObserver.observe(document.documentElement, opts)
  if (document.body) themeObserver.observe(document.body, opts)
  watchDpr()
}

function useRepaint(fn) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    const call = () => ref.current()
    repaints.add(call)
    return () => repaints.delete(call)
  }, [])
}

/** Size a canvas to its CSS box at the device pixel ratio (capped at 2); returns the ratio. */
function fitCanvas(cv, w, h, scale) {
  const dpr = scale || Math.min(2, (typeof window !== 'undefined' && window.devicePixelRatio) || 1)
  const W = Math.max(1, Math.round(w * dpr))
  const H = Math.max(1, Math.round(h * dpr))
  if (cv.width !== W) cv.width = W
  if (cv.height !== H) cv.height = H
  return dpr
}

const inkOf = el => {
  try { return getComputedStyle(el).color } catch (e) { return '#0053fd' }
}

/** One short tween on requestAnimationFrame; returns its cancel. k goes 0 → 1 over `ms`, after `delay`. */
function tween(ms, step, done, delay = 0) {
  let raf = 0
  let t0 = 0
  const tick = now => {
    if (!t0) t0 = now + delay
    const k = now < t0 ? 0 : Math.min(1, (now - t0) / ms)
    step(k)
    if (k < 1) raf = requestAnimationFrame(tick)
    else if (done) done()
  }
  raf = requestAnimationFrame(tick)
  return () => cancelAnimationFrame(raf)
}

const easeOut = k => 1 - Math.pow(1 - k, 3)

// ---- bars: a faint dotted track, a dithered fill whose density grows with progress, solid at T3.
const BAR_CELL = 2
const BAR_ROWS = 6
const TRUST_DENSITY = 0.2

/**
 * fill: 0..1 · solid: draw the fill at full density · print: 0..1 Bayer threshold sweep (entrance) ·
 * crumble: { from, k } cells of the old fill beyond `fill` drop and fade · (the benchmark range has its own draw-in).
 */
function paintBar(cv, { fill, solid, trust = false, print = 1, crumble = null, rows = BAR_ROWS, headroom = 4, segments = 0, notch = null, width = 0, ink = null, scale = 0 }) {
  const w = width || cv.clientWidth || (cv.parentElement && cv.parentElement.clientWidth) || 0
  if (!w) return
  const h = rows * BAR_CELL + headroom
  const dpr = fitCanvas(cv, w, h, scale)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, w, h)
  x.fillStyle = ink || inkOf(cv)
  const cols = Math.floor(w / BAR_CELL)
  const dot = BAR_CELL - 0.5
  const density = solid ? 1 : 0.38 + 0.62 * clamp01(fill)
  const fade = Math.min(4, Math.max(1, cols * 0.02))
  const edgeOf = f => f * cols
  const value = (i, f, tr = trust) => {
    if (tr) return TRUST_DENSITY // trusted start: one even, light texture end to end, no edge, nothing earned
    if (solid && f >= 1) return 1
    const edge = edgeOf(f)
    const v = i < edge - fade ? density : i < edge ? density * ((edge - i) / fade) : 0
    return Math.max(v, 0.07)
  }
  // One segment per verified success the series needs (when each gets at least 3 cells), and a notch where the type
  // reaches T2.
  const per = segments > 0 ? cols / segments : 0
  const segW = per ? per * Math.max(1, Math.ceil(3 / per)) : 0           // a gap every k successes, k cells >= 3
  const gap = i => segW > 0 && i < cols - 1 && Math.floor((i + 1) / segW) !== Math.floor(i / segW)
  const nx = notch == null ? -9 : Math.min(cols - 1, Math.round(notch * cols))
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      if (i === nx) {
        x.globalAlpha = 1
        x.fillRect(i * BAR_CELL, j * BAR_CELL, dot, dot)
        continue
      }
      if (Math.abs(i - nx) === 1 || gap(i)) continue
      const th = bayer(i, j)
      if (th >= print) continue
      if (value(i, fill) > th) {
        x.globalAlpha = 1
        x.fillRect(i * BAR_CELL, j * BAR_CELL, dot, dot)
      } else if (crumble && value(i, crumble.from, !!crumble.trust) > th) {
        // A cell the fault took away: it drops a few pixels and fades, each with its own small delay.
        const r = ((i * 73 + j * 151) % 97) / 97
        const k = clamp01((crumble.k - r * 0.35) / 0.65)
        if (k >= 1) continue
        x.globalAlpha = 1 - k
        x.fillRect(i * BAR_CELL, j * BAR_CELL + k * k * headroom * (0.6 + r), dot, dot)
      }
    }
  }
  x.globalAlpha = 1
}

function useWidth(ref, onResize) {
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver !== 'function') return
    let last = el.clientWidth
    const ro = new ResizeObserver(() => {
      if (el.clientWidth !== last) {
        last = el.clientWidth
        onResize()
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
}

/**
 * A type's progress bar. change = { dir: 'up' | 'down', token } replays a promotion (fills toward the new value)
 * or a fault (the lost cells crumble, then the bar prints again at its lower value). First mount prints in.
 */
function DitherBar({ value, solid, track, trust, change, motion, delay = 0, rows = BAR_ROWS, className, segments = 0, notch = null }) {
  const ref = useRef(null)
  const st = useRef({ fill: null, solid: false, cancel: null, token: null, trust: false })
  const target = track ? 0 : trust ? 1 : solid ? 1 : clamp01(value || 0)
  const geo = { segments: track || solid || trust ? 0 : segments, notch: track || solid || trust ? null : notch }
  const draw = (fill, extra) => ref.current && paintBar(ref.current, { fill, solid: !!solid, trust: !!trust, rows, headroom: rows > 3 ? 4 : 2, ...geo, ...extra })
  useRepaint(() => draw(st.current.fill == null ? target : st.current.fill))
  useWidth(ref, () => draw(st.current.fill == null ? target : st.current.fill))
  const token = change ? change.token : null
  useEffect(() => {
    const s = st.current
    if (s.cancel) s.cancel()
    s.cancel = null
    const from = s.fill
    const wasTrust = s.trust
    const fresh = token && token !== s.token
    s.token = token
    s.fill = target
    s.trust = !!trust
    if (!motion) return draw(target)
    if (from == null) {
      // A. Entrance: the bar prints, threshold by threshold.
      draw(target, { print: 0 })
      s.cancel = tween(600, k => draw(target, { print: k }), null, delay)
    } else if (fresh && change.dir === 'down') {
      // D. Fault: the dots crumble, then the bar prints again at its new value.
      s.cancel = tween(520, k => draw(target, { crumble: { from, k, trust: wasTrust } }), () => {
        s.cancel = tween(380, k => draw(target, { print: k }))
      })
    } else if (fresh && change.dir === 'reprint') {
      // A drop without a fault (a revoke, stricter settings, a stakes change): the bar prints again, nothing crumbles.
      s.cancel = tween(420, k => draw(target, { print: k }))
    } else if (wasTrust !== !!trust) {
      // Into or out of the trusted texture: nothing grows, the bar prints again.
      s.cancel = tween(420, k => draw(target, { print: k }))
    } else if (from !== target) {
      // C. Promotion (or plain progress): the fill grows to its new value.
      s.cancel = tween(fresh ? 700 : 450, k => draw(from + (target - from) * easeOut(k)))
    } else draw(target)
    return () => {
      if (s.cancel) s.cancel()
    }
  }, [target, solid, track, trust, token, motion, segments, notch])
  return jsx('canvas', { 'aria-hidden': true, className: cn('tn-bar tn-mirror', className), ref })
}

// ---- the emblem: an original dithered sunburst; its density is the share of autonomy the agent earned.
// The passport can draw it as concentric rings or a square lattice instead (Settings, "Your passport"): the same
// density from the same share, laid out from a seed taken from the agent's id, so one agent's emblem never changes.
function emblemValue(dx, dy, rot, share, pattern = 'sunburst', seed = 0) {
  const r = Math.hypot(dx, dy)
  if (r > 1) return -1
  if (pattern === 'rings' || pattern === 'grid') {
    let w
    if (pattern === 'rings') {
      const wob = 0.035 * Math.cos((Math.atan2(dy, dx) + rot) * 3 + seed * 6.283)
      w = Math.pow((Math.cos((r + wob) * Math.PI * 2 * (6 + Math.floor(seed * 3)) + seed * 6.283) + 1) / 2, 2)
    } else {
      const ang = rot + seed * 1.571
      const c = Math.cos(ang), sn = Math.sin(ang)
      const u = (dx * c - dy * sn) / 0.19 + seed * 7, v = (dx * sn + dy * c) / 0.19 + seed * 3
      w = Math.max(Math.abs(u - Math.round(u)), Math.abs(v - Math.round(v))) < 0.3 ? 1 : 0.2
    }
    const core = pattern === 'rings' ? Math.max(0, 1 - r / 0.2) * (0.45 + 0.55 * share) : 0
    let v = Math.max(core * 1.15, w * (1.1 - r) * 1.25 * (0.18 + 0.82 * share), 0.16 * (1 - r))
    // Each pattern keeps a fixed mark of its own, as the sunburst keeps its inner circle: three thin rings, or a
    // square turned with the lattice. Only the dither around it says how much autonomy was earned.
    if (pattern === 'rings') {
      if (Math.abs(r - 0.3) < 0.02 || Math.abs(r - 0.55) < 0.02 || Math.abs(r - 0.78) < 0.02) v = 1
    } else {
      const ang = rot + seed * 1.571
      const q = Math.max(Math.abs(dx * Math.cos(ang) - dy * Math.sin(ang)), Math.abs(dx * Math.sin(ang) + dy * Math.cos(ang)))
      if (Math.abs(q - 0.4) < 0.022) v = 1
    }
    if (Math.abs(r - 0.97) < 0.02) v = 1
    return v
  }
  const a = Math.atan2(dy, dx) + rot
  const ray = Math.pow((Math.cos(a * 36) + 1) / 2, 2)
  const core = Math.max(0, 1 - r / 0.42) * (0.45 + 0.55 * share)
  let v = Math.max(core * 1.15, ray * (1.08 - r) * 1.25 * (0.18 + 0.82 * share), 0.16 * (1 - r))
  if (Math.abs(r - 0.47) < 0.025 || Math.abs(r - 0.97) < 0.02) v = 1
  return v
}

/**
 * crumble = { from, k }: the emblem as it was at share `from` loses cells (those the new share no longer lights, and
 * about a quarter of the others), which drop a few cells and fade as k goes 0 -> 1; the new state prints under them.
 */
function paintEmblem(cv, { size, n, share, develop = 1, rot = 0, crumble = null, ink = null, scale = 0, pattern = 'sunburst', seed = 0 }) {
  const dpr = fitCanvas(cv, size, size, scale)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, size, size)
  x.fillStyle = ink || inkOf(cv)
  const cell = size / n
  const dot = Math.max(0.6, cell - 0.6)
  const c = n / 2
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const th = bayer(i, j)
      const dx = (i - c + 0.5) / c, dy = (j - c + 0.5) / c
      if (crumble) {
        const was = emblemValue(dx, dy, rot, crumble.from, pattern, seed) > th
        const now = emblemValue(dx, dy, rot, share, pattern, seed) > th
        const r = ((i * 73 + j * 151) % 97) / 97
        const falls = was && (!now || r < 0.25)
        if (falls) {
          const k = clamp01((crumble.k - r * 0.4) / 0.6)
          if (k < 1) {
            x.globalAlpha = 1 - k
            x.fillRect(i * cell, j * cell + k * k * cell * 5 * (0.6 + r), dot, dot)
            x.globalAlpha = 1
          }
        }
        // Cells that stay are drawn; the new state's other cells print back in (develop) once the old ones fell.
        if (now && ((was && !falls) || th < develop)) x.fillRect(i * cell, j * cell, dot, dot)
        continue
      }
      if (th >= develop) continue
      if (emblemValue(dx, dy, rot, share, pattern, seed) > th) x.fillRect(i * cell, j * cell, dot, dot)
    }
  }
}

/**
 * The emblem. develops point by point on mount (B), can turn slowly (the passport), and pulses once when `pulse`
 * changes (C: density up, then back). The turning loop stops while the emblem is off screen or the window hidden.
 */
function Emblem({ share, size = 120, n = 60, rotate = false, hot = false, pulse = 0, crumble = 0, motion, className, label, pattern = 'sunburst', seed = 0 }) {
  const ref = useRef(null)
  const hotRef = useRef(hot)
  hotRef.current = hot                                    // hovered or focused: a pulse, then a faster turn
  const st = useRef({ raf: 0, dev0: 0, pulse0: 0, crumble0: 0, from: share, rot: 0, rot0: 0, visible: true, share, prev: share })
  st.current.prev = st.current.share                     // the share before this render: a crumble starts from it
  st.current.share = share
  const paint = (develop, boost, rot, crumbleAt) =>
    ref.current &&
    paintEmblem(ref.current, { size, n, share: clamp01(st.current.share + boost), develop, rot, pattern, seed, crumble: crumbleAt == null ? null : { from: st.current.from, k: crumbleAt } })
  useRepaint(() => paint(1, 0, st.current.rot))
  useEffect(() => {
    if (!st.current.raf) paint(1, 0, st.current.rot)
  }, [pattern, seed])
  const wake = () => {
    const s = st.current
    if (s.raf || !ref.current) return
    const tick = now => {
      s.raf = 0
      if (!s.dev0) s.dev0 = now
      const develop = Math.min(1, (now - s.dev0) / 1400)
      const pk = s.pulse0 ? (now - s.pulse0) / 900 : 1
      const boost = pk < 1 ? Math.sin(Math.PI * pk) * 0.35 : 0
      if (pk >= 1) s.pulse0 = 0
      // D. A real drop: the cells it lost crumble (~600 ms), then the new state prints back in (~500 ms).
      let ck = null
      let cdev = 1
      if (s.crumble0) {
        ck = Math.min(1, (now - s.crumble0) / 600)
        cdev = clamp01((now - s.crumble0 - 450) / 500)
        if (ck >= 1 && cdev >= 1) {
          s.crumble0 = 0
          ck = null
        }
      }
      const turning = (rotate || hotRef.current) && develop >= 1 && s.visible && !(typeof document !== 'undefined' && document.hidden)
      if (turning) {
        const speed = hotRef.current ? 0.0009 : 0.00006 // ~0.9 rad/s hovered, ~0.06 rad/s at rest
        if (s.speed !== speed) {
          s.speed = speed
          s.rot0 = 0
        }
        if (!s.rot0) s.rot0 = now - s.rot / speed
        s.rot = (now - s.rot0) * speed
      } else s.rot0 = 0
      // The slow turn alone needs no more than ~14 frames a second; developing and pulsing paint every frame.
      const idle = develop >= 1 && !s.pulse0 && !s.crumble0 && !hotRef.current
      if (!idle || now - (s.last || 0) >= 70) {
        s.last = now
        paint(ck == null ? develop : cdev, boost, s.rot, ck)
      }
      if (develop < 1 || s.pulse0 || s.crumble0 || turning) s.raf = requestAnimationFrame(tick)
    }
    s.raf = requestAnimationFrame(tick)
  }
  useEffect(() => {
    const s = st.current
    if (!motion) {
      paint(1, 0, s.rot)
      return
    }
    s.dev0 = 0
    wake()
    let io = null
    if (rotate && typeof IntersectionObserver === 'function' && ref.current) {
      io = new IntersectionObserver(entries => {
        s.visible = entries.some(e => e.isIntersecting)
        if (s.visible) wake()
      })
      io.observe(ref.current)
    }
    const onVis = () => {
      if (!document.hidden) wake()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelAnimationFrame(s.raf)
      s.raf = 0
      if (io) io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [motion, rotate])
  useEffect(() => {
    if (!motion) return paint(1, 0, st.current.rot)
    if (!st.current.dev0) return
    wake()
  }, [share])
  useEffect(() => {
    if (!pulse || !motion) return
    st.current.pulse0 = performance.now()
    wake()
  }, [pulse])
  useEffect(() => {
    if (!hot || !motion) return
    st.current.pulse0 = performance.now()
    wake()
  }, [hot])
  useEffect(() => {
    if (!crumble || !motion) return
    const s = st.current
    s.from = s.prev
    s.pulse0 = 0
    s.crumble0 = performance.now()
    wake()
  }, [crumble])
  return jsx('canvas', {
    'aria-hidden': label ? undefined : true,
    'aria-label': label,
    className: cn('tn-emblem', className),
    ref,
    role: label ? 'img' : undefined,
    style: { width: size, height: size }
  })
}

const shareOf = agent => {
  const types = agent.types || []
  if (!types.length) return 0
  let s = 0
  // A trusted type counts for nothing: the emblem's density is earned autonomy only.
  for (const ty of types) s += tierKey(ty) === 'alone' ? 1 : tierKey(ty) === 'notify' ? 0.5 : 0
  return s / types.length
}

// ---- a seal that prints at the end of a passport that verifies.
function paintSeal(cv, { size, print = 1, ink = null, scale = 0 }) {
  const dpr = fitCanvas(cv, size, size, scale)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, size, size)
  x.fillStyle = ink || inkOf(cv)
  const n = 24
  const cell = size / n
  const c = n / 2
  const seg = (px, py, ax, ay, bx, by) => {
    const vx = bx - ax, vy = by - ay
    const k = clamp01(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy))
    return Math.hypot(px - ax - k * vx, py - ay - k * vy)
  }
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const th = bayer(i, j)
      if (th >= print) continue
      const dx = (i - c + 0.5) / c, dy = (j - c + 0.5) / c
      const r = Math.hypot(dx, dy)
      if (r > 1) continue
      const check = Math.min(seg(dx, dy, -0.42, 0.02, -0.12, 0.34), seg(dx, dy, -0.12, 0.34, 0.45, -0.3)) < 0.11
      const v = r > 0.84 ? 1 : r > 0.72 ? 0 : check ? 1 : 0.22
      if (v > th) x.fillRect(i * cell, j * cell, cell - 0.5, cell - 0.5)
    }
  }
}

// ---- benchmark range: a dotted axis from 0 to the scale shared by the type's ranked models, the 95 % range as a
// segment from its low to its high end, the observed rate as a dot; draws in from the start (F).
function paintRange(cv, { rate, low, high, max, reveal = 1 }) {
  const w = cv.clientWidth || 120
  const rows = 5
  const h = rows * BAR_CELL
  const dpr = fitCanvas(cv, w, h)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, w, h)
  x.fillStyle = inkOf(cv)
  const cols = Math.floor(w / BAR_CELL)
  const at = v => Math.min(cols - 1, Math.round(((cols - 1) * v) / (max || 1)))
  const lo = at(low), hi = Math.max(at(high), lo + 1), rt = at(rate)
  const edge = reveal * (cols + 6)
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      let v = j === 2 ? 0.2 : 0
      if (i >= lo && i <= hi && j >= 1 && j <= 3) v = j === 2 ? 1 : 0.5
      if (Math.abs(i - rt) <= 1) v = 1
      const fade = i < edge - 6 ? 1 : i < edge ? (edge - i) / 6 : 0
      if (v * fade > bayer(i, j)) x.fillRect(i * BAR_CELL, j * BAR_CELL, BAR_CELL - 0.5, BAR_CELL - 0.5)
    }
  }
}

function RangeBar({ rate, low, high, max, motion, delay = 0 }) {
  const ref = useRef(null)
  const draw = reveal => ref.current && paintRange(ref.current, { rate, low, high, max, reveal })
  useRepaint(() => draw(1))
  useWidth(ref, () => draw(1))
  useEffect(() => {
    if (!motion) return draw(1)
    draw(0)
    return tween(560, k => draw(easeOut(k)), null, delay)
  }, [rate, low, high, max, motion])
  return jsx('canvas', { 'aria-hidden': true, className: 'tn-range tn-mirror', ref })
}

// ---- styles, injected once (Tailwind arbitrary classes are not compiled for plugins loaded from disk).
function bayerMask(level) {
  let cells = ''
  for (let j = 0; j < 4; j++) for (let i = 0; i < 4; i++) if (BAYER[j][i] < level) cells += `<rect x='${i * 2}' y='${j * 2}' width='2' height='2'/>`
  return `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'>${cells}</svg>`)}")`
}

const MASKS = [16, 12, 8, 4, 0].map(bayerMask)
const maskFrame = (pct, m) => `${pct}%{-webkit-mask-image:${m};mask-image:${m}}`

const CSS = `
.tn-root{--tn-acc:var(--ui-accent,var(--color-primary,#0053fd));--tn-on:var(--dt-midground-foreground,var(--dt-primary-foreground,#fcfcfc));
  --tn-fg:var(--ui-text-primary,currentColor);--tn-fg2:var(--ui-text-secondary,currentColor);--tn-mut:color-mix(in srgb,var(--tn-fg) 66%,transparent);
  --tn-acc-text:color-mix(in srgb,var(--tn-acc) 80%,var(--tn-fg));--tn-line:color-mix(in srgb,var(--tn-fg) 13%,transparent);
  --tn-mono:'JetBrains Mono',var(--font-mono,ui-monospace),monospace;--tn-display:'Collapse',var(--font-sans,system-ui),sans-serif}
.tn-root canvas{display:block}
.tn-probe{position:fixed;inset-block-start:0;inset-inline-start:0;width:0;height:0;overflow:hidden;pointer-events:none;color:var(--tn-acc);background:var(--tn-fg)}
.tn-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.tn-detail{width:100%;max-width:58rem}
.tn-bdi{unicode-bidi:isolate;direction:ltr}
.tn-eyebrow{font:500 0.7rem/1.4 var(--tn-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--tn-acc-text)}
.tn-eyebrow .tn-dim{color:var(--tn-mut)}
.tn-section{display:flex;flex-direction:column;gap:0.5rem}
.tn-section-head{display:flex;align-items:center;justify-content:space-between;gap:0.5rem;min-height:1.5rem}
.tn-hero{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:1rem 1.5rem;padding-block:0.25rem 0.75rem;border-block-end:1px solid var(--tn-line)}
.tn-hero-main{min-width:0;flex:1 1 18rem;display:flex;flex-direction:column;gap:0.35rem}
.tn-name{font-family:var(--tn-display);font-weight:700;font-size:clamp(2rem,4.4vw,3.4rem);line-height:0.92;letter-spacing:-0.01em;color:var(--tn-fg);margin:0.15rem 0 0.2rem;overflow-wrap:anywhere}
.tn-pills{display:flex;flex-wrap:wrap;align-items:center;gap:0.375rem}
.tn-stats{display:flex;flex-wrap:wrap;gap:0.35rem 1.25rem;margin-block-start:0.35rem}
.tn-stat{display:flex;align-items:baseline;gap:0.35rem;font-size:0.72rem;color:var(--tn-mut)}
.tn-stat b{font:400 0.95rem var(--tn-mono);color:var(--tn-fg);font-variant-numeric:tabular-nums}
.tn-preset{font-size:0.7rem;color:var(--tn-mut)}
.tn-preset span:first-child{font-family:var(--tn-mono);text-transform:uppercase;letter-spacing:0.1em;font-size:0.6rem;margin-inline-end:0.4rem}
.tn-hero-side{display:flex;flex-direction:column;align-items:center;gap:0.25rem;flex:none}
.tn-hero-side .tn-emblem{color:var(--tn-acc)}
.tn-emblem-cap{font:0.66rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;color:var(--tn-mut);text-align:center;max-width:11rem}
.tn-chip{display:inline-flex;align-items:center;font-family:var(--tn-display);font-weight:700;font-size:0.72rem;letter-spacing:0.08em;line-height:1;padding:0.2rem 0.35rem 0.15rem;border:1px solid var(--tn-acc);color:var(--tn-acc-text);white-space:nowrap}
.tn-chip[data-tier=alone]{background:var(--tn-acc);color:var(--tn-on)}
.tn-chip[data-tier=cap]{border-style:dashed;border-color:var(--tn-mut);color:var(--tn-mut)}
.tn-chip[data-tier=trusted]{border-style:dotted;color:var(--tn-fg2);background-image:radial-gradient(color-mix(in srgb,var(--tn-acc) 38%,transparent) 0.6px,transparent 0.9px);background-size:3px 3px}
.tn-tname[data-tier=trusted]{font-weight:400;color:var(--tn-fg2)}
.tn-trust-note{margin:0.15rem 0 0;font-size:0.72rem;line-height:1.5;color:var(--tn-mut)}
.tn-start{display:inline-flex;align-items:center;gap:0.35rem;outline:none;cursor:help}
.tn-start i{font-style:normal;display:inline-block;width:0.55rem;height:0.55rem;border:1px dotted var(--tn-acc);background-image:radial-gradient(color-mix(in srgb,var(--tn-acc) 45%,transparent) 0.6px,transparent 0.9px);background-size:3px 3px}
.tn-start[data-start=probation] i{border-style:solid;background:none}
.tn-start:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-chip-wrap{position:relative;display:inline-flex;outline:none}
.tn-chip-wrap:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-chip-ghost{position:absolute;inset-block-start:0;inset-inline-start:0;pointer-events:none}
.tn-chip.tn-out{animation:tn-dissolve 520ms steps(1,end) forwards}
.tn-chip.tn-in{animation:tn-print 520ms steps(1,end) both}
@keyframes tn-dissolve{${maskFrame(0, MASKS[0])}${maskFrame(25, MASKS[1])}${maskFrame(50, MASKS[2])}${maskFrame(75, MASKS[3])}${maskFrame(100, MASKS[4])}}
@keyframes tn-print{${maskFrame(0, MASKS[4])}${maskFrame(25, MASKS[3])}${maskFrame(50, MASKS[2])}${maskFrame(75, MASKS[1])}${maskFrame(100, MASKS[0])}}
.tn-rows{display:flex;flex-direction:column}
.tn-trow{position:relative;display:grid;grid-template-columns:2.6rem minmax(0,1fr);gap:0.6rem;padding-block:0.85rem;border-block-end:1px solid var(--tn-line)}
.tn-trow:first-child{border-block-start:1px solid var(--tn-line)}
.tn-tnum{font:0.68rem var(--tn-mono);color:var(--tn-acc-text);padding-block-start:0.2rem;font-variant-numeric:tabular-nums}
.tn-tl{display:flex;flex-wrap:wrap;align-items:baseline;gap:0.3rem 0.6rem;margin-block-end:0.45rem}
.tn-tk{font:0.85rem var(--tn-mono);color:var(--tn-fg);overflow-wrap:anywhere}
.tn-tname{font-family:var(--tn-display);font-weight:700;font-size:1.05rem;line-height:1;color:var(--tn-fg)}
.tn-tstakes{font-size:0.7rem;color:var(--tn-mut);margin-inline-start:auto}
.tn-bar{width:100%;height:16px;color:var(--tn-acc)}
.tn-tbar{position:relative;display:flex;align-items:center;gap:0.75rem}
.tn-tbar .tn-bar{flex:1 1 auto;min-width:0}
.tn-count{flex:none;font:500 0.8rem var(--tn-mono);color:var(--tn-fg);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.tn-count i{font-style:normal;color:var(--tn-mut)}
.tn-flag{display:inline-flex;align-items:center;height:1.2rem;padding:0 0.4rem;font:500 0.66rem var(--tn-mono);letter-spacing:0.04em;color:var(--tn-acc-text);border:1px dotted var(--tn-acc);white-space:nowrap;outline:none}
.tn-flag[data-kind=fault]{border-style:solid}
.tn-flag:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-status{display:flex;align-items:flex-start;gap:0.4rem;padding:0.5rem 0.6rem;font-size:0.72rem;line-height:1.5;border:1px solid var(--tn-line);color:var(--tn-fg2)}
.tn-status[data-ok=true]{color:var(--tn-acc-text);border-color:color-mix(in srgb,var(--tn-acc) 40%,transparent)}
.tn-status[data-ok=false]{border-color:var(--tn-acc);color:var(--tn-fg)}
.tn-note{margin:0;font-size:0.72rem;line-height:1.5;color:var(--tn-fg2);border-inline-start:2px dotted var(--tn-acc);padding-inline-start:0.6rem}
.tn-tnext{margin:0.3rem 0 0;font-size:0.74rem;line-height:1.5;color:var(--tn-fg2)}
.tn-tnext .tn-g{font:0.68rem var(--tn-mono);color:var(--tn-mut);font-variant-numeric:tabular-nums}
.tn-tguar{margin:0.15rem 0 0;font-size:0.72rem;line-height:1.5;color:var(--tn-fg2);width:fit-content;outline:none;cursor:help}
.tn-tguar:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-mirror:dir(rtl){transform:scaleX(-1)}
.tn-enter{animation:tn-enter 380ms cubic-bezier(.2,.7,.2,1) both}
@keyframes tn-enter{from{opacity:0;transform:translateY(4px)}}
.tn-scan{position:absolute;inset-block:0;inset-inline-start:0;width:1px;background:var(--tn-acc);pointer-events:none;opacity:0;animation:tn-scan 900ms cubic-bezier(.4,0,.2,1) 1}
@keyframes tn-scan{0%{inset-inline-start:0;opacity:0}10%{opacity:1}90%{opacity:1}100%{inset-inline-start:100%;opacity:0}}
.tn-band{position:relative;overflow:hidden;background:var(--tn-acc);color:var(--tn-on)}
.tn-band-in{padding:1.1rem 1.25rem 0.25rem;position:relative;z-index:1}
.tn-band .tn-eyebrow{color:var(--tn-on);opacity:0.85}
.tn-band-title{font-family:var(--tn-display);font-weight:700;font-size:clamp(2.2rem,5vw,3.6rem);line-height:0.9;margin:0.35rem 0 0.45rem;clip-path:inset(0 0 0 0)}
.tn-band-sub{font:0.7rem/1.5 var(--tn-mono);opacity:0.9;max-width:34rem}
.tn-band canvas{width:100%;height:44px;color:var(--tn-on)}
.tn-band[data-motion=on] .tn-band-title{animation:tn-wipe 900ms cubic-bezier(.2,.7,.2,1) both 120ms}
.tn-band[data-motion=on] .tn-band-title:dir(rtl){animation-name:tn-wipe-rtl}
@keyframes tn-wipe{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes tn-wipe-rtl{from{clip-path:inset(0 0 0 100%)}to{clip-path:inset(0 0 0 0)}}
.tn-band-close{position:absolute;inset-block-start:0.5rem;inset-inline-end:0.5rem;z-index:2;display:grid;place-items:center;width:1.5rem;height:1.5rem;border:0;background:transparent;color:inherit;cursor:pointer;opacity:0.8}
.tn-band-close:hover{opacity:1}
.tn-band-close:focus-visible{outline:1px solid currentColor;outline-offset:1px}
.tn-fault{position:relative;border:1px solid var(--tn-line);padding:1rem 1.25rem}
.tn-fault .tn-band-title{color:var(--tn-fg);font-size:clamp(1.8rem,4vw,2.8rem)}
.tn-fault .tn-band-sub{color:var(--tn-fg2);font-family:inherit;font-size:0.78rem}
.tn-fault .tn-band-close{color:var(--tn-mut)}
.tn-leaving{animation:tn-leave 280ms ease forwards}
@keyframes tn-leave{to{opacity:0;transform:translateY(-4px)}}
.tn-intro{margin:0 1rem 0.75rem;max-width:calc(58rem + 17rem);display:flex;align-items:flex-start;gap:0.75rem;padding:0.7rem 0.85rem;border:1px solid var(--tn-line)}
.tn-intro p{margin:0}
.tn-intro-body{font-size:0.74rem;line-height:1.55;color:var(--tn-fg2);max-width:48rem}
.tn-pass-wrap{perspective:1400px;width:100%;max-width:46rem;container-type:inline-size}
.tn-pass-grid{display:flex;flex-direction:column;gap:0.9rem}
.tn-pass-side{display:flex;flex-direction:column;gap:0.75rem;min-width:0;max-width:46rem}
.tn-pass-acts{display:flex;flex-wrap:wrap;gap:0.5rem}
.tn-pass-acts > p{flex-basis:100%}
.tn-pass-types{display:flex;flex-direction:column;gap:0.5rem;margin-block-start:1.25rem}
.tn-pass{position:relative;overflow:hidden;background:var(--tn-acc);color:var(--tn-on);padding:clamp(1.1rem,4.4cqi,2.1rem) clamp(1.1rem,5cqi,2.4rem) clamp(1rem,4cqi,1.8rem);transform-style:preserve-3d;transition:transform 400ms cubic-bezier(.2,.7,.2,1);will-change:transform}
.tn-pass.tn-tilting{transition:transform 80ms linear}
.tn-ptop{display:flex;justify-content:space-between;gap:0.5rem;font:500 clamp(0.62rem,1.5cqi,0.74rem) var(--tn-mono);letter-spacing:0.14em;text-transform:uppercase}
.tn-ok{opacity:0;transition:opacity 400ms}
.tn-ok.tn-on{opacity:1}
.tn-pemb{display:grid;place-items:center;margin:clamp(0.8rem,3cqi,1.4rem) 0 0.2rem}
.tn-pemb .tn-emblem{color:var(--tn-on)}
.tn-pname{font-family:var(--tn-display);font-weight:700;font-size:clamp(2.4rem,13cqi,6.2rem);line-height:0.9;letter-spacing:-0.01em;text-align:center;margin:0.35rem 0 clamp(0.8rem,3cqi,1.3rem);min-height:0.9em;overflow-wrap:anywhere}
.tn-prows{border-block-start:1px solid color-mix(in srgb,var(--tn-on) 35%,transparent);padding-block-start:0.75rem;display:flex;flex-direction:column;gap:0.6rem}
.tn-prow{display:grid;grid-template-columns:2rem minmax(0,1fr) minmax(5rem,11rem) 3.4rem;gap:0.15rem 0.9rem;align-items:center;font:0.8rem var(--tn-mono)}
.tn-pnum{opacity:0.7;font-size:0.72rem;font-variant-numeric:tabular-nums}
.tn-pmore{margin-block-start:0.5rem;font:0.7rem var(--tn-mono);opacity:0.8}
@container (max-width:30rem){.tn-prow{grid-template-columns:1.5rem minmax(0,1fr) 4.5rem 2.6rem;gap:0.1rem 0.6rem;font-size:0.68rem}.tn-pnum{font-size:0.62rem}}
.tn-prow[data-motion=on]{opacity:0;transform:translateY(4px);transition:opacity 400ms,transform 400ms}
.tn-prow.tn-on{opacity:1;transform:none}
.tn-prow .tn-pk{min-width:0;display:flex;flex-wrap:wrap;align-items:baseline;column-gap:0.7rem;overflow:hidden}
.tn-prow .tn-pk>.tn-bdi{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.tn-prow b{font-family:var(--tn-display);font-weight:700;letter-spacing:0.06em;text-transform:uppercase;unicode-bidi:isolate;white-space:nowrap}
.tn-prow b[data-tier=trusted]{font-weight:400;opacity:0.85}
.tn-prow .tn-pn{direction:ltr;unicode-bidi:isolate;text-align:end;font-variant-numeric:tabular-nums}
.tn-prow .tn-bar{height:10px;color:var(--tn-on)}
.tn-pfoot{display:flex;justify-content:space-between;flex-wrap:wrap;gap:0.25rem 0.75rem;margin-block-start:1rem;padding-block-start:0.75rem;border-block-start:1px solid color-mix(in srgb,var(--tn-on) 35%,transparent);font:500 clamp(0.58rem,1.4cqi,0.68rem) var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase}
.tn-hash{font-family:var(--tn-mono);text-transform:none;letter-spacing:0.06em}
.tn-psig{display:flex;align-items:center;gap:0.5rem;margin-block-start:0.85rem;font:clamp(0.56rem,1.3cqi,0.64rem) var(--tn-mono);letter-spacing:0.12em;opacity:0.85}
.tn-psig b{font-family:var(--tn-display);font-weight:700;letter-spacing:0.12em}
.tn-psig .tn-emblem{color:var(--tn-on)}
.tn-seal{position:absolute;inset-block-start:clamp(2.6rem,9cqi,3.8rem);inset-inline-end:clamp(0.9rem,4cqi,2rem);width:64px;height:64px;color:var(--tn-on);transform:rotate(-10deg);opacity:0.92}
.tn-sweep{position:absolute;inset-inline:0;height:46px;inset-block-start:-60px;background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--tn-on) 16%,transparent),transparent);pointer-events:none}
.tn-glare{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity 300ms;
  background:linear-gradient(105deg,transparent 38%,color-mix(in srgb,var(--tn-on) 34%,transparent) 50%,transparent 62%);background-size:260% 100%;
  background-position:calc(50% - var(--tn-gx,0) * 120%) 0;-webkit-mask-image:${MASKS[2]};mask-image:${MASKS[2]};-webkit-mask-size:8px 8px;mask-size:8px 8px}
.tn-pass[data-motion=on]:hover .tn-glare{opacity:1}
.tn-pass[data-card=ink]{--tn-on:#ecebe6;background:#121316;box-shadow:inset 0 0 0 1px rgba(236,235,230,0.14)}
.tn-pass[data-card=ink] :is(.tn-pemb .tn-emblem,.tn-psig .tn-emblem,.tn-seal,.tn-ok){color:color-mix(in srgb,var(--tn-acc) 72%,#fff)}
.tn-pass[data-card=paper]{--tn-on:#17181b;background:#f3f1ea;box-shadow:inset 0 0 0 1px rgba(23,24,27,0.12)}
.tn-pass[data-anim=holographic]:not(.tn-tilting){animation:tn-holo-tilt 9s ease-in-out infinite}
@keyframes tn-holo-tilt{0%,100%{transform:rotateX(1.2deg) rotateY(-2.5deg)}50%{transform:rotateX(-1.2deg) rotateY(2.5deg)}}
.tn-holo{position:absolute;inset:0;pointer-events:none;background:linear-gradient(110deg,transparent 40%,color-mix(in srgb,var(--tn-on) 26%,transparent) 50%,transparent 60%);background-size:320% 100%;animation:tn-holo-shimmer 7s linear infinite;-webkit-mask-image:${MASKS[2]};mask-image:${MASKS[2]};-webkit-mask-size:8px 8px;mask-size:8px 8px}
@keyframes tn-holo-shimmer{from{background-position:100% 0}to{background-position:0 0}}
.tn-pass[data-anim=scan]{animation:tn-scan-print 1.8s steps(40,end) both}
@keyframes tn-scan-print{from{clip-path:inset(0 0 100% 0)}to{clip-path:inset(0 0 0 0)}}
.tn-scanline{position:absolute;inset-inline:0;height:3px;inset-block-start:0;background:var(--tn-on);pointer-events:none;animation:tn-scan-line 1.8s steps(40,end) both}
@keyframes tn-scan-line{from{inset-block-start:0;opacity:1}96%{opacity:1}to{inset-block-start:calc(100% - 3px);opacity:0}}
.tn-pstyle{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,22rem);gap:1rem 1.5rem;align-items:start}
@container (max-width:44rem){.tn-pstyle{grid-template-columns:minmax(0,1fr)}}
.tn-pstyle-ctl{display:flex;flex-direction:column;gap:0.5rem}
.tn-pstyle-row{display:flex;flex-direction:column;gap:0.3rem;margin-block-start:0.35rem}
.tn-pstyle-preview .tn-pass-wrap{max-width:22rem}
.tn-ext{display:inline-flex;align-items:center;gap:0.25rem;color:var(--tn-acc-text);text-decoration:underline;text-underline-offset:3px}
.tn-ext:hover{color:var(--tn-fg)}
.tn-linkbtn{display:inline-flex;align-items:center;gap:0.35rem;padding:0.3rem 0.2rem;border:0;background:transparent;color:var(--tn-acc-text);font:500 0.66rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;text-decoration:underline;text-underline-offset:3px;cursor:pointer}
.tn-linkbtn:hover{color:var(--tn-fg)}
.tn-chip.tn-out,.tn-chip.tn-in{-webkit-mask-size:8px 8px;mask-size:8px 8px}
.tn-range{width:100%;height:10px;color:var(--tn-acc)}
.tn-btn{display:inline-flex;align-items:center;gap:0.45rem;min-height:2rem;padding:0.3rem 0.9rem;font:500 0.66rem/1.2 var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;border:1px solid var(--tn-acc);border-radius:0;background:transparent;color:var(--tn-acc-text);cursor:pointer;outline:none;transition:background 120ms,color 120ms}
.tn-btn:hover:not(:disabled){background:color-mix(in srgb,var(--tn-acc) 10%,transparent)}
.tn-btn[data-kind=primary]{background:var(--tn-acc);color:var(--tn-on)}
.tn-btn[data-kind=primary]:hover:not(:disabled){background:color-mix(in srgb,var(--tn-acc) 88%,var(--tn-fg))}
.tn-btn:disabled{opacity:0.5;cursor:default}
.tn-btn:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-cmd{display:flex;align-items:flex-start;gap:0.25rem;min-width:0}
.tn-hint{margin:0;font-size:0.7rem;line-height:1.5;color:var(--tn-mut)}
.tn-verify{display:flex;flex-direction:column;gap:0.35rem}
.tn-verdict-title{display:block;font-weight:600;color:var(--tn-fg)}
.tn-verdict[data-tone=ok] .tn-verdict-title{color:var(--tn-acc-text)}
.tn-verdict-lines{margin:0.2rem 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:0.1rem}
.tn-verdict-lines li::before{content:'· ';color:var(--tn-mut)}
.tn-doc-wrap{min-height:0;flex:1 1 auto;overflow-y:auto}
.tn-doc{display:flex;flex-direction:column;gap:0;max-width:58rem;padding:0.25rem 1rem 2.5rem}
.tn-doc>.tn-hero{margin-block-end:0.25rem}
.tn-hrow{display:grid;grid-template-columns:2.6rem minmax(0,1fr);gap:0.6rem;padding-block:1.1rem;border-block-end:1px solid var(--tn-line)}
.tn-hbody{min-width:0;display:flex;flex-direction:column;gap:0.6rem}
.tn-htitle{margin:0;font-family:var(--tn-display);font-weight:700;font-size:1.35rem;line-height:1;color:var(--tn-fg)}
.tn-htext{margin:0;font-size:0.78rem;line-height:1.6;color:var(--tn-fg2);max-width:46rem}
.tn-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:0.4rem;max-width:46rem}
.tn-list li{position:relative;padding-inline-start:1.1rem;font-size:0.78rem;line-height:1.55;color:var(--tn-fg2)}
.tn-list li::before{content:'';position:absolute;inset-inline-start:0.15rem;inset-block-start:0.5em;width:0.45rem;height:0.45rem;background-image:radial-gradient(var(--tn-acc) 0.7px,transparent 1px);background-size:3px 3px}
.tn-opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:0.6rem}
.tn-opt{display:flex;flex-direction:column;gap:0.55rem;padding:0.85rem 0.95rem;border:1px solid var(--tn-line);min-width:0}
.tn-opt[data-current=true]{border-color:var(--tn-acc);box-shadow:inset 0 2px 0 var(--tn-acc)}
.tn-opt-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:0.4rem}
.tn-opt-name{font-family:var(--tn-display);font-weight:700;font-size:1.3rem;line-height:1;color:var(--tn-fg)}
.tn-opt-name.tn-start{cursor:default;font-size:1.05rem}
.tn-chip-in{background:var(--tn-acc);color:var(--tn-on);font-family:var(--tn-mono);font-weight:500;font-size:0.58rem;letter-spacing:0.12em;text-transform:uppercase}
.tn-levels{margin:0;display:flex;flex-direction:column}
.tn-levels>div{display:grid;grid-template-columns:max-content minmax(0,1fr);text-align:end;align-items:baseline;gap:0.1rem 0.75rem;padding-block:0.4rem;border-block-start:1px solid var(--tn-line);font-size:0.72rem}
.tn-levels dt{color:var(--tn-mut);text-align:start}
.tn-levels dd{margin:0;display:contents;color:var(--tn-fg2);text-align:end}
.tn-levels dd>b{font:500 0.76rem var(--tn-mono);color:var(--tn-fg);text-align:end;font-variant-numeric:tabular-nums}
.tn-levels dd>span{grid-column:1 / -1;font-size:0.68rem;color:var(--tn-mut);text-align:start}
.tn-opt>.tn-cmd{margin-block-start:auto}
.tn-tiers{display:flex;flex-direction:column}
.tn-ctl{display:flex;flex-direction:column;gap:0.6rem}
.tn-btn.tn-btn-sm{min-height:1.5rem;padding:0.15rem 0.6rem;font-size:0.6rem}
.tn-seg{display:inline-flex;flex-wrap:wrap}
.tn-seg button{min-height:1.75rem;padding:0.2rem 0.75rem;font:500 0.68rem var(--tn-mono);border:1px solid var(--tn-line);margin-inline-start:-1px;background:transparent;color:var(--tn-fg2);cursor:pointer;outline:none}
.tn-seg button:first-child{margin-inline-start:0}
.tn-seg button[aria-pressed=true]{background:var(--tn-acc);border-color:var(--tn-acc);color:var(--tn-on);position:relative}
.tn-seg button:hover:not(:disabled):not([aria-pressed=true]){border-color:var(--tn-acc);color:var(--tn-acc-text);position:relative}
.tn-seg button:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent);position:relative}
.tn-seg button:disabled{cursor:default;opacity:0.6}
.tn-row-end{display:flex;flex-wrap:wrap;align-items:center;gap:0.5rem 0.75rem}
.tn-save{margin:0;display:flex;align-items:center;gap:0.4rem;font-size:0.72rem;color:var(--tn-fg2)}
.tn-save[data-state=saved]{color:var(--tn-acc-text)}
.tn-save[data-state=error],.tn-save[data-state=nowriter]{color:var(--tn-fg)}
.tn-or{display:flex;flex-direction:column;gap:0.25rem;opacity:0.8}
.tn-or[data-strong=true]{opacity:1}
.tn-or-list{display:flex;flex-direction:column;gap:0.4rem}
.tn-risk-ctl{grid-column:1 / -1;display:flex;flex-wrap:wrap;align-items:center;gap:0.4rem 1rem}
.tn-risk-k{display:inline-flex;align-items:center;gap:0.35rem;font-size:0.72rem;color:var(--tn-mut)}
.tn-risk-k input{width:4.5rem;height:1.75rem;padding:0 0.45rem;font:0.75rem var(--tn-mono);background:transparent;color:var(--tn-fg);border:1px solid var(--tn-line);border-radius:0;outline:none}
.tn-risk-k input:focus-visible{border-color:var(--tn-acc)}
.tn-risk-k input[aria-invalid=true]{border-color:var(--tn-fg)}
.tn-risk-k input:disabled{opacity:0.4}
.tn-htext[data-warn=true]{color:var(--tn-fg);border-inline-start:2px solid var(--tn-acc);padding-inline-start:0.5rem}
.tn-pre{margin:0;padding:0.6rem 0.75rem;overflow-x:auto;font:0.72rem/1.55 var(--tn-mono);color:var(--tn-fg);background:color-mix(in srgb,var(--tn-fg) 5%,transparent);border:1px solid var(--tn-line);direction:ltr;text-align:start}
.tn-tier{display:flex;flex-wrap:wrap;align-items:baseline;gap:0.3rem 0.7rem;padding-block:0.5rem;border-block-start:1px solid var(--tn-line)}
.tn-tier:last-child{border-block-end:1px solid var(--tn-line)}
.tn-brow{position:relative;border-block-end:1px solid var(--tn-line)}
.tn-urow{display:flex;align-items:center;gap:0.6rem;padding:0.4rem 0.25rem;font-size:0.78rem;border-block-end:1px solid var(--tn-line)}
.tn-urow:hover{background:var(--ui-row-hover-background,color-mix(in srgb,var(--tn-fg) 5%,transparent))}
.tn-urow.tn-sub{padding-inline-start:1.6rem}
.tn-uicon{flex:none;display:inline-flex;color:var(--tn-mut);outline:none}
.tn-uicon:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-uname{min-width:0;flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--tn-fg)}
.tn-uname .tn-mono{font-family:var(--tn-mono)}
.tn-uname .tn-dim{color:var(--tn-mut);font-size:0.7rem;margin-inline-start:0.5rem}
.tn-uacts{flex:none;display:flex;align-items:center;gap:0.25rem;opacity:0;transition:opacity 120ms}
.tn-urow:hover .tn-uacts,.tn-urow:focus-within .tn-uacts{opacity:1}
.tn-uago{flex:none;min-width:5.5rem;text-align:end;font-size:0.72rem;color:var(--tn-fg2);font-variant-numeric:tabular-nums}
.tn-ugroup{display:flex;align-items:center;gap:0.4rem;min-width:0;flex:1 1 auto;border:0;background:transparent;color:inherit;font:inherit;cursor:pointer;padding:0;text-align:start}
.tn-ugroup:focus-visible{outline:1px solid var(--tn-acc);outline-offset:2px}
.tn-ugroup b{font:600 0.78rem var(--tn-mono);color:var(--tn-acc-text);font-variant-numeric:tabular-nums}
.tn-head{display:flex;flex-direction:column;gap:0.5rem;padding:0.6rem 1rem 0.5rem}
.tn-head-row{display:flex;flex-wrap:wrap;align-items:center;gap:0.5rem 0.75rem}
.tn-head-ctl{display:flex;flex-wrap:wrap;align-items:center;gap:0.5rem 1rem}
.tn-bench{display:grid;grid-template-columns:2rem minmax(9rem,1fr) 7rem minmax(7rem,10rem) 8.5rem;align-items:center;gap:0.25rem 0.75rem;padding:0.5rem 0.25rem;font-size:0.78rem;border-block-end:1px solid var(--tn-line)}
.tn-bench[data-pub=true]{grid-template-columns:2rem minmax(9rem,1fr) 7rem minmax(7rem,10rem) 8.5rem 3.5rem}
.tn-bench-h{padding-block:0.25rem;border-block-end:1px solid var(--tn-line)}
.tn-bench .tn-bm{min-width:0}
.tn-bench .tn-bm>span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tn-bench .tn-bsub{font-size:0.7rem;color:var(--tn-mut)}
.tn-bench .tn-bnum{font:0.72rem var(--tn-mono);font-variant-numeric:tabular-nums;color:var(--tn-fg2);white-space:nowrap}
.tn-bench .tn-end{text-align:end}
.tn-wait{display:flex;flex-wrap:wrap;gap:0.3rem 1rem;padding:0.5rem 0.25rem;font-size:0.75rem;color:var(--tn-fg2)}
.tn-anim-toggle{display:inline-flex;align-items:center;gap:0.4rem;font:0.66rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;color:var(--tn-fg2);white-space:nowrap}
.tn-anim-toggle[data-off=true]{opacity:0.6}
.tn-root:dir(rtl),.tn-root:dir(rtl) *{letter-spacing:0!important}
.tn-root:dir(rtl) :is(.tn-tile-window,.tn-magent-tot,.tn-mcell-mid,.tn-mprofile b,.tn-table th,.tn-kbd,.tn-eyebrow,.tn-emblem-cap,.tn-anim-toggle,.tn-ptop,.tn-pfoot,.tn-psig,.tn-btn,.tn-seg button,.tn-chip-in,.tn-preset span:first-child){font-family:var(--font-sans,system-ui),system-ui,sans-serif;text-transform:none}
.tn-bench[data-pub=wide]{grid-template-columns:2rem minmax(9rem,1fr) 7rem minmax(7rem,10rem) 8.5rem 7rem}
.tn-bench[data-s=true]{grid-template-columns:2rem minmax(9rem,1fr) 7rem minmax(7rem,10rem) 8.5rem 4rem}
.tn-bench[data-s=true][data-pub=true]{grid-template-columns:2rem minmax(9rem,1fr) 7rem minmax(7rem,10rem) 8.5rem 4rem 3.5rem}
.tn-root .tn-mono{font-family:var(--tn-mono)}
.tn-root .tn-dim{color:var(--tn-mut)}
.tn-root .tn-end{text-align:end}
.tn-root td.tn-end{white-space:nowrap}
.tn-root td.tn-end > span + span{margin-inline-start:0.35rem}
.tn-head-tog{display:flex;align-items:center;gap:0.5rem 1rem;margin-inline-start:auto}
.tn-raw{border:0;background:transparent;padding:0;cursor:pointer;outline:none}
.tn-raw i{font-style:normal;display:inline-block;width:0.6rem;height:0.6rem;border:1px solid var(--tn-acc)}
.tn-raw i[data-on=true]{background:var(--tn-acc)}
.tn-raw:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-doc.tn-doc-wide{max-width:84rem;gap:1.25rem}
.tn-tiles-wrap{display:flex;flex-direction:column;gap:0.4rem;padding-block:0.25rem 0.75rem;border-block-end:1px solid var(--tn-line)}
.tn-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}
.tn-tile{display:flex;flex-direction:column;gap:0.2rem;padding:0.4rem 1rem 0.4rem 0;min-width:0}
.tn-tile+.tn-tile{padding-inline-start:1rem;border-inline-start:1px solid var(--tn-line)}
.tn-tile-n{font-family:var(--tn-display);font-weight:700;font-size:clamp(1.9rem,3.6vw,2.8rem);line-height:0.95;color:var(--tn-fg);font-variant-numeric:tabular-nums}
.tn-tile-label{font-size:0.78rem;color:var(--tn-fg)}
.tn-tile-sub{font-size:0.7rem;color:var(--tn-mut)}
.tn-tile-window{margin:0;font:0.62rem var(--tn-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--tn-mut)}
@container (max-width:40rem){.tn-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.tn-tile:nth-child(3){border-inline-start:0;padding-inline-start:0}}
.tn-doc-wrap{container-type:inline-size}
.tn-map-scroll{overflow-x:auto;max-width:100%}
.tn-map{border-collapse:collapse;width:100%;font-size:0.75rem}
.tn-map th,.tn-map td{padding:0.45rem 0.6rem;text-align:start;vertical-align:top;font-weight:400}
.tn-map thead th{border-block-end:1px solid var(--tn-line)}
.tn-mth-agent,.tn-mth-group{vertical-align:bottom}
.tn-mth-agent>span,.tn-mth-group>span{display:block}
.tn-mth-sub{font-size:0.66rem;color:var(--tn-mut);margin-block-start:0.15rem}
.tn-mth-type code{font:0.72rem var(--tn-mono);color:var(--tn-fg);overflow-wrap:anywhere}
.tn-mth-agent,.tn-mtd-agent{position:sticky;inset-inline-start:0;z-index:1;background:var(--ui-surface-background,var(--background-base,Canvas));width:17rem;min-width:15rem}
.tn-mprofile th{padding-block:0.9rem 0.35rem;border-block-end:1px solid var(--tn-line)}
.tn-mprofile th>div{display:flex;flex-wrap:wrap;align-items:center;gap:0.25rem 0.6rem;position:sticky;inset-inline-start:0.6rem;width:fit-content;max-width:min(100%,60rem)}
.tn-mprofile b{font:500 0.7rem var(--tn-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--tn-acc-text)}
.tn-mprof-set{font-size:0.7rem}
.tn-mrow{cursor:pointer;border-block-end:1px solid var(--tn-line)}
.tn-mrow:hover>*{background:var(--ui-row-hover-background,color-mix(in srgb,var(--tn-fg) 4%,transparent))}
.tn-mrow:hover .tn-mtd-agent{background:color-mix(in srgb,var(--tn-fg) 4%,var(--ui-surface-background,var(--background-base,Canvas)))}
.tn-magent{display:flex;align-items:flex-start;gap:0.6rem;width:100%;border:0;background:transparent;color:inherit;font:inherit;text-align:start;padding:0;cursor:pointer;outline:none}
.tn-magent:focus-visible{box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 45%,transparent)}
.tn-magent .tn-emblem{color:var(--tn-acc);flex:none}
.tn-magent-txt{display:flex;flex-direction:column;gap:0.15rem;min-width:0;flex:1 1 auto}
.tn-magent-name{font-family:var(--tn-display);font-weight:700;font-size:1.05rem;line-height:1.05;color:var(--tn-fg);overflow-wrap:anywhere}
.tn-magent-name .tn-dim{font:400 0.68rem var(--tn-mono);margin-inline-start:0.2rem}
.tn-magent-tot{font:0.66rem var(--tn-mono);color:var(--tn-mut);font-variant-numeric:tabular-nums}
.tn-mopen{flex:none;color:var(--tn-mut);margin-block-start:0.2rem}
.tn-mopen:dir(rtl){transform:scaleX(-1)}
.tn-mrow:hover .tn-mopen{color:var(--tn-acc)}
.tn-mcell{min-width:8rem}
.tn-mcell-in{display:flex;flex-direction:column;gap:0.3rem;outline:none}
.tn-mcell-top{display:flex;align-items:center;justify-content:space-between;gap:0.4rem}
.tn-mcell .tn-bar{height:11px}
.tn-mcell-mid{font:0.64rem var(--tn-mono);color:var(--tn-mut)}
.tn-mcell-miss{font-size:0.68rem;line-height:1.4;color:var(--tn-fg2)}
.tn-mcell-miss[data-tone=ok]{color:var(--tn-acc-text)}
.tn-mcell-miss[data-tone=warn]{color:var(--tn-fg)}
.tn-mnone{color:var(--tn-mut);text-align:center!important;vertical-align:middle!important}
.tn-legend{display:flex;flex-wrap:wrap;gap:0.5rem 1.25rem;padding-block:0.6rem 0.25rem;font-size:0.7rem;color:var(--tn-fg2)}
.tn-legend-i{display:inline-flex;align-items:center;gap:0.4rem}
.tn-legend-bar{display:inline-flex;align-items:center;gap:0.35rem}
.tn-legend-bar .tn-bar{width:3rem;height:10px}
.tn-trans{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;border-block-start:1px solid var(--tn-line)}
.tn-trans li{display:flex;flex-wrap:wrap;align-items:center;gap:0.3rem 0.75rem;padding:0.45rem 0.25rem;font-size:0.75rem;border-block-end:1px solid var(--tn-line)}
.tn-trans code{font-size:0.72rem;color:var(--tn-fg)}
.tn-trans-move{display:inline-flex;align-items:center;gap:0.35rem;color:var(--tn-mut)}
.tn-flag[data-kind=ok]{border-style:solid;background:color-mix(in srgb,var(--tn-acc) 12%,transparent)}
.tn-flag[data-kind=muted]{border-color:var(--tn-mut);color:var(--tn-fg2)}
.tn-sw-form{display:flex;flex-wrap:wrap;align-items:flex-end;gap:0.6rem 0.75rem;padding-block:0.25rem 0.5rem}
.tn-field{display:flex;flex-direction:column;gap:0.3rem;min-width:12rem}
.tn-field-grow{flex:1 1 16rem}
.tn-input{height:2rem;padding:0 0.6rem;font:0.78rem var(--tn-mono);color:var(--tn-fg);background:transparent;border:1px solid var(--tn-line);border-radius:0;outline:none;min-width:0}
.tn-input:focus{border-color:var(--tn-acc);box-shadow:0 0 0 2px color-mix(in srgb,var(--tn-acc) 25%,transparent)}
.tn-input option{color:initial}
.tn-input-sm{height:1.6rem;font-size:0.7rem;padding:0 0.4rem}
.tn-sw-arrow{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;min-width:2rem;height:2rem;margin:0;padding:0 0.5rem;border:1px solid color-mix(in srgb,var(--tn-fg) 30%,transparent);border-radius:0;background:transparent;color:var(--tn-acc-text);font:0.9rem var(--tn-mono);cursor:pointer;outline:none}
.tn-sw-arrow:hover{border-color:var(--tn-acc);background:color-mix(in srgb,var(--tn-acc) 14%,transparent)}
.tn-sw-arrow:focus-visible{outline:2px solid var(--tn-acc);outline-offset:1px}
.tn-sw-pair{font:0.78rem var(--tn-mono);color:var(--tn-fg2);margin-inline-end:0.4rem}
.tn-sw-pair b{color:var(--tn-fg);font-weight:500}
.tn-sw-legend{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:0.35rem 0.75rem;margin:0.25rem 0;font-size:0.72rem;color:var(--tn-fg2);align-items:center}
.tn-sw-legend dd{margin:0}
.tn-sw-tier{display:inline-flex;align-items:center;gap:0.4rem;font-size:0.72rem}
.tn-table{border-collapse:collapse;width:100%;font-size:0.75rem}
.tn-table th{font:500 0.62rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;color:var(--tn-acc-text);text-align:start;padding:0.35rem 0.6rem;border-block-end:1px solid var(--tn-line);white-space:nowrap}
.tn-table td{padding:0.5rem 0.6rem;vertical-align:top;border-block-end:1px solid var(--tn-line);color:var(--tn-fg)}
.tn-table tr.tn-sub td:first-child{padding-inline-start:1.6rem}
.tn-table code{font-size:0.72rem}
.tn-table .tn-hint{margin:0}
.tn-tacts{display:inline-flex;align-items:center;gap:0.1rem;opacity:0;transition:opacity 120ms}
.tn-trow:hover .tn-tacts,.tn-trow:focus-within .tn-tacts{opacity:1}
.tn-tl-wrap{display:flex;flex-direction:column;gap:0.75rem}
.tn-tl-day ol{margin:0.25rem 0 0;padding:0;list-style:none;border-block-start:1px solid var(--tn-line)}
.tn-tl-label{color:var(--tn-mut)}
.tn-tl-item{display:grid;grid-template-columns:5.5rem 1rem minmax(0,1fr) auto auto;gap:0.25rem 0.6rem;align-items:baseline;padding:0.35rem 0.25rem;font-size:0.74rem;border-block-end:1px solid var(--tn-line);color:var(--tn-fg2)}
.tn-tl-time,.tn-tl-seq{font:0.66rem var(--tn-mono);color:var(--tn-mut);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.tn-tl-glyph{color:var(--tn-mut);text-align:center}
.tn-tl-item[data-tone=ok] .tn-tl-glyph,.tn-tl-item[data-tone=move] .tn-tl-glyph{color:var(--tn-acc-text)}
.tn-tl-item[data-tone=fault] .tn-tl-glyph{color:var(--tn-fg);font-weight:700}
.tn-tl-item[data-tone=move] .tn-tl-text{color:var(--tn-fg)}
.tn-tl-text b{font:600 0.7rem var(--tn-mono);color:var(--tn-acc-text)}
.tn-tl-type{font:0.68rem var(--tn-mono);color:var(--tn-fg)}
.tn-keys{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:0.4rem 1rem;margin:0.25rem 0 0;align-items:center}
.tn-keys dd{margin:0;font-size:0.76rem;color:var(--tn-fg2)}
.tn-kbd{display:inline-flex;min-width:1.4rem;justify-content:center;padding:0.1rem 0.35rem;font:500 0.7rem var(--tn-mono);color:var(--tn-acc-text);border:1px solid var(--tn-acc);border-block-end-width:2px}
@media (prefers-reduced-motion:reduce){.tn-uacts,.tn-tacts{transition:none}.tn-enter,.tn-scan,.tn-chip.tn-out,.tn-chip.tn-in,.tn-band-title,.tn-leaving{animation:none!important}.tn-prow,.tn-pass,.tn-ok{transition:none!important}.tn-prow{opacity:1;transform:none}}
`

// ------------------------------------------------------------------------------------------------ pieces
function TierLabel(tier, t) {
  return { ask: t('tier.t1'), trusted: t('tier.trusted'), notify: t('tier.t2'), alone: t('tier.t3'), cap: t('tier.cap') }[tier]
}

/** The tier's display name in the tenure vocabulary (Trusted, Probation, Under review, Tenured, Always asks). */
function tierName(tier, t) {
  return { ask: t('tier.name.t1'), trusted: t('tier.name.trusted'), notify: t('tier.name.t2'), alone: t('tier.name.t3'), cap: t('tier.name.cap') }[tier]
}

/** Flat rectangular chip: outlined T1/T2, filled accent T3, dashed CAP, dotted half-dither for the trusted start.
 *  A tier change dissolves the old chip. */
function TierChip({ tier, t, motion }) {
  const [ghost, setGhost] = useState(null)
  const prev = useRef(tier)
  useEffect(() => {
    if (prev.current === tier) return
    const old = prev.current
    prev.current = tier
    if (!motion) return
    setGhost({ tier: old, key: Date.now() })
    const id = setTimeout(() => setGhost(null), 560)
    return () => clearTimeout(id)
  }, [tier, motion])
  return jsx(Tip, {
    label: TierLabel(tier, t),
    children: jsxs('span', {
      'aria-label': tier === 'trusted' ? `${tierName(tier, t)}: ${TierLabel(tier, t)}` : `${TIER_SHORT[tier]} · ${tierName(tier, t)}: ${TierLabel(tier, t)}`,
      className: 'tn-chip-wrap',
      tabIndex: 0,
      children: [
        jsx('span', { className: cn('tn-chip', ghost && 'tn-in'), 'data-tier': tier, children: tierShort(tier, t) }, 'chip-' + tier + (ghost ? ghost.key : '')),
        ghost ? jsx('span', { 'aria-hidden': true, className: 'tn-chip tn-chip-ghost tn-out', 'data-tier': ghost.tier, children: tierShort(ghost.tier, t) }, 'ghost') : null
      ]
    })
  })
}

/** A state flag in the one colour: dotted outline for carried / trial states, solid outline for a fault. */
function StatePill({ label, tip, kind, t }) {
  return jsx(Tip, {
    label: tip,
    children: jsx('span', { 'aria-label': t('state.aria', { label, tip }), className: 'tn-flag', 'data-kind': kind || 'state', tabIndex: 0, children: label })
  })
}

/** Small numbered mono eyebrow: "#02 · Acted without asking". */
function Eyebrow({ n, children, as = 'h4' }) {
  return jsxs(as, { className: 'tn-eyebrow', style: { margin: 0 }, children: [n != null ? jsx('span', { className: 'tn-dim', children: `#${pad2(n)} · ` }) : null, children] })
}

const SERIES_SESSIONS = 2 // rule.SESSIONS: T3 also needs the series spread over at least two sessions
const WALD = { low: [0.1, 0.3], medium: [0.05, 0.2] } // params.WALD (alpha = beta = 0.05): the middle tier's stakes
const LN_B = Math.log(0.05 / 0.95)

/** Verified successes without a fault still needed before T2 (from the Wald score); null when T2 is out of reach. */
function toT2(ty) {
  const w = WALD[ty.stakes]
  if (!w || !ty.reversible || ty.wald == null || ty.capped) return null
  const step = -Math.log((1 - w[1]) / (1 - w[0]))
  return Math.max(0, Math.ceil((ty.wald - LN_B) / step - 1e-9))
}

/**
 * One number, one meaning: every bar runs from 0 to the series T3 requires, filled to series / required, one
 * segment per success needed; T3 is solid; a capped type shows only its dotted track. A T1 type that can reach T2
 * carries a notch at series + the successes still missing for T2.
 */
const fillOf = ty => (ty.capped ? 0 : tierKey(ty) === 'alone' ? 1 : ty.required > 0 ? clamp01(ty.series / ty.required) : 0)
function notchOf(ty) {
  if (ty.capped || tierKey(ty) !== 'ask' || !(ty.required > 0)) return null
  const k = toT2(ty)
  if (k == null) return null
  const at = (ty.series || 0) + k
  return at < ty.required ? at / ty.required : null
}
const barGeo = ty => ({ segments: ty.capped ? 0 : ty.required || 0, notch: notchOf(ty) })

/** The next step first (T2 when it is the next one), then T3. */
function nextLine(ty, t, spot) {
  const tier = tierKey(ty)
  if (ty.capped) return t('type.always_asks')
  if (tier === 'trusted') return t(ty.reversible ? 'type.trusted_line_undo' : 'type.trusted_line')
  if (tier === 'alone') return t('type.tenured_line', { k: Math.round(1 / (spot || 0.1)) })
  const left = Math.max(0, (ty.required || 0) - (ty.series || 0))
  const k2 = tier === 'ask' ? toT2(ty) : null
  if (k2) return left > 0 ? t('type.more_to_t2', { n: k2 }) + ' · ' + t('type.more_to_t3', { n: left }) : t('type.more_to_t2', { n: k2 })
  if (left > 0) return t('type.next', { n: left })
  if ((ty.sessions || 0) < SERIES_SESSIONS) return t('type.next_session')
  return ''
}

/** "9/52": the series against what T3 requires; a capped type has no series to show. */
function Count({ ty }) {
  if (ty.capped) return null
  return jsxs('span', { 'aria-hidden': true, className: 'tn-count', children: [String(ty.series || 0), jsx('i', { children: '/' + String(ty.required || 0) })] })
}

/** The guarantee in plain words, its statistical detail in a tooltip. */
function Guarantee({ g, t }) {
  const detail = t(g.conditional ? 'type.guarantee_provisional' : 'type.guarantee', { aoql: pct(g.aoql), worst: pct(g.worst_case) })
  if (!(g.aoql > 0)) return jsx('p', { className: 'tn-tguar', children: detail })
  const plain = t('type.guarantee_plain', { k: Math.max(1, Math.round(1 / g.aoql)) }) + (g.conditional ? ' · ' + t('state.provisional') : '')
  return jsx(Tip, { label: detail, children: jsx('p', { 'aria-label': plain + ' ' + detail, className: 'tn-tguar', tabIndex: 0, children: plain }) })
}

function TypeRow({ type, t, index, motion, change, spot, mine, onAct }) {
  const tier = tierKey(type)
  const g = type.guarantee
  const stakes = ['low', 'medium', 'high'].includes(type.stakes) ? t('type.stakes_' + type.stakes) : t('type.stakes_other', { stakes: type.stakes })
  const trusted = tier === 'trusted'
  const progress = t('type.in_a_row', { series: type.series, required: type.required })
  const next = nextLine(type, t, spot)
  const geo = barGeo(type)
  // A trusted type has no progress to show: a light, even texture, labelled as nothing earned.
  const plain = type.capped || trusted
  return jsxs('div', {
    className: cn('tn-trow', motion && 'tn-enter'),
    style: motion ? { animationDelay: `${index * 40}ms` } : undefined,
    children: [
      jsx('div', { 'aria-hidden': true, className: 'tn-tnum', children: '#' + pad2(index + 1) }),
      jsxs('div', {
        className: 'min-w-0',
        children: [
          jsxs('div', {
            className: 'tn-tl',
            children: [
              jsx('span', { className: 'tn-tk tn-bdi', children: type.type }),
              jsx(TierChip, { tier, t, motion }),
              jsx('span', { className: 'tn-tname', 'data-tier': tier, children: tierName(tier, t) }),
              jsx('span', { className: 'tn-tstakes', children: stakes }),
              onAct
                ? jsxs('span', {
                    className: 'tn-tacts',
                    children: [
                      jsx(Tip, {
                        label: mine ? t('type.flag_title') : t('common.own_profile_only'),
                        children: jsx('span', { children: jsx(Button, { disabled: !mine, onClick: () => onAct('flag', type), size: 'xs', variant: 'ghost', children: t('type.flag_button') }) })
                      }),
                      jsx(Tip, {
                        label: mine ? t('type.revoke_title') : t('common.own_profile_only'),
                        children: jsx('span', { children: jsx(Button, { disabled: !mine, onClick: () => onAct('revoke', type), size: 'xs', variant: 'ghost', children: t('type.revoke_button') }) })
                      })
                    ]
                  })
                : null
            ]
          }),
          jsx('div', {
            'aria-label': type.capped ? t('type.always_asks') : trusted ? t('type.trusted_bar') : progress,
            'aria-valuemax': plain ? undefined : type.required,
            'aria-valuemin': plain ? undefined : 0,
            'aria-valuenow': plain ? undefined : type.series,
            className: 'tn-tbar',
            role: plain ? 'img' : 'progressbar',
            children: [
              jsx(DitherBar, { change: change && change.dir !== 'spot' ? change : null, delay: 120 + index * 40, motion, notch: geo.notch, segments: geo.segments, solid: tier === 'alone', track: type.capped, trust: trusted, value: fillOf(type) }),
              trusted ? null : jsx(Count, { ty: type })
            ]
          }),
          jsxs('p', {
            className: 'tn-tnext',
            children: [
              next,
              !plain
                ? jsx('span', { className: 'tn-g', children: (next ? ' · ' : '') + t('type.sessions', { n: type.sessions }) })
                : null
            ]
          }),
          trusted ? jsx('p', { className: 'tn-trust-note', children: t('type.trusted_no_guarantee') }) : null,
          !plain && g && tier === 'alone' ? jsx(Guarantee, { g, t }) : null   // the guarantee holds once tenured
        ]
      }),
      change && change.dir === 'spot' && motion ? jsx('span', { 'aria-hidden': true, className: 'tn-scan' }, change.token) : null
    ]
  })
}

function Intro({ t, spot, start }) {
  const trustedStart = start === 'trusted'
  const [hidden, setHidden] = useState(() => (storage ? storage.get('introDismissed', false) : false))
  if (hidden) return null
  return jsxs('div', {
    className: 'tn-intro',
    children: [
      jsxs('div', {
        className: 'min-w-0 flex-1',
        style: { display: 'flex', flexDirection: 'column', gap: '0.3rem' },
        children: [
          jsx(Eyebrow, { as: 'p', n: 0, children: t('intro.title') }),
          jsx('p', { className: 'tn-intro-body', children: t(trustedStart ? 'intro.body_trusted' : 'intro.body', { k: Math.round(1 / (spot || 0.1)) }) })
        ]
      }),
      jsx(Button, {
        onClick: () => {
          if (storage) storage.set('introDismissed', true)
          setHidden(true)
        },
        size: 'xs',
        variant: 'ghost',
        children: t('intro.got_it')
      })
    ]
  })
}

/** Consecutive actions of the same type with no file to name collapse into one row: "12 × file:write". */
function groupUndo(rows) {
  const out = []
  for (const r of rows) {
    const last = out[out.length - 1]
    if (!r.file && last && !last.file && last.type === r.type && last.agent === r.agent && last.profile === r.profile) last.rows.push(r)
    else out.push({ key: r.profile + '|' + r.id, file: r.file, type: r.type, agent: r.agent, profile: r.profile, rows: [r] })
  }
  return out
}

function RecentSection({ agent, t, n }) {
  const profile = useValue(host.state.profile)
  const [flagging, setFlagging] = useState(null)
  const [open, setOpen] = useState({})
  const [target, setTarget] = useState(null)
  const { data } = useActivity()
  const mine = agent.profile === profile
  const [all, setAll] = useState(false)
  const every = ((data && data.undoable) || []).filter(r => r.agent === agent.agent && r.profile === agent.profile)
  const groups = groupUndo(every)
  const shown = all ? groups : groups.slice(0, 5)
  const icon = () =>
    jsx(Tip, {
      label: t('recent.restore_icon'),
      children: jsx('span', { 'aria-label': t('recent.restore_icon'), className: 'tn-uicon', role: 'img', tabIndex: 0, children: jsx(Codicon, { name: 'history', size: '0.8rem' }) })
    })
  const name = r =>
    jsxs('span', {
      className: 'tn-uname',
      children: [
        jsx('span', { className: 'tn-mono tn-bdi', children: r.file || r.type }),
        r.files > 1 ? jsx('span', { className: 'tn-dim tn-bdi', children: t('recent.more_files', { n: r.files - 1 }) }) : null,
        r.file ? jsx('span', { className: 'tn-dim tn-mono tn-bdi', children: r.type }) : jsx('span', { className: 'tn-dim', children: t('recent.no_snapshot') })
      ]
    })
  const row = (r, sub) =>
    jsxs(
      'div',
      {
        className: cn('tn-urow', sub && 'tn-sub'),
        children: [
          icon(),
          name(r),
          r.counts_as_fault === false ? jsx(StatePill, { kind: 'fault', label: t('recent.check_failed'), tip: t('recent.check_failed_tip'), t }) : null,
          jsxs('span', {
            className: 'tn-uacts',
            children: [
              jsx(Tip, {
                label: mine ? t('recent.flag_tip') : t('common.own_profile_only'),
                children: jsx('span', { children: jsx(Button, { disabled: !mine, onClick: () => setFlagging(r), size: 'xs', variant: 'ghost', children: t('recent.flag') }) })
              }),
              jsx(Tip, {
                label: mine ? t('recent.undo_tip') : t('common.own_profile_only'),
                children: jsx('span', { children: jsx(Button, { disabled: !mine, onClick: () => setTarget(r), size: 'xs', variant: 'outline', children: t('recent.undo') }) })
              })
            ]
          }),
          jsx('span', { className: 'tn-uago', children: ago(t, r.age) })
        ]
      },
      r.profile + r.id
    )
  const groupRow = g => {
    const expanded = !!open[g.key]
    const first = g.rows[0]
    return [
      jsxs(
        'div',
        {
          className: 'tn-urow',
          children: [
            icon(),
            jsxs('button', {
              'aria-expanded': expanded,
              'aria-label': (expanded ? t('recent.collapse') : t('recent.expand')) + ': ' + g.rows.length + ' × ' + g.type,
              className: 'tn-ugroup',
              onClick: () => setOpen(o => ({ ...o, [g.key]: !expanded })),
              type: 'button',
              children: [
                jsx(Codicon, { name: expanded ? 'chevron-down' : 'chevron-right', size: '0.75rem' }),
                jsx('b', { className: 'tn-bdi', children: g.rows.length + ' ×' }),
                jsx('span', { className: 'tn-mono tn-bdi', children: g.type }),
                jsx('span', { className: 'tn-dim', style: { color: 'var(--tn-mut)', fontSize: '0.7rem' }, children: t('recent.no_snapshot') })
              ]
            }),
            jsx('span', { className: 'tn-uago', children: ago(t, first.age) })
          ]
        },
        'g' + g.key
      ),
      ...(expanded ? g.rows.map(r => row(r, true)) : [])
    ]
  }
  return jsxs('section', {
    className: 'tn-section',
    children: [
      jsx(Eyebrow, { n, children: t('recent.title') }),
      shown.length === 0
        ? jsx('p', { style: { margin: 0, fontSize: '0.75rem', color: 'var(--tn-fg2)' }, children: t('recent.none') })
        : jsx('div', {
            className: 'flex flex-col',
            style: { borderBlockStart: '1px solid var(--tn-line)' },
            children: shown.flatMap(g => (g.rows.length > 1 ? groupRow(g) : [row(g.rows[0], false)])).concat(
              groups.length > 5
                ? [jsx('div', { style: { paddingBlockStart: '0.5rem' }, children: jsx(Button, { onClick: () => setAll(!all), size: 'xs', variant: 'outline', children: all ? t('recent.show_fewer') : t('recent.show_all', { n: groups.length }) }) }, 'more')]
                : []
            )
          }),
      jsx(UndoDialog, { onClose: () => setTarget(null), t, target }),
      jsx(FlagDialog, { onClose: () => setFlagging(null), t, target: flagging })
    ]
  })
}

// ------------------------------------------------------------------------------------------------ passport card
const HEX = '0123456789abcdef'
const scramble = n => Array.from({ length: n }, () => HEX[Math.floor(Math.random() * 16)]).join('')

/**
 * B. The passport as a card: the emblem develops then turns, the name types in, the rows print, the ledger hash
 * scrambles while the passport verifies and settles on the real head (✓ only if it verifies), then a seal prints.
 * Hover tilts it (≤ 4°) with a dithered glare that follows the pointer (mouse only, motion on).
 */
const PASS_ROWS = 8 // rows the card shows; the rest is counted on one line (the JSON file carries every type)

function PassportCard({ agent, doc, settled, ok, t, motion: motionOn, outerRef, look }) {
  const style = look || PASS_STYLE_DEFAULT
  // The Animations switch and reduced motion force Still; only Develop runs the printed sequence below.
  const anim = motionOn ? style.animation : 'still'
  const motion = anim === 'develop'
  const tilts = anim === 'develop' || anim === 'holographic'
  const seed = seedOf(agent.agent)
  const cardRef = useRef(null)
  const setCard = el => {
    cardRef.current = el
    if (outerRef) outerRef.current = el
  }
  const nameRef = useRef(null)
  const hashRef = useRef(null)
  const okRef = useRef(null)
  const sealRef = useRef(null)
  const sweepRef = useRef(null)
  const rowsRef = useRef(null)
  const live = useRef({ settled, ok, head: null })
  const p = doc && doc.passport
  const head = p && p.ledger ? String(p.ledger.head).slice(0, 8) : null
  live.current = { settled, ok, head }
  const name = displayName(agent.model)
  const types = agent.types || []
  const shown = types.slice(0, PASS_ROWS)
  const more = types.length - shown.length
  const totals = types.reduce((acc, ty) => ({ f: acc.f + (ty.faults || 0), n: acc.n + (ty.successes || 0) + (ty.faults || 0) }), { f: 0, n: 0 })
  const paintSealAt = k => sealRef.current && paintSeal(sealRef.current, { size: 64, print: k })
  useRepaint(() => {
    if (live.current.ok && live.current.settled) paintSealAt(1)
  })
  // Static end state (motion off) and live updates after the sequence.
  const finish = () => {
    if (nameRef.current) nameRef.current.textContent = name
    if (hashRef.current) hashRef.current.textContent = live.current.head || '········'
    if (okRef.current) okRef.current.classList.toggle('tn-on', !!(live.current.ok && live.current.settled))
    if (rowsRef.current) for (const r of rowsRef.current.children) r.classList.add('tn-on')
    if (sealRef.current) {
      if (live.current.ok && live.current.settled) paintSealAt(1)
      else paintSealAt(0)
    }
  }
  const done = useRef(false)
  useEffect(() => {
    done.current = false
    if (!motion) {
      done.current = true
      finish()
      return
    }
    let raf = 0
    let t0 = 0
    let settledAt = 0
    let lastScramble = 0
    if (nameRef.current) nameRef.current.textContent = ''
    if (okRef.current) okRef.current.classList.remove('tn-on')
    if (rowsRef.current) for (const r of rowsRef.current.children) r.classList.remove('tn-on')
    paintSealAt(0)
    const frame = now => {
      if (!t0) t0 = now
      const s = (now - t0) / 1000
      const L = live.current
      if (nameRef.current) nameRef.current.textContent = name.slice(0, Math.max(0, Math.min(name.length, Math.floor((s - 0.9) * 22))))
      if (rowsRef.current) [...rowsRef.current.children].forEach((r, i) => s > 1.6 + i * 0.2 && r.classList.add('tn-on'))
      const verified = L.settled && s >= 3.0
      if (!settledAt && verified) settledAt = now
      if (hashRef.current) {
        if (settledAt) hashRef.current.textContent = L.head || '········'
        else if (s < 2.2) hashRef.current.textContent = '········'
        else if (now - lastScramble > 50) {
          lastScramble = now
          hashRef.current.textContent = scramble(8)
        }
      }
      if (sweepRef.current) {
        const h = cardRef.current ? cardRef.current.offsetHeight : 520
        const on = s > 2.2 && !settledAt
        sweepRef.current.style.transform = on ? `translateY(${(((s - 2.2) % 1.2) / 1.2) * (h + 60)}px)` : 'translateY(0)'
      }
      if (settledAt && okRef.current && L.ok) okRef.current.classList.add('tn-on')
      const sk = settledAt && L.ok ? clamp01((now - settledAt - 250) / 600) : 0
      if (settledAt && L.ok) paintSealAt(sk)
      const nameDone = s > 0.9 + name.length / 22
      if (settledAt && (!L.ok || sk >= 1) && nameDone && s > 1.6 + shown.length * 0.2) {
        done.current = true
        finish()
        return
      }
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [motion])
  // After the sequence, follow the data (a new verification, another head).
  useEffect(() => {
    if (done.current) finish()
  }, [settled, ok, head])
  const onMove = e => {
    const el = cardRef.current
    if (!el || !tilts || e.pointerType !== 'mouse') return
    const r = el.getBoundingClientRect()
    const px = clamp01((e.clientX - r.x) / r.width) - 0.5
    const py = clamp01((e.clientY - r.y) / r.height) - 0.5
    const rtl = getComputedStyle(el).direction === 'rtl' ? -1 : 1
    el.classList.add('tn-tilting')
    el.style.transform = `rotateX(${(-py * 8).toFixed(2)}deg) rotateY(${(px * 8).toFixed(2)}deg)`
    el.style.setProperty('--tn-gx', String(px * rtl))
  }
  const onLeave = () => {
    const el = cardRef.current
    if (!el) return
    el.classList.remove('tn-tilting')
    el.style.transform = ''
    el.style.setProperty('--tn-gx', '0')
  }
  return jsx('div', {
    className: 'tn-pass-wrap',
    children: jsxs('div', {
      className: 'tn-pass',
      'data-anim': anim,
      'data-card': style.card,
      'data-motion': tilts ? 'on' : 'off',
      onPointerLeave: onLeave,
      onPointerMove: onMove,
      ref: setCard,
      children: [
        jsx('div', { 'aria-hidden': true, className: 'tn-sweep', ref: sweepRef }),
        jsx('div', { 'aria-hidden': true, className: 'tn-glare' }),
        anim === 'holographic' ? jsx('div', { 'aria-hidden': true, className: 'tn-holo' }) : null,
        anim === 'scan' ? jsx('div', { 'aria-hidden': true, className: 'tn-scanline' }) : null,
        jsxs('div', {
          className: 'tn-ptop',
          children: [
            jsx('span', { children: t('page.title') }),
            jsxs('span', { children: [t('passport.card_title'), ' ', jsx('span', { 'aria-hidden': true, className: 'tn-ok', ref: okRef, children: '✓' })] })
          ]
        }),
        jsx('div', { className: 'tn-pemb', children: jsx(Emblem, { motion, n: 96, pattern: style.pattern, rotate: true, seed, share: shareOf(agent), size: 216 }) }),
        jsx('div', {
          'aria-label': name,
          className: 'tn-pname',
          ref: nameRef,
          role: 'heading',
          'aria-level': 4,
          // As large as the card allows on one line: Collapse runs about half an em per character.
          style: { fontSize: `clamp(1.6rem, ${Math.min(13, 165 / Math.max(1, name.length)).toFixed(2)}cqi, 6.2rem)` },
          children: motion ? '' : name
        }),
        jsx('div', {
          className: 'tn-prows',
          ref: rowsRef,
          children: shown.map((ty, i) => {
            const tier = tierKey(ty)
            const geo = barGeo(ty)
            return jsxs(
              'div',
              {
                className: cn('tn-prow', !motion && 'tn-on'),
                'data-motion': motion ? 'on' : 'off',
                children: [
                  jsx('span', { 'aria-hidden': true, className: 'tn-pnum', children: '#' + pad2(i + 1) }),
                  jsxs('span', {
                    className: 'tn-pk',
                    children: [
                      jsx('span', { className: 'tn-bdi tn-ptype', children: ty.type }),
                      // A trusted type is never shown as an earned tier on the passport.
                      jsx('b', { 'data-tier': tier, children: tier === 'trusted' ? t('passport.trusted') : `${TIER_SHORT[tier]} · ${tierName(tier, t)}` })
                    ]
                  }),
                  jsx(DitherBar, { delay: 1700 + i * 200, motion, notch: geo.notch, rows: 4, segments: geo.segments, solid: tier === 'alone', track: ty.capped, trust: tier === 'trusted', value: fillOf(ty) }),
                  jsx('span', { className: 'tn-pn', children: ty.capped || tier === 'trusted' ? '' : `${ty.series || 0}/${ty.required || 0}` })
                ]
              },
              ty.type
            )
          })
        }),
        more > 0 ? jsx('div', { className: 'tn-pmore', children: t('passport.more_types', { n: more }) }) : null,
        jsxs('div', {
          className: 'tn-pfoot',
          children: [
            jsx('span', { children: t('passport.faults_checks', { n: totals.f, total: totals.n }) }),
            jsxs('span', { children: [t('passport.ledger'), ' ', jsx('span', { className: 'tn-hash', ref: hashRef, children: motion ? '········' : head || '········' })] })
          ]
        }),
        jsxs('div', {
          className: 'tn-psig',
          children: [jsx(Emblem, { motion: false, n: 18, share: 1, size: 18 }), jsx('b', { children: 'TENURE' }), jsx('span', { children: t('passport.signature') })]
        }),
        jsx('canvas', { 'aria-hidden': true, className: 'tn-seal', ref: sealRef })
      ]
    })
  })
}

/** A command in a block, with the host's copy button. */
function Cmd({ text, t }) {
  return jsxs('div', {
    className: 'tn-cmd',
    children: [jsx(PanelBlock, { className: 'min-w-0 flex-1', children: text }), jsx(CopyButton, { appearance: 'icon', label: t('passport.copy_command'), text })]
  })
}

/** `hermes tenure …`, with `-p PROFILE` for a profile other than the default one. */
const hermesCmd = (profile, rest) => (profile && profile !== 'default' ? `hermes -p ${profile} tenure ${rest}` : `hermes tenure ${rest}`)

/** A file name safe on every system, from a model name. */
const fileSafe = name => String(name || 'agent').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'agent'

/** Hand the viewer a file: a blob URL on a temporary link, revoked once the download started. */
function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.rel = 'noopener'
  a.style.display = 'none'
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

/**
 * The passport card drawn on a canvas, for a PNG: the same pieces as the card (emblem, name, one row per type with its
 * dither bar, faults / verified outcomes, ledger head, signature), its colours read from the card as displayed, the
 * host's own fonts. The seal and the ✓ only when the passport verified.
 */
async function passportPng({ card, agent, doc, ok, t, look }) {
  const cs = getComputedStyle(card)
  const paper = cs.backgroundColor
  const ink = cs.color
  // The emblem, the seal and the signature take the card's detail colour (the accent on an Ink card).
  const embEl = card.querySelector('.tn-pemb .tn-emblem')
  const detail = embEl ? getComputedStyle(embEl).color : ink
  const style = look || PASS_STYLE_DEFAULT
  const rtl = cs.direction === 'rtl'
  // The host's faces, as the page uses them (Collapse, JetBrains Mono); loaded before drawing, fallbacks otherwise.
  const fam = { display: "'Collapse', system-ui, sans-serif", mono: "'JetBrains Mono', ui-monospace, monospace", sans: 'system-ui, sans-serif' }
  try {
    await Promise.all([document.fonts.load('700 120px Collapse'), document.fonts.load("500 20px 'JetBrains Mono'")])
  } catch (e) {
    /* the fallback faces draw instead */
  }
  // Arabic: no letter spacing and the sans face for the small labels, as on the page.
  const labelFont = rtl ? fam.sans : fam.mono
  const S = 2
  const W = 1200
  const pad = 64
  const p = doc && doc.passport
  const name = displayName(agent.model)
  const types = agent.types || []
  const shown = types.slice(0, PASS_ROWS)
  const more = types.length - shown.length
  const totals = types.reduce((acc, ty) => ({ f: acc.f + (ty.faults || 0), n: acc.n + (ty.successes || 0) + (ty.faults || 0) }), { f: 0, n: 0 })
  const ROW = 50
  const EMB = 340
  // The name fits the width: largest size up to 168 px.
  const probe = document.createElement('canvas').getContext('2d')
  let nameSize = 168
  probe.font = `700 ${nameSize}px ${fam.display}`
  while (nameSize > 48 && probe.measureText(name).width > W - pad * 2) {
    nameSize -= 4
    probe.font = `700 ${nameSize}px ${fam.display}`
  }
  const yTop = 72
  const yEmb = 112
  const yName = yEmb + EMB + 28 + nameSize * 0.82
  const yRule1 = yName + 44
  const yRows = yRule1 + 22
  const yMore = yRows + shown.length * ROW
  const yRule2 = yMore + (more > 0 ? 40 : 6) + 10
  const yFoot = yRule2 + 40
  const ySig = yFoot + 56
  const H = Math.round(ySig + 40)
  const cv = document.createElement('canvas')
  cv.width = W * S
  cv.height = H * S
  const x = cv.getContext('2d')
  x.setTransform(S, 0, 0, S, 0, 0)
  x.fillStyle = paper
  x.fillRect(0, 0, W, H)
  x.fillStyle = ink
  x.strokeStyle = ink
  x.textBaseline = 'alphabetic'
  x.direction = rtl ? 'rtl' : 'ltr'
  const start = rtl ? W - pad : pad
  const end = rtl ? pad : W - pad
  const at = (dx, w = 0) => (rtl ? W - pad - dx - w : pad + dx)       // a box of width w, dx from the start edge
  const text = (str, px, y, font, align = 'start', spacing = 0) => {
    x.font = font
    try { x.letterSpacing = rtl ? '0px' : `${spacing}px` } catch (e) { /* older engines: no spacing */ }
    x.textAlign = align
    x.fillText(str, px, y)
  }
  const up = str => (rtl ? str : String(str).toLocaleUpperCase())
  const rule = y => {
    x.globalAlpha = 0.35
    x.fillRect(pad, y, W - pad * 2, 1.5)
    x.globalAlpha = 1
  }
  // Top line: TENURE · PASSPORT · ED25519 ✓
  text(up(t('page.title')), start, yTop, `500 17px ${labelFont}`, 'start', 2.4)
  text(up(t('passport.card_title')) + (ok ? ' ✓' : ''), end, yTop, `500 17px ${labelFont}`, 'end', 2.4)
  // Emblem, as a drawing of the same function the card uses.
  const em = document.createElement('canvas')
  paintEmblem(em, { size: EMB, n: 96, share: shareOf(agent), ink: detail, scale: S, pattern: style.pattern, seed: seedOf(agent.agent) })
  x.drawImage(em, (W - EMB) / 2, yEmb, EMB, EMB)
  if (ok) {
    const seal = document.createElement('canvas')
    paintSeal(seal, { size: 96, ink: detail, scale: S })
    x.save()
    x.translate(rtl ? pad + 48 : W - pad - 48, yEmb + 40)
    x.rotate((-10 * Math.PI) / 180)
    x.globalAlpha = 0.92
    x.drawImage(seal, -48, -48, 96, 96)
    x.restore()
  }
  // Name: not mirrored, centred.
  x.direction = 'ltr'
  text(name, W / 2, yName, `700 ${nameSize}px ${fam.display}`, 'center', -nameSize * 0.01)
  x.direction = rtl ? 'rtl' : 'ltr'
  rule(yRule1)
  const BAR_W = 300
  const COUNT_W = 90
  shown.forEach((ty, i) => {
    const tier = tierKey(ty)
    const y = yRows + i * ROW + 30
    text('#' + pad2(i + 1), start, y, `400 17px ${fam.mono}`, 'start')
    x.globalAlpha = 1
    const label = tier === 'trusted' ? t('passport.trusted') : `${TIER_SHORT[tier]} · ${tierName(tier, t)}`
    // Type name, then the tier in the display face; the type is cut to its room.
    x.font = `400 20px ${fam.mono}`
    try { x.letterSpacing = '0px' } catch (e) { /* noop */ }
    const tierFont = tier === 'trusted' ? `400 19px ${rtl ? fam.sans : fam.display}` : `700 19px ${rtl ? fam.sans : fam.display}`
    const room = W - pad * 2 - 56 - BAR_W - COUNT_W - 40
    x.font = tierFont
    try { x.letterSpacing = rtl ? '0px' : '1.4px' } catch (e) { /* noop */ }
    const tierText = up(label)
    const tierW = Math.min(room * 0.55, x.measureText(tierText).width)
    x.font = `400 20px ${fam.mono}`
    try { x.letterSpacing = '0px' } catch (e) { /* noop */ }
    let typ = ty.type
    while (typ.length > 4 && x.measureText(typ).width > room - tierW - 18) typ = typ.slice(0, -2)
    if (typ !== ty.type) typ = typ.slice(0, -1) + '…'
    x.save()
    x.direction = 'ltr'
    x.textAlign = rtl ? 'right' : 'left'
    x.fillText(typ, at(56), y)
    x.restore()
    const typW = x.measureText(typ).width
    x.save()
    x.globalAlpha = tier === 'trusted' ? 0.85 : 1
    text(tierText, at(56 + typW + 18), y, tierFont, 'start', 1.4)
    x.restore()
    const bar = document.createElement('canvas')
    const geo = barGeo(ty)
    const plain = ty.capped || tier === 'trusted' || tier === 'alone'
    paintBar(bar, {
      fill: ty.capped ? 0 : tier === 'trusted' ? 1 : fillOf(ty),
      solid: tier === 'alone',
      trust: tier === 'trusted',
      rows: 6,
      headroom: 0,
      segments: plain ? 0 : geo.segments,
      notch: plain ? null : geo.notch,
      width: BAR_W,
      ink,
      scale: S
    })
    const bx = rtl ? pad + COUNT_W : W - pad - COUNT_W - BAR_W
    if (rtl) {
      x.save()
      x.translate(bx + BAR_W, 0)
      x.scale(-1, 1)
      x.drawImage(bar, 0, y - 12, BAR_W, 12)
      x.restore()
    } else x.drawImage(bar, bx, y - 12, BAR_W, 12)
    if (!ty.capped && tier !== 'trusted') {
      x.save()
      x.direction = 'ltr'
      text(`${ty.series || 0}/${ty.required || 0}`, rtl ? pad : W - pad, y, `500 18px ${fam.mono}`, rtl ? 'left' : 'right')
      x.restore()
    }
  })
  if (more > 0) text(t('passport.more_types', { n: more }), at(56), yMore + 26, `400 16px ${labelFont}`, 'start')
  rule(yRule2)
  text(up(t('passport.faults_checks', { n: totals.f, total: totals.n })), start, yFoot, `500 15px ${labelFont}`, 'start', 1.6)
  const head = p && p.ledger ? String(p.ledger.head).slice(0, 8) : '········'
  x.font = `500 15px ${fam.mono}`
  try { x.letterSpacing = '0.9px' } catch (e) { /* noop */ }
  const headW = x.measureText(head).width
  x.save()
  x.direction = 'ltr'
  text(head, end, yFoot, `500 15px ${fam.mono}`, rtl ? 'left' : 'right', 0.9)
  x.restore()
  text(up(t('passport.ledger')), rtl ? end + headW + 12 : end - headW - 12, yFoot, `500 15px ${labelFont}`, 'end', 1.6)
  // Signature: emblem + TENURE + a plugin for Hermes Agent.
  const sig = document.createElement('canvas')
  paintEmblem(sig, { size: 30, n: 18, share: 1, ink: detail, scale: S })
  x.save()
  x.globalAlpha = 0.85
  x.drawImage(sig, rtl ? W - pad - 30 : pad, ySig - 22, 30, 30)
  x.direction = 'ltr'
  x.font = `700 17px ${fam.display}`
  try { x.letterSpacing = '2px' } catch (e) { /* noop */ }
  const brandW = x.measureText('TENURE').width
  x.textAlign = rtl ? 'right' : 'left'
  x.fillText('TENURE', rtl ? W - pad - 42 : pad + 42, ySig)
  x.direction = rtl ? 'rtl' : 'ltr'
  text(t('passport.signature'), rtl ? W - pad - 42 - brandW - 14 : pad + 42 + brandW + 14, ySig, `400 15px ${labelFont}`, rtl ? 'right' : 'left', 1.8)
  x.restore()
  return await new Promise((resolve, reject) => cv.toBlob(b => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/png'))
}

function PassportSection({ agent, t, n, motion }) {
  const look = usePassStyle()
  const head = agent.totals ? agent.totals.actions : 0
  const cardRef = useRef(null)
  const [drawing, setDrawing] = useState(false)
  const { data: doc, error, isLoading } = useQuery({
    queryKey: ['tenure', agent.profile, 'passport', agent.agent, head],
    queryFn: () => rest(`/passport?agent=${encodeURIComponent(agent.agent)}&of=${encodeURIComponent(agent.profile)}`),
    staleTime: Infinity,
    placeholderData: (previous, query) => (query && query.queryKey[3] === agent.agent ? previous : undefined)
  })
  const ok = doc && Array.isArray(doc.verify) && doc.verify.length === 0
  const problems = (doc && Array.isArray(doc.verify) && doc.verify) || []
  // The verdict in three lines, as on the dashboard: signature, hash chain, replay.
  const verdict = ok
    ? { tone: 'ok', title: t('passport.verdict_ok_title'), lines: [t('passport.verdict_ok_signature'), t('passport.verdict_chain'), t('passport.verdict_ok_replay')] }
    : problems.length === 1 && problems[0] === 'unsigned'
      ? {
          tone: 'warn',
          title: t('passport.verdict_unsigned_title'),
          lines: [t('passport.verdict_chain'), t('passport.verdict_unsigned_replay'), t('passport.verdict_unsigned_no_key', { cmd: hermesCmd(agent.profile, 'passport') })]
        }
      : { tone: 'fault', title: t('passport.verdict_problems', { n: problems.length }), lines: problems }
  const p = doc && doc.passport
  const pending = !!(agent.settings && agent.settings.pending)
  const base = 'passport-' + fileSafe(displayName(agent.model))
  const jsonName = base + '.json'
  const exportCmd = hermesCmd(agent.profile, 'export ledger.jsonl')
  const verifyCmd = `hermes tenure verify ${jsonName} ledger.jsonl`
  // The file `hermes tenure verify` reads: the signed passport exactly as the agent half returned it.
  const download = () => {
    haptic('tap')
    saveBlob(new Blob([JSON.stringify(p, null, 2) + '\n'], { type: 'application/json' }), jsonName)
  }
  const saveImage = async () => {
    if (!cardRef.current || drawing) return
    setDrawing(true)
    try {
      const blob = await passportPng({ card: cardRef.current, agent, doc, look, ok: !!ok, t })
      haptic('tap')
      saveBlob(blob, base + '.png')
    } catch (e) {
      host.notifyError(e, t('passport.image_failed'))
    } finally {
      setDrawing(false)
    }
  }
  return jsxs('section', {
    className: 'tn-section',
    children: [
      jsx('div', { className: 'tn-section-head', children: jsx(Eyebrow, { n, children: t('passport.title') }) }),
      jsxs('div', {
        className: 'tn-pass-grid',
        children: [
          jsx(PassportCard, { agent, doc, look, motion, ok: !!ok, outerRef: cardRef, settled: !!error || (!!doc && !isLoading), t }, agent.key + look.animation),
          jsxs('div', {
            className: 'tn-pass-acts',
            children: [
              jsxs('button', {
                className: 'tn-btn',
                'data-kind': 'primary',
                disabled: !p,
                onClick: download,
                type: 'button',
                children: [jsx(Codicon, { name: 'desktop-download', size: '0.8rem' }), t('passport.download')]
              }),
              jsxs('button', {
                'aria-busy': drawing ? 'true' : undefined,
                className: 'tn-btn',
                disabled: !p || drawing,
                onClick: saveImage,
                type: 'button',
                children: [jsx(Codicon, { name: drawing ? 'loading' : 'file-media', size: '0.8rem', spinning: drawing }), t('passport.save_image')]
              }),
              jsxs('button', {
                className: 'tn-linkbtn',
                onClick: () => {
                  focusPassStyle = true
                  openView('settings')
                },
                type: 'button',
                children: [jsx(Codicon, { name: 'paintcan', size: '0.75rem' }), t('pstyle.customise')]
              }),
              jsx('p', { className: 'tn-hint', style: { margin: 0 }, children: t('passport.note') })
            ]
          }),
          jsxs('div', {
            className: 'tn-pass-side',
            children: [
              pending ? jsx('p', { className: 'tn-note', children: t('passport.pending_note') }) : null,
              isLoading && !doc
                ? jsxs('p', { className: 'tn-status', style: { margin: 0 }, children: [jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }), t('passport.verifying')] })
                : error
                  ? jsxs('div', {
                      className: 'tn-status',
                      'data-ok': 'false',
                      role: 'status',
                      children: [
                        jsx(Codicon, { className: 'mt-px shrink-0', name: 'warning', size: '0.85rem' }),
                        jsx('span', { className: 'min-w-0 break-words', children: t('passport.unavailable', { error: error.message || String(error) }) })
                      ]
                    })
                  : jsxs('div', {
                      className: 'tn-status tn-verdict',
                      'data-ok': verdict.tone === 'ok' ? 'true' : 'false',
                      'data-tone': verdict.tone,
                      role: 'status',
                      children: [
                        jsx(Codicon, { className: 'mt-px shrink-0', name: verdict.tone === 'ok' ? 'verified-filled' : 'warning', size: '0.85rem' }),
                        jsxs('div', {
                          className: 'min-w-0 break-words',
                          children: [
                            jsx('b', { className: 'tn-verdict-title', children: verdict.title }),
                            jsx('ul', { className: 'tn-verdict-lines', children: verdict.lines.map((l, i) => jsx('li', { children: l }, i)) })
                          ]
                        })
                      ]
                    }),
              p
                ? jsx(PanelMeta, {
                    rows: [
                      { label: t('passport.protocol'), value: jsx('span', { className: 'font-mono', children: p.protocol }) },
                      { label: t('passport.field_agent'), value: jsx('span', { className: 'font-mono tn-bdi', children: `${(p.agent || {}).model}@${(p.agent || {}).provider}` }) },
                      {
                        label: t('passport.rule'),
                        value: jsxs('span', {
                          children: [
                            jsx('span', { className: 'font-mono', children: `${p.rule.name} · ${String(p.rule.fingerprint).slice(0, 16)}` }),
                            ' · ',
                            jsx(ExtLink, { href: OSF_URL, children: t('passport.rule_osf') })
                          ]
                        })
                      },
                      { label: t('passport.ledger'), value: jsx('span', { children: t('passport.ledger_value', { n: p.ledger.count, head: String(p.ledger.head).slice(0, 12) }) }) },
                      { label: t('passport.generated'), value: when(p.generated_at) },
                      { label: t('passport.field_profile'), value: jsx('span', { className: 'font-mono', children: t('passport.value_hashed', { profile: (p.agent || {}).profile }) }) },
                      { label: t('passport.field_settings'), value: jsx('span', { className: 'font-mono', children: short(p.settings_fingerprint, 16) }) },
                      { label: t('passport.field_public_key'), value: jsx('span', { className: 'font-mono', children: p.public_key ? short(p.public_key, 24) : t('passport.value_none') }) },
                      { label: t('passport.field_signature'), value: jsx('span', { className: 'font-mono', children: p.signature ? short(p.signature, 24) + '…' : t('passport.value_unsigned') }) },
                      { label: t('passport.field_type_names'), value: p.redacted ? t('passport.value_redacted') : t('passport.value_raw') }
                    ]
                  })
                : null,
              p
                ? jsxs('div', {
                    className: 'tn-verify',
                    children: [
                      jsx('p', { className: 'tn-hint', children: t('passport.ledger_hint') }),
                      jsx(Cmd, { t, text: exportCmd }),
                      jsx('p', { className: 'tn-hint', children: t('passport.verify_hint') }),
                      jsx(Cmd, { t, text: verifyCmd })
                    ]
                  })
                : null
            ]
          })
        ]
      }),
      p && (p.types || []).length ? jsx(PassportTypes, { live: agent.types || [], t, types: p.types }) : null
    ]
  })
}

/** The passport's attested types, as the dashboard lists them: a type the trusted start covers shows "—" and
 *  "Trusted (not earned)", never a tier it did not earn. */
function PassportTypes({ types, live, t }) {
  const byType = new Map(live.map(ty => [ty.type, ty]))
  return jsxs('div', {
    className: 'tn-pass-types',
    children: [
      jsx(Eyebrow, { children: t('passport.types_title') }),
      jsx('div', {
        className: 'tn-map-scroll',
        children: jsxs('table', {
          className: 'tn-table',
          children: [
            jsx('thead', {
              children: jsxs('tr', {
                children: [
                  jsx('th', { children: t('undo.col_type') }),
                  jsx('th', { children: t('passport.col_tier') }),
                  jsx('th', { className: 'tn-end', children: t('passport.col_series') }),
                  jsx('th', { className: 'tn-end', children: t('passport.col_sessions') }),
                  jsx('th', { children: t('passport.col_guarantee') })
                ]
              })
            }),
            jsx('tbody', {
              children: types.map(ty => {
                const g = ty.guarantee || {}
                const m = byType.get(ty.type)
                const eff = ty.effective_tier || ty.tier
                const trust = !!(m && m.trusted && eff !== 'alone') && !g.capped
                const tier = g.capped ? 'cap' : trust ? 'trusted' : eff || 'ask'
                const stakes = ['low', 'medium', 'high'].includes(ty.stakes) ? t('type.stakes_' + ty.stakes) : t('type.stakes_other', { stakes: ty.stakes })
                return jsxs(
                  'tr',
                  {
                    children: [
                      jsxs('td', { children: [jsx('code', { className: 'tn-mono tn-bdi', children: ty.type }), jsx('div', { className: 'tn-hint', children: stakes })] }),
                      jsxs('td', {
                        children: [
                          jsx(TierChip, { motion: false, t, tier }),
                          jsx('div', { className: 'tn-hint', children: trust ? t('passport.trusted') : TierLabel(tier, t) })
                        ]
                      }),
                      jsx('td', { className: 'tn-end tn-mono', children: trust || ty.required == null ? '—' : num(ty.series) + '/' + num(ty.required) }),
                      jsx('td', { className: 'tn-end tn-mono', children: trust ? '—' : num(ty.sessions) }),
                      jsx('td', {
                        children: g.capped
                          ? jsx('span', { className: 'tn-hint', children: t('legend.capped') })
                          : trust
                            ? jsx('span', { className: 'tn-hint', children: t('type.trusted_no_guarantee') })
                            : jsx(Guarantee, { g, t })
                      })
                    ]
                  },
                  ty.type
                )
              })
            })
          ]
        })
      })
    ]
  })
}

/** The Passport tab: any agent's signed passport, picked from a list; the same section as on the agent's page. */
function PassportView({ data, t }) {
  const motion = useMotion()
  const agents = allAgents(data)
  const [sel, setSel] = useState(() => focusKey)
  const a = agents.find(x => x.key === sel) || agents[0]
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc tn-doc-wide',
      children: [
        jsxs('header', {
          className: 'tn-hero',
          style: { display: 'block' },
          children: [
            jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_passport') }),
            agents.length ? null : jsx('h3', { className: 'tn-name', children: t('passport.empty_title') }),
            agents.length ? null : jsx('p', { className: 'tn-intro-body', style: { margin: '0.35rem 0 0' }, children: t('passport.empty_body') })
          ]
        }),
        agents.length
          ? jsxs('label', {
              className: 'tn-field',
              style: { maxWidth: '28rem' },
              children: [
                jsx('span', { className: 'tn-eyebrow', children: t('passport.agent') }),
                jsx('select', {
                  className: 'tn-input',
                  onChange: e => setSel(e.target.value),
                  value: a ? a.key : '',
                  children: agents.map(x => jsx('option', { value: x.key, children: `${displayName(x.model)}@${x.provider} · ${x.profile}` }, x.key))
                })
              ]
            })
          : null,
        a ? jsx(PassportSection, { agent: a, motion, n: 1, t }, a.key) : null
      ]
    })
  })
}

// ------------------------------------------------------------------------------------------------ live transitions
// Animations play on real state transitions only: each render diffs the types against the previous answer for the
// same agent. The first sight of an agent records its state and plays nothing (the entrance plays instead).
const seen = new Map()                               // agent key -> Map(type -> { rank, faults, spots })

function useTransitions(agent) {
  const [changes, setChanges] = useState({})
  const [moment, setMoment] = useState(null)
  const [pulse, setPulse] = useState(0)
  const [crumble, setCrumble] = useState(0)
  const timers = useRef([])
  useEffect(() => () => timers.current.forEach(clearTimeout), [])
  useEffect(() => {
    const now = new Map((agent.types || []).map(ty => [ty.type, { rank: TIER_RANK[tierKey(ty)], faults: ty.faults || 0, spots: ty.spot_checks || 0 }]))
    const prev = seen.get(agent.key)
    seen.set(agent.key, now)
    if (!prev) return
    const out = {}
    let best = null
    let fault = false
    const stamp = Date.now()
    const rankOf = m => ({ granted: 3, probation: 2, on_probation: 2, review: 1 })[m.kind]
    for (const ty of agent.types || []) {
      const a = prev.get(ty.type)
      const b = now.get(ty.type)
      if (!a) continue
      let m = null
      if (b.faults > a.faults) {
        // A fault, and only a fault, crumbles the bar; "Back on probation" when it sent an earned type back to T1.
        out[ty.type] = { dir: 'down', token: stamp + ty.type }
        fault = true
        // "On probation" for a type the trusted start covered (nothing earned to come back from), else "Back on…".
        if (b.rank === TIER_RANK.ask && a.rank > TIER_RANK.ask) m = { kind: a.rank === TIER_RANK.trusted ? 'on_probation' : 'probation', type: ty }
      } else if (b.rank < a.rank) {
        // A drop without a fault (a revoke, stricter settings, a stakes change, a copied profile): no crumble, no band.
        out[ty.type] = { dir: 'reprint', token: stamp + ty.type }
      } else if (b.rank > a.rank) {
        out[ty.type] = { dir: 'up', token: stamp + ty.type }
        // CAP -> T1 is no promotion: a moment only from T2 up, "Under review" for T2, "Tenure granted" for T3.
        if (b.rank === TIER_RANK.alone) m = { kind: 'granted', type: ty }
        else if (b.rank === TIER_RANK.notify) m = { kind: 'review', type: ty }
      } else if (b.spots > a.spots) out[ty.type] = { dir: 'spot', token: stamp + ty.type }
      if (m && (!best || rankOf(m) > rankOf(best))) best = m
    }
    if (Object.keys(out).length) {
      setChanges(c => ({ ...c, ...out }))
      // The scan line plays once: the spot-check change is gone after its 900 ms sweep.
      const spots = Object.keys(out).filter(k => out[k].dir === 'spot')
      if (spots.length)
        timers.current.push(
          setTimeout(() => setChanges(c => {
            const next = { ...c }
            for (const k of spots) if (next[k] && next[k].token === out[k].token) delete next[k]
            return next
          }), 950)
        )
    }
    if (best && (best.kind === 'granted' || best.kind === 'review')) setPulse(x => x + 1)
    else if (fault) setCrumble(x => x + 1)
    if (best) setMoment({ ...best, key: stamp })
  }, [agent])
  return { changes, moment, pulse, crumble, dismiss: key => setMoment(m => (m && m.key === key ? null : m)) }
}

const momentDown = moment => moment.kind === 'probation' || moment.kind === 'on_probation'
const momentTitle = (moment, t) =>
  moment.kind === 'probation'
    ? t('moment.probation')
    : moment.kind === 'on_probation'
      ? t('moment.on_probation')
      : moment.kind === 'granted'
        ? t('moment.granted')
        : t('moment.review')

/** C / D. The big moment, once: a filled accent band for a promotion, a quiet card for a fault (the repair path). */
function MomentBand({ moment, agent, t, motion, onClose }) {
  const ref = useRef(null)
  const [leaving, setLeaving] = useState(false)
  const leave = useRef(0)
  const close = () => {
    if (!motion) return onClose()
    setLeaving(true)
    clearTimeout(leave.current)
    leave.current = setTimeout(onClose, 280)
  }
  useEffect(() => {
    const id = setTimeout(close, 6000)
    return () => {
      clearTimeout(id)
      clearTimeout(leave.current)
    }
  }, [moment.key])
  const down = momentDown(moment)
  const paintFade = k => {
    const cv = ref.current
    if (!cv) return
    const w = cv.clientWidth
    const h = 44
    const dpr = fitCanvas(cv, w, h)
    const x = cv.getContext('2d')
    x.setTransform(dpr, 0, 0, dpr, 0, 0)
    x.clearRect(0, 0, w, h)
    x.fillStyle = inkOf(cv)
    const c = 4
    const rows = h / c
    for (let j = 0; j < rows; j++) {
      const v = (j / rows) * k
      for (let i = 0; i < w / c; i++) if (v > bayer(i, j) + ((i * 7) % 3) * 0.02) x.fillRect(i * c, j * c, c - 0.8, c - 0.8)
    }
  }
  useRepaint(() => paintFade(1))
  useWidth(ref, () => paintFade(1))
  useEffect(() => {
    if (down) return
    if (!motion) return paintFade(1)
    return tween(1000, k => paintFade(k), null, 200)
  }, [moment.key, motion])
  const ty = moment.type
  const title = momentTitle(moment, t)
  // T2: it acts again, then tells you (the band says so in words); T3: the tier's own line.
  const sub = down
    ? nextLine(ty, t, (agent.settings || {}).spot)
    : moment.kind === 'review'
      ? t('moment.review_sub', { name: displayName(agent.model) })
      : `${displayName(agent.model)} · ${TierLabel(tierKey(ty), t)}`
  const geo = barGeo(ty)
  return jsxs('div', {
    className: cn(down ? 'tn-fault' : 'tn-band', leaving && 'tn-leaving', motion && 'tn-enter'),
    'data-motion': motion ? 'on' : 'off',
    children: [
      jsx('button', { 'aria-label': t('moment.dismiss'), className: 'tn-band-close', onClick: close, type: 'button', children: jsx(Codicon, { name: 'close', size: '0.8rem' }) }),
      jsxs('div', {
        'aria-hidden': true,
        className: down ? undefined : 'tn-band-in',
        children: [
          jsx('div', { className: 'tn-eyebrow', children: t(down ? 'moment.eyebrow_down' : 'moment.eyebrow_up', { type: ty.type }) }),
          jsx('div', { className: 'tn-band-title', children: title }),
          jsx('div', { className: 'tn-band-sub', children: sub })
        ]
      }),
      down
        ? jsx('div', { style: { marginBlockStart: '0.75rem' }, children: jsx(DitherBar, { change: { dir: 'down', token: moment.key }, motion, notch: geo.notch, segments: geo.segments, value: fillOf(ty) }) })
        : jsx('canvas', { 'aria-hidden': true, className: 'tn-mirror', ref })
    ]
  })
}

function AgentDetail({ agent, t, onRevoke }) {
  const motion = useMotion()
  const qc = useQueryClient()
  const mine = agent.profile === useValue(host.state.profile)
  const [acting, setActing] = useState(null)        // { kind: 'flag' | 'revoke', type }
  const tot = agent.totals || {}
  const s = agent.settings || {}
  const types = agent.types || []
  const { changes, moment, pulse, crumble, dismiss } = useTransitions(agent)
  const t3 = types.filter(ty => tierKey(ty) === 'alone').length
  const t2 = types.filter(ty => tierKey(ty) === 'notify').length
  const nTrusted = types.filter(ty => tierKey(ty) === 'trusted').length
  const start = startOf(s, types)
  const startTrusted = start === 'trusted'
  // Earned tiers first; trusted types are named apart, never as autonomy earned.
  const caption =
    [t3 ? t('emblem.tenured', { n: t3 }) : null, t2 ? t('emblem.review', { n: t2 }) : null, !t3 && !t2 ? t('emblem.none') : null, nTrusted ? t('emblem.trusted', { n: nTrusted }) : null]
      .filter(Boolean)
      .join(' · ')
  const stat = (value, label, tip) =>
    jsxs('span', {
      className: 'tn-stat',
      children: [
        tip ? jsx(Tip, { label: tip, children: jsx('b', { tabIndex: 0, children: String(value || 0) }) }) : jsx('b', { children: String(value || 0) }),
        jsx('span', { children: label })
      ]
    })
  return jsxs(PanelDetail, {
    className: 'tn-root tn-detail',
    children: [
      jsx('div', {
        'aria-live': 'polite',
        className: 'tn-sr',
        role: 'status',
        children: moment ? `${momentTitle(moment, t)} · ${moment.type.type} · ${momentDown(moment) ? nextLine(moment.type, t, s.spot) : TierLabel(tierKey(moment.type), t)}` : ''
      }),
      jsxs('header', {
        className: 'tn-hero',
        children: [
          jsxs('div', {
            className: 'tn-hero-main',
            children: [
              jsxs('div', {
                className: 'tn-eyebrow',
                children: [
                  '#' + t('hero.agent'),
                  jsx('span', { className: 'tn-dim', children: ' · ' }),
                  jsx(Tip, { label: t('meta.provider'), children: jsx('span', { className: 'tn-bdi', tabIndex: 0, children: agent.provider }) }),
                  jsx('span', { className: 'tn-dim', children: ' · ' }),
                  `${t('meta.profile')} `,
                  jsx('span', { className: 'tn-bdi', children: agent.profile })
                ]
              }),
              jsx(Tip, { label: agent.agent, children: jsx('h3', { className: 'tn-name', children: displayName(agent.model) }) }),
              jsxs('div', {
                className: 'tn-pills',
                children: [
                  jsx(TierChip, { motion, t, tier: bestTier(agent) }),
                  agent.provisional ? jsx(StatePill, { label: t('state.provisional'), tip: t('state.provisional_tip'), t }) : null,
                  agent.trial ? jsx(StatePill, { label: t('state.trial'), tip: t('state.trial_tip'), t }) : null,
                  agent.unresolved_fault ? jsx(StatePill, { kind: 'fault', label: t('state.fault'), tip: t('state.fault_tip'), t }) : null,
                  agent.suspended ? jsx(StatePill, { kind: 'fault', label: t('state.suspended'), tip: t('state.suspended_tip'), t }) : null
                ]
              }),
              jsxs('div', {
                className: 'tn-stats',
                children: [
                  stat(tot.actions, t('meta.actions'), t('meta.actions_tip')),
                  stat(tot.checked, t('meta.checked')),
                  stat(tot.alone, t('meta.alone')),
                  stat(tot.faults, t('meta.faults'))
                ]
              }),
              jsxs('p', {
                className: 'tn-preset',
                style: { margin: 0 },
                children: [
                  jsx('span', { children: t('meta.preset') }),
                  jsx('span', {
                    children:
                      t(s.pending ? 'preset.value_pending' : 'preset.value', { preset: presetName(t, s.preset || 'balanced'), k: Math.round(1 / (s.spot || 0.1)) }) +
                      (s.copy_pending ? ' · ' + t('preset.copy_pending') : '')
                  })
                ]
              }),
              start
                ? jsxs('p', {
                    className: 'tn-preset',
                    style: { margin: 0 },
                    children: [
                      jsx('span', { children: t('meta.start') }),
                      jsx(Tip, {
                        label: t('start.change_tip'),
                        children: jsxs('span', {
                          'aria-label': t(startTrusted ? 'start.trusted' : 'start.probation') + ' · ' + t('start.change_tip'),
                          className: 'tn-start',
                          'data-start': start,
                          tabIndex: 0,
                          children: [jsx('i', { 'aria-hidden': true }), t(startTrusted ? 'start.trusted' : 'start.probation')]
                        })
                      })
                    ]
                  })
                : null
            ]
          }),
          jsxs('div', {
            className: 'tn-hero-side',
            children: [
              jsxs('div', {
                style: { alignSelf: 'flex-end', display: 'flex', gap: '0.25rem' },
                children: [
                  jsx(PanelAction, { icon: 'arrow-swap', onClick: () => openView('switch', agent.key), children: t('page.view_switch') }),
                  jsx(PanelAction, { icon: 'circle-slash', onClick: onRevoke, children: t('revoke.action') })
                ]
              }),
              jsx(Emblem, { crumble, label: caption, motion, n: 60, pulse, rotate: true, share: shareOf(agent), size: 120 }, agent.key),
              jsx('div', { 'aria-hidden': true, className: 'tn-emblem-cap', children: caption })
            ]
          })
        ]
      }),
      moment ? jsx(MomentBand, { agent, moment, motion, onClose: () => dismiss(moment.key), t }, moment.key) : null,
      jsxs('section', {
        className: 'tn-section',
        children: [
          jsx(Eyebrow, { n: 1, children: t('types.title') }),
          jsx('div', {
            className: 'tn-rows',
            children: types.map((ty, i) =>
              jsx(TypeRow, { change: changes[ty.type], index: i, mine, motion, onAct: (kind, type) => setActing({ kind, type }), spot: s.spot, t, type: ty }, agent.key + '|' + ty.type)
            )
          })
        ]
      }),
      jsx(RecentSection, { agent, n: 2, t }),
      jsx(PassportSection, { agent, motion, n: 3, t }),
      jsx(TimelineSection, { agent, n: 4, t }),
      jsx(ConfirmDialog, {
        confirmLabel: acting && acting.kind === 'flag' ? t('type.flag_button') : t('type.revoke_button'),
        description: acting ? (acting.kind === 'flag' ? t('confirm.flag_desc', { type: acting.type.type }) : t('confirm.revoke_desc', { type: acting.type.type })) : null,
        destructive: true,
        onClose: () => setActing(null),
        onConfirm: async () => {
          const { kind, type } = acting
          const body = { agent: agent.agent, type: type.type }
          try {
            const r = await rest('/' + kind + '?of=' + encodeURIComponent(agent.profile), { method: 'POST', body })
            const tier = TIER_SHORT[r && r.tier] || ''
            haptic('success')
            host.notify({ kind: 'success', message: kind === 'flag' ? t('type.flag_done', { type: type.type, tier }) : t('type.revoke_done', { type: type.type }) })
          } catch (e) {
            host.notifyError(e, kind === 'flag' ? t('confirm.flag_title', { type: type.type }) : t('confirm.revoke_title', { type: type.type }))
          } finally {
            qc.invalidateQueries({ queryKey: ['tenure'] })
          }
        },
        open: acting !== null,
        title: acting ? (acting.kind === 'flag' ? t('confirm.flag_title', { type: acting.type.type }) : t('confirm.revoke_title', { type: acting.type.type })) : ''
      })
    ]
  })
}
function AgentsView({ data, t }) {
  const agents = allAgents(data)
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(() => focusKey || (agents[0] && agents[0].key) || null)
  const [pending, setPending] = useState(null)
  useEffect(() => {
    const onFocus = e => {
      if (e.detail.key) setSelected(e.detail.key)
      if (e.detail.revoke) setPending(agents.find(a => a.key === e.detail.key) || null)
      focusKey = null
    }
    bus.addEventListener('focus', onFocus)
    if (focusKey) onFocus({ detail: { key: focusKey, revoke: focusRevoke } })
    focusRevoke = false
    return () => bus.removeEventListener('focus', onFocus)
  }, [data])
  const q = query.trim().toLowerCase()
  const visible = agents.filter(a => !q || a.agent.toLowerCase().includes(q))
  const agent = visible.find(a => a.key === selected) || visible[0] || null
  const profiles = [...new Set(visible.map(a => a.profile))]
  return jsxs(PanelBody, {
    className: 'px-4 pb-4',
    children: [
      jsxs(PanelList, {
        onSearchChange: setQuery,
        searchLabel: t('agents.search'),
        searchPlaceholder: t('agents.search'),
        searchValue: query,
        children: [
          ...profiles.flatMap(profile => [
            profiles.length > 1 || profile !== data.current ? jsx(PanelSectionLabel, { className: 'mt-2 px-2', children: profile }, 'label-' + profile) : null,
            ...visible
              .filter(a => a.profile === profile)
              .map(a =>
                jsx(
                  PanelListRow,
                  {
                    active: !!agent && agent.key === a.key,
                    dotClassName: TIER_DOT[bestTier(a)],
                    menuItems: [{ icon: 'circle-slash', label: t('revoke.action'), onSelect: () => setPending(a) }],
                    menuLabel: displayName(a.model),
                    meta: tierShort(bestTier(a), t),
                    onSelect: () => setSelected(a.key),
                    rowKey: a.key,
                    title: displayName(a.model)
                  },
                  a.key
                )
              )
          ]),
          visible.length === 0 ? jsx('p', { className: 'px-2 py-4 text-center text-xs text-muted-foreground', children: t('common.no_match') }, 'nomatch') : null
        ]
      }),
      agent ? jsx(AgentDetail, { agent, t, onRevoke: () => setPending(agent) }, agent.key) : jsx(PanelEmpty, { description: q ? t('common.no_match') : t('agents.pick'), icon: q ? 'search' : 'shield' }),
      jsx(ConfirmDialog, {
        busyLabel: t('revoke.busy'),
        confirmLabel: t('revoke.confirm'),
        description: pending
          ? jsxs('span', { children: withNode(t, 'revoke.desc', 'name', jsx('span', { className: 'font-medium text-foreground', children: displayName(pending.model) }, 'name')) })
          : null,
        destructive: true,
        onClose: () => setPending(null),
        onConfirm: async () => {
          await revokeAgent(pending, t)
          qc.invalidateQueries({ queryKey: ['tenure'] })
        },
        open: pending !== null,
        title: t('revoke.title')
      })
    ]
  })
}


const RANK_MIN = 20 // checks on a type before a model is ranked on it

function BenchmarkView({ t }) {
  const profile = useValue(host.state.profile)
  const motion = useMotion()
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['tenure', profile, 'models'], queryFn: () => rest('/models') })
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  if (isLoading) return jsx(PanelEmpty, { description: t('common.loading'), icon: 'loading~spin' })
  if (error)
    return jsx(ErrorState, {
      description: error.message || String(error),
      title: t('backend.title'),
      children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('common.retry') })
    })
  const rows = (data && data.rows) || []
  if (!rows.length)
    return jsx(PanelEmpty, { description: t('benchmark.empty_body', { cmd: 'hermes tenure models' }), icon: 'graph', title: t('benchmark.empty_title') })
  const types = [...new Set(rows.map(r => r.type))]
  const q = query.trim().toLowerCase()
  const visibleTypes = types.filter(x => !q || x.toLowerCase().includes(q))
  const type = selected && visibleTypes.includes(selected) ? selected : visibleTypes[0]
  // Ranked from RANK_MIN checks on the type: below that, the 95 % range is too wide to order anything.
  const ofType = rows.filter(r => r.type === type)
  const ranked = ofType.filter(r => r.successes + r.faults >= RANK_MIN)
  const waiting = ofType.filter(r => r.successes + r.faults < RANK_MIN)
  const max = Math.min(1, Math.max(0.05, Math.ceil(Math.max(0, ...ranked.map(r => r.high || 0)) * 20) / 20))
  const pub = (ofType.find(r => r.public) || {}).public
  // The public column only when most ranked models have a public score.
  const showPub = ranked.length > 0 && ranked.filter(r => r.public && r.public.new != null).length * 2 >= ranked.length
  return jsxs(PanelBody, {
    className: 'px-4 pb-4',
    children: [
      jsxs(PanelList, {
        onSearchChange: setQuery,
        searchLabel: t('benchmark.search'),
        searchPlaceholder: t('benchmark.search'),
        searchValue: query,
        children: [
          ...visibleTypes.map(x =>
            jsx(
              PanelListRow,
              {
                active: x === type,
                icon: 'symbol-event',
                meta: String(rows.filter(r => r.type === x && r.successes + r.faults >= RANK_MIN).length),
                onSelect: () => setSelected(x),
                rowKey: x,
                title: jsx('span', { className: 'font-mono', children: x })
              },
              x
            )
          ),
          visibleTypes.length === 0 ? jsx('p', { className: 'px-2 py-4 text-center text-xs text-muted-foreground', children: t('common.no_match') }, 'nomatch') : null
        ]
      }),
      !type
        ? jsx(PanelEmpty, { description: t('common.no_match'), icon: 'search' })
        : jsxs(PanelDetail, {
            className: 'tn-root tn-detail',
            children: [
              jsxs('header', {
                className: 'tn-hero',
                style: { display: 'block' },
                children: [
                  jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_benchmark') }),
                  jsx('h3', { className: 'tn-name', style: { fontFamily: 'var(--tn-mono)', fontWeight: 500, fontSize: 'clamp(1.4rem,3vw,2rem)', letterSpacing: 0 }, children: type }),
                  jsx('p', { className: 'tn-intro-body', style: { margin: 0 }, children: t('benchmark.note') })
                ]
              }),
              jsxs('div', {
                'aria-hidden': true,
                className: 'tn-bench tn-bench-h',
                'data-pub': showPub ? 'true' : 'false',
                'data-s': 'true',
                children: [
                  jsx('span', {}),
                  jsx('span', {}),
                  jsx('span', { className: 'tn-eyebrow tn-end', children: t('benchmark.col_faults') }),
                  jsx('span', { className: 'tn-eyebrow', children: t('benchmark.col_range') }),
                  jsx('span', { className: 'tn-eyebrow', children: t('benchmark.col_rate') }),
                  jsx('span', { className: 'tn-eyebrow tn-end', children: t('benchmark.col_sessions') }),
                  showPub ? jsx('span', { className: 'tn-eyebrow tn-end', children: t('benchmark.col_public') }) : null
                ]
              }),
              jsx('div', {
                className: 'flex flex-col',
                children: ranked.map((r, i) =>
                  jsxs(
                    'div',
                    {
                      className: cn('tn-bench', motion && 'tn-enter'),
                      'data-pub': showPub ? 'true' : 'false',
                      'data-s': 'true',
                      style: motion ? { animationDelay: `${i * 40}ms` } : undefined,
                      children: [
                        jsx('span', { className: 'tn-tnum', style: { paddingBlockStart: 0 }, children: '#' + pad2(i + 1) }),
                        jsxs('span', {
                          className: 'tn-bm',
                          children: [
                            jsx(Tip, { label: r.agent, children: jsx('span', { style: { color: 'var(--tn-fg)' }, children: displayName(r.model) }) }),
                            jsx('span', { className: 'tn-bsub tn-bdi', children: `${r.provider} · ${r.profile}` })
                          ]
                        }),
                        jsx('span', { className: 'tn-bnum tn-end', children: t('benchmark.faults', { n: r.faults, total: r.successes + r.faults }) }),
                        jsx(Tip, {
                          label: t('benchmark.range_tip', { max: pct(max) }),
                          children: jsx('span', {
                            'aria-label': t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }),
                            role: 'img',
                            style: { display: 'block', outline: 'none' },
                            tabIndex: 0,
                            children: jsx(RangeBar, { delay: 80 + i * 40, high: r.high, low: r.low, max, motion, rate: r.rate })
                          })
                        }),
                        r.enough === false
                          ? jsx('span', { className: 'tn-bnum tn-dim', children: t('benchmark.not_enough') })
                          : jsx('span', { className: 'tn-bnum', children: t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }) }),
                        jsx('span', { className: 'tn-bnum tn-end', children: num(r.sessions_in_series) }),
                        showPub
                          ? jsx(Tip, {
                              label: pub ? t('benchmark.public_score', { benchmark: pub.benchmark, source: pub.source }) : '',
                              children: jsx('span', {
                                className: 'tn-bnum tn-end',
                                children: r.public && r.public.new != null ? t('benchmark.public_value', { value: dec1(Number(r.public.new)) }) : t('benchmark.no_public')
                              })
                            })
                          : null
                      ]
                    },
                    type + '|' + r.agent + r.profile
                  )
                )
              }),
              waiting.length
                ? jsxs('div', {
                    className: 'tn-section',
                    style: { marginBlockStart: '0.5rem' },
                    children: [
                      jsx(Eyebrow, { children: t('benchmark.not_ranked') }),
                      jsx('p', { className: 'tn-intro-body', style: { margin: 0 }, children: t('benchmark.not_ranked_note', { n: RANK_MIN }) }),
                      jsx('div', {
                        className: 'tn-wait',
                        children: waiting.map(r =>
                          jsx(Tip, { label: `${r.provider} · ${r.profile}`, children: jsx('span', { tabIndex: 0, children: displayName(r.model) }) }, r.agent + r.profile)
                        )
                      })
                    ]
                  })
                : null,
              // The public measure, as information: whose score, how it was obtained, and what it does not say.
              jsxs('div', {
                style: { display: 'flex', flexDirection: 'column', gap: '0.15rem', fontSize: '0.7rem', color: 'var(--tn-fg2)' },
                children: [
                  pub
                    ? jsx('p', {
                        style: { margin: 0 },
                        children: pub.accessed
                          ? t('benchmark.source_accessed', { source: [pub.benchmark, pub.source].filter(Boolean).join(' · '), accessed: pub.accessed })
                          : t('benchmark.source', { source: [pub.benchmark, pub.source].filter(Boolean).join(' · ') })
                      })
                    : jsx('p', { style: { margin: 0 }, children: t('benchmark.no_public_type') }),
                  jsx('p', { style: { margin: 0, color: 'var(--tn-fg)' }, children: t('benchmark.public_note') })
                ]
              })
            ]
          })
    ]
  })
}

// ------------------------------------------------------------------------------------------------ settings & help
// params.PRESETS (tenure/params.py): the accepted share of unchecked errors per stakes level; null = capped (always asks).
const PRESETS = {
  careful: { low: 1 / 100, medium: 1 / 200, high: 1 / 1000 },
  balanced: { low: 1 / 50, medium: 1 / 100, high: null },
  fast: { low: 1 / 20, medium: 1 / 50, high: null }
}
const LEVELS = ['low', 'medium', 'high']
// params.study_n: the series T3 needs, N = ceil(1 / (DETECTION * bar)) - 1 with DETECTION = 0.95 (rounded to 9 places
// first, so a float a hair above a whole number does not add one).
const studyN = bar => Math.ceil(Number((1 / (0.95 * bar)).toFixed(9))) - 1
// params.DEFAULT_PRESET / DEFAULT_START / DEFAULT_SPOT: what applies before a profile logged any settings.
const DEFAULTS = { preset: 'balanced', start: 'trusted', spot: 0.1, strict: false }

function SettingRow({ n, title, help, children, id }) {
  return jsxs('section', {
    className: 'tn-hrow',
    id,
    children: [
      jsx('div', { 'aria-hidden': true, className: 'tn-tnum', children: '#' + pad2(n) }),
      jsxs('div', {
        className: 'tn-hbody',
        children: [jsx('h4', { className: 'tn-htitle', children: title }), help ? jsx('p', { className: 'tn-htext', children: help }) : null, children]
      })
    ]
  })
}

// The last settings the agent half confirmed after a save (it reports `enabled` only there).
const savedSettings = { enabled: null }

/** The HTTP status of a failed ctx.rest call, from the error or its message. */
const statusOf = e => Number((e && (e.status || e.statusCode || (e.response && e.response.status))) || (String((e && e.message) || e).match(/\b(4\d\d|5\d\d)\b/) || [])[1] || 0)

/**
 * Saves through the agent half's POST /settings (Hermes' own plugin-settings writer). State: idle | saving | saved |
 * error | nowriter (501/403: this Hermes cannot save here, the command is the way). Re-fetches after a save, so the
 * page shows what is in force, never what was asked.
 */
function useSave(profile) {
  const qc = useQueryClient()
  const [st, setSt] = useState({ state: 'idle', error: '' })
  const timer = useRef(0)
  useEffect(() => () => clearTimeout(timer.current), [])
  const run = async body => {
    clearTimeout(timer.current)
    setSt({ state: 'saving', error: '' })
    try {
      const out = await rest('/settings?of=' + encodeURIComponent(profile), { method: 'POST', body })
      if (out && out.settings && typeof out.settings.enabled === 'boolean') savedSettings.enabled = out.settings.enabled
      haptic('success')
      setSt({ state: 'saved', error: '' })
      timer.current = setTimeout(() => setSt(x => (x.state === 'saved' ? { state: 'idle', error: '' } : x)), 6000)
    } catch (e) {
      const code = statusOf(e)
      setSt({ state: code === 501 || code === 403 ? 'nowriter' : 'error', error: (e && e.message) || String(e) })
    } finally {
      qc.invalidateQueries({ queryKey: ['tenure'] })
    }
  }
  return [st, run]
}

/** The inline outcome of a save. */
function SaveStatus({ st, t }) {
  if (st.state === 'idle') return null
  const text =
    st.state === 'saving'
      ? t('settings.saving')
      : st.state === 'saved'
        ? t('settings.saved')
        : st.state === 'nowriter'
          ? t('settings.no_writer')
          : t('settings.save_failed', { error: st.error })
  return jsxs('p', {
    className: 'tn-save',
    'data-state': st.state,
    role: 'status',
    children: [jsx(Codicon, { name: st.state === 'saving' ? 'loading' : st.state === 'saved' ? 'check' : 'warning', size: '0.75rem', spinning: st.state === 'saving' }), text]
  })
}

/** The command that does the same in a terminal: secondary under a control, the way when saving here is refused. */
function OrTerminal({ text, t, st, config = false }) {
  return jsxs('div', {
    className: 'tn-or',
    'data-strong': st && st.state === 'nowriter' ? 'true' : 'false',
    children: [jsx('p', { className: 'tn-hint', children: config ? t('settings.or_config') : t('settings.or_terminal') }), jsx(Cmd, { t, text })]
  })
}

/** One option: its name, "In force" or a Use button, what it means. */
function Option({ current, head, children, onUse, busy, t }) {
  return jsxs('div', {
    className: 'tn-opt',
    'data-current': current ? 'true' : 'false',
    children: [
      jsxs('div', {
        className: 'tn-opt-head',
        children: [
          head,
          current
            ? jsx('span', { className: 'tn-chip tn-chip-in', children: t('settings.in_force') })
            : jsx('button', { className: 'tn-btn tn-btn-sm', disabled: busy, onClick: onUse, type: 'button', children: t('settings.use') })
        ]
      }),
      children
    ]
  })
}

/** Flat segmented buttons (aria-pressed); value may be null when the state is not known. */
function Seg({ options, value, onPick, busy, label }) {
  return jsx('div', {
    'aria-label': label,
    className: 'tn-seg',
    role: 'group',
    children: options.map(o =>
      jsx('button', { 'aria-pressed': value === o.id ? 'true' : 'false', disabled: busy, onClick: () => value !== o.id && onPick(o.id), type: 'button', children: o.label }, String(o.id))
    )
  })
}

function riskLines(risks, t) {
  return jsx('dl', {
    className: 'tn-levels',
    children: LEVELS.map(level => {
      const bar = risks ? risks[level] : null
      return jsxs(
        'div',
        {
          children: [
            jsx('dt', { children: t('type.stakes_' + level) }),
            bar == null || !(bar > 0)
              ? jsx('dd', { children: t('type.always_asks') })
              : jsxs('dd', { children: [jsx('b', { children: t('settings.series', { n: studyN(bar) }) }), jsx('span', { children: t('settings.risk', { k: Math.round(1 / bar) }) })] })
          ]
        },
        level
      )
    })
  })
}

/** The preset whose risks these are, else custom. */
const presetOf = r => Object.keys(PRESETS).find(n => LEVELS.every(l => (PRESETS[n][l] == null ? r[l] == null : r[l] != null && Math.abs(1 / r[l] - 1 / PRESETS[n][l]) < 1e-6))) || 'custom'
/** A preset's risks as POST /settings takes them, so that choosing it also replaces risk values of your own. */
const presetRisks = id => Object.fromEntries(LEVELS.map(l => [l, PRESETS[id][l] == null ? 'cap' : '1/' + Math.round(1 / PRESETS[id][l])]))
const kOf = bar => (bar > 0 ? String(Math.round(1 / bar)) : '')
const riskYaml = r => `risks: {${LEVELS.map(l => `${l}: ${r[l] == null ? 'cap' : '1/' + r[l]}`).join(', ')}}`

// The "1 in k" choices of the risk buttons (the same on the dashboard tab); null = capped (always asks).
const LADDER = [20, 50, 100, 200, 500, 1000, null]

/**
 * Accepted risk per stakes level: segmented buttons 1/20 … 1/1000 and cap, plus a "1 in k" of your own, with the
 * series it implies shown live; one Save for the three levels.
 */
function RiskEditor({ risks, profile, t }) {
  const init = () => Object.fromEntries(LEVELS.map(l => [l, risks && risks[l] > 0 ? kOf(risks[l]) : null]))
  const initCustom = d => Object.fromEntries(LEVELS.map(l => [l, d[l] != null && !LADDER.includes(Number(d[l])) ? d[l] : '']))
  const [draft, setDraft] = useState(init)
  const [custom, setCustom] = useState(() => initCustom(init()))
  const key = JSON.stringify(risks || {})
  useEffect(() => {
    const d = init()
    setDraft(d)
    setCustom(initCustom(d))
  }, [key])
  const [st, run] = useSave(profile)
  const valid = l => custom[l] === '' || (/^\d+$/.test(custom[l]) && Number(custom[l]) >= 2)
  const allValid = LEVELS.every(valid)
  const changed = LEVELS.some(l => (draft[l] == null ? !!(risks && risks[l] > 0) : !(risks && risks[l] > 0) || kOf(risks[l]) !== draft[l]))
  const pick = (level, k) => {
    setDraft(d => ({ ...d, [level]: k == null ? null : String(k) }))
    setCustom(c => ({ ...c, [level]: '' }))
  }
  const type = (level, v) => {
    const text = v.replace(/[^\d]/g, '')
    setCustom(c => ({ ...c, [level]: text }))
    if (/^\d+$/.test(text) && Number(text) >= 2) setDraft(d => ({ ...d, [level]: String(Number(text)) }))
  }
  return jsxs('div', {
    className: 'tn-opt',
    children: [
      jsx('dl', {
        className: 'tn-levels tn-risk-edit',
        children: LEVELS.map(level => {
          const cap = draft[level] == null
          const k = Number(draft[level])
          return jsxs(
            'div',
            {
              children: [
                jsx('dt', { children: t('type.stakes_' + level) }),
                jsxs('dd', {
                  children: [
                    jsx('b', { children: cap ? t('type.always_asks') : t('settings.series', { n: studyN(1 / k) }) }),
                    jsxs('span', {
                      className: 'tn-risk-ctl',
                      children: [
                        jsx(Seg, {
                          busy: st.state === 'saving',
                          label: t('type.stakes_' + level),
                          onPick: id => pick(level, id === 'cap' ? null : id),
                          options: LADDER.map(n => ({ id: n == null ? 'cap' : n, label: n == null ? t('settings.rung_cap') : '1/' + n })),
                          value: cap ? 'cap' : custom[level] !== '' || !LADDER.includes(k) ? null : k
                        }),
                        jsxs('label', {
                          className: 'tn-risk-k',
                          children: [
                            jsx('span', { children: t('settings.one_in') }),
                            jsx('input', {
                              'aria-invalid': valid(level) ? undefined : 'true',
                              'aria-label': t('type.stakes_' + level) + ' · ' + t('settings.one_in'),
                              inputMode: 'numeric',
                              onChange: e => type(level, e.target.value),
                              placeholder: 'k',
                              type: 'text',
                              value: custom[level]
                            })
                          ]
                        })
                      ]
                    })
                  ]
                })
              ]
            },
            level
          )
        })
      }),
      jsxs('div', {
        className: 'tn-row-end',
        children: [
          jsx('button', {
            className: 'tn-btn',
            'data-kind': 'primary',
            disabled: !allValid || !changed || st.state === 'saving',
            onClick: () => run({ risks: Object.fromEntries(LEVELS.map(l => [l, draft[l] == null ? 'cap' : '1/' + draft[l]])) }),
            type: 'button',
            children: t('settings.save')
          }),
          !allValid ? jsx('span', { className: 'tn-hint', children: t('settings.risk_invalid') }) : null
        ]
      }),
      jsx(SaveStatus, { st, t }),
      jsx(OrTerminal, { config: true, st, t, text: riskYaml(Object.fromEntries(LEVELS.map(l => [l, draft[l]]))) })
    ]
  })
}

/** Spot checks: 1 in 5 / 10 / 20, or a whole number of your own. */
function SpotControl({ spot, profile, t }) {
  const k = Math.round(1 / spot)
  const presets = [5, 10, 20]
  const [custom, setCustom] = useState(presets.includes(k) ? '' : String(k))
  useEffect(() => setCustom(presets.includes(k) ? '' : String(k)), [k])
  const [st, run] = useSave(profile)
  const ok = /^\d+$/.test(custom) && Number(custom) >= 2
  return jsxs('div', {
    className: 'tn-opt',
    'data-current': 'true',
    children: [
      jsxs('div', { className: 'tn-opt-head', children: [jsx('span', { className: 'tn-opt-name', children: t('settings.spot_value', { k }) }), jsx('span', { className: 'tn-chip tn-chip-in', children: t('settings.in_force') })] }),
      jsx('p', { className: 'tn-htext', children: t('settings.spot_desc', { k }) }),
      jsxs('div', {
        className: 'tn-row-end',
        children: [
          jsx(Seg, { busy: st.state === 'saving', label: t('settings.spot_title'), onPick: id => run({ spot: 1 / id }), options: presets.map(n => ({ id: n, label: t('settings.spot_value', { k: n }) })), value: presets.includes(k) ? k : null }),
          jsxs('label', {
            className: 'tn-risk-k',
            children: [
              jsx('span', { children: t('settings.one_in') }),
              jsx('input', { 'aria-label': t('settings.spot_custom'), inputMode: 'numeric', onChange: e => setCustom(e.target.value.replace(/[^\d]/g, '')), placeholder: String(k), type: 'text', value: custom })
            ]
          }),
          jsx('button', { className: 'tn-btn tn-btn-sm', disabled: !ok || Number(custom) === k || st.state === 'saving', onClick: () => run({ spot: 1 / Number(custom) }), type: 'button', children: t('settings.save') })
        ]
      }),
      jsx(SaveStatus, { st, t }),
      jsx('p', { className: 'tn-hint', children: t('settings.spot_change') }),
      jsx(Cmd, { t, text: `spot_check: ${spot}` })
    ]
  })
}

/** A row of options that save on Use (preset, start, strict). */
function OptionsControl({ options, current, profile, t, cmdOf, bodyOf }) {
  const [st, run] = useSave(profile)
  return jsxs('div', {
    className: 'tn-ctl',
    children: [
      jsx('div', {
        className: 'tn-opts',
        children: options.map(o => jsx(Option, { busy: st.state === 'saving', current: current === o.id, head: o.head, onUse: () => run(bodyOf(o.id)), t, children: o.body }, String(o.id)))
      }),
      jsx(SaveStatus, { st, t }),
      jsx('div', {
        className: 'tn-or-list',
        children: options.filter(o => o.id !== current).map(o => jsx(OrTerminal, { st, t, text: cmdOf(o.id) }, String(o.id)))
      })
    ]
  })
}

/** Tenure on / off. */
function EnabledControl({ enabled, profile, t }) {
  const [st, run] = useSave(profile)
  return jsxs('div', {
    className: 'tn-opt',
    'data-current': enabled === true ? 'true' : 'false',
    children: [
      jsxs('div', {
        className: 'tn-row-end',
        children: [
          jsx(Seg, { busy: st.state === 'saving', label: t('settings.enabled_title'), onPick: id => run({ enabled: id === 'on' }), options: [{ id: 'on', label: t('settings.enabled_on') }, { id: 'off', label: t('settings.enabled_off') }], value: enabled == null ? null : enabled ? 'on' : 'off' }),
          enabled == null ? jsx('span', { className: 'tn-hint', children: t('settings.enabled_unknown') }) : null
        ]
      }),
      jsx('p', { className: 'tn-htext', 'data-warn': enabled === false ? 'true' : 'false', children: t('settings.enabled_warn') }),
      jsx(SaveStatus, { st, t }),
      jsx(OrTerminal, { config: true, st, t, text: `enabled: ${enabled === false ? 'true' : 'false'}` })
    ]
  })
}

const TYPES_YAML = `plugins:
  entries:
    tenure:
      settings:
        types:
          "mcp:notion:*": medium      # free | low | medium | high | cap`

/**
 * The settings in force in the current profile, each one changeable here: saved through the agent half (Hermes' own
 * plugin-settings writer), then re-read, so what shows is what is in force. The equivalent command stays under each
 * control, and is the way when this Hermes refuses to save from here (501 / 403).
 */
// The preregistration of the study whose rule tenure applies after a first mistake (docs/the-study.md).
const OSF_URL = 'https://osf.io/vycge/overview?view_only=6c0c2ac8fc9f4b92a6b4d6db76538201'

/** A link out, opened by the host in the browser (a new window), as the app's own outside links. */
function ExtLink({ href, children }) {
  return jsxs('a', { className: 'tn-ext', href, rel: 'noreferrer', target: '_blank', children: [children, jsx(Codicon, { name: 'link-external', size: '0.7rem' })] })
}

/** Settings, "Your passport": animation, emblem pattern and card, with the card itself as a live preview. */
function PassportStyleControl({ agent, t }) {
  const look = usePassStyle()
  const motion = useMotion()
  const row = (key, label, options) =>
    jsxs('div', {
      className: 'tn-pstyle-row',
      children: [jsx('span', { className: 'tn-eyebrow', children: label }), jsx(Seg, { label, onPick: id => setPassStyle({ [key]: id }), options, value: look[key] })]
    })
  return jsxs('div', {
    className: 'tn-pstyle',
    children: [
      jsxs('div', {
        className: 'tn-pstyle-ctl',
        children: [
          row('animation', t('pstyle.animation'), PASS_STYLE.animation.map(id => ({ id, label: t('pstyle.animation_' + id) }))),
          jsx('p', { className: 'tn-hint', style: { margin: 0 }, children: motion ? t('pstyle.animation_desc_' + look.animation) : t('pstyle.forced_still') }),
          row('pattern', t('pstyle.pattern'), PASS_STYLE.pattern.map(id => ({ id, label: t('pstyle.pattern_' + id) }))),
          jsx('p', { className: 'tn-hint', style: { margin: 0 }, children: t('pstyle.pattern_note') }),
          row('card', t('pstyle.card'), PASS_STYLE.card.map(id => ({ id, label: t('pstyle.card_' + id) })))
        ]
      }),
      agent
        ? jsx('div', {
            'aria-label': t('pstyle.preview'),
            className: 'tn-pstyle-preview',
            role: 'group',
            children: jsx(PassportCard, { agent, doc: null, look, motion, ok: false, settled: true, t }, agent.key + look.animation + look.pattern + look.card)
          })
        : jsx('p', { className: 'tn-hint', children: t('pstyle.no_agent') })
    ]
  })
}

function SettingsView({ data, t }) {
  const here = ((data && data.profiles) || []).find(p => p.current) || null
  const s = here && !here.error ? here.settings : null
  const profile = (here && here.profile) || (data && data.current) || 'default'
  const types = here && here.agents ? here.agents.flatMap(a => a.types || []) : []
  const start = startOf(s, types) || DEFAULTS.start
  const spot = s && s.spot > 0 && s.spot < 1 ? s.spot : DEFAULTS.spot
  const strict = s ? !!s.strict : DEFAULTS.strict
  const enabled = s && typeof s.enabled === 'boolean' ? s.enabled : savedSettings.enabled
  const risks = (s && s.risks) || PRESETS[(s && s.preset) || DEFAULTS.preset] || PRESETS.balanced
  // Risk values of their own override the preset: the preset shown is the one they match, else custom.
  const preset = presetOf(risks)
  const k = Math.round(1 / spot)
  const trustedStart = start === 'trusted'
  const presetOpt = id => ({
    id,
    head: jsx('span', { className: 'tn-opt-name', children: presetName(t, id) }),
    body: [jsx('p', { className: 'tn-htext', children: t('settings.preset_desc_' + id) }, 'd'), jsx('div', { children: riskLines(PRESETS[id], t) }, 'r')]
  })
  // "Customise" next to a passport opens Settings on this section.
  useEffect(() => {
    if (!focusPassStyle) return
    focusPassStyle = false
    const el = document.getElementById('tn-pass-style')
    if (el) el.scrollIntoView({ block: 'start' })
  }, [])
  const startHead = trusted =>
    jsxs('span', { className: 'tn-opt-name tn-start', 'data-start': trusted ? 'trusted' : 'probation', children: [jsx('i', { 'aria-hidden': true }), t(trusted ? 'start.trusted' : 'start.probation')] })
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc',
      children: [
        jsxs('header', {
          className: 'tn-hero',
          style: { display: 'block' },
          children: [
            jsxs('div', {
              className: 'tn-eyebrow',
              children: ['#' + t('page.view_settings'), jsx('span', { className: 'tn-dim', children: ' · ' }), `${t('meta.profile')} `, jsx('span', { className: 'tn-bdi', children: profile })]
            }),
            jsx('h3', { className: 'tn-name', children: presetName(t, preset) }),
            jsx('p', {
              className: 'tn-hint',
              style: { margin: '0 0 0.6rem' },
              children: t(trustedStart ? 'start.trusted' : 'start.probation') + ' · ' + t('settings.spot_title') + ' ' + t('settings.spot_value', { k }) + ' · ' + t(strict ? 'settings.strict_on' : 'settings.strict_off')
            }),
            jsx('p', { className: 'tn-note', children: t('settings.saves_here') }),
            s && s.pending ? jsx('p', { className: 'tn-note', style: { marginBlockStart: '0.4rem' }, children: t('settings.pending') }) : null,
            !s ? jsx('p', { className: 'tn-note', style: { marginBlockStart: '0.4rem' }, children: t('settings.none') }) : null
          ]
        }),
        jsx(SettingRow, {
          help: t('settings.preset_help'),
          n: 1,
          title: t('meta.preset'),
          children: jsx(OptionsControl, {
            bodyOf: id => ({ preset: id, risks: presetRisks(id) }),
            cmdOf: id => hermesCmd(profile, 'setup ' + id),
            current: preset,
            options: ['careful', 'balanced', 'fast'].map(presetOpt),
            profile,
            t
          })
        }),
        jsx(SettingRow, {
          help: t('settings.custom_help'),
          n: 2,
          title: t('settings.custom_title'),
          children: [preset === 'custom' ? jsx('p', { className: 'tn-htext', children: t('settings.preset_desc_custom') }, 'c') : null, jsx(RiskEditor, { profile, risks, t }, 'e')]
        }),
        jsx(SettingRow, {
          help: t('settings.start_help'),
          n: 3,
          title: t('meta.start'),
          children: jsx(OptionsControl, {
            bodyOf: id => ({ start: id }),
            cmdOf: id => hermesCmd(profile, 'start ' + id),
            current: start,
            options: [true, false].map(trusted => ({
              id: trusted ? 'trusted' : 'probation',
              head: startHead(trusted),
              body: trusted
                ? jsx('p', { className: 'tn-htext', children: t('settings.start_trusted') })
                : [
                    jsx('p', { className: 'tn-htext', children: t('settings.start_probation') }, 'p'),
                    jsxs('p', { className: 'tn-hint', style: { margin: 0 }, children: [t('settings.start_study'), ' · ', jsx(ExtLink, { href: OSF_URL, children: 'OSF' })] }, 's')
                  ]
            })),
            profile,
            t
          })
        }),
        jsx(SettingRow, { n: 4, title: t('settings.spot_title'), children: jsx(SpotControl, { profile, spot, t }) }),
        jsx(SettingRow, {
          help: t('settings.strict_help'),
          n: 5,
          title: t('settings.strict_title'),
          children: jsx(OptionsControl, {
            bodyOf: id => ({ strict: id === 'on' }),
            cmdOf: id => hermesCmd(profile, id === 'on' ? 'strict on' : 'strict off'),
            current: strict ? 'on' : 'off',
            options: [false, true].map(on => ({
              id: on ? 'on' : 'off',
              head: jsx('span', { className: 'tn-opt-name', children: t(on ? 'settings.strict_on' : 'settings.strict_off') }),
              body: jsx('p', { className: 'tn-htext', children: t(on ? 'settings.strict_desc_on' : 'settings.strict_desc_off') })
            })),
            profile,
            t
          })
        }),
        jsx(SettingRow, {
          help: t('settings.animations_help'),
          n: 6,
          title: t('page.animations'),
          children: jsx('div', { className: 'tn-opt', children: jsx(AnimationsToggle, { t }) })
        }),
        jsx(SettingRow, {
          help: t('pstyle.help'),
          id: 'tn-pass-style',
          n: 7,
          title: t('pstyle.title'),
          children: jsx(PassportStyleControl, { agent: allAgents(data).find(a => a.profile === profile) || allAgents(data)[0] || null, t })
        }),
        jsx(SettingRow, { help: t('settings.enabled_help'), n: 8, title: t('settings.enabled_title'), children: jsx(EnabledControl, { enabled, profile, t }) }),
        jsx(SettingRow, {
          help: t('settings.advanced_help'),
          n: 9,
          title: t('settings.advanced_title'),
          children: [
            jsx('p', { className: 'tn-htext', children: t('settings.advanced_types') }, 't'),
            jsx('pre', { className: 'tn-pre', children: TYPES_YAML }, 'y'),
            jsx('p', { className: 'tn-hint', children: t('settings.advanced_docs') }, 'd')
          ]
        })
      ]
    })
  })
}

/** Plain words on how tenure decides, what asks and why, the tiers, the passport and the benchmark. */
function HelpView({ data, t }) {
  const motion = useMotion()
  const here = ((data && data.profiles) || []).find(p => p.current) || null
  const spot = here && here.settings && here.settings.spot > 0 ? here.settings.spot : DEFAULTS.spot
  const k = Math.round(1 / spot)
  // From a fresh Wald score (no fault yet): the fewest verified successes that reach T2, per stakes.
  const low = toT2({ stakes: 'low', reversible: true, wald: 0, capped: false })
  const medium = toT2({ stakes: 'medium', reversible: true, wald: 0, capped: false })
  const tiers = ['ask', 'notify', 'alone']
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc',
      children: [
        jsxs('header', {
          className: 'tn-hero',
          style: { display: 'block' },
          children: [
            jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_help') }),
            jsx('h3', { className: 'tn-name', children: t('help.title') }),
            jsx('p', { className: 'tn-intro-body', style: { margin: 0 }, children: t('help.intro') })
          ]
        }),
        jsx(SettingRow, { n: 1, title: t('help.trusted_title'), children: jsx('p', { className: 'tn-htext', children: t('help.trusted_body') }) }),
        jsx(SettingRow, {
          n: 2,
          title: t('help.asks_title'),
          help: t('help.asks_body'),
          children: jsx('ul', {
            className: 'tn-list',
            children: [
              jsx('li', { children: t('help.asks_leaves') }, 'a'),
              jsx('li', { children: t('help.asks_irreversible') }, 'b'),
              jsx('li', { children: t('help.asks_unknown') }, 'c'),
              jsx('li', { children: t('help.asks_outside') }, 'd'),
              jsx('li', { children: t('help.asks_files') }, 'e')
            ]
          })
        }),
        jsx(SettingRow, { n: 3, title: t('help.session_title'), children: jsx('p', { className: 'tn-htext', children: t('help.session_body') }) }),
        jsx(SettingRow, {
          n: 4,
          title: t('help.undo_title'),
          children: [
            jsx('p', { className: 'tn-htext', children: t('help.undo_body') }, 'u'),
            jsx(Cmd, { t, text: '/tenure undo N' }, 'uc'),
            jsx('p', { className: 'tn-htext', children: t('help.flag_body') }, 'f'),
            jsx(Cmd, { t, text: '/tenure flag TYPE' }, 'fc')
          ]
        }),
        jsx(SettingRow, {
          n: 5,
          title: t('help.tiers_title'),
          children: [
            jsx(
              'div',
              {
                className: 'tn-tiers',
                children: tiers.map(tier =>
                  jsxs(
                    'div',
                    {
                      className: 'tn-tier',
                      children: [
                        jsx(TierChip, { motion, t, tier }),
                        jsx('span', { className: 'tn-tname', 'data-tier': tier, children: tierName(tier, t) }),
                        jsx('span', { className: 'tn-htext', children: tier === 'alone' ? t('type.tenured_line', { k }) : TierLabel(tier, t) })
                      ]
                    },
                    tier
                  )
                )
              },
              'tiers'
            ),
            jsx('p', { className: 'tn-htext', children: t('help.tiers_climb', { low, medium, sessions: SERIES_SESSIONS }) }, 'c'),
            jsx('p', { className: 'tn-htext', children: t('help.tiers_drop') }, 'd')
          ]
        }),
        jsx(SettingRow, {
          n: 6,
          title: t('passport.title'),
          children: [
            jsx('p', { className: 'tn-htext', children: t('help.passport_body') }, 'b'),
            jsx(Cmd, { t, text: EXPORT_COMMAND }, 'e'),
            jsx(Cmd, { t, text: VERIFY_COMMAND }, 'v'),
            jsx('p', { className: 'tn-htext', children: t('help.passport_checks') }, 'c')
          ]
        }),
        jsx(SettingRow, {
          n: 7,
          title: t('help.study_title'),
          children: [
            jsx('p', { className: 'tn-htext', children: t('help.study_body') }, 'b'),
            jsx('p', { className: 'tn-htext', children: t('help.study_adds') }, 'a'),
            jsx('p', { className: 'tn-htext', children: jsx(ExtLink, { href: OSF_URL, children: t('help.study_link') }) }, 'l')
          ]
        }),
        jsx(SettingRow, { n: 8, title: t('page.view_benchmark'), children: jsx('p', { className: 'tn-htext', children: t('help.benchmark_body', { n: RANK_MIN }) }) }),
        jsx(SettingRow, {
          help: t('help.keys_note'),
          n: 9,
          title: t('help.keys_title'),
          children: jsx('dl', {
            className: 'tn-keys',
            children: [
              ...PAGE_KEYS.filter(([k]) => k !== '?').map(([k, v]) => [k, t('page.view_' + v)]),
              ['j / k · ↑ / ↓', t('help.key_next_prev')],
              ['↵', t('help.key_open')],
              ['r', t('help.key_raw')],
              ['esc', t('help.key_close')],
              ['?', t('help.key_help')]
            ].flatMap(([k, label]) => [
              jsx('dt', { children: jsx('kbd', { className: 'tn-kbd', children: k }) }, 'k' + k),
              jsx('dd', { children: k === '?' ? t('help.key_help') : label }, 'd' + k)
            ])
          })
        })
      ]
    })
  })
}

// ------------------------------------------------------------------------------------------------ map, community, switch, undo
// The dashboard tab's views, on the Desktop: same API calls, same words (the catalog keys are copied from
// dashboard.json), drawn in ink and dither.
const WEEK = 7 * 86400
const TRIAL = 3 // rule.TRIAL
const UNDO_WINDOW = 86400 // core.UNDO_WINDOW: an act-then-notify snapshot is kept 24 h
const COMMUNITY_REPO = 'github.com/otsoa-dubief/tenure-community' // tenure/community.py REPO

// Raw or redacted type names (the dashboard's `r` switch): every call carries raw=1 while it is on.
let rawPref = false
function setRawPref(on) {
  rawPref = !!on
  if (storage) storage.set('raw', rawPref ? 'on' : 'off')
  seen.clear()
  bus.dispatchEvent(new Event('raw'))
}
function useRaw() {
  const [on, setOn] = useState(rawPref)
  useEffect(() => {
    const sync = () => setOn(rawPref)
    bus.addEventListener('raw', sync)
    return () => bus.removeEventListener('raw', sync)
  }, [])
  return on
}

/** /activity over the last 7 days, every profile: the header totals and the undoable actions (24 h). */
function useActivity() {
  const profile = useValue(host.state.profile)
  return useQuery({
    queryKey: ['tenure', profile, 'activity'],
    queryFn: () => rest('/activity?since=' + Math.floor(Date.now() / 1000 - WEEK)),
    refetchInterval: HEARTBEAT_MS
  })
}

const num = n => {
  if (n == null) return '—'
  try { return new Intl.NumberFormat(pageLocale()).format(Number(n)) } catch (e) { return String(n) }
}
/** A duration in seconds, short units: "12s", "5m", "2h 05m", "3d". */
function duration(t, sec) {
  const s = Math.max(0, Math.round(sec))
  if (s < 60) return t('time.seconds', { n: s })
  if (s < 3600) return t('time.minutes', { n: Math.floor(s / 60) })
  const mm = pad2(Math.floor((s % 3600) / 60))
  if (s < 86400) return t('time.hours_minutes', { n: Math.floor(s / 3600), mm })
  return t('time.days', { n: Math.floor(s / 86400) })
}
const hm = at => {
  const d = new Date(at * 1000)
  return pad2(d.getHours()) + ':' + pad2(d.getMinutes())
}
const hms = ms => hm(ms / 1000) + ':' + pad2(new Date(ms).getSeconds())
const dayKey = at => {
  const d = new Date(at * 1000)
  return d.getFullYear() + '-' + d.getMonth() + '-' + d.getDate()
}
const dayLabel = at => {
  try { return new Intl.DateTimeFormat(pageLocale(), { weekday: 'short', day: 'numeric', month: 'short' }).format(new Date(at * 1000)) } catch (e) { return new Date(at * 1000).toDateString() }
}
const short = (hash, n) => (hash ? String(hash).slice(0, n || 12) : '—')
const oneIn = (t, r) => (r == null ? t('map.capped') : t('map.one_in', { k: Math.round(1 / r) }))
const groupName = (t, s) => (LEVELS.includes(s) ? t('map.group_' + s) : s)
const tierCode = (tier, t) => (tier === 'trusted' ? t('tier.chip_trusted') : TIER_SHORT[tier] || tier)

/** What a type still needs, said as missing evidence (the dashboard's words). */
function missing(ty, t) {
  if (ty.capped) return t('missing.always_asks')
  if (ty.trusted) return ty.reversible ? t('missing.trusted_undo') : t('missing.trusted')
  if (ty.trial_wait) return t('missing.trial_wait', { n: ty.trial_wait })
  if (ty.trial_left) return t('missing.trial_left', { n: ty.trial_left, total: TRIAL })
  const eff = ty.effective_tier
  if (eff === 'alone') return t('missing.earned')
  const gap = (ty.required || 0) - (ty.series || 0)
  if (gap <= 0 && (ty.sessions || 0) < SERIES_SESSIONS) return t('missing.second_session')
  const parts = []
  const k2 = eff === 'ask' ? toT2(ty) : null
  if (k2) parts.push(t('missing.more_to_t2', { n: k2 }))
  if (gap > 0) parts.push(t('missing.more_to_t3', { n: gap }))
  return parts.join(' · ') || t('missing.rechecking')
}

/** The map cell's tooltip: kind, tier now, series, record. */
function cellTitle(ty, t) {
  const stakes = groupName(t, ty.stakes)
  const name = tierName(tierKey(ty), t)
  const tier = tierCode(tierKey(ty), t)
  const kind = ty.reversible ? t('cell.kind_reversible', { type: ty.type, stakes }) : t('cell.kind_irreversible', { type: ty.type, stakes })
  const stored = TIER_SHORT[ty.tier] || ty.tier
  const now = t('cell.tier_now', { tier, name })
  const lines = [kind, ty.tier !== ty.effective_tier && !ty.trusted ? now + ' · ' + t('map.held', { tier: stored }) : now]
  const series = String(ty.series || 0)
  const required = String(ty.required || 0)
  lines.push(ty.capped ? t('cell.capped_by_settings') : t('cell.series', { series, required }) + ' · ' + t('cell.sessions', { n: ty.sessions || 0 }))
  const successes = String(ty.successes || 0)
  const faults = String(ty.faults || 0)
  const neutrals = String(ty.neutrals || 0)
  const spot = String(ty.spot_checks || 0)
  lines.push(t('cell.record', { successes, faults, neutrals, spot }))
  if (ty.provisional) lines.push(t('cell.provisional_long', { n: ty.provisional }))
  if (ty.unresolved_fault) lines.push(t('map.fault_on_record'))
  return lines
}

function profileSummary(st, types, t) {
  const parts = [t('map.preset', { preset: presetName(t, st.preset || DEFAULTS.preset) }), t('map.spot', { rate: oneIn(t, st.spot) })]
  const start = startOf(st, types)
  if (start) parts.push(start === 'trusted' ? t('map.start_trusted') : t('map.start_probation'))
  if (st.strict) parts.push(t('map.strict'))
  if (st.pending) parts.push(t('map.pending'))
  if (st.copy_pending) parts.push(t('map.copy_pending'))
  return parts.join(' · ')
}

/** Every type seen on any agent, grouped by stakes (low, medium, high, then anything else), sorted by name. */
function columns(profiles) {
  const seenType = {}
  const groups = { low: [], medium: [], high: [] }
  for (const p of profiles)
    for (const a of p.agents || [])
      for (const ty of a.types || []) {
        if (seenType[ty.type]) continue
        seenType[ty.type] = 1
        ;(groups[ty.stakes] || (groups[ty.stakes] = [])).push(ty.type)
      }
  const order = s => (LEVELS.indexOf(s) + 9) % 9
  return Object.keys(groups)
    .sort((a, b) => order(a) - order(b))
    .filter(s => groups[s].length)
    .map(s => ({ stakes: s, types: groups[s].sort() }))
}

function Tiles({ totals: tot, t }) {
  const actions = tot ? tot.actions || 0 : 0
  // "12 actions": the number is drawn big, the words stay as the catalog says them.
  const actionsLabel = t('overview.actions_label', { n: actions }).replace(String(actions), '').trim()
  const cells = [
    { n: tot ? tot.actions : null, label: actionsLabel, sub: t('overview.actions_sub') },
    { n: tot ? tot.checked : null, label: t('overview.checked_label'), sub: tot ? t('overview.checked_sub', { total: actions }) : '' },
    { n: tot ? tot.alone : null, label: t('overview.alone_label'), sub: tot ? t('overview.alone_sub', { total: actions }) : '' },
    { n: tot ? tot.faults : null, label: t('overview.faults_label'), sub: tot ? t('overview.faults_sub', { faults: tot.faults || 0, n: tot.checked || 0 }) : '' }
  ]
  return jsxs('section', {
    'aria-label': t('overview.aria'),
    className: 'tn-tiles-wrap',
    children: [
      jsx('div', {
        className: 'tn-tiles',
        children: cells.map((c, i) =>
          jsxs(
            'div',
            {
              className: 'tn-tile',
              children: [
                jsx('span', { 'aria-hidden': true, className: 'tn-tnum', style: { padding: 0 }, children: '#' + pad2(i + 1) }),
                jsx('b', { className: 'tn-tile-n', children: num(c.n) }),
                jsx('span', { className: 'tn-tile-label', children: c.label }),
                jsx('span', { className: 'tn-tile-sub', children: c.sub })
              ]
            },
            i
          )
        )
      }),
      jsx('p', { className: 'tn-tile-window', children: t('overview.window') })
    ]
  })
}

function MapCell({ ty, t, motion, row }) {
  if (!ty) return jsx('td', { className: 'tn-mcell tn-mnone', children: '—' })
  const tier = tierKey(ty)
  const geo = barGeo(ty)
  const held = ty.tier !== ty.effective_tier && !ty.trusted
  return jsx('td', {
    className: 'tn-mcell',
    children: jsx(Tip, {
      label: jsx('span', { style: { whiteSpace: 'pre-line' }, children: cellTitle(ty, t).join('\n') }),
      children: jsxs('div', {
        className: 'tn-mcell-in',
        tabIndex: -1,
        children: [
          jsxs('div', {
            className: 'tn-mcell-top',
            children: [
              jsx(TierChip, { motion, t, tier }),
              ty.capped
                ? jsxs('span', { className: 'tn-count', children: [num((ty.successes || 0) + (ty.faults || 0)), jsx('i', { children: t('map.asked_suffix') })] })
                : ty.trusted
                  ? null
                  : jsx(Count, { ty })
            ]
          }),
          jsx(DitherBar, { delay: 120 + row * 40, motion, notch: geo.notch, rows: 4, segments: geo.segments, solid: tier === 'alone', track: ty.capped, trust: tier === 'trusted', value: fillOf(ty) }),
          jsxs('div', {
            className: 'tn-mcell-mid',
            children: [
              ty.capped ? t('map.count_faults', { n: ty.faults || 0 }) : t('map.count_sessions', { n: ty.sessions || 0 }),
              held ? jsx('span', { children: ' · ' + t('map.held', { tier: TIER_SHORT[ty.tier] || ty.tier }) }) : null
            ]
          }),
          jsx('div', { className: 'tn-mcell-miss', 'data-tone': tier === 'alone' ? 'ok' : ty.trial_left || ty.trial_wait ? 'warn' : 'muted', children: missing(ty, t) }),
          ty.provisional || ty.unresolved_fault
            ? jsxs('div', {
                className: 'tn-pills',
                children: [
                  ty.provisional ? jsx('span', { className: 'tn-flag', children: t('map.carried_n', { n: ty.provisional }) }, 'p') : null,
                  ty.unresolved_fault ? jsx('span', { className: 'tn-flag', 'data-kind': 'fault', children: t('map.fault_on_record') }, 'f') : null
                ]
              })
            : null
        ]
      })
    })
  })
}

function Legend({ t, spot, trusted, motion }) {
  const item = (chip, text) => jsxs('span', { className: 'tn-legend-i', children: [chip, jsx('span', { children: text })] })
  return jsxs('div', {
    className: 'tn-legend',
    children: [
      trusted ? item(jsx(TierChip, { motion: false, t, tier: 'trusted' }), t('legend.trusted')) : null,
      item(jsx(TierChip, { motion: false, t, tier: 'ask' }), t('legend.ask')),
      item(jsx(TierChip, { motion: false, t, tier: 'notify' }), t('legend.notify')),
      item(jsx(TierChip, { motion: false, t, tier: 'alone' }), t('legend.alone', { share: spot ? oneIn(t, spot) : t('legend.a_share') })),
      item(jsx(TierChip, { motion: false, t, tier: 'cap' }), t('legend.capped')),
      item(jsxs('span', { className: 'tn-legend-bar', children: [jsx(DitherBar, { motion, rows: 4, segments: 0, value: 0.55 }), jsx('span', { className: 'tn-mono', children: 'n/N' })] }), t('legend.series')),
      item(jsx('span', { className: 'tn-flag', children: t('legend.carried_flag') }), t('legend.carried'))
    ]
  })
}

function Transitions({ items, t, n }) {
  return jsxs('section', {
    'aria-live': 'polite',
    className: 'tn-section',
    children: [
      jsx(Eyebrow, { n, children: t('transitions.title') }),
      items.length
        ? jsx('ol', {
            className: 'tn-trans',
            children: items.slice(0, 8).map(x =>
              jsxs(
                'li',
                {
                  children: [
                    jsx('span', { className: 'tn-mono tn-dim', children: hms(x.at) }),
                    jsx('span', { className: 'tn-bdi', children: displayName(x.model) }),
                    jsx('code', { className: 'tn-mono tn-bdi', children: x.type }),
                    jsxs('span', { className: 'tn-trans-move', children: [jsx(TierChip, { motion: false, t, tier: x.from }), jsx('span', { 'aria-hidden': true, className: 'tn-mirror', children: '→' }), jsx(TierChip, { motion: false, t, tier: x.to })] }),
                    jsx('span', { className: 'tn-dim', children: t('transitions.why_' + x.why) })
                  ]
                },
                x.id
              )
            )
          })
        : jsx('p', { className: 'tn-hint', children: t('transitions.empty') })
    ]
  })
}

/** The dashboard's Map: four totals, every profile × agent × action type, the legend, the tier changes seen here. */
function MapView({ data, t, transitions, onOpen }) {
  const motion = useMotion()
  const [hot, setHot] = useState(null)               // the agent row under the pointer or the focus
  const { data: activity } = useActivity()
  const profiles = ((data && data.profiles) || []).filter(p => !p.error)
  const cols = columns(profiles)
  const ncols = cols.reduce((n, g) => n + g.types.length, 0)
  const here = profiles.find(p => p.current)
  const cur = here && here.settings
  const rows = allAgents(data)
  const trusted = rows.some(a => (a.types || []).some(ty => ty.trusted && !ty.capped))
  let i = 0
  const open = key => {
    haptic('tap')
    onOpen(key)
  }
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc tn-doc-wide',
      children: [
        jsx(Tiles, { t, totals: activity && activity.totals }),
        jsxs('section', {
          className: 'tn-section',
          children: [
            jsx(Eyebrow, { n: 1, children: t('map.aria') }),
            jsx('div', {
              className: 'tn-map-scroll',
              children: jsxs('table', {
                'aria-label': t('map.aria'),
                className: 'tn-map',
                style: { minWidth: `calc(17rem + ${ncols} * 8.5rem)` },
                children: [
                  jsxs('thead', {
                    children: [
                      jsxs('tr', {
                        children: [
                          jsxs('th', { className: 'tn-mth-agent', rowSpan: 2, scope: 'col', children: [jsx('span', { className: 'tn-eyebrow', children: t('map.th_agent') }), jsx('span', { className: 'tn-mth-sub', children: t('map.th_agent_sub') })] }),
                          ...cols.map(g => {
                            const bar = cur && cur.risks ? cur.risks[g.stakes] : undefined
                            const n = bar == null || !(bar > 0) ? null : studyN(bar)
                            const risk = oneIn(t, bar)
                            const sub = n == null ? (g.stakes === 'high' ? t('map.th_capped') : '') : t('map.th_risk', { risk, n })
                            return jsxs('th', { className: 'tn-mth-group', colSpan: g.types.length, scope: 'colgroup', children: [jsx('span', { className: 'tn-eyebrow', children: groupName(t, g.stakes) }), jsx('span', { className: 'tn-mth-sub', children: sub })] }, g.stakes)
                          })
                        ]
                      }),
                      jsx('tr', { children: cols.flatMap(g => g.types.map(ty => jsx('th', { className: 'tn-mth-type', scope: 'col', children: jsx('code', { className: 'tn-bdi', children: ty }) }, ty))) })
                    ]
                  }),
                  ...profiles.map(p =>
                    jsxs(
                      'tbody',
                      {
                        children: [
                          jsx('tr', {
                            className: 'tn-mprofile',
                            children: jsx('th', {
                              colSpan: ncols + 1,
                              scope: 'rowgroup',
                              children: jsxs('div', {
                                children: [
                                  jsx('b', { className: 'tn-bdi', children: t('map.profile', { profile: p.profile }) }),
                                  jsx('span', { className: 'tn-dim', children: p.current ? t('map.current') : t('map.read_only') }),
                                  p.suspended ? jsx(StatePill, { kind: 'fault', label: t('map.suspended', { n: p.suspended }), tip: t('state.suspended_tip'), t }) : null,
                                  p.settings ? jsx('span', { className: 'tn-dim tn-mprof-set', children: profileSummary(p.settings, (p.agents || []).flatMap(a => a.types || []), t) }) : null
                                ]
                              })
                            })
                          }),
                          ...(p.agents || []).map(a => {
                            const key = `${p.profile}|${a.agent}`
                            const byType = {}
                            for (const ty of a.types || []) byType[ty.type] = ty
                            const tot = a.totals || {}
                            const row = i++
                            return jsxs(
                              'tr',
                              {
                                className: cn('tn-mrow', motion && 'tn-enter'),
                                onClick: () => open(key),
                                onMouseEnter: () => setHot(key),
                                onMouseLeave: () => setHot(h => (h === key ? null : h)),
                                onFocus: () => setHot(key),
                                onBlur: () => setHot(h => (h === key ? null : h)),
                                style: motion ? { animationDelay: `${row * 40}ms` } : undefined,
                                children: [
                                  jsx('th', {
                                    className: 'tn-mtd-agent',
                                    scope: 'row',
                                    children: jsxs('button', {
                                      className: 'tn-magent',
                                      onClick: e => {
                                        e.stopPropagation()
                                        open(key)
                                      },
                                      type: 'button',
                                      children: [
                                        jsx(Emblem, { hot: hot === key, label: displayName(a.model), motion, n: 26, rotate: true, share: shareOf(a), size: 30 }, key),
                                        jsxs('span', {
                                          className: 'tn-magent-txt',
                                          children: [
                                            jsxs('span', { className: 'tn-magent-name tn-bdi', children: [displayName(a.model), jsx('span', { className: 'tn-dim', children: '@' + a.provider })] }),
                                            jsx('span', { className: 'tn-magent-tot', children: t('map.tot_actions', { n: tot.actions || 0 }) + ' · ' + t('map.tot_checked', { n: tot.checked || 0 }) }),
                                            jsx('span', { className: 'tn-magent-tot', children: t('map.tot_alone', { n: tot.alone || 0 }) + ' · ' + t('map.tot_faults', { n: tot.faults || 0 }) }),
                                            a.provisional || a.trial || a.unresolved_fault
                                              ? jsxs('span', {
                                                  className: 'tn-pills',
                                                  children: [
                                                    a.provisional ? jsx('span', { className: 'tn-flag', children: t('state.provisional') }, 'p') : null,
                                                    a.trial ? jsx('span', { className: 'tn-flag', children: t('state.trial') }, 't') : null,
                                                    a.unresolved_fault ? jsx('span', { className: 'tn-flag', 'data-kind': 'fault', children: t('state.fault') }, 'f') : null
                                                  ]
                                                })
                                              : null
                                          ]
                                        }),
                                        jsx(Codicon, { className: 'tn-mopen', name: 'chevron-right', size: '0.8rem' })
                                      ]
                                    })
                                  }),
                                  ...cols.flatMap(g => g.types.map(ty => jsx(MapCell, { motion, row, t, ty: byType[ty] }, ty)))
                                ]
                              },
                              key
                            )
                          })
                        ]
                      },
                      p.profile
                    )
                  )
                ]
              })
            }),
            jsx(Legend, { motion, spot: cur && cur.spot, t, trusted })
          ]
        }),
        jsx(Transitions, { items: transitions, n: 2, t })
      ]
    })
  })
}

/** The page's own record of tier changes, diffed between two answers (since this page opened). */
function usePageTransitions(data, t) {
  const prev = useRef(null)
  const [items, setItems] = useState([])
  useEffect(() => {
    const reset = () => {
      prev.current = null
    }
    bus.addEventListener('raw', reset)
    return () => bus.removeEventListener('raw', reset)
  }, [])
  useEffect(() => {
    if (!data) return
    const now = {}
    for (const a of allAgents(data)) for (const ty of a.types || []) now[a.key + '\u0000' + ty.type] = { tier: tierKey(ty), a, ty }
    const before = prev.current
    prev.current = now
    if (!before) return
    const found = []
    const stamp = Date.now()
    for (const k of Object.keys(now)) {
      const b = before[k]
      const x = now[k]
      if (!b || b.tier === x.tier) continue
      // A fault (or the trial it opened) explains a drop; a climb is earned on evidence; a drop with no fault is a
      // revoke, a settings or stakes change: said as such, never "on evidence".
      const faulted = (x.ty.faults || 0) > (b.ty.faults || 0)
      const why = faulted ? (x.ty.trial_left ? 'trial_open' : 'after_fault') : TIER_RANK[x.tier] > TIER_RANK[b.tier] ? 'on_evidence' : 'changed'
      found.push({ id: k + stamp, at: stamp, model: x.a.model, agent: x.a.agent, type: x.ty.type, from: b.tier, to: x.tier, why })
    }
    if (!found.length) return
    setItems(xs => found.concat(xs).slice(0, 30))
    const f = found[0]
    const from = tierCode(f.from, t)
    const to = tierCode(f.to, t)
    host.notify({ kind: 'info', message: t('toast.transition', { agent: displayName(f.model), type: f.type, from, to }) })
  }, [data])
  return items
}

// ---- community
function CommunityView({ t }) {
  const profile = useValue(host.state.profile)
  const motion = useMotion()
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['tenure', profile, 'community'], queryFn: () => rest('/community'), refetchInterval: HEARTBEAT_MS * 5 })
  if (isLoading && !data) return jsx(PanelEmpty, { description: t('common.loading'), icon: 'loading~spin' })
  if (error && !data)
    // A plain error, as on the dashboard: the board is a local file the agent half reads, not the agent half itself.
    return jsx(ErrorState, { title: error.message || String(error), children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('common.retry') }) })
  const board = data && data.board
  const head = (title, body) =>
    jsxs('header', {
      className: 'tn-hero',
      style: { display: 'block' },
      children: [jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_community') }), title ? jsx('h3', { className: 'tn-name', children: title }) : null, body]
    })
  if (!board || !(board.families || []).length) {
    const path = (data && data.path) || 'community-board.json'
    return jsx('div', {
      className: 'tn-root tn-doc-wrap',
      children: jsxs('div', {
        className: 'tn-doc',
        children: [
          head(t('community.empty_title'), null),
          jsx(SettingRow, {
            n: 1,
            title: t('page.view_community'),
            children: [
              jsx('p', { className: 'tn-htext', children: t('community.empty_what') }, 'w'),
              jsx('p', { className: 'tn-htext', children: t('community.empty_how', { repo: COMMUNITY_REPO }) }, 'h'),
              jsx(Cmd, { t, text: 'hermes tenure share' }, 'c'),
              jsx('p', { className: 'tn-hint', children: t('community.empty_where', { path }) }, 'p')
            ]
          })
        ]
      })
    })
  }
  const records = t('community.records', { n: board.records || 0 })
  const date = board.generated || '—'
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc',
      children: [
        head(
          null,
          jsxs('div', {
            style: { display: 'flex', flexDirection: 'column', gap: '0.4rem', marginBlockStart: '0.35rem' },
            children: [
              jsxs('p', { className: 'tn-intro-body', style: { margin: 0 }, children: [t('community.lede'), jsx('b', { children: t('community.lede_bold') }), ' ', t('community.ranking')] }),
              jsx('p', { className: 'tn-hint', children: t('community.generated', { records, date }) })
            ]
          })
        ),
        ...board.families.map((g, gi) => {
          const ranked = (g.models || []).filter(r => r.checks >= RANK_MIN)
          const waiting = (g.models || []).filter(r => r.checks < RANK_MIN)
          const max = Math.min(1, Math.ceil(Math.max(0.05, ...ranked.map(r => r.high || 0)) * 20) / 20)
          return jsxs(
            'section',
            {
              className: 'tn-section',
              style: { paddingBlock: '1rem 0.5rem' },
              children: [
                jsxs('div', { className: 'tn-section-head', children: [jsx(Eyebrow, { n: gi + 1, children: jsx('span', { className: 'tn-bdi', style: { textTransform: 'none' }, children: g.family }) }), jsx('span', { className: 'tn-hint', children: t('community.models', { n: (g.models || []).length }) })] }),
                ranked.length
                  ? jsxs('div', {
                      children: [
                        jsxs('div', {
                          'aria-hidden': true,
                          className: 'tn-bench tn-bench-h',
                          'data-pub': 'wide',
                          children: [
                            jsx('span', {}),
                            jsx('span', { className: 'tn-eyebrow', children: t('community.col_model') }),
                            jsx('span', { className: 'tn-eyebrow tn-end', children: t('benchmark.col_faults') }),
                            jsx('span', { className: 'tn-eyebrow', children: t('benchmark.col_range') }),
                            jsx('span', { className: 'tn-eyebrow', children: t('benchmark.col_rate') }),
                            jsx('span', { className: 'tn-eyebrow tn-end', children: t('community.col_contributors') })
                          ]
                        }),
                        ...ranked.map((r, i) =>
                          jsxs(
                            'div',
                            {
                              className: cn('tn-bench', motion && 'tn-enter'),
                              'data-pub': 'wide',
                              style: motion ? { animationDelay: `${i * 40}ms` } : undefined,
                              children: [
                                jsx('span', { className: 'tn-tnum', style: { paddingBlockStart: 0 }, children: '#' + pad2(i + 1) }),
                                jsxs('span', { className: 'tn-bm', children: [jsx('span', { className: 'tn-bdi', style: { color: 'var(--tn-fg)' }, children: displayName(r.model) }), jsx('span', { className: 'tn-bsub tn-bdi', children: '@' + r.provider })] }),
                                jsx('span', { className: 'tn-bnum tn-end', children: t('benchmark.faults', { n: r.faults, total: r.checks }) }),
                                jsx(Tip, {
                                  label: t('benchmark.range_tip', { max: pct(max) }),
                                  children: jsx('span', {
                                    'aria-label': t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }),
                                    role: 'img',
                                    style: { display: 'block', outline: 'none' },
                                    tabIndex: 0,
                                    children: jsx(RangeBar, { delay: 80 + i * 40, high: r.high, low: r.low, max, motion, rate: r.rate })
                                  })
                                }),
                                jsx('span', { className: 'tn-bnum', children: t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }) }),
                                jsx('span', { className: 'tn-bnum tn-end', children: num(r.contributors) })
                              ]
                            },
                            r.model + '@' + r.provider
                          )
                        )
                      ]
                    })
                  : null,
                waiting.length
                  ? jsxs('div', {
                      className: 'tn-section',
                      children: [
                        jsx(Eyebrow, { children: t('benchmark.not_ranked') }),
                        jsx('p', { className: 'tn-hint', children: t('benchmark.not_ranked_note', { n: RANK_MIN }) }),
                        jsx('div', {
                          className: 'tn-wait',
                          children: waiting.map(r => jsx('span', { className: 'tn-bdi', children: `${displayName(r.model)}@${r.provider} · ${num(r.faults)} / ${num(r.checks)}` }, r.model + '@' + r.provider))
                        })
                      ]
                    })
                  : null
              ]
            },
            g.family
          )
        })
      ]
    })
  })
}

// ---- switch preview
const SWITCH_STATES = ['carried', 'reset', 'vetoed', 'kept']
const SWITCH_KIND = { carried: 'state', reset: 'muted', vetoed: 'fault', kept: 'ok' }
function SwitchFlag({ k, children }) {
  return jsx('span', { className: 'tn-flag', 'data-kind': SWITCH_KIND[k] || 'muted', children })
}

function SwitchView({ data, t }) {
  const agents = allAgents(data)
  const motion = useMotion()
  const [from, setFrom] = useState(() => focusKey || (agents[0] && agents[0].key) || '')
  const [draft, setDraft] = useState('')
  const [to, setTo] = useState('')
  useEffect(() => {
    focusKey = null
  }, [])
  const a = agents.find(x => x.key === from) || agents[0] || null
  const models = [...new Set(agents.map(x => displayName(x.model)))].sort()
  // Every model Hermes' own picker offers, by provider (GET /switch-models); "Other model" types any id.
  const { data: catalog } = useQuery({ queryKey: ['tenure', 'switch-models'], queryFn: () => rest('/switch-models'), staleTime: 300000 })
  const providers = (catalog && catalog.providers) || []
  const [other, setOther] = useState(false)
  const known = v => models.includes(v) || providers.some(p => p.models.some(m => m + '@' + p.slug === v))
  const pick = v => {
    if (v === '__other') {
      setOther(true)
      setDraft('')
      return
    }
    setOther(false)
    setDraft(v)
    setTo(v)
  }
  const { data: res, error, isFetching } = useQuery({
    queryKey: ['tenure', a ? a.profile : '', 'preview', a ? a.agent : '', to],
    queryFn: () => rest(`/preview?agent=${encodeURIComponent(a.agent)}&to=${encodeURIComponent(to)}&of=${encodeURIComponent(a.profile)}`),
    enabled: !!(a && to)
  })
  const counts = {}
  for (const ty of (res && res.types) || []) counts[ty.status] = (counts[ty.status] || 0) + 1
  const cellTier = x =>
    jsxs('span', {
      className: 'tn-sw-tier',
      children: [jsx(TierChip, { motion: false, t, tier: tierKey(x) }), jsx('span', { className: 'tn-mono', children: x.capped ? t('switch.capped') : num(x.series) + '/' + num(x.required) })]
    })
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc tn-doc-wide',
      children: [
        jsxs('header', {
          className: 'tn-hero',
          style: { display: 'block' },
          children: [jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_switch') }), jsx('p', { className: 'tn-intro-body', style: { margin: '0.35rem 0 0' }, children: t('switch.lede') })]
        }),
        !agents.length
          ? jsx(PanelEmpty, { description: t('switch.empty'), icon: 'arrow-swap' })
          : jsxs('form', {
              className: 'tn-sw-form',
              onSubmit: e => {
                e.preventDefault()
                if (draft.trim()) setTo(draft.trim())
              },
              children: [
                jsxs('label', {
                  className: 'tn-field',
                  children: [
                    jsx('span', { className: 'tn-eyebrow', children: t('switch.from') }),
                    jsx('select', {
                      className: 'tn-input',
                      onChange: e => setFrom(e.target.value),
                      value: a ? a.key : '',
                      children: agents.map(x => jsx('option', { value: x.key, children: `${displayName(x.model)}@${x.provider} · ${x.profile}` }, x.key))
                    })
                  ]
                }),
                // The arrow runs the preview too: it reads as the action between the two agents.
                jsx('button', { 'aria-label': t('switch.preview'), className: 'tn-sw-arrow', title: t('switch.preview'), type: 'submit', children: t('switch.arrow') }),
                jsxs('label', {
                  className: 'tn-field tn-field-grow',
                  children: [
                    jsx('span', { className: 'tn-eyebrow', children: t('switch.to') }),
                    jsxs('select', {
                      'aria-label': t('switch.to_aria'),
                      className: 'tn-input',
                      name: 'to_pick',
                      onChange: e => pick(e.target.value),
                      value: other ? '__other' : to || '',
                      children: [
                        jsx('option', { value: '', children: t('switch.pick_title') }, 'none'),
                        models.length
                          ? jsx('optgroup', { label: t('switch.group_agents'), children: models.map(m => jsx('option', { value: m, children: m }, 'a:' + m)) }, 'agents')
                          : null,
                        ...providers.map(p =>
                          jsx('optgroup', { label: p.name, children: p.models.map(m => jsx('option', { value: m + '@' + p.slug, children: m }, p.slug + ':' + m)) }, p.slug)
                        ),
                        to && !other && !known(to) ? jsx('option', { value: to, children: to }, 'typed') : null,
                        jsx('option', { value: '__other', children: t('switch.other') }, 'other')
                      ]
                    }),
                    other
                      ? jsx('input', {
                          'aria-label': t('switch.to_aria'),
                          autoFocus: true,
                          className: 'tn-input',
                          name: 'to',
                          onChange: e => setDraft(e.target.value),
                          placeholder: t('switch.placeholder', { example: models[0] || 'gpt-5' }),
                          value: draft
                        })
                      : null
                  ]
                }),
                jsxs('button', {
                  'aria-busy': isFetching ? 'true' : undefined,
                  className: 'tn-btn',
                  'data-kind': 'primary',
                  type: 'submit',
                  children: [isFetching ? jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }) : null, t('switch.preview')]
                })
              ]
            }),
        error ? jsx('p', { className: 'tn-note', children: error.message || String(error) }) : null,
        agents.length && !to
          ? jsx(SettingRow, { n: 1, title: t('switch.pick_title'), children: jsx('p', { className: 'tn-htext', children: t('switch.pick_body') }) })
          : null,
        res
          ? jsxs('div', {
              className: 'tn-section',
              style: { paddingBlockStart: '1rem' },
              children: [
                jsxs('div', {
                  className: 'tn-pills',
                  children: [
                    jsxs('span', { className: 'tn-sw-pair tn-bdi', children: [jsx('b', { children: res.from }), ' ' + t('switch.arrow') + ' ', jsx('b', { children: res.to })] }),
                    ...SWITCH_STATES.map(k => (counts[k] ? jsx(SwitchFlag, { k, children: t('switch.count_' + k, { n: counts[k] }) }, k) : null)),
                    res.strict ? jsx('span', { className: 'tn-flag', 'data-kind': 'fault', children: t('switch.strict') }) : null
                  ]
                }),
                jsx('dl', {
                  className: 'tn-sw-legend',
                  children: SWITCH_STATES.flatMap(k => [jsx('dt', { children: jsx(SwitchFlag, { k, children: t('switch.label_' + k) }) }, 'dt' + k), jsx('dd', { children: t('switch.text_' + k) }, 'dd' + k)])
                }),
                jsx('div', {
                  className: 'tn-map-scroll',
                  children: jsxs('table', {
                    className: 'tn-table',
                    children: [
                      jsx('thead', {
                        children: jsxs('tr', {
                          children: [
                            jsx('th', { children: t('switch.col_type') }),
                            jsx('th', { children: t('switch.col_outcome') }),
                            jsx('th', { children: t('switch.col_now') }),
                            jsx('th', { children: t('switch.col_after') }),
                            jsx('th', { children: t('switch.col_public') }),
                            jsx('th', { children: t('switch.col_record') })
                          ]
                        })
                      }),
                      jsx('tbody', {
                        children: res.types.map((ty, ri) => {
                          const c = ty.card || {}
                          const delta = c.delta != null ? t('switch.delta', { delta: (c.delta > 0 ? '+' : '') + dec1(c.delta) }) : ''
                          return jsxs(
                            'tr',
                            {
                              className: motion ? 'tn-enter' : undefined,
                              style: motion ? { animationDelay: `${ri * 30}ms` } : undefined,
                              children: [
                                jsxs('td', { children: [jsx('code', { className: 'tn-mono tn-bdi', children: ty.type }), jsx('div', { className: 'tn-hint', children: groupName(t, ty.stakes) })] }),
                                jsx('td', { children: jsx(SwitchFlag, { k: ty.status, children: SWITCH_STATES.includes(ty.status) ? t('switch.label_' + ty.status) : ty.status }) }),
                                jsx('td', { children: cellTier(ty.old) }),
                                jsxs('td', { children: [cellTier(ty.new), ty.new.provisional ? jsx('div', { className: 'tn-hint', children: t('switch.provisional', { n: ty.new.provisional }) }) : null] }),
                                jsx('td', {
                                  children: c.benchmark
                                    ? jsxs('div', {
                                        children: [
                                          jsx('div', { className: 'tn-hint', children: c.benchmark }),
                                          jsx('div', { className: 'tn-mono tn-bdi', children: (c.old != null ? dec1(c.old) : '—') + ' ' + t('switch.arrow') + ' ' + (c.new != null ? dec1(c.new) : '—') + delta })
                                        ]
                                      })
                                    : jsx('span', { className: 'tn-hint', children: t('switch.no_public') })
                                }),
                                jsx('td', {
                                  children: (ty.personal || []).length
                                    ? ty.personal.map(p => jsxs('div', { className: 'tn-hint', children: [jsx('span', { className: 'tn-mono', style: { color: 'var(--tn-fg)' }, children: num(p.faults) + ' / ' + num(p.successes + p.faults) }), ' ' + displayName(p.model)] }, p.agent))
                                    : jsx('span', { className: 'tn-hint', children: t('switch.none') })
                                })
                              ]
                            },
                            ty.type
                          )
                        })
                      })
                    ]
                  })
                }),
                jsx('p', { className: 'tn-hint', children: t('switch.footnote') })
              ]
            })
          : null
      ]
    })
  })
}

// ---- undo
const undoEffect = (u, t) => (!u.file ? t('undo.effect_none') : u.counts_as_fault ? t('undo.effect_fault') : t('undo.effect_already'))

/** Undo, after Hermes' own confirmation dialog: restores the files from their snapshot, counts as a fault. */
function UndoDialog({ target, onClose, t }) {
  const qc = useQueryClient()
  return jsx(ConfirmDialog, {
    confirmLabel: t('recent.undo'),
    description: target ? undoEffect(target, t) : null,
    destructive: true,
    onClose,
    onConfirm: async () => {
      const u = target
      try {
        const r = await rest('/undo?of=' + encodeURIComponent(u.profile), { method: 'POST', body: { id: u.id } })
        haptic('success')
        host.notify({ kind: r && r.ok === false ? 'warning' : 'success', message: (r && r.message) || t('recent.undone') })
      } catch (e) {
        host.notifyError(e, t('recent.undo_failed'))
      } finally {
        qc.invalidateQueries({ queryKey: ['tenure'] })
      }
    },
    open: target !== null,
    title: target ? t('confirm.undo_title', { id: target.id }) : ''
  })
}

/** Flag one action an error nobody caught, after Hermes' own confirmation dialog: a fault on its type. */
function FlagDialog({ target, onClose, t }) {
  const qc = useQueryClient()
  return jsx(ConfirmDialog, {
    busyLabel: t('revoke.busy'),
    confirmLabel: t('flag.confirm'),
    description: target ? t('flag.desc', { type: target.type }) : null,
    destructive: true,
    onClose,
    onConfirm: async () => {
      const r = target
      await rest('/flag?of=' + encodeURIComponent(r.profile), { method: 'POST', body: { agent: r.agent, type: r.type } })
      haptic('success')
      host.notify({ kind: 'success', message: t('recent.flagged', { type: r.type }) })
      qc.invalidateQueries({ queryKey: ['tenure'] })
    },
    open: target !== null,
    title: t('flag.title')
  })
}

function UndoView({ data, t }) {
  const motion = useMotion()
  const { data: act } = useActivity()
  const [open, setOpen] = useState({})
  const [target, setTarget] = useState(null)
  const [flagging, setFlagging] = useState(null)
  const list = (act && act.undoable) || []
  const current = data && data.current
  const head = jsxs('header', {
    className: 'tn-hero',
    style: { display: 'block' },
    children: [
      jsx('div', { className: 'tn-eyebrow', children: '#' + t('page.view_undo') }),
      list.length ? null : jsx('h3', { className: 'tn-name', children: t('undo.empty_title') }),
      jsx('p', { className: 'tn-intro-body', style: { margin: '0.35rem 0 0' }, children: list.length ? t('undo.lede') : t('undo.empty_body') })
    ]
  })
  let i = 0
  const row = (u, sub) => {
    const mine = u.profile === current
    const idx = i++
    return jsxs(
      'tr',
      {
        className: cn(motion && 'tn-enter', sub && 'tn-sub'),
        style: motion ? { animationDelay: `${idx * 30}ms` } : undefined,
        children: [
          jsx('td', { className: 'tn-mono tn-dim', children: String(u.id) }),
          jsxs('td', { children: [jsx('span', { className: 'tn-mono', children: ago(t, u.age) }), jsx('div', { className: 'tn-hint', children: t('undo.window_ends', { duration: duration(t, UNDO_WINDOW - u.age) }) })] }),
          jsxs('td', { children: [jsx('span', { className: 'tn-bdi', children: u.agent }), jsx('div', { className: 'tn-hint tn-bdi', children: t('map.profile', { profile: u.profile }) })] }),
          jsx('td', { children: jsx('code', { className: 'tn-mono tn-bdi', children: u.type }) }),
          jsx('td', {
            children: u.file
              ? jsxs('span', { children: [jsx('code', { className: 'tn-mono tn-bdi', children: u.file }), u.files > 1 ? jsx('span', { className: 'tn-dim', children: ' ' + t('recent.more_files', { n: u.files - 1 }) }) : null] })
              : jsx('span', { className: 'tn-hint', children: t('recent.no_snapshot') })
          }),
          jsx('td', { className: 'tn-hint', children: undoEffect(u, t) }),
          jsxs('td', {
            className: 'tn-end',
            children: [
              jsx(Tip, {
                label: mine ? t('recent.flag_tip') : t('common.own_profile_only'),
                children: jsx('span', { tabIndex: mine ? undefined : 0, children: jsx(Button, { disabled: !mine, onClick: () => setFlagging(u), size: 'xs', variant: 'ghost', children: t('recent.flag') }) })
              }),
              jsx(Tip, {
                label: mine ? t('undo.title') : t('common.own_profile_only'),
                children: jsx('span', { tabIndex: mine ? undefined : 0, children: jsx(Button, { disabled: !mine, onClick: () => setTarget(u), size: 'xs', variant: 'outline', children: t('undo.confirm', { id: u.id }) }) })
              })
            ]
          })
        ]
      },
      u.profile + u.id
    )
  }
  return jsx('div', {
    className: 'tn-root tn-doc-wrap',
    children: jsxs('div', {
      className: 'tn-doc tn-doc-wide',
      children: [
        head,
        list.length
          ? jsx('div', {
              className: 'tn-map-scroll',
              children: jsxs('table', {
                className: 'tn-table',
                children: [
                  jsx('thead', {
                    children: jsxs('tr', {
                      children: [
                        jsx('th', { children: '#' }),
                        jsx('th', { children: t('undo.col_when') }),
                        jsx('th', { children: t('undo.col_agent') }),
                        jsx('th', { children: t('undo.col_type') }),
                        jsx('th', { children: t('undo.col_file') }),
                        jsx('th', { children: t('undo.col_effect') }),
                        jsx('th', {})
                      ]
                    })
                  }),
                  jsx('tbody', {
                    children: groupUndo(list).flatMap(g => {
                      if (g.rows.length === 1) return [row(g.rows[0], false)]
                      const first = g.rows[0]
                      const expanded = !!open[g.key]
                      const toggle = () => setOpen(o => ({ ...o, [g.key]: !expanded }))
                      const idx = i++
                      return [
                        jsxs(
                          'tr',
                          {
                            className: motion ? 'tn-enter' : undefined,
                            style: motion ? { animationDelay: `${idx * 30}ms` } : undefined,
                            children: [
                              jsx('td', {
                                children: jsxs('button', {
                                  'aria-expanded': expanded,
                                  'aria-label': (expanded ? t('recent.collapse') : t('recent.expand')) + ': ' + g.rows.length + ' × ' + g.type,
                                  className: 'tn-ugroup',
                                  onClick: toggle,
                                  type: 'button',
                                  children: [jsx(Codicon, { name: expanded ? 'chevron-down' : 'chevron-right', size: '0.75rem' }), jsx('b', { children: num(g.rows.length) + ' ×' })]
                                })
                              }),
                              jsx('td', { children: jsx('span', { className: 'tn-mono', children: ago(t, first.age) }) }),
                              jsxs('td', { children: [jsx('span', { className: 'tn-bdi', children: g.agent }), jsx('div', { className: 'tn-hint tn-bdi', children: t('map.profile', { profile: g.profile }) })] }),
                              jsx('td', { children: jsx('code', { className: 'tn-mono tn-bdi', children: g.type }) }),
                              jsx('td', { children: jsx('span', { className: 'tn-hint', children: t('recent.no_snapshot') }) }),
                              jsx('td', { className: 'tn-hint', children: undoEffect(first, t) }),
                              jsx('td', { className: 'tn-end', children: jsx(Button, { onClick: toggle, size: 'xs', variant: 'ghost', children: expanded ? t('recent.collapse') : t('recent.expand') }) })
                            ]
                          },
                          'g' + g.key
                        ),
                        ...(expanded ? g.rows.map(u => row(u, true)) : [])
                      ]
                    })
                  })
                ]
              })
            })
          : null,
        jsx(UndoDialog, { onClose: () => setTarget(null), t, target }),
        jsx(FlagDialog, { onClose: () => setFlagging(null), t, target: flagging })
      ]
    })
  })
}

// ---- the agent's evidence timeline (/timeline): the ledger, newest first, repeated outcomes grouped
const FAULT_SOURCES = ['refusal', 'spot', 'check', 'undo', 'flag']
const NEUTRAL_SOURCES = ['alone', 'error', 'blocked', 'timeout', 'nobody', 'expired', 'ambiguous']
const TIER_REASONS = ['wald', 'fault', 'settings', 'stakes']

function describeEvent(e, t) {
  const src = e.source
  if (e.event === 'outcome') {
    if (e.result === 'success')
      return { glyph: '✓', tone: 'ok', text: src === 'notify' ? t('event.success_notify') : src === 'spot' ? t('event.success_spot') : t('event.success_approved') }
    if (e.result === 'fault') return { glyph: '✕', tone: 'fault', text: FAULT_SOURCES.includes(src) ? t('event.fault_' + src) : t('event.fault_other', { source: String(src) }) }
    return { glyph: '○', tone: 'muted', text: NEUTRAL_SOURCES.includes(src) ? t('event.neutral_' + src) : t('event.neutral_other', { source: String(src) }) }
  }
  if (e.event === 'tier') {
    const required = String(e.required || '')
    const series = e.required ? t('event.why_series_n', { required }) : t('event.why_series_complete')
    const why =
      e.reason === 'series' ? (e.sessions ? series + ' · ' + t('event.why_sessions', { n: e.sessions }) : series) : TIER_REASONS.includes(e.reason) ? t('event.why_' + e.reason) : e.reason
    const from = tierCode(e.from, t)
    const to = tierCode(e.to, t)
    return { glyph: '◆', tone: 'move', text: t('event.tier', { from, to, why }) }
  }
  if (e.event === 'trial') {
    const left = Number(e.left) || TRIAL
    const text =
      e.to === 'open'
        ? e.reason === 'wait over'
          ? t('event.trial_reopens', { n: left })
          : t('event.trial_opened', { n: left })
        : e.to === 'wait'
          ? t('event.trial_failed', { n: Number(e.wait) || 0 })
          : t('event.trial_passed')
    return { glyph: '◇', tone: 'warn', text }
  }
  if (e.event === 'revoke' || e.event === 'revoked') return { glyph: '↺', tone: 'fault', text: t('event.revoked') }
  if (e.event === 'confirmed') return { glyph: '✓', tone: 'ok', text: t('event.confirmed') }
  if (e.event === 'agent') return { glyph: '⇄', tone: 'move', text: e.from ? t('event.switch_from', { from: e.from }) : t('event.switch') }
  if (e.event === 'neutral_expired') return { glyph: '○', tone: 'muted', text: t('event.neutral_expired') }
  return { glyph: '·', tone: 'muted', text: e.event }
}

function runs(events) {
  const out = []
  for (const e of events) {
    const sig = [e.event, e.result, e.source, e.type, e.reason, e.from, e.to].join('|')
    const last = out[out.length - 1]
    if (last && last.sig === sig && e.event === 'outcome' && dayKey(last.first.at) === dayKey(e.at)) {
      last.count += 1
      last.last = e
    } else out.push({ sig, first: e, last: e, count: 1 })
  }
  return out
}

const TIMELINE_SHOWN = 30

function TimelineSection({ agent, t, n }) {
  const [filter, setFilter] = useState('all')
  const [all, setAll] = useState(false)
  const { data, error } = useQuery({
    queryKey: ['tenure', agent.profile, 'timeline', agent.agent],
    queryFn: () => rest(`/timeline?agent=${encodeURIComponent(agent.agent)}&of=${encodeURIComponent(agent.profile)}`),
    refetchInterval: HEARTBEAT_MS
  })
  const events = data ? data.events || [] : null
  const shown = events && filter !== 'all' ? events.filter(e => e.type === filter) : events
  const grouped = shown ? runs(shown) : []
  const visible = all ? grouped : grouped.slice(0, TIMELINE_SHOWN)
  const days = []
  for (const r of visible) {
    const k = dayKey(r.first.at)
    let g = days[days.length - 1]
    if (!g || g.key !== k) days.push((g = { key: k, label: dayLabel(r.first.at), items: [] }))
    g.items.push(r)
  }
  return jsxs('section', {
    className: 'tn-section',
    children: [
      jsxs('div', {
        className: 'tn-section-head',
        children: [
          jsx(Eyebrow, { n, children: t('timeline.title') }),
          jsx('select', {
            'aria-label': t('timeline.filter_label'),
            className: 'tn-input tn-input-sm',
            onChange: e => setFilter(e.target.value),
            value: filter,
            children: [jsx('option', { value: 'all', children: t('timeline.all_types') }, 'all'), ...(agent.types || []).map(ty => jsx('option', { value: ty.type, children: ty.type }, ty.type))]
          })
        ]
      }),
      jsx('p', { className: 'tn-hint', children: t('timeline.note') }),
      error
        ? jsx('p', { className: 'tn-note', children: error.message || String(error) })
        : !events
          ? jsx('p', { className: 'tn-hint', children: t('common.loading') })
          : !grouped.length
            ? jsx('p', { className: 'tn-hint', children: t('timeline.empty') })
            : jsxs('div', {
                className: 'tn-tl-wrap',
                children: [
                  ...days.map(g =>
                    jsxs(
                      'div',
                      {
                        className: 'tn-tl-day',
                        children: [
                          jsx('div', { className: 'tn-eyebrow tn-tl-label', children: g.label }),
                          jsx('ol', {
                            children: g.items.map(r => {
                              const d = describeEvent(r.first, t)
                              const span = r.count > 1 && hm(r.last.at) !== hm(r.first.at) ? hm(r.last.at) + '–' + hm(r.first.at) : hm(r.first.at)
                              return jsxs(
                                'li',
                                {
                                  className: 'tn-tl-item',
                                  'data-tone': d.tone,
                                  children: [
                                    jsx('span', { className: 'tn-tl-time', children: span }),
                                    jsx('span', { 'aria-hidden': true, className: 'tn-tl-glyph', children: d.glyph }),
                                    jsxs('span', { className: 'tn-tl-text', children: [r.count > 1 ? jsx('b', { children: t('timeline.count', { n: r.count }) + ' ' }) : null, d.text] }),
                                    r.first.type ? jsx('code', { className: 'tn-tl-type tn-bdi', children: r.first.type }) : null,
                                    jsx('span', { className: 'tn-tl-seq', children: '#' + (r.count > 1 ? r.last.seq + '–' + r.first.seq : r.first.seq) })
                                  ]
                                },
                                r.first.seq
                              )
                            })
                          })
                        ]
                      },
                      g.key
                    )
                  ),
                  grouped.length > TIMELINE_SHOWN
                    ? jsx('div', { children: jsx(Button, { onClick: () => setAll(!all), size: 'xs', variant: 'outline', children: all ? t('recent.show_fewer') : t('recent.show_all', { n: grouped.length }) }) }, 'more')
                    : null
                ]
              })
    ]
  })
}

/** The keys of this page (while focus is inside it); the keys stay as they are, only their descriptions are translated. */
const PAGE_KEYS = [
  ['m', 'map'],
  ['b', 'benchmark'],
  ['c', 'community'],
  ['w', 'switch'],
  ['p', 'passport'],
  ['u', 'undo'],
  ['s', 'settings'],
  ['a', 'agents'],
  ['?', 'help']
]

let focusKey = null
let focusRevoke = false

/** Open another tab of the page, with an agent in mind (the switch preview starts from it). */
function openView(view, key) {
  focusKey = key || null
  bus.dispatchEvent(new CustomEvent('view', { detail: { view } }))
}

function AnimationsToggle({ t }) {
  const [on, setOn] = useState(() => animPref !== 'off')
  const [reduced, setReduced] = useState(() => !!(reducedQuery && reducedQuery.matches))
  // The header switch and the one in Settings share ctx.storage `animations`: each follows the other.
  useEffect(() => {
    const sync = () => setOn(animPref !== 'off')
    bus.addEventListener('motion', sync)
    return () => bus.removeEventListener('motion', sync)
  }, [])
  useEffect(() => {
    if (!reducedQuery || !reducedQuery.addEventListener) return
    const update = () => setReduced(reducedQuery.matches)
    reducedQuery.addEventListener('change', update)
    return () => reducedQuery.removeEventListener('change', update)
  }, [])
  const label = jsxs('label', {
    className: 'tn-anim-toggle',
    'data-off': reduced ? 'true' : 'false',
    children: [
      jsx('span', { children: t('page.animations') }),
      jsx(Switch, {
        'aria-label': reduced ? t('page.animations_reduced') : t('page.animations'),
        checked: on && !reduced,
        disabled: reduced,
        onCheckedChange: value => {
          setOn(!!value)
          setAnimPref(value ? 'on' : 'off')
        },
        size: 'xs'
      })
    ]
  })
  return reduced ? jsx(Tip, { label: t('page.animations_reduced'), children: jsx('span', { tabIndex: 0, children: label }) }) : label
}

function RawToggle({ t }) {
  const on = useRaw()
  const qc = useQueryClient()
  return jsx(Tip, {
    label: t('page.raw_title'),
    children: jsxs('button', {
      'aria-pressed': on ? 'true' : 'false',
      className: 'tn-anim-toggle tn-raw',
      onClick: () => {
        setRawPref(!on)
        qc.resetQueries({ queryKey: ['tenure'] })
      },
      type: 'button',
      children: [jsx('i', { 'aria-hidden': true, 'data-on': on ? 'true' : 'false' }), t(on ? 'page.raw_on' : 'page.raw_off')]
    })
  })
}

const VIEWS = ['map', 'agents', 'benchmark', 'community', 'switch', 'passport', 'undo', 'settings', 'help']
const typing = e => {
  const el = e.target
  const tag = ((el && el.tagName) || '').toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || (el && el.isContentEditable) || !!(el && el.closest && el.closest('[role=dialog],[role=alertdialog]'))
}

function TenurePage() {
  const t = usePluginI18n(ID)
  const { data, error, isLoading, refetch, dataUpdatedAt } = useAgents()
  const { data: activity } = useActivity()
  const qc = useQueryClient()
  const [view, setViewNow] = useState('map')
  const back = useRef('map')                           // the view "?" or Esc returns to from Help
  const setView = v => {
    setViewNow(cur => {
      if (cur !== 'help') back.current = cur
      return v
    })
  }
  const rootRef = useRef(null)
  useEffect(() => {
    const onFocus = () => setView('agents')
    const onView = e => setView(e.detail.view)
    bus.addEventListener('focus', onFocus)
    bus.addEventListener('view', onView)
    // Shortcuts work while focus is inside the page: it takes focus when it opens.
    if (rootRef.current && document.activeElement === document.body) rootRef.current.focus()
    return () => {
      bus.removeEventListener('focus', onFocus)
      bus.removeEventListener('view', onView)
    }
  }, [])
  const transitions = usePageTransitions(data, t)
  const agents = allAgents(data)
  const here = ((data && data.profiles) || []).find(p => p.current) || {}
  const start = startOf(here.settings, (here.agents || []).flatMap(a => a.types || []))
  const trustedStart = (start || DEFAULTS.start) === 'trusted'
  const unreadable = ((data && data.profiles) || []).filter(p => p.error).map(p => p.profile)
  const undoCount = ((activity && activity.undoable) || []).length
  const onKey = e => {
    if (e.metaKey || e.ctrlKey || e.altKey || typing(e)) return
    const hit = PAGE_KEYS.find(([k]) => k === e.key)
    if (e.key === '?') {
      setView(view === 'help' ? back.current : 'help')    // ? toggles the help
      e.preventDefault()
    } else if (hit) {
      setView(hit[1])
      e.preventDefault()
    } else if (e.key === 'r') {
      setRawPref(!rawPref)
      qc.resetQueries({ queryKey: ['tenure'] })
      e.preventDefault()
    } else if (e.key === 'Escape' && (view === 'help' || view === 'agents')) {
      // Dialogs keep their own Escape (typing() skips them); then the agent's page closes, then the help.
      setView(view === 'help' ? (back.current === 'help' ? 'map' : back.current) : 'map')
      e.preventDefault()
    } else if (['j', 'k', 'ArrowDown', 'ArrowUp'].includes(e.key) && view === 'map' && rootRef.current) {
      // Next / previous agent: focus moves between the map's agent buttons; Enter opens the focused one.
      const btns = [...rootRef.current.querySelectorAll('.tn-magent')]
      if (!btns.length) return
      const at = btns.indexOf(document.activeElement)
      const next = at < 0 ? 0 : Math.max(0, Math.min(btns.length - 1, at + (e.key === 'j' || e.key === 'ArrowDown' ? 1 : -1)))
      btns[next].focus()
      if (btns[next].scrollIntoView) btns[next].scrollIntoView({ block: 'nearest' })
      e.preventDefault()
    }
  }
  const openAgent = key => {
    focusKey = key
    focusRevoke = false
    setView('agents')
  }
  let body
  if (isLoading && !data) body = jsx(PanelEmpty, { description: t('common.loading'), icon: 'loading~spin' })
  else if (error && !data)
    body = jsx(ErrorState, {
      description: t('backend.desc', { error: error.message || String(error) }),
      title: t('backend.title'),
      children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('common.retry') })
    })
  else if (view === 'settings') body = jsx(SettingsView, { data, t })
  else if (view === 'help') body = jsx(HelpView, { data, t })
  else if (view === 'community') body = jsx(CommunityView, { t })
  else if (!agents.length && (view === 'map' || view === 'agents'))
    body = jsx(PanelEmpty, {
      description: trustedStart
        ? t('map.empty_trusted')
        : jsxs('span', { children: [t('map.empty_before'), jsx('b', { children: t('map.empty_bold') }), t('map.empty_after')] }),
      icon: 'shield',
      title: t('map.empty_title')
    })
  else if (view === 'passport') body = jsx(PassportView, { data, t })
  else if (view === 'map') body = jsx(MapView, { data, onOpen: openAgent, t, transitions })
  else if (view === 'benchmark') body = jsx(BenchmarkView, { t })
  else if (view === 'switch') body = jsx(SwitchView, { data, t })
  else if (view === 'undo') body = jsx(UndoView, { data, t })
  else body = jsx(AgentsView, { data, t })
  return jsxs('div', {
    className: 'tn-root relative flex h-full flex-col overflow-hidden bg-(--ui-surface-background)',
    onKeyDown: onKey,
    ref: rootRef,
    style: { outline: 'none' },
    tabIndex: -1,
    children: [
      jsxs('header', {
        className: 'tn-head shrink-0',
        children: [
          jsxs('div', {
            className: 'tn-head-row',
            children: [
              jsx('h1', { className: 'text-sm font-semibold text-foreground', style: { margin: 0 }, children: t('page.title') }),
              agents.length
                ? jsx('span', { className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 py-px text-[0.625rem] tabular-nums text-(--ui-text-tertiary)', children: String(agents.length) })
                : null,
              data ? jsxs('div', { className: 'tn-head-tog', children: [jsx(RawToggle, { t }), jsx(AnimationsToggle, { t })] }) : null
            ]
          }),
          data
            ? jsx('div', {
                className: 'tn-head-ctl',
                children: jsx(SegmentedControl, {
                  onChange: setView,
                  options: VIEWS.map(id => ({ id, label: id === 'undo' && undoCount ? `${t('page.view_undo')} · ${num(undoCount)}` : t('page.view_' + id) })),
                  sizing: 'content',
                  value: view
                })
              })
            : null
        ]
      }),
      unreadable.length ? jsx('p', { className: 'tn-note', style: { margin: '0 1rem 0.75rem' }, children: t('page.unreadable', { profiles: unreadable.join(', ') }) }) : null,
      error && data
        ? jsx('p', { className: 'tn-note', role: 'status', style: { margin: '0 1rem 0.75rem' }, children: t('page.stale', { error: error.message || String(error), time: dataUpdatedAt ? hms(dataUpdatedAt) : '—' }) })
        : null,
      agents.length && (view === 'map' || view === 'agents' || view === 'benchmark') ? jsx(Intro, { t, spot: (here.settings || {}).spot, start }) : null,
      body
    ]
  })
}

// ------------------------------------------------------------------------------------------------ status-bar chip
function Chip() {
  const t = usePluginI18n(ID)
  const { data } = useAgents()
  const model = useValue(host.state.model)
  const a = agentForModel(data, model)
  if (!a) return null
  const total = (a.types || []).filter(x => !x.capped).length
  const n = earned(a)
  const tip = t('chip.tip', { name: displayName(a.model), earned: n, n: total })
  return jsx(Tip, {
    label: tip,
    children: jsxs('button', {
      'aria-label': tip,
      className: cn(
        'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] tabular-nums transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      onClick: () => {
        haptic('tap')
        host.navigate(ROUTE)
      },
      type: 'button',
      children: [jsx(Codicon, { className: n > 0 ? 'text-primary' : undefined, name: 'shield', size: '0.7rem' }), `${n}/${total}`]
    })
  })
}

// ------------------------------------------------------------------------------------------------ registration
export default {
  id: ID,
  name: 'Tenure',
  description: 'Autonomy each action type earns on verified evidence: tiers, your own benchmark, a signed passport.',
  register(ctx) {
    ctx.i18n.register(hostBundles(TENURE_LOCALES))
    storage = ctx.storage
    rawPref = !!storage && storage.get('raw', 'off') === 'on'
    // Every call of the page carries raw=1 while raw names are on (the dashboard's `r` switch).
    rest = (path, opts) => ctx.rest(rawPref ? path + (path.includes('?') ? '&' : '?') + 'raw=1' : path, opts)
    animPref = storage && storage.get('animations', 'on') === 'off' ? 'off' : 'on'
    passStyle = cleanPassStyle(storage ? storage.get('passport_style', null) : null)
    const style = document.createElement('style')
    style.dataset.plugin = ID
    style.textContent = CSS
    document.head.append(style)
    onStyle = document.createElement('style')
    onStyle.dataset.plugin = ID
    document.head.append(onStyle)
    watchTheme()
    ctx.onDispose(() => {
      rest = null
      storage = null
      style.remove()
      if (onStyle) onStyle.remove()
      onStyle = null
      if (probe) probe.remove()
      probe = null
      lastInk = ''
      if (dprQuery) dprQuery.removeEventListener('change', onDpr)
      dprQuery = null
      if (themeObserver) themeObserver.disconnect()
      themeObserver = null
      repaints.clear()
      seen.clear()
    })
    const tr = (key, ...args) => ctx.i18n.t(key, ...args)
    const current = () => agentForModel(cache.agents, host.state.model.get())
    const focus = (key, revoke) => {
      focusKey = key
      focusRevoke = !!revoke
      host.navigate(ROUTE)
      bus.dispatchEvent(new CustomEvent('focus', { detail: { key, revoke: !!revoke } }))
    }

    // Live: the agent half pushes `changed` after every outcome and `acted` when a T2 action ran.
    ctx.onEvent('plugin.tenure.changed', () => bus.dispatchEvent(new Event('changed')))
    const acted = new Map()                       // type -> changes since its toast opened
    ctx.onEvent('plugin.tenure.acted', ({ payload }) => {
      bus.dispatchEvent(new Event('changed'))
      if (!payload || payload.undo_id == null) return
      const name = displayName(String(payload.agent || '').split('@')[0])
      const n = (acted.get(payload.type) || 0) + 1
      acted.set(payload.type, n)
      ctx.setTimeout(() => acted.delete(payload.type), 60_000)
      host.notify({
        id: 'tenure-acted-' + payload.type,
        kind: payload.fault ? 'warning' : 'info',
        message: tr('toast.acted', { type: payload.type, n, name }),
        detail: tr('toast.acted_detail'),
        action: {
          label: tr('recent.undo'),
          onClick: async () => {
            try {
              await ctx.rest('/undo' + (payload.profile ? '?of=' + encodeURIComponent(payload.profile) : ''), { method: 'POST', body: { id: payload.undo_id } })
              host.notify({ kind: 'success', message: tr('recent.undone') })
              bus.dispatchEvent(new Event('changed'))
            } catch (e) {
              host.notifyError(e, tr('recent.undo_failed'))
            }
          }
        }
      })
    })

    const contributions = () => [
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(TenurePage, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, order: 60, data: { codicon: 'shield', label: tr('nav.label'), path: ROUTE } },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 85, render: () => jsx(Chip, {}) },
      { id: 'open', area: PALETTE_AREA, data: { id: 'tenure.open', label: tr('palette.open'), keywords: ['tenure', 'autonomy', 'tier', 'trust'], run: () => host.navigate(ROUTE) } },
      {
        id: 'passport',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.passport',
          label: tr('palette.passport'),
          keywords: ['tenure', 'passport', 'verify'],
          run: () => {
            const a = current()
            if (!a) return host.notify({ kind: 'info', message: tr('palette.no_current') })
            focus(a.key, false)
          }
        }
      },
      {
        id: 'revoke',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.revoke',
          label: tr('palette.revoke'),
          keywords: ['tenure', 'revoke', 'trust'],
          run: () => {
            const a = current()
            if (!a) return host.notify({ kind: 'info', message: tr('palette.no_current') })
            focus(a.key, true)
          }
        }
      }
    ]
    let dispose = ctx.registerMany(contributions())
    const badge = () =>
      ctx.register({
        id: 'model-badge',
        area: MODEL_MENU_ROW_AREA,
        data: {
          decorate: ({ model }) => {
            const a = agentForModel(cache.agents, model)
            if (!a) return null
            const tier = bestTier(a)
            return tier === 'ask' || tier === 'cap' || tier === 'trusted' ? null : { badge: tr('model_menu.badge', { tier: TIER_SHORT[tier] }) }
          }
        }
      })
    let disposeBadge = badge()
    let badgeTiers = ''
    const tiersKey = () => allAgents(cache.agents).map(a => a.key + ':' + bestTier(a)).join('|')
    ctx.onEvent('plugin.tenure.changed', () => {
      fetchAgents()
        .then(() => {
          const now = tiersKey()
          if (now !== badgeTiers) {
            badgeTiers = now
            disposeBadge()
            disposeBadge = badge()                 // decorate() reruns only when the registry changes
          }
        })
        .catch(() => {})
    })
    ctx.i18n.onLocaleChange(() => {
      dispose()
      dispose = ctx.registerMany(contributions())
      disposeBadge()
      disposeBadge = badge()
    })

    // Warm the cache for the model menu and the palette even before the page or the chip mounts.
    fetchAgents()
      .then(() => {
        badgeTiers = tiersKey()
      })
      .catch(() => {})
  }
}
