/**
 * tenure, desktop half.
 *
 * - A Tenure page: each agent's earned tiers per action type, what it did on its own (with Undo and Flag), the signed
 *   passport, and your own benchmark per action type.
 * - A status-bar chip for the model in use, a tier badge on each model in the model menu, ⌘K commands, and an
 *   Undo toast when an action type acts, then notifies.
 *
 * Built only from the app's own components (the Panel family of the Scheduled jobs page, ConfirmDialog,
 * SegmentedControl, CopyButton, Tip, Codicon) and its data layer (useQuery, refreshed live by the agent half's
 * `plugin.tenure.*` events). Every number comes from the agent half's backend (`dashboard/plugin_api.py`, through
 * `ctx.rest`). Plain ESM, loaded uncompiled: UI is jsx() calls; only @hermes/plugin-sdk, react and react/jsx-runtime.
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
  Tip,
  usePluginI18n,
  useQuery,
  useQueryClient,
  useValue,
  WorkspacePageHeaderControl
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
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
    "empty.desc": "Work as usual. Every change asks first, and each action type earns its tier from the answers you give.",
    "empty.title": "No agent has acted yet",
    "flag.confirm": "Flag",
    "flag.desc": "This counts as a fault: {type} will drop at least one tier and climb again. Use it for an error nobody caught.",
    "flag.title": "Flag this change as an error?",
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
    "nav.label": "Tenure",
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
    "passport.title": "Signed passport",
    "passport.unavailable": "Not available: {error}",
    "passport.verified": "Verified: signature valid, hash chain intact, and replaying the ledger gives the same tiers.",
    "passport.verify_hint": "Anyone can check it:",
    "passport.verifying": "Verifying…",
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
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "high stakes",
    "type.stakes_low": "low stakes",
    "type.stakes_medium": "medium stakes",
    "type.stakes_other": "{stakes} stakes",
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
    "empty.desc": "اعمل كالمعتاد. كل تغيير يسأل أولًا، وكل نوع إجراء يكتسب مستواه من إجاباتك.",
    "empty.title": "لم ينفّذ أي وكيل شيئًا بعد",
    "flag.confirm": "إبلاغ",
    "flag.desc": "يُحسب هذا إخفاقًا: سينزل {type} مستوى واحدًا على الأقل ثم يصعد من جديد. استخدمه لخطأ لم يلحظه أحد.",
    "flag.title": "الإبلاغ عن هذا التغيير كخطأ؟",
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
    "nav.label": "Tenure",
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
    "passport.title": "جواز موقَّع",
    "passport.unavailable": "غير متاح: {error}",
    "passport.verified": "تم التحقق: التوقيع صالح، وسلسلة التجزئة سليمة، وإعادة تشغيل الدفتر تعطي المستويات نفسها.",
    "passport.verify_hint": "يمكن لأي شخص التحقق منه:",
    "passport.verifying": "جارٍ التحقق…",
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
    "empty.desc": "Trabaja como siempre. Cada cambio pregunta antes, y cada tipo de acción se gana su nivel con tus respuestas.",
    "empty.title": "Ningún agente ha actuado todavía",
    "flag.confirm": "Marcar",
    "flag.desc": "Cuenta como un fallo: {type} bajará al menos un nivel y tendrá que volver a subir. Úsalo para un error que nadie detectó.",
    "flag.title": "¿Marcar este cambio como error?",
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
    "nav.label": "Tenure",
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
    "passport.title": "Pasaporte firmado",
    "passport.unavailable": "No disponible: {error}",
    "passport.verified": "Verificado: firma válida, cadena de hashes intacta, y al reproducir el registro se obtienen los mismos niveles.",
    "passport.verify_hint": "Cualquiera puede comprobarlo:",
    "passport.verifying": "Verificando…",
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
    "type.sessions": {
      "one": "{n} sesión",
      "other": "{n} sesiones"
    },
    "type.stakes_high": "impacto alto",
    "type.stakes_low": "impacto bajo",
    "type.stakes_medium": "impacto medio",
    "type.stakes_other": "impacto {stakes}",
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
    "empty.desc": "Travaillez comme d'habitude. L'agent demande avant chaque modification, et chaque type d'action gagne son niveau selon vos réponses.",
    "empty.title": "Aucun agent n'a encore agi",
    "flag.confirm": "Signaler",
    "flag.desc": "Cela compte comme une faute : {type} descendra d'au moins un niveau et devra remonter. À utiliser pour une erreur que personne n'a repérée.",
    "flag.title": "Signaler cette modification comme une erreur ?",
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
    "nav.label": "Tenure",
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
    "passport.title": "Passeport signé",
    "passport.unavailable": "Indisponible : {error}",
    "passport.verified": "Vérifié : signature valide, chaîne de hachage intacte, et le registre rejoué redonne les mêmes niveaux.",
    "passport.verify_hint": "Tout le monde peut le vérifier :",
    "passport.verifying": "Vérification…",
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
    "type.sessions": {
      "one": "{n} session",
      "other": "{n} sessions"
    },
    "type.stakes_high": "enjeu élevé",
    "type.stakes_low": "enjeu faible",
    "type.stakes_medium": "enjeu moyen",
    "type.stakes_other": "enjeu {stakes}",
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
    "empty.desc": "照常工作即可。每次更改都会先询问你，每个操作类型会根据你的回答赢得相应级别。",
    "empty.title": "还没有智能体执行过操作",
    "flag.confirm": "标记",
    "flag.desc": "这会记为一次失误：{type} 至少下降一个级别，之后需重新晋升。用于没人发现的错误。",
    "flag.title": "将此更改标记为错误？",
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
    "nav.label": "Tenure",
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
    "passport.title": "已签名护照",
    "passport.unavailable": "不可用：{error}",
    "passport.verified": "已验证：签名有效，哈希链完整，重放账本得到相同的级别。",
    "passport.verify_hint": "任何人都可以验证：",
    "passport.verifying": "正在验证…",
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
    "type.sessions": {
      "other": "{n} 个会话"
    },
    "type.stakes_high": "高风险",
    "type.stakes_low": "低风险",
    "type.stakes_medium": "中风险",
    "type.stakes_other": "{stakes}风险",
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
const TIER_TONE = { ask: 'muted', notify: 'good', alone: 'good', cap: 'muted' }
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

// ------------------------------------------------------------------------------------------------ pieces
function TierLabel(tier, t) {
  return { ask: t('tier.t1'), notify: t('tier.t2'), alone: t('tier.t3'), cap: t('tier.cap') }[tier]
}

function TierPill({ tier, t }) {
  return jsx(Tip, {
    label: TierLabel(tier, t),
    children: jsx('span', {
      'aria-label': TierLabel(tier, t),
      className: 'inline-flex items-center gap-1 rounded-full focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring/50',
      tabIndex: 0,
      children: jsx(PanelPill, {
        tone: TIER_TONE[tier],
        children: tier === 'alone' ? jsxs('span', { className: 'inline-flex items-center gap-0.5', children: [jsx(Codicon, { name: 'verified', size: '0.6rem' }), 'T3'] }) : TIER_SHORT[tier]
      })
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

function Progress({ value, max, label }) {
  const width = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0
  return jsx('span', {
    'aria-label': label,
    'aria-valuemax': max,
    'aria-valuemin': 0,
    'aria-valuenow': value,
    className: 'relative inline-block h-1 shrink-0 overflow-hidden rounded-full bg-foreground/10',
    role: 'progressbar',
    style: { width: 64 },
    children: jsx('span', { className: 'absolute inset-y-0 rounded-full bg-primary', style: { insetInlineStart: 0, width: `${width}%` } })
  })
}

function Range({ rate, low, high, enough }) {
  const axis = 0.7
  const at = x => `${Math.min(100, (100 * x) / axis)}%`
  return jsxs('span', {
    'aria-hidden': true,
    className: 'relative inline-block h-2 shrink-0',
    style: { width: 96 },
    children: [
      jsx('span', { className: 'absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-foreground/15' }),
      jsx('span', {
        className: cn('absolute top-1/2 h-1 -translate-y-1/2 rounded-full', enough ? 'bg-primary' : 'bg-foreground/20'),
        style: { insetInlineStart: at(low), width: `calc(${at(high)} - ${at(low)})`, minWidth: 2, opacity: enough ? 0.4 : 1 }
      }),
      enough ? jsx('span', { className: 'absolute top-1/2 size-1.5 -translate-y-1/2 rounded-full bg-primary', style: { insetInlineStart: at(rate), marginInlineStart: '-0.1875rem' } }) : null
    ]
  })
}

function TypeRow({ type, t }) {
  const tier = tierKey(type)
  const g = type.guarantee
  return jsxs('div', {
    className: 'rounded-md px-2 py-1.5 hover:bg-(--ui-row-hover-background)',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.78rem]',
        children: [
          jsx(TierPill, { tier, t }),
          jsx('span', { className: 'min-w-0 flex-1 truncate font-mono text-[0.75rem] text-foreground/85', children: type.type }),
          jsx('span', { className: 'shrink-0 text-[0.7rem] text-muted-foreground/70', children: ['low', 'medium', 'high'].includes(type.stakes) ? t('type.stakes_' + type.stakes) : t('type.stakes_other', { stakes: type.stakes }) }),
          type.capped
            ? jsx('span', { className: 'shrink-0 text-[0.7rem] text-muted-foreground/70', children: t('type.always_asks') })
            : jsxs('span', {
                className: 'flex shrink-0 items-center gap-2 text-[0.7rem] tabular-nums text-muted-foreground/80',
                children: [
                  jsx(Progress, { value: type.series, max: type.required, label: t('type.in_a_row', { series: type.series, required: type.required }) }),
                  jsx('span', { children: t('type.in_a_row', { series: type.series, required: type.required }) }),
                  jsx('span', { className: 'text-muted-foreground/60', children: t('type.sessions', { n: type.sessions }) })
                ]
              })
        ]
      }),
      !type.capped && g
        ? jsx('p', {
            className: 'mt-0.5 text-[0.7rem] leading-relaxed text-muted-foreground/75',
            style: { paddingInlineStart: '2.5rem' },
            children: t(g.conditional ? 'type.guarantee_provisional' : 'type.guarantee', { aoql: pct(g.aoql), worst: pct(g.worst_case) })
          })
        : null
    ]
  })
}

function Intro({ t, spot }) {
  const [hidden, setHidden] = useState(() => (storage ? storage.get('introDismissed', false) : false))
  if (hidden) return null
  return jsxs('div', {
    className: 'mx-4 mb-3 flex items-start gap-3 rounded-md bg-(--ui-bg-quinary) px-3 py-2.5',
    children: [
      jsx(Codicon, { className: 'mt-0.5 shrink-0 text-muted-foreground/70', name: 'shield', size: '0.95rem' }),
      jsxs('div', {
        className: 'min-w-0 flex-1 space-y-0.5',
        children: [
          jsx('p', { className: 'text-xs font-medium text-foreground', children: t('intro.title') }),
          jsx('p', { className: 'max-w-3xl text-xs leading-relaxed text-muted-foreground/80', children: t('intro.body', { k: Math.round(1 / (spot || 0.1)) }) })
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

function RecentSection({ agent, t }) {
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
    className: 'space-y-1.5',
    children: [
      jsx(PanelSectionLabel, { children: t('recent.title') }),
      rows.length === 0
        ? jsx('p', { className: 'px-2 text-xs text-muted-foreground/70', children: t('recent.none') })
        : jsx('div', {
            className: 'flex flex-col',
            children: rows.map(r =>
              jsxs(
                'div',
                {
                  className: 'group/row flex items-center gap-3 rounded-md px-2 py-1 text-[0.78rem] hover:bg-(--ui-row-hover-background)',
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
                ? [jsx('div', { className: 'px-2 pt-1', children: jsx(Button, { onClick: () => setAll(!all), size: 'xs', variant: 'ghost', children: all ? t('recent.show_fewer') : t('recent.show_all', { n: every.length }) }) }, 'more')]
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

function PassportSection({ agent, t }) {
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
    className: 'space-y-2',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx(PanelSectionLabel, { children: t('passport.title') }),
          p ? jsx(CopyButton, { buttonSize: 'xs', label: t('passport.copy'), showLabel: true, text: JSON.stringify(p, null, 2) }) : null
        ]
      }),
      isLoading && !doc
        ? jsxs('p', { className: 'flex items-center gap-1.5 text-xs text-muted-foreground/70', children: [jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }), t('passport.verifying')] })
        : jsxs('div', {
            className: cn('flex items-start gap-1.5 rounded p-2 text-[0.72rem]', ok ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'),
            role: 'status',
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
              jsx('p', { className: 'text-[0.7rem] text-muted-foreground/75', children: t('passport.verify_hint') }),
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

function AgentDetail({ agent, t, onRevoke }) {
  const tot = agent.totals || {}
  const s = agent.settings || {}
  return jsxs(PanelDetail, {
    className: 'max-w-3xl',
    children: [
      jsxs('header', {
        className: 'space-y-3',
        children: [
          jsxs('div', {
            className: 'flex flex-wrap items-start justify-between gap-3',
            children: [
              jsxs('div', {
                className: 'flex min-w-0 flex-wrap items-center gap-2',
                children: [
                  jsx(Tip, { label: agent.agent, children: jsx('h3', { className: 'text-[0.95rem] font-semibold tracking-tight text-foreground', children: displayName(agent.model) }) }),
                  jsx(TierPill, { tier: bestTier(agent), t }),
                  agent.provisional ? jsx(StatePill, { label: t('state.provisional'), tip: t('state.provisional_tip'), tone: 'warn', t }) : null,
                  agent.trial ? jsx(StatePill, { label: t('state.trial'), tip: t('state.trial_tip'), tone: 'warn', t }) : null,
                  agent.unresolved_fault ? jsx(StatePill, { label: t('state.fault'), tip: t('state.fault_tip'), tone: 'bad', t }) : null,
                  agent.suspended ? jsx(StatePill, { label: t('state.suspended'), tip: t('state.suspended_tip'), tone: 'bad', t }) : null
                ]
              }),
              jsx('div', { className: 'flex shrink-0 items-center gap-0.5', children: jsx(PanelAction, { icon: 'circle-slash', onClick: onRevoke, children: t('revoke.action') }) })
            ]
          }),
          jsx(PanelMeta, {
            rows: [
              { label: t('meta.profile'), value: agent.profile },
              { label: t('meta.provider'), value: agent.provider },
              { label: t('meta.actions'), value: jsx(Tip, { label: t('meta.actions_tip'), children: jsx('span', { tabIndex: 0, children: String(tot.actions || 0) }) }) },
              { label: t('meta.checked'), value: String(tot.checked || 0) },
              { label: t('meta.alone'), value: String(tot.alone || 0) },
              { label: t('meta.faults'), value: String(tot.faults || 0) },
              { label: t('meta.preset'), value: t(s.pending ? 'preset.value_pending' : 'preset.value', { preset: presetName(t, s.preset || 'balanced'), k: Math.round(1 / (s.spot || 0.1)) }) }
            ]
          })
        ]
      }),
      jsxs('section', {
        className: 'space-y-1.5',
        children: [jsx(PanelSectionLabel, { children: t('types.title') }), jsx('div', { className: 'flex flex-col', children: (agent.types || []).map(ty => jsx(TypeRow, { type: ty, t }, ty.type)) })]
      }),
      jsx(RecentSection, { agent, t }),
      jsx(PassportSection, { agent, t })
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
      agent ? jsx(AgentDetail, { agent, t, onRevoke: () => setPending(agent) }) : jsx(PanelEmpty, { description: q ? t('common.no_match') : t('agents.pick'), icon: q ? 'search' : 'shield' }),
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
            className: 'max-w-3xl',
            children: [
              jsxs('header', {
                className: 'space-y-2',
                children: [
                  jsx('h3', { className: 'font-mono text-[0.95rem] font-semibold tracking-tight text-foreground', children: type }),
                  jsx('p', { className: 'text-xs leading-relaxed text-muted-foreground/80', children: t('benchmark.note') })
                ]
              }),
              jsxs('div', {
                className: 'flex items-center gap-x-3 px-2',
                'aria-hidden': true,
                children: [
                  jsx('span', { className: 'w-4 shrink-0' }),
                  jsx('span', { className: 'min-w-[10rem] flex-1' }),
                  jsxs('span', {
                    className: 'flex shrink-0 items-center gap-3',
                    children: [
                      jsx('span', { className: 'w-24', style: { textAlign: 'end' }, children: jsx(PanelSectionLabel, { children: t('benchmark.col_faults') }) }),
                      jsx(PanelSectionLabel, { className: 'w-24', children: t('benchmark.col_range') }),
                      jsx(PanelSectionLabel, { className: 'w-28', children: t('benchmark.col_rate') }),
                      jsx('span', { className: 'w-12', style: { textAlign: 'end' }, children: jsx(PanelSectionLabel, { children: t('benchmark.col_public') }) })
                    ]
                  })
                ]
              }),
              jsx('div', {
                className: 'flex flex-col',
                children: ranked.map((r, i) =>
                  jsxs(
                    'div',
                    {
                      className: 'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-1.5 text-[0.78rem] hover:bg-(--ui-row-hover-background)',
                      children: [
                        jsx('span', { className: 'w-4 shrink-0 tabular-nums text-muted-foreground/60', children: String(i + 1) }),
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
                            jsx(Tip, { label: t('benchmark.range_tip'), children: jsx('span', { className: 'inline-flex', tabIndex: 0, children: jsx(Range, { rate: r.rate, low: r.low, high: r.high, enough: r.enough }) }) }),
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
                    r.agent + r.profile
                  )
                )
              }),
              pub ? jsx('p', { className: 'text-[0.7rem] text-muted-foreground/70', children: t('benchmark.public_score_accessed', { benchmark: pub.benchmark, source: pub.source, accessed: pub.accessed }) }) : null
            ]
          })
    ]
  })
}

let focusKey = null
let focusRevoke = false

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
    className: 'relative flex h-full flex-col overflow-hidden bg-(--ui-surface-background)',
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
                children: jsx('div', {
                  style: { marginInlineStart: 'auto' },
                  children: jsx(SegmentedControl, {
                    onChange: setView,
                    options: [
                      { id: 'agents', label: t('page.view_agents') },
                      { id: 'benchmark', label: t('page.view_benchmark') }
                    ],
                    sizing: 'content',
                    value: view
                  })
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
    ctx.onDispose(() => {
      rest = null
      storage = null
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
