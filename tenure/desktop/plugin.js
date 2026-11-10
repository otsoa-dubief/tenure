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
  PanelPill,
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
  useValue,
  WorkspacePageHeaderControl
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
    "benchmark.col_faults": "Faults",
    "benchmark.col_public": "Public",
    "benchmark.col_range": "95% range",
    "benchmark.col_rate": "Rate",
    "benchmark.faults": {
      "one": "{n} fault / {total}",
      "other": "{n} faults / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.not_enough": "not enough evidence",
    "benchmark.note": "Each model's verified record on your work for this action type, with the 95% range of its fault rate, ranked by the top of that range. The public score is context: capability on their tasks, not reliability on yours.",
    "benchmark.public_score": "Public score: {benchmark}, {source}",
    "benchmark.public_score_accessed": "Public score: {benchmark}, {source}, {accessed}.",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "Fault rate and its 95% range, on a 0–70% axis",
    "benchmark.rate": "{rate}% ({low}–{high}%)",
    "benchmark.search": "Search action types",
    "chip.tip": {
      "one": "{name}: {earned} of {n} action type has earned autonomy (T2 or T3). Open Tenure.",
      "other": "{name}: {earned} of {n} action types have earned autonomy (T2 or T3). Open Tenure."
    },
    "common.loading": "Reading the evidence…",
    "common.no_match": "No match",
    "common.retry": "Try again",
    "emblem.none": "No autonomy earned yet",
    "emblem.review": {
      "one": "{n} under review",
      "other": "{n} under review"
    },
    "emblem.tenured": {
      "one": "{n} tenured",
      "other": "{n} tenured"
    },
    "empty.desc": "Work as usual. Every change asks first, and each action type earns its tier from the answers you give.",
    "empty.title": "No agent has acted yet",
    "flag.confirm": "Flag",
    "flag.desc": "This counts as a fault: {type} will drop at least one tier and climb again. Use it for an error nobody caught.",
    "flag.title": "Flag this change as an error?",
    "hero.agent": "Agent",
    "intro.body": "Every action type of every model starts at T1: it asks first. A run of clean, approved actions moves it to T2: it acts, then tells you, with an Undo. A longer run, over two sessions, moves it to T3: it acts on its own, and 1 action in {k} still asks, as a spot check. One fault sends the type back down.",
    "intro.got_it": "Got it",
    "intro.title": "How an action type earns its tier",
    "meta.actions": "Actions",
    "meta.actions_tip": "Every action of this agent tenure saw. Actions nobody verified (no answer, a timeout) count for nothing.",
    "meta.alone": "On its own",
    "meta.checked": "By you",
    "meta.faults": "Faults",
    "meta.preset": "Preset",
    "meta.profile": "Profile",
    "meta.provider": "Provider",
    "model_menu.badge": "{tier} earned",
    "moment.dismiss": "Dismiss",
    "moment.eyebrow_down": "#Fault · {type}",
    "moment.eyebrow_up": "#Promotion · {type}",
    "moment.granted": "Tenure granted",
    "moment.probation": "Back on probation",
    "moment.review": "Under review",
    "nav.label": "Tenure",
    "page.animations": "Animations",
    "page.title": "Tenure",
    "page.view_agents": "Agents",
    "page.view_benchmark": "Your benchmark",
    "palette.no_current": "The current model has no record yet: every change asks first.",
    "palette.open": "Tenure: Open",
    "palette.passport": "Tenure: Show passport for current model",
    "palette.revoke": "Tenure: Revoke current model…",
    "passport.copy": "Copy passport",
    "passport.copy_command": "Copy command",
    "passport.generated": "Generated",
    "passport.ledger": "Ledger",
    "passport.ledger_value": {
      "one": "{n} event · head {head}",
      "other": "{n} events · head {head}"
    },
    "passport.problems": "Does not verify: {problems}",
    "passport.protocol": "Protocol",
    "passport.rule": "Rule",
    "passport.signature": "a plugin for Hermes Agent",
    "passport.title": "Signed passport",
    "passport.unavailable": "Not available: {error}",
    "passport.verified": "Verified: signature valid, hash chain intact, and replaying the ledger gives the same tiers.",
    "passport.verify_hint": "Anyone can check it:",
    "passport.verifying": "Verifying…",
    "preset.copy_pending": "copied from another profile, checked when it starts",
    "preset.name.balanced": "balanced",
    "preset.name.careful": "careful",
    "preset.name.custom": "custom",
    "preset.name.fast": "fast",
    "preset.value": "{preset} · 1 in {k} spot-checked",
    "preset.value_pending": "{preset} · 1 in {k} spot-checked · applies from the next action",
    "recent.check_failed": "check failed",
    "recent.check_failed_tip": "The automatic check failed: already counted as a fault. Undo restores the files.",
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
    "recent.none": "Nothing to undo in the last 24 hours.",
    "recent.show_all": "Show all {n}",
    "recent.show_fewer": "Show fewer",
    "recent.title": "Acted without asking",
    "recent.undo": "Undo",
    "recent.undo_failed": "Could not undo",
    "recent.undo_tip": "Restore the files as they were. Counts as a fault: the type goes back down.",
    "recent.undone": "Files restored. Counted as a fault.",
    "revoke.action": "Revoke…",
    "revoke.busy": "Revoking…",
    "revoke.confirm": "Revoke",
    "revoke.desc": "{name} will ask before every action again. Its record stays in the ledger.",
    "revoke.done": "{name} asks first again on every action type.",
    "revoke.title": "Revoke earned autonomy?",
    "state.aria": "{label}: {tip}",
    "state.fault": "fault",
    "state.fault_tip": "A medium or high fault stays on record until a trial is passed.",
    "state.provisional": "provisional",
    "state.provisional_tip": "Carried over from the previous model, halved, until its own approvals confirm it.",
    "state.suspended": "suspended",
    "state.suspended_tip": "A session read outside content: it asks for everything until it ends.",
    "state.trial": "trial",
    "state.trial_tip": "A medium or high fault opened a trial: 3 verified successes in a row.",
    "tier.cap": "Capped · always asks",
    "tier.name.cap": "Always asks",
    "tier.name.t1": "Probation",
    "tier.name.t2": "Under review",
    "tier.name.t3": "Tenured",
    "tier.t1": "T1 · asks first",
    "tier.t2": "T2 · acts, then tells you, with an Undo",
    "tier.t3": "T3 · acts on its own, spot-checked",
    "toast.acted": {
      "one": "{type} changed, then told you ({name}).",
      "other": "{type}: {n} changes, then told you ({name})."
    },
    "toast.acted_detail": "Undo restores the files of the last change and counts as a fault.",
    "type.always_asks": "always asks",
    "type.guarantee": "At most {aoql}% of this type's actions run with an error nobody approved; {worst}% if the model turns bad.",
    "type.guarantee_provisional": "At most {aoql}% of this type's actions run with an error nobody approved; {worst}% if the model turns bad. Provisional: carried-over evidence.",
    "type.in_a_row": "{series} of {required} in a row",
    "type.next": {
      "one": "{n} more verified success in a row to be tenured.",
      "other": "{n} more verified successes in a row to be tenured."
    },
    "type.next_session": "The series is complete: one more session finishes it.",
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "high stakes",
    "type.stakes_low": "low stakes",
    "type.stakes_medium": "medium stakes",
    "type.stakes_other": "{stakes} stakes",
    "type.tenured_line": "Acts on its own. 1 action in {k} is still spot-checked.",
    "types.title": "Action types"
  },
  "ar": {
    "agents.pick": "اختر وكيلًا لترى ما اكتسبه.",
    "agents.search": "البحث في الوكلاء",
    "backend.desc": "فعّل tenure لهذا الملف الشخصي من المهارات ← الإضافات (عمود «الوكيل»). {error}",
    "backend.title": "جزء الوكيل لا يستجيب",
    "benchmark.col_faults": "الإخفاقات",
    "benchmark.col_public": "عام",
    "benchmark.col_range": "نطاق 95%",
    "benchmark.col_rate": "المعدل",
    "benchmark.faults": {
      "zero": "{n} إخفاقات / {total}",
      "one": "{n} إخفاق / {total}",
      "two": "{n} إخفاقان / {total}",
      "few": "{n} إخفاقات / {total}",
      "many": "{n} إخفاقًا / {total}",
      "other": "{n} إخفاق / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.not_enough": "أدلة غير كافية",
    "benchmark.note": "السجل الموثَّق لكل نموذج على عملك لنوع الإجراء هذا، مع نطاق 95% لمعدل إخفاقه، مرتبًا حسب الحد الأعلى لهذا النطاق. النتيجة العامة للسياق فقط: قدرة على مهامهم، لا موثوقية على مهامك.",
    "benchmark.public_score": "النتيجة العامة: {benchmark}، {source}",
    "benchmark.public_score_accessed": "النتيجة العامة: {benchmark}، {source}، {accessed}.",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "معدل الإخفاق ونطاق 95% له، على محور من 0 إلى 70%",
    "benchmark.rate": "{rate}% ({low}–{high}%)",
    "benchmark.search": "البحث في أنواع الإجراءات",
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
    "common.retry": "حاول مرة أخرى",
    "emblem.none": "لم تُكتسب أي استقلالية بعد",
    "emblem.review": {
      "zero": "قيد المراجعة: {n}",
      "one": "قيد المراجعة: {n}",
      "two": "قيد المراجعة: {n}",
      "few": "قيد المراجعة: {n}",
      "many": "قيد المراجعة: {n}",
      "other": "قيد المراجعة: {n}"
    },
    "emblem.tenured": {
      "zero": "مُثبَّت: {n}",
      "one": "مُثبَّت: {n}",
      "two": "مُثبَّت: {n}",
      "few": "مُثبَّت: {n}",
      "many": "مُثبَّت: {n}",
      "other": "مُثبَّت: {n}"
    },
    "empty.desc": "اعمل كالمعتاد. كل تغيير يسأل أولًا، وكل نوع إجراء يكتسب مستواه من إجاباتك.",
    "empty.title": "لم ينفّذ أي وكيل شيئًا بعد",
    "flag.confirm": "إبلاغ",
    "flag.desc": "يُحسب هذا إخفاقًا: سينزل {type} مستوى واحدًا على الأقل ثم يصعد من جديد. استخدمه لخطأ لم يلحظه أحد.",
    "flag.title": "الإبلاغ عن هذا التغيير كخطأ؟",
    "hero.agent": "الوكيل",
    "intro.body": "يبدأ كل نوع إجراء لكل نموذج في T1: يسأل أولًا. سلسلة من الإجراءات السليمة الموافق عليها تنقله إلى T2: ينفّذ ثم يُبلغك، مع زر تراجع. وسلسلة أطول، على جلستين، تنقله إلى T3: يعمل وحده، ويظل إجراء واحد من كل {k} يسأل، كفحص عشوائي. إخفاق واحد يُنزل النوع من جديد.",
    "intro.got_it": "فهمت",
    "intro.title": "كيف يكتسب نوع الإجراء مستواه",
    "meta.actions": "الإجراءات",
    "meta.actions_tip": "كل إجراء لهذا الوكيل رآه tenure. الإجراءات التي لم يتحقق منها أحد (بلا إجابة، أو انتهت المهلة) لا تُحسب.",
    "meta.alone": "وحده",
    "meta.checked": "بفحصك",
    "meta.faults": "الإخفاقات",
    "meta.preset": "الإعداد المسبق",
    "meta.profile": "الملف الشخصي",
    "meta.provider": "المزوّد",
    "model_menu.badge": "{tier} مكتسب",
    "moment.dismiss": "إغلاق",
    "moment.eyebrow_down": "#إخفاق · {type}",
    "moment.eyebrow_up": "#ترقية · {type}",
    "moment.granted": "مُنح التثبيت",
    "moment.probation": "العودة إلى فترة الاختبار",
    "moment.review": "قيد المراجعة",
    "nav.label": "Tenure",
    "page.animations": "الرسوم المتحركة",
    "page.title": "Tenure",
    "page.view_agents": "الوكلاء",
    "page.view_benchmark": "مقياسك",
    "palette.no_current": "لا سجل للنموذج الحالي بعد: كل تغيير يسأل أولًا.",
    "palette.open": "Tenure: فتح",
    "palette.passport": "Tenure: عرض جواز النموذج الحالي",
    "palette.revoke": "Tenure: سحب استقلالية النموذج الحالي…",
    "passport.copy": "نسخ الجواز",
    "passport.copy_command": "نسخ الأمر",
    "passport.generated": "أُنشئ في",
    "passport.ledger": "الدفتر",
    "passport.ledger_value": {
      "zero": "{n} أحداث · الرأس {head}",
      "one": "{n} حدث · الرأس {head}",
      "two": "{n} حدثان · الرأس {head}",
      "few": "{n} أحداث · الرأس {head}",
      "many": "{n} حدثًا · الرأس {head}",
      "other": "{n} حدث · الرأس {head}"
    },
    "passport.problems": "لا يجتاز التحقق: {problems}",
    "passport.protocol": "البروتوكول",
    "passport.rule": "القاعدة",
    "passport.signature": "إضافة لـ Hermes Agent",
    "passport.title": "جواز موقَّع",
    "passport.unavailable": "غير متاح: {error}",
    "passport.verified": "تم التحقق: التوقيع صالح، وسلسلة التجزئة سليمة، وإعادة تشغيل الدفتر تعطي المستويات نفسها.",
    "passport.verify_hint": "يمكن لأي شخص التحقق منه:",
    "passport.verifying": "جارٍ التحقق…",
    "preset.copy_pending": "منسوخ من ملف شخصي آخر، يُفحص عند تشغيله",
    "preset.name.balanced": "متوازن",
    "preset.name.careful": "حذِر",
    "preset.name.custom": "مخصص",
    "preset.name.fast": "سريع",
    "preset.value": "{preset} · فحص عشوائي لإجراء من كل {k}",
    "preset.value_pending": "{preset} · فحص عشوائي لإجراء من كل {k} · يسري من الإجراء التالي",
    "recent.check_failed": "فشل الفحص",
    "recent.check_failed_tip": "فشل الفحص التلقائي: حُسب إخفاقًا بالفعل. التراجع يستعيد الملفات.",
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
    "recent.none": "لا شيء للتراجع عنه في آخر 24 ساعة.",
    "recent.show_all": "عرض الكل ({n})",
    "recent.show_fewer": "عرض أقل",
    "recent.title": "نُفّذ دون سؤال",
    "recent.undo": "تراجع",
    "recent.undo_failed": "تعذّر التراجع",
    "recent.undo_tip": "استعادة الملفات كما كانت. يُحسب إخفاقًا: ينزل النوع من جديد.",
    "recent.undone": "استُعيدت الملفات. حُسب إخفاقًا.",
    "revoke.action": "سحب…",
    "revoke.busy": "جارٍ السحب…",
    "revoke.confirm": "سحب",
    "revoke.desc": "سيعود {name} إلى السؤال قبل كل إجراء. يبقى سجله في الدفتر.",
    "revoke.done": "يسأل {name} أولًا من جديد في كل أنواع الإجراءات.",
    "revoke.title": "سحب الاستقلالية المكتسبة؟",
    "state.aria": "{label}: {tip}",
    "state.fault": "إخفاق",
    "state.fault_tip": "يبقى الإخفاق المتوسط أو العالي الخطورة مسجّلًا حتى يُجتاز اختبار.",
    "state.provisional": "مؤقت",
    "state.provisional_tip": "منقول من النموذج السابق، منصّفًا، حتى تؤكده موافقاته هو.",
    "state.suspended": "معلّق",
    "state.suspended_tip": "قرأت الجلسة محتوى خارجيًا: يسأل عن كل شيء حتى تنتهي.",
    "state.trial": "اختبار",
    "state.trial_tip": "فتح إخفاق متوسط أو عالي الخطورة اختبارًا: 3 نجاحات موثّقة على التوالي.",
    "tier.cap": "مقيَّد · يسأل دائمًا",
    "tier.name.cap": "يسأل دائمًا",
    "tier.name.t1": "فترة اختبار",
    "tier.name.t2": "قيد المراجعة",
    "tier.name.t3": "مُثبَّت",
    "tier.t1": "T1 · يسأل أولًا",
    "tier.t2": "T2 · ينفّذ ثم يُبلغك، مع زر تراجع",
    "tier.t3": "T3 · يعمل وحده، مع فحص عشوائي",
    "toast.acted": {
      "zero": "{type}: {n} تغييرات، ثم أبلغك ({name}).",
      "one": "{type}: تغيير واحد، ثم أبلغك ({name}).",
      "two": "{type}: تغييران، ثم أبلغك ({name}).",
      "few": "{type}: {n} تغييرات، ثم أبلغك ({name}).",
      "many": "{type}: {n} تغييرًا، ثم أبلغك ({name}).",
      "other": "{type}: {n} تغيير، ثم أبلغك ({name})."
    },
    "toast.acted_detail": "التراجع يستعيد ملفات آخر تغيير ويُحسب إخفاقًا.",
    "type.always_asks": "يسأل دائمًا",
    "type.guarantee": "على الأكثر {aoql}% من إجراءات هذا النوع تُنفَّذ بخطأ لم يوافق عليه أحد؛ و{worst}% إذا ساء النموذج.",
    "type.guarantee_provisional": "على الأكثر {aoql}% من إجراءات هذا النوع تُنفَّذ بخطأ لم يوافق عليه أحد؛ و{worst}% إذا ساء النموذج. مؤقت: أدلة منقولة.",
    "type.in_a_row": "{series} من {required} على التوالي",
    "type.next": {
      "zero": "لم يبقَ أي نجاح موثَّق للتثبيت ({n}).",
      "one": "نجاح موثَّق واحد آخر على التوالي للتثبيت.",
      "two": "نجاحان موثَّقان آخران على التوالي للتثبيت.",
      "few": "{n} نجاحات موثَّقة أخرى على التوالي للتثبيت.",
      "many": "{n} نجاحًا موثَّقًا آخر على التوالي للتثبيت.",
      "other": "{n} نجاح موثَّق آخر على التوالي للتثبيت."
    },
    "type.next_session": "اكتملت السلسلة: تبقى جلسة واحدة أخرى.",
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
    "types.title": "أنواع الإجراءات"
  },
  "es": {
    "agents.pick": "Elige un agente para ver lo que se ha ganado.",
    "agents.search": "Buscar agentes",
    "backend.desc": "Activa tenure para este perfil en Capacidades → Plugins (columna Agente). {error}",
    "backend.title": "La mitad del agente no responde",
    "benchmark.col_faults": "Fallos",
    "benchmark.col_public": "Pública",
    "benchmark.col_range": "Rango 95 %",
    "benchmark.col_rate": "Tasa",
    "benchmark.faults": {
      "one": "{n} fallo / {total}",
      "other": "{n} fallos / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.not_enough": "evidencia insuficiente",
    "benchmark.note": "El historial verificado de cada modelo en tu trabajo para este tipo de acción, con el rango del 95 % de su tasa de fallos, ordenado por el extremo superior de ese rango. La puntuación pública es contexto: capacidad en sus tareas, no fiabilidad en las tuyas.",
    "benchmark.public_score": "Puntuación pública: {benchmark}, {source}",
    "benchmark.public_score_accessed": "Puntuación pública: {benchmark}, {source}, {accessed}.",
    "benchmark.public_value": "{value} %",
    "benchmark.range_tip": "Tasa de fallos y su rango del 95 %, en un eje de 0 a 70 %",
    "benchmark.rate": "{rate} % ({low}–{high} %)",
    "benchmark.search": "Buscar tipos de acción",
    "chip.tip": {
      "one": "{name}: {earned} de {n} tipo de acción se ha ganado autonomía (T2 o T3). Abrir Tenure.",
      "other": "{name}: {earned} de {n} tipos de acción se han ganado autonomía (T2 o T3). Abrir Tenure."
    },
    "common.loading": "Leyendo la evidencia…",
    "common.no_match": "Sin resultados",
    "common.retry": "Reintentar",
    "emblem.none": "Aún sin autonomía ganada",
    "emblem.review": {
      "one": "{n} en revisión",
      "other": "{n} en revisión"
    },
    "emblem.tenured": {
      "one": "{n} titular",
      "other": "{n} titulares"
    },
    "empty.desc": "Trabaja como siempre. Cada cambio pregunta antes, y cada tipo de acción se gana su nivel con tus respuestas.",
    "empty.title": "Ningún agente ha actuado todavía",
    "flag.confirm": "Marcar",
    "flag.desc": "Cuenta como un fallo: {type} bajará al menos un nivel y tendrá que volver a subir. Úsalo para un error que nadie detectó.",
    "flag.title": "¿Marcar este cambio como error?",
    "hero.agent": "Agente",
    "intro.body": "Cada tipo de acción de cada modelo empieza en T1: pregunta antes. Una serie de acciones limpias y aprobadas lo sube a T2: actúa y luego te avisa, con opción de Deshacer. Una serie más larga, en dos sesiones, lo sube a T3: actúa por su cuenta, y 1 acción de cada {k} sigue preguntando, como control aleatorio. Un solo fallo lo hace bajar.",
    "intro.got_it": "Entendido",
    "intro.title": "Cómo se gana su nivel un tipo de acción",
    "meta.actions": "Acciones",
    "meta.actions_tip": "Todas las acciones de este agente que tenure ha visto. Las que nadie verificó (sin respuesta, tiempo agotado) no cuentan.",
    "meta.alone": "Por su cuenta",
    "meta.checked": "Por ti",
    "meta.faults": "Fallos",
    "meta.preset": "Preajuste",
    "meta.profile": "Perfil",
    "meta.provider": "Proveedor",
    "model_menu.badge": "{tier} ganado",
    "moment.dismiss": "Cerrar",
    "moment.eyebrow_down": "#Fallo · {type}",
    "moment.eyebrow_up": "#Ascenso · {type}",
    "moment.granted": "Titularidad concedida",
    "moment.probation": "De vuelta a prueba",
    "moment.review": "En revisión",
    "nav.label": "Tenure",
    "page.animations": "Animaciones",
    "page.title": "Tenure",
    "page.view_agents": "Agentes",
    "page.view_benchmark": "Tu benchmark",
    "palette.no_current": "El modelo actual aún no tiene historial: cada cambio pregunta antes.",
    "palette.open": "Tenure: Abrir",
    "palette.passport": "Tenure: Mostrar el pasaporte del modelo actual",
    "palette.revoke": "Tenure: Revocar el modelo actual…",
    "passport.copy": "Copiar pasaporte",
    "passport.copy_command": "Copiar comando",
    "passport.generated": "Generado",
    "passport.ledger": "Registro",
    "passport.ledger_value": {
      "one": "{n} evento · último hash {head}",
      "other": "{n} eventos · último hash {head}"
    },
    "passport.problems": "No se verifica: {problems}",
    "passport.protocol": "Protocolo",
    "passport.rule": "Regla",
    "passport.signature": "un plugin para Hermes Agent",
    "passport.title": "Pasaporte firmado",
    "passport.unavailable": "No disponible: {error}",
    "passport.verified": "Verificado: firma válida, cadena de hashes intacta, y al reproducir el registro se obtienen los mismos niveles.",
    "passport.verify_hint": "Cualquiera puede comprobarlo:",
    "passport.verifying": "Verificando…",
    "preset.copy_pending": "copiado de otro perfil, se verifica al iniciarse",
    "preset.name.balanced": "equilibrado",
    "preset.name.careful": "prudente",
    "preset.name.custom": "personalizado",
    "preset.name.fast": "rápido",
    "preset.value": "{preset} · 1 de cada {k} con control aleatorio",
    "preset.value_pending": "{preset} · 1 de cada {k} con control aleatorio · se aplica desde la próxima acción",
    "recent.check_failed": "falló la comprobación",
    "recent.check_failed_tip": "La comprobación automática falló: ya se contó como fallo. Deshacer restaura los archivos.",
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
    "recent.none": "Nada que deshacer en las últimas 24 horas.",
    "recent.show_all": "Mostrar los {n}",
    "recent.show_fewer": "Mostrar menos",
    "recent.title": "Actuó sin preguntar",
    "recent.undo": "Deshacer",
    "recent.undo_failed": "No se pudo deshacer",
    "recent.undo_tip": "Restaura los archivos como estaban. Cuenta como fallo: el tipo vuelve a bajar.",
    "recent.undone": "Archivos restaurados. Contado como fallo.",
    "revoke.action": "Revocar…",
    "revoke.busy": "Revocando…",
    "revoke.confirm": "Revocar",
    "revoke.desc": "{name} volverá a preguntar antes de cada acción. Su historial se queda en el registro.",
    "revoke.done": "{name} vuelve a preguntar antes en todos los tipos de acción.",
    "revoke.title": "¿Revocar la autonomía ganada?",
    "state.aria": "{label}: {tip}",
    "state.fault": "fallo",
    "state.fault_tip": "Un fallo de impacto medio o alto queda en el historial hasta superar un periodo de prueba.",
    "state.provisional": "provisional",
    "state.provisional_tip": "Heredado del modelo anterior, a la mitad, hasta que sus propias aprobaciones lo confirmen.",
    "state.suspended": "suspendido",
    "state.suspended_tip": "Una sesión leyó contenido externo: pregunta por todo hasta que termine.",
    "state.trial": "a prueba",
    "state.trial_tip": "Un fallo de impacto medio o alto abrió un periodo de prueba: 3 éxitos verificados seguidos.",
    "tier.cap": "Limitado · siempre pregunta",
    "tier.name.cap": "Siempre pregunta",
    "tier.name.t1": "Período de prueba",
    "tier.name.t2": "En revisión",
    "tier.name.t3": "Titular",
    "tier.t1": "T1 · pregunta antes",
    "tier.t2": "T2 · actúa y luego te avisa, con opción de Deshacer",
    "tier.t3": "T3 · actúa por su cuenta, con control aleatorio",
    "toast.acted": {
      "one": "{type} hizo un cambio y luego te avisó ({name}).",
      "other": "{type} hizo {n} cambios y luego te avisó ({name})."
    },
    "toast.acted_detail": "Deshacer restaura los archivos del último cambio y cuenta como fallo.",
    "type.always_asks": "siempre pregunta",
    "type.guarantee": "Como máximo el {aoql} % de las acciones de este tipo se ejecutan con un error que nadie aprobó; el {worst} % si el modelo empeora.",
    "type.guarantee_provisional": "Como máximo el {aoql} % de las acciones de este tipo se ejecutan con un error que nadie aprobó; el {worst} % si el modelo empeora. Provisional: evidencia heredada.",
    "type.in_a_row": "{series} de {required} seguidas",
    "type.next": {
      "one": "Falta {n} éxito verificado seguido para la titularidad.",
      "other": "Faltan {n} éxitos verificados seguidos para la titularidad."
    },
    "type.next_session": "La serie está completa: falta una sesión más.",
    "type.sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "type.stakes_high": "impacto alto",
    "type.stakes_low": "impacto bajo",
    "type.stakes_medium": "impacto medio",
    "type.stakes_other": "impacto {stakes}",
    "type.tenured_line": "Actúa por su cuenta. 1 acción de cada {k} sigue con control aleatorio.",
    "types.title": "Tipos de acción"
  },
  "fr": {
    "agents.pick": "Choisissez un agent pour voir ce qu'il a gagné.",
    "agents.search": "Rechercher des agents",
    "backend.desc": "Activez tenure pour ce profil dans Capacités → Plugins (colonne Agent). {error}",
    "backend.title": "La partie agent ne répond pas",
    "benchmark.col_faults": "Fautes",
    "benchmark.col_public": "Public",
    "benchmark.col_range": "Fourch. 95 %",
    "benchmark.col_rate": "Taux",
    "benchmark.faults": {
      "one": "{n} faute / {total}",
      "other": "{n} fautes / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.not_enough": "pas assez de preuves",
    "benchmark.note": "L'historique vérifié de chaque modèle sur votre travail pour ce type d'action, avec la fourchette à 95 % de son taux de fautes, classé par le haut de cette fourchette. Le score public sert de contexte : il mesure la capacité sur les tâches du benchmark, pas la fiabilité sur les vôtres.",
    "benchmark.public_score": "Score public : {benchmark}, {source}",
    "benchmark.public_score_accessed": "Score public : {benchmark}, {source}, {accessed}.",
    "benchmark.public_value": "{value} %",
    "benchmark.range_tip": "Taux de fautes et sa fourchette à 95 %, sur un axe de 0 à 70 %",
    "benchmark.rate": "{rate} % ({low}–{high} %)",
    "benchmark.search": "Rechercher des types d'action",
    "chip.tip": {
      "one": "{name} : {earned} type d'action sur {n} a gagné son autonomie (T2 ou T3). Ouvrir Tenure.",
      "other": "{name} : {earned} types d'action sur {n} ont gagné leur autonomie (T2 ou T3). Ouvrir Tenure."
    },
    "common.loading": "Lecture des preuves…",
    "common.no_match": "Aucun résultat",
    "common.retry": "Réessayer",
    "emblem.none": "Pas encore d'autonomie acquise",
    "emblem.review": {
      "one": "{n} en examen",
      "other": "{n} en examen"
    },
    "emblem.tenured": {
      "one": "{n} titulaire",
      "other": "{n} titulaires"
    },
    "empty.desc": "Travaillez comme d'habitude. L'agent demande avant chaque modification, et chaque type d'action gagne son niveau selon vos réponses.",
    "empty.title": "Aucun agent n'a encore agi",
    "flag.confirm": "Signaler",
    "flag.desc": "Cela compte comme une faute : {type} descendra d'au moins un niveau et devra remonter. À utiliser pour une erreur que personne n'a repérée.",
    "flag.title": "Signaler cette modification comme une erreur ?",
    "hero.agent": "Agent",
    "intro.body": "Chaque type d'action de chaque modèle commence en T1 : il demande d'abord. Une série d'actions approuvées sans faute le fait passer en T2 : il agit, puis vous prévient, avec un bouton Annuler. Une série plus longue, sur deux sessions, le fait passer en T3 : il agit seul, et 1 action sur {k} vous est encore demandée, par contrôle aléatoire. Une seule faute le fait redescendre.",
    "intro.got_it": "Compris",
    "intro.title": "Comment un type d'action gagne son niveau",
    "meta.actions": "Actions",
    "meta.actions_tip": "Toutes les actions de cet agent vues par tenure. Les actions que personne n'a vérifiées (pas de réponse, délai expiré) ne comptent pas.",
    "meta.alone": "Sans demander",
    "meta.checked": "Par vous",
    "meta.faults": "Fautes",
    "meta.preset": "Préréglage",
    "meta.profile": "Profil",
    "meta.provider": "Fournisseur",
    "model_menu.badge": "{tier} acquis",
    "moment.dismiss": "Fermer",
    "moment.eyebrow_down": "#Faute · {type}",
    "moment.eyebrow_up": "#Promotion · {type}",
    "moment.granted": "Titularisé",
    "moment.probation": "Retour en probation",
    "moment.review": "En examen",
    "nav.label": "Tenure",
    "page.animations": "Animations",
    "page.title": "Tenure",
    "page.view_agents": "Agents",
    "page.view_benchmark": "Votre benchmark",
    "palette.no_current": "Le modèle actuel n'a pas encore d'historique : il demande avant chaque modification.",
    "palette.open": "Tenure : Ouvrir",
    "palette.passport": "Tenure : Afficher le passeport du modèle actuel",
    "palette.revoke": "Tenure : Révoquer le modèle actuel…",
    "passport.copy": "Copier le passeport",
    "passport.copy_command": "Copier la commande",
    "passport.generated": "Généré",
    "passport.ledger": "Registre",
    "passport.ledger_value": {
      "one": "{n} événement · tête {head}",
      "other": "{n} événements · tête {head}"
    },
    "passport.problems": "Ne se vérifie pas : {problems}",
    "passport.protocol": "Protocole",
    "passport.rule": "Règle",
    "passport.signature": "un plugin pour Hermes Agent",
    "passport.title": "Passeport signé",
    "passport.unavailable": "Indisponible : {error}",
    "passport.verified": "Vérifié : signature valide, chaîne de hachage intacte, et le registre rejoué redonne les mêmes niveaux.",
    "passport.verify_hint": "Tout le monde peut le vérifier :",
    "passport.verifying": "Vérification…",
    "preset.copy_pending": "copié depuis un autre profil, vérifié à son démarrage",
    "preset.name.balanced": "équilibré",
    "preset.name.careful": "prudent",
    "preset.name.custom": "personnalisé",
    "preset.name.fast": "rapide",
    "preset.value": "{preset} · 1 action sur {k} contrôlée",
    "preset.value_pending": "{preset} · 1 action sur {k} contrôlée · s'applique dès la prochaine action",
    "recent.check_failed": "vérification échouée",
    "recent.check_failed_tip": "La vérification automatique a échoué : déjà comptée comme une faute. Annuler restaure les fichiers.",
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
    "recent.none": "Rien à annuler depuis 24 heures.",
    "recent.show_all": "Tout afficher ({n})",
    "recent.show_fewer": "Afficher moins",
    "recent.title": "A agi sans demander",
    "recent.undo": "Annuler",
    "recent.undo_failed": "Annulation impossible",
    "recent.undo_tip": "Restaurer les fichiers tels qu'ils étaient. Compte comme une faute : le type redescend.",
    "recent.undone": "Fichiers restaurés. Compté comme une faute.",
    "revoke.action": "Révoquer…",
    "revoke.busy": "Révocation…",
    "revoke.confirm": "Révoquer",
    "revoke.desc": "{name} demandera de nouveau avant chaque action. Son historique reste dans le registre.",
    "revoke.done": "{name} demande de nouveau avant d'agir, pour tous les types d'action.",
    "revoke.title": "Révoquer l'autonomie acquise ?",
    "state.aria": "{label} : {tip}",
    "state.fault": "faute",
    "state.fault_tip": "Une faute à enjeu moyen ou élevé reste à l'historique jusqu'à la réussite d'un essai.",
    "state.provisional": "provisoire",
    "state.provisional_tip": "Hérité du modèle précédent, divisé par deux, jusqu'à ce que ses propres approbations le confirment.",
    "state.suspended": "suspendu",
    "state.suspended_tip": "La session a lu du contenu externe : elle demande avant chaque action, jusqu'à sa fin.",
    "state.trial": "à l'essai",
    "state.trial_tip": "Une faute à enjeu moyen ou élevé a ouvert un essai : 3 succès vérifiés d'affilée.",
    "tier.cap": "Plafonné · demande toujours",
    "tier.name.cap": "Toujours demandé",
    "tier.name.t1": "Probation",
    "tier.name.t2": "En examen",
    "tier.name.t3": "Titulaire",
    "tier.t1": "T1 · demande d'abord",
    "tier.t2": "T2 · agit, puis vous prévient, avec un bouton Annuler",
    "tier.t3": "T3 · agit seul, avec contrôles aléatoires",
    "toast.acted": {
      "one": "{type} a fait une modification, puis vous a prévenu ({name}).",
      "other": "{type} a fait {n} modifications, puis vous a prévenu ({name})."
    },
    "toast.acted_detail": "Annuler restaure les fichiers de la dernière modification et compte comme une faute.",
    "type.always_asks": "demande toujours",
    "type.guarantee": "Au plus {aoql} % des actions de ce type s'exécutent avec une erreur que personne n'a approuvée ; {worst} % si le modèle se dégrade.",
    "type.guarantee_provisional": "Au plus {aoql} % des actions de ce type s'exécutent avec une erreur que personne n'a approuvée ; {worst} % si le modèle se dégrade. Provisoire : preuves héritées.",
    "type.in_a_row": "{series} sur {required} d'affilée",
    "type.next": {
      "one": "Encore {n} succès vérifié d'affilée pour être titularisé.",
      "other": "Encore {n} succès vérifiés d'affilée pour être titularisé."
    },
    "type.next_session": "La série est complète : une session de plus et c'est fait.",
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "enjeu élevé",
    "type.stakes_low": "enjeu faible",
    "type.stakes_medium": "enjeu moyen",
    "type.stakes_other": "enjeu {stakes}",
    "type.tenured_line": "Agit seul. 1 action sur {k} reste contrôlée au hasard.",
    "types.title": "Types d'action"
  },
  "zh": {
    "agents.pick": "选择一个智能体，查看它已赢得的自主权。",
    "agents.search": "搜索智能体",
    "backend.desc": "请在「能力 → 插件」（智能体列）中为此配置文件启用 tenure。{error}",
    "backend.title": "智能体端没有响应",
    "benchmark.col_faults": "失误",
    "benchmark.col_public": "公开",
    "benchmark.col_range": "95% 区间",
    "benchmark.col_rate": "失误率",
    "benchmark.faults": {
      "other": "{n} 次失误 / {total}"
    },
    "benchmark.no_public": "—",
    "benchmark.not_enough": "证据不足",
    "benchmark.note": "每个模型在你的工作中、针对此操作类型的已验证记录，附失误率的 95% 区间，按区间上限排名。公开分数仅供参考：它衡量的是模型在别人任务上的能力，而不是在你的工作上的可靠性。",
    "benchmark.public_score": "公开分数：{benchmark}，{source}",
    "benchmark.public_score_accessed": "公开分数：{benchmark}，{source}，{accessed}。",
    "benchmark.public_value": "{value}%",
    "benchmark.range_tip": "失误率及其 95% 区间，坐标轴 0–70%",
    "benchmark.rate": "{rate}%（{low}–{high}%）",
    "benchmark.search": "搜索操作类型",
    "chip.tip": {
      "other": "{name}：{n} 个操作类型中有 {earned} 个已赢得自主权（T2 或 T3）。打开 Tenure。"
    },
    "common.loading": "正在读取证据…",
    "common.no_match": "无匹配项",
    "common.retry": "重试",
    "emblem.none": "尚未赢得自主权",
    "emblem.review": {
      "other": "{n} 个考察中"
    },
    "emblem.tenured": {
      "other": "{n} 个已转正"
    },
    "empty.desc": "照常工作即可。每次更改都会先询问你，每个操作类型会根据你的回答赢得相应级别。",
    "empty.title": "还没有智能体执行过操作",
    "flag.confirm": "标记",
    "flag.desc": "这会记为一次失误：{type} 至少下降一个级别，之后需重新晋升。用于没人发现的错误。",
    "flag.title": "将此更改标记为错误？",
    "hero.agent": "智能体",
    "intro.body": "每个模型的每个操作类型都从 T1 开始：先询问。连续多次获批且无误后，它升到 T2：先执行后告知，并可撤销。跨两个会话的更长连续记录会让它升到 T3：自主执行，但每 {k} 个操作仍会抽查 1 个，先询问你。一次失误就会让该类型降级。",
    "intro.got_it": "知道了",
    "intro.title": "操作类型如何赢得级别",
    "meta.actions": "操作",
    "meta.actions_tip": "tenure 看到的此智能体的全部操作。没人验证的操作（无回应、超时）不计入。",
    "meta.alone": "自主执行",
    "meta.checked": "由你确认",
    "meta.faults": "失误",
    "meta.preset": "预设",
    "meta.profile": "配置文件",
    "meta.provider": "提供方",
    "model_menu.badge": "已赢得 {tier}",
    "moment.dismiss": "关闭",
    "moment.eyebrow_down": "#失误 · {type}",
    "moment.eyebrow_up": "#晋升 · {type}",
    "moment.granted": "已获转正",
    "moment.probation": "重回试用期",
    "moment.review": "进入考察",
    "nav.label": "Tenure",
    "page.animations": "动画",
    "page.title": "Tenure",
    "page.view_agents": "智能体",
    "page.view_benchmark": "你的基准",
    "palette.no_current": "当前模型还没有记录：每次更改都会先询问。",
    "palette.open": "Tenure：打开",
    "palette.passport": "Tenure：显示当前模型的护照",
    "palette.revoke": "Tenure：收回当前模型的自主权…",
    "passport.copy": "复制护照",
    "passport.copy_command": "复制命令",
    "passport.generated": "生成时间",
    "passport.ledger": "账本",
    "passport.ledger_value": {
      "other": "{n} 个事件 · 头部 {head}"
    },
    "passport.problems": "验证未通过：{problems}",
    "passport.protocol": "协议",
    "passport.rule": "规则",
    "passport.signature": "Hermes Agent 插件",
    "passport.title": "已签名护照",
    "passport.unavailable": "不可用：{error}",
    "passport.verified": "已验证：签名有效，哈希链完整，重放账本得到相同的级别。",
    "passport.verify_hint": "任何人都可以验证：",
    "passport.verifying": "正在验证…",
    "preset.copy_pending": "从另一个配置文件复制而来，启动时检查",
    "preset.name.balanced": "平衡",
    "preset.name.careful": "谨慎",
    "preset.name.custom": "自定义",
    "preset.name.fast": "快速",
    "preset.value": "{preset} · 每 {k} 个抽查 1 个",
    "preset.value_pending": "{preset} · 每 {k} 个抽查 1 个 · 从下一个操作起生效",
    "recent.check_failed": "检查失败",
    "recent.check_failed_tip": "自动检查失败：已记为一次失误。撤销可恢复文件。",
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
    "recent.none": "过去 24 小时内没有可撤销的操作。",
    "recent.show_all": "显示全部 {n} 条",
    "recent.show_fewer": "收起",
    "recent.title": "未询问即执行",
    "recent.undo": "撤销",
    "recent.undo_failed": "无法撤销",
    "recent.undo_tip": "将文件恢复原样。记为一次失误：该类型会降级。",
    "recent.undone": "文件已恢复。已记为一次失误。",
    "revoke.action": "收回…",
    "revoke.busy": "正在收回…",
    "revoke.confirm": "收回",
    "revoke.desc": "{name} 每次操作前都会重新询问。它的记录仍保留在账本中。",
    "revoke.done": "{name} 的所有操作类型都已恢复为先询问。",
    "revoke.title": "收回已赢得的自主权？",
    "state.aria": "{label}：{tip}",
    "state.fault": "有失误",
    "state.fault_tip": "中、高风险的失误会一直留在记录中，直到通过考察期。",
    "state.provisional": "暂定",
    "state.provisional_tip": "从上一个模型继承并减半，直到它自己的批准将其确认。",
    "state.suspended": "已暂停",
    "state.suspended_tip": "此会话读取了外部内容：在会话结束前，每次操作都会询问。",
    "state.trial": "考察期",
    "state.trial_tip": "一次中、高风险的失误开启了考察期：需连续 3 次已验证的成功。",
    "tier.cap": "受限 · 始终询问",
    "tier.name.cap": "始终询问",
    "tier.name.t1": "试用期",
    "tier.name.t2": "考察中",
    "tier.name.t3": "已转正",
    "tier.t1": "T1 · 先询问",
    "tier.t2": "T2 · 先执行后告知，可撤销",
    "tier.t3": "T3 · 自主执行，接受抽查",
    "toast.acted": {
      "other": "{type}：{n} 项更改，已执行并告知你（{name}）。"
    },
    "toast.acted_detail": "撤销会恢复最近一次更改的文件，并记为一次失误。",
    "type.always_asks": "始终询问",
    "type.guarantee": "此类型最多有 {aoql}% 的操作会带着无人批准的错误运行；若模型变差，最多 {worst}%。",
    "type.guarantee_provisional": "此类型最多有 {aoql}% 的操作会带着无人批准的错误运行；若模型变差，最多 {worst}%。暂定：基于继承的证据。",
    "type.in_a_row": "连续 {series}/{required}",
    "type.next": {
      "other": "再连续 {n} 次已验证的成功即可转正。"
    },
    "type.next_session": "连续记录已达标：再完成一个会话即可。",
    "type.sessions": {
      "other": "{n} 个会话"
    },
    "type.stakes_high": "高风险",
    "type.stakes_low": "低风险",
    "type.stakes_medium": "中风险",
    "type.stakes_other": "{stakes}风险",
    "type.tenured_line": "自主执行。每 {k} 个操作仍抽查 1 个。",
    "types.title": "操作类型"
  }
};
/* TENURE_LOCALES_END */

// Commands the user types stay out of the catalogs.
const VERIFY_COMMAND = 'hermes tenure verify passport.json ledger.jsonl'

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

const tierKey = t => (t.capped ? 'cap' : t.effective_tier || t.tier || 'ask')
const TIER_SHORT = { ask: 'T1', notify: 'T2', alone: 'T3', cap: 'CAP' }
const TIER_RANK = { cap: 0, ask: 1, notify: 2, alone: 3 }
const TIER_DOT = { ask: 'bg-muted-foreground/40', notify: 'bg-primary', alone: 'bg-primary', cap: 'bg-muted-foreground/40' }

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

// Static canvases repaint when the theme or the accent changes (the host rewrites attributes on <html> / <body>).
const repaints = new Set()
let themeObserver = null
function watchTheme() {
  if (themeObserver || typeof MutationObserver !== 'function' || typeof document === 'undefined') return
  let queued = false
  themeObserver = new MutationObserver(() => {
    if (queued) return
    queued = true
    requestAnimationFrame(() => {
      queued = false
      for (const fn of repaints) fn()
    })
  })
  const opts = { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-accent'] }
  themeObserver.observe(document.documentElement, opts)
  if (document.body) themeObserver.observe(document.body, opts)
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
function fitCanvas(cv, w, h) {
  const dpr = Math.min(2, (typeof window !== 'undefined' && window.devicePixelRatio) || 1)
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

/**
 * fill: 0..1 · solid: draw the fill at full density · print: 0..1 Bayer threshold sweep (entrance) ·
 * crumble: { from, k } cells of the old fill beyond `fill` drop and fade · (the benchmark range has its own draw-in).
 */
function paintBar(cv, { fill, solid, print = 1, crumble = null, rows = BAR_ROWS, headroom = 4 }) {
  const w = cv.clientWidth || (cv.parentElement && cv.parentElement.clientWidth) || 0
  if (!w) return
  const h = rows * BAR_CELL + headroom
  const dpr = fitCanvas(cv, w, h)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, w, h)
  x.fillStyle = inkOf(cv)
  const cols = Math.floor(w / BAR_CELL)
  const dot = BAR_CELL - 0.5
  const density = solid ? 1 : 0.38 + 0.62 * clamp01(fill)
  const fade = Math.min(12, Math.max(3, cols * 0.06))
  const edgeOf = f => f * cols
  const value = (i, f) => {
    if (solid && f >= 1) return 1
    const edge = edgeOf(f)
    const v = i < edge - fade ? density : i < edge ? density * ((edge - i) / fade) : 0
    return Math.max(v, 0.07)
  }
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const th = bayer(i, j)
      if (th >= print) continue
      if (value(i, fill) > th) {
        x.globalAlpha = 1
        x.fillRect(i * BAR_CELL, j * BAR_CELL, dot, dot)
      } else if (crumble && value(i, crumble.from) > th) {
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
function DitherBar({ value, solid, track, change, motion, delay = 0, rows = BAR_ROWS, className }) {
  const ref = useRef(null)
  const st = useRef({ fill: null, solid: false, cancel: null, token: null })
  const target = track ? 0 : solid ? 1 : clamp01(value || 0)
  const draw = (fill, extra) => ref.current && paintBar(ref.current, { fill, solid: !!solid, rows, headroom: rows > 3 ? 4 : 2, ...extra })
  useRepaint(() => draw(st.current.fill == null ? target : st.current.fill))
  useWidth(ref, () => draw(st.current.fill == null ? target : st.current.fill))
  const token = change ? change.token : null
  useEffect(() => {
    const s = st.current
    if (s.cancel) s.cancel()
    s.cancel = null
    const from = s.fill
    const fresh = token && token !== s.token
    s.token = token
    s.fill = target
    if (!motion) return draw(target)
    if (from == null) {
      // A. Entrance: the bar prints, threshold by threshold.
      draw(target, { print: 0 })
      s.cancel = tween(600, k => draw(target, { print: k }), null, delay)
    } else if (fresh && change.dir === 'down') {
      // D. Fault: the dots crumble, then the bar prints again at its new value.
      s.cancel = tween(520, k => draw(target, { crumble: { from, k } }), () => {
        s.cancel = tween(380, k => draw(target, { print: k }))
      })
    } else if (from !== target) {
      // C. Promotion (or plain progress): the fill grows to its new value.
      s.cancel = tween(fresh ? 700 : 450, k => draw(from + (target - from) * easeOut(k)))
    } else draw(target)
    return () => {
      if (s.cancel) s.cancel()
    }
  }, [target, solid, track, token, motion])
  return jsx('canvas', { 'aria-hidden': true, className: cn('tn-bar tn-mirror', className), ref })
}

// ---- the emblem: an original dithered sunburst; its density is the share of autonomy the agent earned.
function emblemValue(dx, dy, rot, share) {
  const r = Math.hypot(dx, dy)
  if (r > 1) return -1
  const a = Math.atan2(dy, dx) + rot
  const ray = Math.pow((Math.cos(a * 36) + 1) / 2, 2)
  const core = Math.max(0, 1 - r / 0.42) * (0.45 + 0.55 * share)
  let v = Math.max(core * 1.15, ray * (1.08 - r) * 1.25 * (0.18 + 0.82 * share), 0.16 * (1 - r))
  if (Math.abs(r - 0.47) < 0.025 || Math.abs(r - 0.97) < 0.02) v = 1
  return v
}

function paintEmblem(cv, { size, n, share, develop = 1, rot = 0 }) {
  const dpr = fitCanvas(cv, size, size)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, size, size)
  x.fillStyle = inkOf(cv)
  const cell = size / n
  const dot = Math.max(0.6, cell - 0.6)
  const c = n / 2
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const th = bayer(i, j)
      if (th >= develop) continue
      const v = emblemValue((i - c + 0.5) / c, (j - c + 0.5) / c, rot, share)
      if (v > th) x.fillRect(i * cell, j * cell, dot, dot)
    }
  }
}

/**
 * The emblem. develops point by point on mount (B), can turn slowly (the passport), and pulses once when `pulse`
 * changes (C: density up, then back). The turning loop stops while the emblem is off screen or the window hidden.
 */
function Emblem({ share, size = 120, n = 60, rotate = false, pulse = 0, motion, className, label }) {
  const ref = useRef(null)
  const st = useRef({ raf: 0, dev0: 0, pulse0: 0, rot: 0, rot0: 0, visible: true, share })
  st.current.share = share
  const paint = (develop, boost, rot) =>
    ref.current && paintEmblem(ref.current, { size, n, share: clamp01(st.current.share + boost), develop, rot })
  useRepaint(() => paint(1, 0, st.current.rot))
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
      const turning = rotate && develop >= 1 && s.visible && !(typeof document !== 'undefined' && document.hidden)
      if (turning) {
        if (!s.rot0) s.rot0 = now - s.rot / 0.00006
        s.rot = (now - s.rot0) * 0.00006 // ~0.06 rad/s
      } else s.rot0 = 0
      paint(develop, boost, s.rot)
      if (develop < 1 || s.pulse0 || turning) s.raf = requestAnimationFrame(tick)
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
  for (const ty of types) s += tierKey(ty) === 'alone' ? 1 : tierKey(ty) === 'notify' ? 0.5 : 0
  return s / types.length
}

// ---- a seal that prints at the end of a passport that verifies.
function paintSeal(cv, { size, print = 1 }) {
  const dpr = fitCanvas(cv, size, size)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, size, size)
  x.fillStyle = inkOf(cv)
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

// ---- benchmark range: dotted 0–70 % axis, the 95 % range dithered, the rate solid; draws in from the start (F).
function paintRange(cv, { rate, low, high, enough, reveal = 1 }) {
  const w = cv.clientWidth || 96
  const rows = 4
  const h = rows * BAR_CELL
  const dpr = fitCanvas(cv, w, h)
  const x = cv.getContext('2d')
  x.setTransform(dpr, 0, 0, dpr, 0, 0)
  x.clearRect(0, 0, w, h)
  x.fillStyle = inkOf(cv)
  const cols = Math.floor(w / BAR_CELL)
  const at = v => Math.min(cols, (cols * v) / 0.7)
  const lo = at(low), hi = Math.max(at(high), at(low) + 1), rt = at(rate)
  const edge = reveal * (cols + 6)
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const th = bayer(i, j)
      let v = j === 1 || j === 2 ? 0.07 : 0
      if (i >= lo && i < hi) v = enough ? 0.5 : 0.25
      if (enough && Math.abs(i - rt) < 1.01) v = 1
      const fade = i < edge - 6 ? 1 : i < edge ? (edge - i) / 6 : 0
      if (v * fade > th) x.fillRect(i * BAR_CELL, j * BAR_CELL, BAR_CELL - 0.5, BAR_CELL - 0.5)
    }
  }
}

function RangeBar({ rate, low, high, enough, motion, delay = 0 }) {
  const ref = useRef(null)
  const draw = reveal => ref.current && paintRange(ref.current, { rate, low, high, enough, reveal })
  useRepaint(() => draw(1))
  useEffect(() => {
    if (!motion) return draw(1)
    draw(0)
    return tween(560, k => draw(easeOut(k)), null, delay)
  }, [rate, low, high, enough, motion])
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
  --tn-fg:var(--ui-text-primary,currentColor);--tn-fg2:var(--ui-text-secondary,currentColor);--tn-mut:var(--ui-text-tertiary,currentColor);
  --tn-acc-text:color-mix(in srgb,var(--tn-acc) 80%,var(--tn-fg));--tn-line:color-mix(in srgb,var(--tn-fg) 13%,transparent);
  --tn-mono:'JetBrains Mono',var(--font-mono,ui-monospace),monospace;--tn-display:'Collapse',var(--font-sans,system-ui),sans-serif}
.tn-root canvas{display:block}
.tn-eyebrow{font:500 0.625rem/1.4 var(--tn-mono);letter-spacing:0.12em;text-transform:uppercase;color:var(--tn-acc-text)}
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
.tn-emblem-cap{font:0.6rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;color:var(--tn-mut);text-align:center;max-width:11rem}
.tn-chip{display:inline-flex;align-items:center;font-family:var(--tn-display);font-weight:700;font-size:0.72rem;letter-spacing:0.08em;line-height:1;padding:0.2rem 0.35rem 0.15rem;border:1px solid var(--tn-acc);color:var(--tn-acc-text);white-space:nowrap}
.tn-chip[data-tier=alone]{background:var(--tn-acc);color:var(--tn-on)}
.tn-chip[data-tier=cap]{border-style:dashed;border-color:var(--tn-mut);color:var(--tn-mut)}
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
.tn-tstakes{font-size:0.68rem;color:var(--tn-mut);margin-inline-start:auto}
.tn-bar{width:100%;height:16px;color:var(--tn-acc)}
.tn-tbar{position:relative}
.tn-tnext{margin:0.3rem 0 0;font-size:0.74rem;line-height:1.5;color:var(--tn-fg2)}
.tn-tnext .tn-g{font:0.68rem var(--tn-mono);color:var(--tn-mut);font-variant-numeric:tabular-nums}
.tn-tguar{margin:0.15rem 0 0;font-size:0.68rem;line-height:1.5;color:var(--tn-mut)}
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
.tn-intro{margin:0 1rem 0.75rem;display:flex;align-items:flex-start;gap:0.75rem;padding:0.7rem 0.85rem;border:1px solid var(--tn-line)}
.tn-intro p{margin:0}
.tn-intro-body{font-size:0.74rem;line-height:1.55;color:var(--tn-fg2);max-width:48rem}
.tn-pass-wrap{perspective:900px;max-width:23rem}
.tn-pass{position:relative;overflow:hidden;background:var(--tn-acc);color:var(--tn-on);padding:1.1rem 1.25rem 1rem;transform-style:preserve-3d;transition:transform 400ms cubic-bezier(.2,.7,.2,1);will-change:transform}
.tn-pass.tn-tilting{transition:transform 80ms linear}
.tn-ptop{display:flex;justify-content:space-between;gap:0.5rem;font:0.62rem var(--tn-mono);letter-spacing:0.14em;text-transform:uppercase}
.tn-ok{opacity:0;transition:opacity 400ms}
.tn-ok.tn-on{opacity:1}
.tn-pemb{display:grid;place-items:center;margin:0.8rem 0 0.2rem}
.tn-pemb .tn-emblem{color:var(--tn-on)}
.tn-pname{font-family:var(--tn-display);font-weight:700;font-size:clamp(1.8rem,3.6vw,2.6rem);line-height:0.95;text-align:center;margin:0.2rem 0 0.8rem;min-height:1em;overflow-wrap:anywhere}
.tn-prows{border-block-start:1px solid color-mix(in srgb,var(--tn-on) 35%,transparent);padding-block-start:0.55rem;display:flex;flex-direction:column;gap:0.35rem}
.tn-prow{display:grid;grid-template-columns:minmax(0,1fr) 5.5rem;gap:0.15rem 0.75rem;align-items:center;font:0.66rem var(--tn-mono)}
.tn-prow[data-motion=on]{opacity:0;transform:translateY(4px);transition:opacity 400ms,transform 400ms}
.tn-prow.tn-on{opacity:1;transform:none}
.tn-prow .tn-pk{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tn-prow b{font-family:var(--tn-display);font-weight:700;letter-spacing:0.06em;margin-inline-start:0.4rem;text-transform:uppercase}
.tn-prow .tn-bar{height:8px;color:var(--tn-on)}
.tn-pfoot{display:flex;justify-content:space-between;flex-wrap:wrap;gap:0.25rem 0.75rem;margin-block-start:0.8rem;padding-block-start:0.55rem;border-block-start:1px solid color-mix(in srgb,var(--tn-on) 35%,transparent);font:0.58rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase}
.tn-hash{font-family:var(--tn-mono);text-transform:none;letter-spacing:0.06em}
.tn-psig{display:flex;align-items:center;gap:0.45rem;margin-block-start:0.6rem;font:0.56rem var(--tn-mono);letter-spacing:0.12em;opacity:0.85}
.tn-psig b{font-family:var(--tn-display);font-weight:700;letter-spacing:0.12em}
.tn-psig .tn-emblem{color:var(--tn-on)}
.tn-seal{position:absolute;inset-block-end:0.7rem;inset-inline-end:0.85rem;width:44px;height:44px;color:var(--tn-on);transform:rotate(-10deg);opacity:0.92}
.tn-sweep{position:absolute;inset-inline:0;height:46px;inset-block-start:-60px;background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--tn-on) 16%,transparent),transparent);pointer-events:none}
.tn-glare{position:absolute;inset:0;pointer-events:none;opacity:0;transition:opacity 300ms;
  background:linear-gradient(105deg,transparent 38%,color-mix(in srgb,var(--tn-on) 34%,transparent) 50%,transparent 62%);background-size:260% 100%;
  background-position:calc(50% - var(--tn-gx,0) * 120%) 0;-webkit-mask-image:${MASKS[2]};mask-image:${MASKS[2]};-webkit-mask-size:8px 8px;mask-size:8px 8px}
.tn-pass[data-motion=on]:hover .tn-glare{opacity:1}
.tn-chip.tn-out,.tn-chip.tn-in{-webkit-mask-size:8px 8px;mask-size:8px 8px}
.tn-range{width:96px;height:8px;color:var(--tn-acc)}
.tn-brow{position:relative;border-block-end:1px solid var(--tn-line)}
.tn-anim-toggle{display:inline-flex;align-items:center;gap:0.4rem;font:0.6rem var(--tn-mono);letter-spacing:0.1em;text-transform:uppercase;color:var(--tn-mut)}
@media (prefers-reduced-motion:reduce){.tn-enter,.tn-scan,.tn-chip.tn-out,.tn-chip.tn-in,.tn-band-title,.tn-leaving{animation:none!important}.tn-prow,.tn-pass,.tn-ok{transition:none!important}.tn-prow{opacity:1;transform:none}}
`

// ------------------------------------------------------------------------------------------------ pieces
function TierLabel(tier, t) {
  return { ask: t('tier.t1'), notify: t('tier.t2'), alone: t('tier.t3'), cap: t('tier.cap') }[tier]
}

/** The tier's display name in the tenure vocabulary (Probation, Under review, Tenured, Always asks). */
function tierName(tier, t) {
  return { ask: t('tier.name.t1'), notify: t('tier.name.t2'), alone: t('tier.name.t3'), cap: t('tier.name.cap') }[tier]
}

/** Flat rectangular chip: outlined T1/T2, filled accent T3, dashed CAP. A tier change dissolves the old chip. */
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
      'aria-label': `${TIER_SHORT[tier]} · ${tierName(tier, t)}: ${TierLabel(tier, t)}`,
      className: 'tn-chip-wrap',
      tabIndex: 0,
      children: [
        jsx('span', { className: cn('tn-chip', ghost && 'tn-in'), 'data-tier': tier, children: TIER_SHORT[tier] }, 'chip-' + tier + (ghost ? ghost.key : '')),
        ghost ? jsx('span', { 'aria-hidden': true, className: 'tn-chip tn-chip-ghost tn-out', 'data-tier': ghost.tier, children: TIER_SHORT[ghost.tier] }, 'ghost') : null
      ]
    })
  })
}

function StatePill({ label, tip, tone, t }) {
  return jsx(Tip, {
    label: tip,
    children: jsx('span', {
      'aria-label': t('state.aria', { label, tip }),
      className: 'inline-flex rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring/50',
      tabIndex: 0,
      children: jsx(PanelPill, { tone, children: label })
    })
  })
}

/** Small numbered mono eyebrow: "#02 · Acted without asking". */
function Eyebrow({ n, children, as = 'h4' }) {
  return jsxs(as, { className: 'tn-eyebrow', style: { margin: 0 }, children: [n != null ? jsx('span', { className: 'tn-dim', children: `#${pad2(n)} · ` }) : null, children] })
}

const SERIES_SESSIONS = 2 // rule.SESSIONS: T3 also needs the series spread over at least two sessions

/** Fill fraction of a type's bar: series toward T3; T3 is solid; a capped type shows only its track. */
const fillOf = ty => (ty.capped ? 0 : tierKey(ty) === 'alone' ? 1 : ty.required > 0 ? clamp01(ty.series / ty.required) : 0)

function nextLine(ty, t, spot) {
  const tier = tierKey(ty)
  if (ty.capped) return t('type.always_asks')
  if (tier === 'alone') return t('type.tenured_line', { k: Math.round(1 / (spot || 0.1)) })
  const left = Math.max(0, (ty.required || 0) - (ty.series || 0))
  if (left > 0) return t('type.next', { n: left })
  if ((ty.sessions || 0) < SERIES_SESSIONS) return t('type.next_session')
  return ''
}

function TypeRow({ type, t, index, motion, change, spot }) {
  const tier = tierKey(type)
  const g = type.guarantee
  const stakes = ['low', 'medium', 'high'].includes(type.stakes) ? t('type.stakes_' + type.stakes) : t('type.stakes_other', { stakes: type.stakes })
  const progress = t('type.in_a_row', { series: type.series, required: type.required })
  const next = nextLine(type, t, spot)
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
              jsx('span', { className: 'tn-tk', children: type.type }),
              jsx(TierChip, { tier, t, motion }),
              jsx('span', { className: 'tn-tname', children: tierName(tier, t) }),
              jsx('span', { className: 'tn-tstakes', children: stakes })
            ]
          }),
          jsx('div', {
            'aria-label': type.capped ? t('type.always_asks') : progress,
            'aria-valuemax': type.capped ? undefined : type.required,
            'aria-valuemin': type.capped ? undefined : 0,
            'aria-valuenow': type.capped ? undefined : type.series,
            className: 'tn-tbar',
            role: type.capped ? 'img' : 'progressbar',
            children: jsx(DitherBar, { change: change && change.dir !== 'spot' ? change : null, delay: 120 + index * 40, motion, solid: tier === 'alone', track: type.capped, value: fillOf(type) })
          }),
          jsxs('p', {
            className: 'tn-tnext',
            children: [
              next,
              !type.capped
                ? jsx('span', { className: 'tn-g', children: (next ? ' · ' : '') + progress + ' · ' + t('type.sessions', { n: type.sessions }) })
                : null
            ]
          }),
          !type.capped && g
            ? jsx('p', { className: 'tn-tguar', children: t(g.conditional ? 'type.guarantee_provisional' : 'type.guarantee', { aoql: pct(g.aoql), worst: pct(g.worst_case) }) })
            : null
        ]
      }),
      change && change.dir === 'spot' && motion ? jsx('span', { 'aria-hidden': true, className: 'tn-scan' }, change.token) : null
    ]
  })
}

function Intro({ t, spot }) {
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
          jsx('p', { className: 'tn-intro-body', children: t('intro.body', { k: Math.round(1 / (spot || 0.1)) }) })
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

function RecentSection({ agent, t, n }) {
  const profile = useValue(host.state.profile)
  const qc = useQueryClient()
  const [busy, setBusy] = useState(null)
  const [flagging, setFlagging] = useState(null)
  const { data } = useQuery({ queryKey: ['tenure', profile, 'activity'], queryFn: () => rest('/activity?since=0'), refetchInterval: HEARTBEAT_MS })
  const [all, setAll] = useState(false)
  const every = ((data && data.undoable) || []).filter(r => r.agent === agent.agent && r.profile === agent.profile)
  const rows = all ? every : every.slice(0, 5)
  const act = async (key, fn, ok, fail) => {
    setBusy(key)
    try {
      await fn()
      haptic('success')
      host.notify({ kind: 'success', message: ok })
      qc.invalidateQueries({ queryKey: ['tenure'] })
    } catch (e) {
      host.notifyError(e, fail)
    } finally {
      setBusy(null)
    }
  }
  return jsxs('section', {
    className: 'tn-section',
    children: [
      jsx(Eyebrow, { n, children: t('recent.title') }),
      rows.length === 0
        ? jsx('p', { className: 'text-xs text-muted-foreground/70', style: { margin: 0 }, children: t('recent.none') })
        : jsx('div', {
            className: 'flex flex-col',
            children: rows.map(r =>
              jsxs(
                'div',
                {
                  className: 'tn-brow group/row flex items-center gap-3 px-1 py-1.5 text-[0.78rem] hover:bg-(--ui-row-hover-background)',
                  children: [
                    jsx(Codicon, { className: 'shrink-0 text-muted-foreground/55', name: 'history', size: '0.8rem' }),
                    jsxs('span', {
                      className: 'min-w-0 flex-1 truncate text-[0.75rem] text-foreground/85',
                      children: [
                        jsx('span', { className: 'font-mono', children: r.file || r.type }),
                        r.files > 1 ? jsx('span', { className: 'text-muted-foreground/60', children: ' ' + t('recent.more_files', { n: r.files - 1 }) }) : null,
                        r.file ? jsx('span', { className: 'font-mono text-[0.68rem] text-muted-foreground/55', style: { marginInlineStart: '0.5rem' }, children: r.type }) : null
                      ]
                    }),
                    r.counts_as_fault === false ? jsx(StatePill, { label: t('recent.check_failed'), tip: t('recent.check_failed_tip'), tone: 'bad', t }) : null,
                    jsx('span', { className: 'shrink-0 text-[0.7rem] tabular-nums text-muted-foreground/60', children: ago(t, r.age) }),
                    jsxs('span', {
                      className: 'flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover/row:opacity-100',
                      children: [
                        jsx(Tip, {
                          label: t('recent.flag_tip'),
                          children: jsx(Button, { disabled: busy !== null, onClick: () => setFlagging(r), size: 'xs', variant: 'ghost', children: t('recent.flag') })
                        }),
                        jsx(Tip, {
                          label: t('recent.undo_tip'),
                          children: jsxs(Button, {
                            'aria-busy': busy === 'undo' + r.id || undefined,
                            disabled: busy !== null,
                            onClick: () =>
                              act('undo' + r.id, () => rest('/undo?of=' + encodeURIComponent(r.profile), { method: 'POST', body: { id: r.id } }), t('recent.undone'), t('recent.undo_failed')),
                            size: 'xs',
                            variant: 'outline',
                            children: [busy === 'undo' + r.id ? jsx(Codicon, { name: 'loading', size: '0.75rem', spinning: true }) : null, t('recent.undo')]
                          })
                        })
                      ]
                    })
                  ]
                },
                r.profile + r.id
              )
            ).concat(
              every.length > 5
                ? [jsx('div', { className: 'pt-1', children: jsx(Button, { onClick: () => setAll(!all), size: 'xs', variant: 'ghost', children: all ? t('recent.show_fewer') : t('recent.show_all', { n: every.length }) }) }, 'more')]
                : []
            )
          }),
      jsx(ConfirmDialog, {
        busyLabel: t('revoke.busy'),
        confirmLabel: t('flag.confirm'),
        description: flagging ? t('flag.desc', { type: flagging.type }) : null,
        destructive: true,
        onClose: () => setFlagging(null),
        onConfirm: async () => {
          const r = flagging
          await rest('/flag?of=' + encodeURIComponent(r.profile), { method: 'POST', body: { agent: r.agent, type: r.type } })
          haptic('success')
          host.notify({ kind: 'success', message: t('recent.flagged', { type: r.type }) })
          qc.invalidateQueries({ queryKey: ['tenure'] })
        },
        open: flagging !== null,
        title: t('flag.title')
      })
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
function PassportCard({ agent, doc, settled, ok, t, motion }) {
  const cardRef = useRef(null)
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
  const shown = types.slice(0, 6)
  const totals = types.reduce((acc, ty) => ({ f: acc.f + (ty.faults || 0), n: acc.n + (ty.successes || 0) + (ty.faults || 0) }), { f: 0, n: 0 })
  const paintSealAt = k => sealRef.current && paintSeal(sealRef.current, { size: 44, print: k })
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
    if (!el || !motion || e.pointerType !== 'mouse') return
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
      'data-motion': motion ? 'on' : 'off',
      onPointerLeave: onLeave,
      onPointerMove: onMove,
      ref: cardRef,
      children: [
        jsx('div', { 'aria-hidden': true, className: 'tn-sweep', ref: sweepRef }),
        jsx('div', { 'aria-hidden': true, className: 'tn-glare' }),
        jsxs('div', {
          className: 'tn-ptop',
          children: [
            jsx('span', { children: t('page.title') }),
            jsxs('span', { children: [t('passport.title'), ' ', jsx('span', { 'aria-hidden': true, className: 'tn-ok', ref: okRef, children: '✓' })] })
          ]
        }),
        jsx('div', { className: 'tn-pemb', children: jsx(Emblem, { motion, n: 88, rotate: true, share: shareOf(agent), size: 176 }) }),
        jsx('div', { 'aria-label': name, className: 'tn-pname', ref: nameRef, role: 'heading', 'aria-level': 4, children: motion ? '' : name }),
        jsx('div', {
          className: 'tn-prows',
          ref: rowsRef,
          children: shown.map((ty, i) => {
            const tier = tierKey(ty)
            return jsxs(
              'div',
              {
                className: cn('tn-prow', !motion && 'tn-on'),
                'data-motion': motion ? 'on' : 'off',
                children: [
                  jsxs('span', { className: 'tn-pk', children: [`#${pad2(i + 1)} ${ty.type}`, jsx('b', { children: `${TIER_SHORT[tier]} · ${tierName(tier, t)}` })] }),
                  jsx(DitherBar, { delay: 1700 + i * 200, motion, rows: 3, solid: tier === 'alone', track: ty.capped, value: fillOf(ty) })
                ]
              },
              ty.type
            )
          })
        }),
        jsxs('div', {
          className: 'tn-pfoot',
          children: [
            jsx('span', { children: t('benchmark.faults', { n: totals.f, total: totals.n }) }),
            jsxs('span', { children: [t('passport.ledger'), ' ', jsx('span', { className: 'tn-hash', ref: hashRef, children: motion ? '········' : head || '········' })] })
          ]
        }),
        jsxs('div', {
          className: 'tn-psig',
          children: [jsx(Emblem, { motion: false, n: 16, share: 1, size: 16 }), jsx('b', { children: 'TENURE' }), jsx('span', { children: t('passport.signature') })]
        }),
        jsx('canvas', { 'aria-hidden': true, className: 'tn-seal', ref: sealRef })
      ]
    })
  })
}

function PassportSection({ agent, t, n, motion }) {
  const head = agent.totals ? agent.totals.actions : 0
  const { data: doc, error, isLoading } = useQuery({
    queryKey: ['tenure', agent.profile, 'passport', agent.agent, head],
    queryFn: () => rest(`/passport?agent=${encodeURIComponent(agent.agent)}&of=${encodeURIComponent(agent.profile)}`),
    staleTime: Infinity,
    placeholderData: (previous, query) => (query && query.queryKey[3] === agent.agent ? previous : undefined)
  })
  const ok = doc && Array.isArray(doc.verify) && doc.verify.length === 0
  const p = doc && doc.passport
  return jsxs('section', {
    className: 'tn-section',
    children: [
      jsxs('div', {
        className: 'tn-section-head',
        children: [
          jsx(Eyebrow, { n, children: t('passport.title') }),
          p ? jsx(CopyButton, { buttonSize: 'xs', label: t('passport.copy'), showLabel: true, text: JSON.stringify(p, null, 2) }) : null
        ]
      }),
      jsx(PassportCard, { agent, doc, motion, ok: !!ok, settled: !!error || (!!doc && !isLoading), t }, agent.key),
      isLoading && !doc
        ? jsxs('p', { className: 'flex items-center gap-1.5 text-xs text-muted-foreground/70', style: { margin: 0 }, children: [jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }), t('passport.verifying')] })
        : jsxs('div', {
            className: cn('flex items-start gap-1.5 p-2 text-[0.72rem]', ok ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'),
            role: 'status',
            style: { maxWidth: '23rem' },
            children: [
              jsx(Codicon, { className: 'mt-px shrink-0', name: ok ? 'verified-filled' : 'warning', size: '0.85rem' }),
              jsx('span', {
                className: 'min-w-0 break-words',
                children: error
                  ? t('passport.unavailable', { error: error.message || String(error) })
                  : ok
                    ? t('passport.verified')
                    : t('passport.problems', { problems: ((doc && doc.verify) || []).join('; ') })
              })
            ]
          }),
      p
        ? jsx(PanelMeta, {
            rows: [
              { label: t('passport.protocol'), value: jsx('span', { className: 'font-mono', children: p.protocol }) },
              { label: t('passport.rule'), value: jsx('span', { className: 'font-mono', children: `${p.rule.name} · ${String(p.rule.fingerprint).slice(0, 16)}` }) },
              { label: t('passport.ledger'), value: jsx('span', { children: t('passport.ledger_value', { n: p.ledger.count, head: String(p.ledger.head).slice(0, 12) }) }) },
              { label: t('passport.generated'), value: when(p.generated_at) }
            ]
          })
        : null,
      p
        ? jsxs('div', {
            className: 'space-y-1',
            children: [
              jsx('p', { className: 'text-[0.7rem] text-muted-foreground/75', style: { margin: 0 }, children: t('passport.verify_hint') }),
              jsxs('div', {
                className: 'flex items-start gap-1',
                children: [
                  jsx(PanelBlock, { className: 'min-w-0 flex-1', children: VERIFY_COMMAND }),
                  jsx(CopyButton, { appearance: 'icon', label: t('passport.copy_command'), text: VERIFY_COMMAND })
                ]
              })
            ]
          })
        : null
    ]
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
  useEffect(() => {
    const now = new Map((agent.types || []).map(ty => [ty.type, { rank: TIER_RANK[tierKey(ty)], faults: ty.faults || 0, spots: ty.spot_checks || 0 }]))
    const prev = seen.get(agent.key)
    seen.set(agent.key, now)
    if (!prev) return
    const out = {}
    let best = null
    const stamp = Date.now()
    const rankOf = m => ({ granted: 3, probation: 2, review: 1 })[m.kind]
    for (const ty of agent.types || []) {
      const a = prev.get(ty.type)
      const b = now.get(ty.type)
      if (!a) continue
      let m = null
      if (b.rank < a.rank || b.faults > a.faults) {
        out[ty.type] = { dir: 'down', token: stamp + ty.type }
        if (b.rank === TIER_RANK.ask && a.rank > TIER_RANK.ask) m = { kind: 'probation', type: ty }
      } else if (b.rank > a.rank) {
        out[ty.type] = { dir: 'up', token: stamp + ty.type }
        m = { kind: b.rank === TIER_RANK.alone ? 'granted' : 'review', type: ty }
      } else if (b.spots > a.spots) out[ty.type] = { dir: 'spot', token: stamp + ty.type }
      if (m && (!best || rankOf(m) > rankOf(best))) best = m
    }
    if (Object.keys(out).length) setChanges(c => ({ ...c, ...out }))
    if (Object.values(out).some(c => c.dir === 'up')) setPulse(x => x + 1)
    if (best) setMoment({ ...best, key: stamp })
  }, [agent])
  return { changes, moment, pulse, dismiss: () => setMoment(null) }
}

/** C / D. The big moment, once: a filled accent band for a promotion, a quiet card for a fault (the repair path). */
function MomentBand({ moment, agent, t, motion, onClose }) {
  const ref = useRef(null)
  const [leaving, setLeaving] = useState(false)
  const close = () => {
    if (!motion) return onClose()
    setLeaving(true)
    setTimeout(onClose, 280)
  }
  useEffect(() => {
    const id = setTimeout(close, 6000)
    return () => clearTimeout(id)
  }, [moment.key])
  const down = moment.kind === 'probation'
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
  useEffect(() => {
    if (down) return
    if (!motion) return paintFade(1)
    return tween(1000, k => paintFade(k), null, 200)
  }, [moment.key, motion])
  const ty = moment.type
  const title = down ? t('moment.probation') : moment.kind === 'granted' ? t('moment.granted') : t('moment.review')
  const sub = down ? nextLine(ty, t, (agent.settings || {}).spot) : `${displayName(agent.model)} · ${TierLabel(tierKey(ty), t)}`
  return jsxs('div', {
    'aria-live': 'polite',
    className: cn(down ? 'tn-fault' : 'tn-band', leaving && 'tn-leaving', motion && 'tn-enter'),
    'data-motion': motion ? 'on' : 'off',
    role: 'status',
    children: [
      jsx('button', { 'aria-label': t('moment.dismiss'), className: 'tn-band-close', onClick: close, type: 'button', children: jsx(Codicon, { name: 'close', size: '0.8rem' }) }),
      jsxs('div', {
        className: down ? undefined : 'tn-band-in',
        children: [
          jsx('div', { className: 'tn-eyebrow', children: t(down ? 'moment.eyebrow_down' : 'moment.eyebrow_up', { type: ty.type }) }),
          jsx('div', { className: 'tn-band-title', children: title }),
          jsx('div', { className: 'tn-band-sub', children: sub })
        ]
      }),
      down
        ? jsx('div', { style: { marginBlockStart: '0.75rem' }, children: jsx(DitherBar, { change: { dir: 'down', token: moment.key }, motion, value: fillOf(ty) }) })
        : jsx('canvas', { 'aria-hidden': true, className: 'tn-mirror', ref })
    ]
  })
}

function AgentDetail({ agent, t, onRevoke }) {
  const motion = useMotion()
  const tot = agent.totals || {}
  const s = agent.settings || {}
  const types = agent.types || []
  const { changes, moment, pulse, dismiss } = useTransitions(agent)
  const t3 = types.filter(ty => tierKey(ty) === 'alone').length
  const t2 = types.filter(ty => tierKey(ty) === 'notify').length
  const caption = [t3 ? t('emblem.tenured', { n: t3 }) : null, t2 ? t('emblem.review', { n: t2 }) : null].filter(Boolean).join(' · ') || t('emblem.none')
  const stat = (value, label, tip) =>
    jsxs('span', {
      className: 'tn-stat',
      children: [
        tip ? jsx(Tip, { label: tip, children: jsx('b', { tabIndex: 0, children: String(value || 0) }) }) : jsx('b', { children: String(value || 0) }),
        jsx('span', { children: label })
      ]
    })
  return jsxs(PanelDetail, {
    className: 'tn-root max-w-3xl',
    children: [
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
                  jsx(Tip, { label: t('meta.provider'), children: jsx('span', { tabIndex: 0, children: agent.provider }) }),
                  jsx('span', { className: 'tn-dim', children: ' · ' }),
                  `${t('meta.profile')} ${agent.profile}`
                ]
              }),
              jsx(Tip, { label: agent.agent, children: jsx('h3', { className: 'tn-name', children: displayName(agent.model) }) }),
              jsxs('div', {
                className: 'tn-pills',
                children: [
                  jsx(TierChip, { motion, t, tier: bestTier(agent) }),
                  agent.provisional ? jsx(StatePill, { label: t('state.provisional'), tip: t('state.provisional_tip'), tone: 'warn', t }) : null,
                  agent.trial ? jsx(StatePill, { label: t('state.trial'), tip: t('state.trial_tip'), tone: 'warn', t }) : null,
                  agent.unresolved_fault ? jsx(StatePill, { label: t('state.fault'), tip: t('state.fault_tip'), tone: 'bad', t }) : null,
                  agent.suspended ? jsx(StatePill, { label: t('state.suspended'), tip: t('state.suspended_tip'), tone: 'bad', t }) : null
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
              })
            ]
          }),
          jsxs('div', {
            className: 'tn-hero-side',
            children: [
              jsx('div', { style: { alignSelf: 'flex-end' }, children: jsx(PanelAction, { icon: 'circle-slash', onClick: onRevoke, children: t('revoke.action') }) }),
              jsx(Emblem, { label: caption, motion, n: 60, pulse, share: shareOf(agent), size: 120 }, agent.key),
              jsx('div', { 'aria-hidden': true, className: 'tn-emblem-cap', children: caption })
            ]
          })
        ]
      }),
      moment ? jsx(MomentBand, { agent, moment, motion, onClose: dismiss, t }, moment.key) : null,
      jsxs('section', {
        className: 'tn-section',
        children: [
          jsx(Eyebrow, { n: 1, children: t('types.title') }),
          jsx('div', {
            className: 'tn-rows',
            children: types.map((ty, i) => jsx(TypeRow, { change: changes[ty.type], index: i, motion, spot: s.spot, t, type: ty }, agent.key + '|' + ty.type))
          })
        ]
      }),
      jsx(RecentSection, { agent, n: 2, t }),
      jsx(PassportSection, { agent, motion, n: 3, t })
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
                    menuItems: [{ icon: 'circle-slash', label: t('revoke.action'), onSelect: () => setPending(a), tone: 'danger' }],
                    menuLabel: displayName(a.model),
                    meta: TIER_SHORT[bestTier(a)],
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
  if (!rows.length) return jsx(PanelEmpty, { description: t('empty.desc'), icon: 'graph', title: t('empty.title') })
  const types = [...new Set(rows.map(r => r.type))]
  const q = query.trim().toLowerCase()
  const visibleTypes = types.filter(x => !q || x.toLowerCase().includes(q))
  const type = selected && visibleTypes.includes(selected) ? selected : visibleTypes[0]
  const ranked = rows.filter(r => r.type === type)
  const pub = (ranked.find(r => r.public) || {}).public
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
                meta: String(rows.filter(r => r.type === x).length),
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
            className: 'tn-root max-w-3xl',
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
                className: 'flex items-center gap-x-3 px-1',
                'aria-hidden': true,
                children: [
                  jsx('span', { className: 'w-6 shrink-0' }),
                  jsx('span', { className: 'min-w-[10rem] flex-1' }),
                  jsxs('span', {
                    className: 'flex shrink-0 items-center gap-3',
                    children: [
                      jsx('span', { className: 'tn-eyebrow w-24', style: { textAlign: 'end' }, children: t('benchmark.col_faults') }),
                      jsx('span', { className: 'tn-eyebrow w-24', children: t('benchmark.col_range') }),
                      jsx('span', { className: 'tn-eyebrow w-28', children: t('benchmark.col_rate') }),
                      jsx('span', { className: 'tn-eyebrow w-12', style: { textAlign: 'end' }, children: t('benchmark.col_public') })
                    ]
                  })
                ]
              }),
              jsx('div', {
                className: 'flex flex-col',
                style: { borderBlockStart: '1px solid var(--tn-line)' },
                children: ranked.map((r, i) =>
                  jsxs(
                    'div',
                    {
                      className: cn('tn-brow flex flex-wrap items-center gap-x-3 gap-y-1 px-1 py-2 text-[0.78rem] hover:bg-(--ui-row-hover-background)', motion && 'tn-enter'),
                      style: motion ? { animationDelay: `${i * 40}ms` } : undefined,
                      children: [
                        jsx('span', { className: 'tn-tnum w-6 shrink-0', style: { paddingBlockStart: 0 }, children: '#' + pad2(i + 1) }),
                        jsxs('span', {
                          className: 'min-w-[10rem] flex-1',
                          children: [
                            jsx(Tip, { label: r.agent, children: jsx('span', { className: 'block truncate text-foreground/85', children: displayName(r.model) }) }),
                            jsx('span', { className: 'block truncate text-[0.68rem] text-muted-foreground/65', children: `${r.provider} · ${r.profile}` })
                          ]
                        }),
                        jsxs('span', {
                          className: 'flex shrink-0 items-center gap-3',
                          children: [
                            jsx('span', { className: 'w-24 whitespace-nowrap font-mono text-[0.72rem] tabular-nums', style: { textAlign: 'end' }, children: t('benchmark.faults', { n: r.faults, total: r.successes + r.faults }) }),
                            jsx(Tip, {
                              label: t('benchmark.range_tip'),
                              children: jsx('span', {
                                'aria-label': r.enough ? t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }) : t('benchmark.not_enough'),
                                className: 'inline-flex w-24',
                                role: 'img',
                                tabIndex: 0,
                                children: jsx(RangeBar, { delay: 80 + i * 40, enough: r.enough, high: r.high, low: r.low, motion, rate: r.rate })
                              })
                            }),
                            jsx('span', { className: 'w-28 text-[0.7rem] tabular-nums text-muted-foreground/80', children: r.enough ? t('benchmark.rate', { rate: pct(r.rate), low: pct(r.low), high: pct(r.high) }) : t('benchmark.not_enough') }),
                            jsx(Tip, {
                              label: pub ? t('benchmark.public_score', { benchmark: pub.benchmark, source: pub.source }) : '',
                              children: jsx('span', {
                                className: 'w-12 text-[0.7rem] tabular-nums text-muted-foreground/80',
                                style: { textAlign: 'end' },
                                children: r.public && r.public.new != null ? t('benchmark.public_value', { value: dec1(Number(r.public.new)) }) : t('benchmark.no_public')
                              })
                            })
                          ]
                        })
                      ]
                    },
                    type + '|' + r.agent + r.profile
                  )
                )
              }),
              pub ? jsx('p', { className: 'text-[0.7rem] text-muted-foreground/70', style: { margin: 0 }, children: t('benchmark.public_score_accessed', { benchmark: pub.benchmark, source: pub.source, accessed: pub.accessed }) }) : null
            ]
          })
    ]
  })
}

let focusKey = null
let focusRevoke = false

function AnimationsToggle({ t }) {
  const [on, setOn] = useState(() => animPref !== 'off')
  return jsxs('label', {
    className: 'tn-anim-toggle',
    children: [
      jsx('span', { children: t('page.animations') }),
      jsx(Switch, {
        'aria-label': t('page.animations'),
        checked: on,
        onCheckedChange: value => {
          setOn(!!value)
          setAnimPref(value ? 'on' : 'off')
        },
        size: 'xs'
      })
    ]
  })
}

function TenurePage() {
  const t = usePluginI18n(ID)
  const { data, error, isLoading, refetch } = useAgents()
  const [view, setView] = useState('agents')
  useEffect(() => {
    const onFocus = () => setView('agents')
    bus.addEventListener('focus', onFocus)
    return () => bus.removeEventListener('focus', onFocus)
  }, [])
  const agents = allAgents(data)
  let body
  if (isLoading && !data) body = jsx(PanelEmpty, { description: t('common.loading'), icon: 'loading~spin' })
  else if (error && !data)
    body = jsx(ErrorState, {
      description: t('backend.desc', { error: error.message || String(error) }),
      title: t('backend.title'),
      children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('common.retry') })
    })
  else if (!agents.length) body = jsx(PanelEmpty, { description: t('empty.desc'), icon: 'shield', title: t('empty.title') })
  else if (view === 'benchmark') body = jsx(BenchmarkView, { t })
  else body = jsx(AgentsView, { data, t })
  return jsxs('div', {
    className: 'tn-root relative flex h-full flex-col overflow-hidden bg-(--ui-surface-background)',
    children: [
      jsxs('header', {
        className: 'flex shrink-0 flex-wrap items-center gap-2 px-4 py-2',
        children: [
          jsx('h1', { className: 'text-sm font-semibold text-foreground', children: t('page.title') }),
          agents.length
            ? jsx('span', { className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 py-px text-[0.625rem] tabular-nums text-(--ui-text-tertiary)', children: String(agents.length) })
            : null,
          agents.length
            ? jsx(WorkspacePageHeaderControl, {
                id: 'tenure:view',
                children: jsxs('div', {
                  className: 'tn-root',
                  style: { marginInlineStart: 'auto', display: 'flex', alignItems: 'center', gap: '0.75rem' },
                  children: [
                    jsx(AnimationsToggle, { t }),
                    jsx(SegmentedControl, {
                      onChange: setView,
                      options: [
                        { id: 'agents', label: t('page.view_agents') },
                        { id: 'benchmark', label: t('page.view_benchmark') }
                      ],
                      sizing: 'content',
                      value: view
                    })
                  ]
                })
              })
            : null
        ]
      }),
      agents.length ? jsx(Intro, { t, spot: (((data && data.profiles) || []).find(p => p.current) || {}).settings?.spot }) : null,
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
    rest = ctx.rest
    storage = ctx.storage
    animPref = storage && storage.get('animations', 'on') === 'off' ? 'off' : 'on'
    const style = document.createElement('style')
    style.dataset.plugin = ID
    style.textContent = CSS
    document.head.append(style)
    watchTheme()
    ctx.onDispose(() => {
      rest = null
      storage = null
      style.remove()
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
            return tier === 'ask' || tier === 'cap' ? null : { badge: tr('model_menu.badge', { tier: TIER_SHORT[tier] }) }
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
