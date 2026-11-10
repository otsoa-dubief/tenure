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

// One vocabulary for the tiers, shared with the CLI and the dashboard tab.
const EN = {
  nav: 'Tenure',
  title: 'Tenure',
  viewAgents: 'Agents',
  viewBenchmark: 'Your benchmark',
  search: 'Search agents',
  searchTypes: 'Search action types',
  noMatch: 'No match',
  loading: 'Reading the evidence…',
  backendTitle: 'The agent half is not answering',
  backendDesc: err => `Enable tenure for this profile in Capabilities → Plugins (Agent column). ${err}`,
  retry: 'Try again',
  emptyTitle: 'No agent has acted yet',
  emptyDesc: 'Work as usual. Every change asks first, and each action type earns its tier from the answers you give.',
  pickAgent: 'Pick an agent to see what it has earned.',
  introTitle: 'How an action type earns its tier',
  introBody: k =>
    `Every action type of every model starts at T1: it asks first. A run of clean, approved actions moves it to T2: it acts, then tells you, with an Undo. A longer run, over two sessions, moves it to T3: it acts on its own, and 1 action in ${k} still asks, as a spot check. One fault sends the type back down.`,
  gotIt: 'Got it',
  tierT1: 'T1 · asks first',
  tierT2: 'T2 · acts, then tells you, with an Undo',
  tierT3: 'T3 · acts on its own, spot-checked',
  tierCap: 'Capped · always asks',
  provisional: 'provisional',
  provisionalTip: 'Carried over from the previous model, halved, until its own approvals confirm it.',
  trial: 'trial',
  trialTip: 'A medium or high fault opened a trial: 3 verified successes in a row.',
  fault: 'fault',
  faultTip: 'A medium or high fault stays on record until a trial is passed.',
  suspended: 'suspended',
  suspendedTip: 'A session read outside content: it asks for everything until it ends.',
  revoke: 'Revoke…',
  revokeTitle: 'Revoke earned autonomy?',
  revokeDescBefore: '',
  revokeDescAfter: ' will ask before every action again. Its record stays in the ledger.',
  revokeConfirm: 'Revoke',
  revoking: 'Revoking…',
  revoked: name => `${name} asks first again on every action type.`,
  revokeFailed: 'Could not revoke',
  metaProfile: 'Profile',
  metaProvider: 'Provider',
  metaActions: 'Actions',
  metaActionsTip: 'Every action of this agent tenure saw. Actions nobody verified (no answer, a timeout) count for nothing.',
  metaChecked: 'By you',
  metaAlone: 'On its own',
  metaFaults: 'Faults',
  showAll: n => `Show all ${n}`,
  showFewer: 'Show fewer',
  metaPreset: 'Preset',
  presetValue: (p, spot, pending) => `${p} · 1 in ${Math.round(1 / (spot || 0.1))} spot-checked` + (pending ? ' · applies from the next action' : ''),
  types: 'Action types',
  stakes: s => `${s} stakes`,
  inARow: (s, r) => `${s} of ${r} in a row`,
  sessions: n => `${n} ${n === 1 ? 'session' : 'sessions'}`,
  alwaysAsks: 'always asks',
  guarantee: (a, w) => `At most ${a}% of this type's actions run with an error nobody approved; ${w}% if the model turns bad.`,
  conditional: ' Provisional: carried-over evidence.',
  recent: 'Acted without asking',
  recentNone: 'Nothing to undo in the last 24 hours.',
  ago: s => (s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`),
  undo: 'Undo',
  undoTip: 'Restore the files as they were. Counts as a fault: the type goes back down.',
  undone: 'Files restored. Counted as a fault.',
  undoFailed: 'Could not undo',
  flag: 'Flag',
  flagTip: 'It made an error nobody caught: revoke this type.',
  flagged: type => `${type} revoked: it asks first again.`,
  flagFailed: 'Could not flag',
  actedToast: (type, n, name) => (n > 1 ? `${type}: ${n} changes, then told you (${name}).` : `${type} changed, then told you (${name}).`),
  actedDetail: 'Undo restores the files of the last change and counts as a fault.',
  passportSection: 'Signed passport',
  verifying: 'Verifying…',
  verified: 'Verified: signature valid, hash chain intact, and replaying the ledger gives the same tiers.',
  problems: p => `Does not verify: ${p}`,
  unavailable: e => `Not available: ${e}`,
  protocol: 'Protocol',
  rule: 'Rule',
  ledger: 'Ledger',
  generated: 'Generated',
  ledgerValue: (c, h) => `${c} events · head ${h}`,
  copyPassport: 'Copy passport',
  verifyHint: 'Anyone can check it:',
  verifyCommand: 'hermes tenure verify passport.json ledger.jsonl',
  benchmarkNote:
    "Each model's verified record on your work for this action type, with the 95% range of its fault rate, ranked by the top of that range. The public score is context: capability on their tasks, not reliability on yours.",
  faults: (f, n) => `${f} ${f === 1 ? 'fault' : 'faults'} / ${n}`,
  colFaults: 'Faults',
  colRange: '95% range',
  colRate: 'Rate',
  colPublic: 'Public',
  moreFiles: n => ` +${n}`,
  checkFailed: 'check failed',
  checkFailedTip: 'The automatic check failed: already counted as a fault. Undo restores the files.',
  flagTitle: 'Flag this change as an error?',
  flagDesc: type => `This counts as a fault: ${type} will drop at least one tier and climb again. Use it for an error nobody caught.`,
  flagConfirm: 'Flag',
  copyCommand: 'Copy command',
  notEnough: 'not enough evidence',
  rate: (r, lo, hi) => `${r}% (${lo}–${hi}%)`,
  rangeTip: 'Fault rate and its 95% range, on a 0–70% axis',
  publicScore: (b, s) => `Public score: ${b}, ${s}`,
  noPublic: '—',
  chipTip: (name, earned, total) => `${name}: ${earned} of ${total} action types have earned autonomy (T2 or T3). Open Tenure.`,
  menuBadge: tier => `${tier} earned`,
  paletteOpen: 'Tenure: Open',
  palettePassport: 'Tenure: Show passport for current model',
  paletteRevoke: 'Tenure: Revoke current model…',
  noCurrent: 'The current model has no record yet: every change asks first.'
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
const pct = x => (x * 100).toFixed(1)

async function revokeAgent(a, t) {
  await rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
  haptic('success')
  host.notify({ kind: 'success', message: t('revoked', displayName(a.model)) })
}

// ------------------------------------------------------------------------------------------------ pieces
function TierLabel(tier, t) {
  return { ask: t('tierT1'), notify: t('tierT2'), alone: t('tierT3'), cap: t('tierCap') }[tier]
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

function StatePill({ label, tip, tone }) {
  return jsx(Tip, {
    label: tip,
    children: jsx('span', {
      'aria-label': `${label}: ${tip}`,
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
    children: jsx('span', { className: 'absolute inset-y-0 left-0 rounded-full bg-primary', style: { width: `${width}%` } })
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
        style: { left: at(low), width: `calc(${at(high)} - ${at(low)})`, minWidth: 2, opacity: enough ? 0.4 : 1 }
      }),
      enough ? jsx('span', { className: 'absolute top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary', style: { left: at(rate) } }) : null
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
          jsx('span', { className: 'shrink-0 text-[0.7rem] text-muted-foreground/70', children: t('stakes', type.stakes) }),
          type.capped
            ? jsx('span', { className: 'shrink-0 text-[0.7rem] text-muted-foreground/70', children: t('alwaysAsks') })
            : jsxs('span', {
                className: 'flex shrink-0 items-center gap-2 text-[0.7rem] tabular-nums text-muted-foreground/80',
                children: [
                  jsx(Progress, { value: type.series, max: type.required, label: t('inARow', type.series, type.required) }),
                  jsx('span', { children: t('inARow', type.series, type.required) }),
                  jsx('span', { className: 'text-muted-foreground/60', children: t('sessions', type.sessions) })
                ]
              })
        ]
      }),
      !type.capped && g
        ? jsx('p', {
            className: 'mt-0.5 pl-10 text-[0.7rem] leading-relaxed text-muted-foreground/75',
            children: t('guarantee', pct(g.aoql), pct(g.worst_case)) + (g.conditional ? t('conditional') : '')
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
          jsx('p', { className: 'text-xs font-medium text-foreground', children: t('introTitle') }),
          jsx('p', { className: 'max-w-3xl text-xs leading-relaxed text-muted-foreground/80', children: t('introBody', Math.round(1 / (spot || 0.1))) })
        ]
      }),
      jsx(Button, {
        onClick: () => {
          if (storage) storage.set('introDismissed', true)
          setHidden(true)
        },
        size: 'xs',
        variant: 'ghost',
        children: t('gotIt')
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
      jsx(PanelSectionLabel, { children: t('recent') }),
      rows.length === 0
        ? jsx('p', { className: 'px-2 text-xs text-muted-foreground/70', children: t('recentNone') })
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
                        r.files > 1 ? jsx('span', { className: 'text-muted-foreground/60', children: t('moreFiles', r.files - 1) }) : null,
                        r.file ? jsx('span', { className: 'ml-2 font-mono text-[0.68rem] text-muted-foreground/55', children: r.type }) : null
                      ]
                    }),
                    r.counts_as_fault === false ? jsx(StatePill, { label: t('checkFailed'), tip: t('checkFailedTip'), tone: 'bad' }) : null,
                    jsx('span', { className: 'shrink-0 text-[0.7rem] tabular-nums text-muted-foreground/60', children: t('ago', r.age) }),
                    jsxs('span', {
                      className: 'flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover/row:opacity-100',
                      children: [
                        jsx(Tip, {
                          label: t('flagTip'),
                          children: jsx(Button, { disabled: busy !== null, onClick: () => setFlagging(r), size: 'xs', variant: 'ghost', children: t('flag') })
                        }),
                        jsx(Tip, {
                          label: t('undoTip'),
                          children: jsxs(Button, {
                            'aria-busy': busy === 'undo' + r.id || undefined,
                            disabled: busy !== null,
                            onClick: () =>
                              act('undo' + r.id, () => rest('/undo?of=' + encodeURIComponent(r.profile), { method: 'POST', body: { id: r.id } }), t('undone'), t('undoFailed')),
                            size: 'xs',
                            variant: 'outline',
                            children: [busy === 'undo' + r.id ? jsx(Codicon, { name: 'loading', size: '0.75rem', spinning: true }) : null, t('undo')]
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
                ? [jsx('div', { className: 'px-2 pt-1', children: jsx(Button, { onClick: () => setAll(!all), size: 'xs', variant: 'ghost', children: all ? t('showFewer') : t('showAll', every.length) }) }, 'more')]
                : []
            )
          }),
      jsx(ConfirmDialog, {
        busyLabel: t('revoking'),
        confirmLabel: t('flagConfirm'),
        description: flagging ? t('flagDesc', flagging.type) : null,
        destructive: true,
        onClose: () => setFlagging(null),
        onConfirm: async () => {
          const r = flagging
          await rest('/flag?of=' + encodeURIComponent(r.profile), { method: 'POST', body: { agent: r.agent, type: r.type } })
          haptic('success')
          host.notify({ kind: 'success', message: t('flagged', r.type) })
          qc.invalidateQueries({ queryKey: ['tenure'] })
        },
        open: flagging !== null,
        title: t('flagTitle')
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
          jsx(PanelSectionLabel, { children: t('passportSection') }),
          p ? jsx(CopyButton, { buttonSize: 'xs', label: t('copyPassport'), showLabel: true, text: JSON.stringify(p, null, 2) }) : null
        ]
      }),
      isLoading && !doc
        ? jsxs('p', { className: 'flex items-center gap-1.5 text-xs text-muted-foreground/70', children: [jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }), t('verifying')] })
        : jsxs('div', {
            className: cn('flex items-start gap-1.5 rounded p-2 text-[0.72rem]', ok ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'),
            role: 'status',
            children: [
              jsx(Codicon, { className: 'mt-px shrink-0', name: ok ? 'verified-filled' : 'warning', size: '0.85rem' }),
              jsx('span', {
                className: 'min-w-0 break-words',
                children: error ? t('unavailable', error.message || String(error)) : ok ? t('verified') : t('problems', ((doc && doc.verify) || []).join('; '))
              })
            ]
          }),
      p
        ? jsx(PanelMeta, {
            rows: [
              { label: t('protocol'), value: jsx('span', { className: 'font-mono', children: p.protocol }) },
              { label: t('rule'), value: jsx('span', { className: 'font-mono', children: `${p.rule.name} · ${String(p.rule.fingerprint).slice(0, 16)}` }) },
              { label: t('ledger'), value: jsx('span', { className: 'font-mono', children: t('ledgerValue', p.ledger.count, String(p.ledger.head).slice(0, 12)) }) },
              { label: t('generated'), value: new Date(p.generated_at).toLocaleString() }
            ]
          })
        : null,
      p
        ? jsxs('div', {
            className: 'space-y-1',
            children: [
              jsx('p', { className: 'text-[0.7rem] text-muted-foreground/75', children: t('verifyHint') }),
              jsxs('div', {
                className: 'flex items-start gap-1',
                children: [
                  jsx(PanelBlock, { className: 'min-w-0 flex-1', children: t('verifyCommand') }),
                  jsx(CopyButton, { appearance: 'icon', label: t('copyCommand'), text: t('verifyCommand') })
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
                  agent.provisional ? jsx(StatePill, { label: t('provisional'), tip: t('provisionalTip'), tone: 'warn' }) : null,
                  agent.trial ? jsx(StatePill, { label: t('trial'), tip: t('trialTip'), tone: 'warn' }) : null,
                  agent.unresolved_fault ? jsx(StatePill, { label: t('fault'), tip: t('faultTip'), tone: 'bad' }) : null,
                  agent.suspended ? jsx(StatePill, { label: t('suspended'), tip: t('suspendedTip'), tone: 'bad' }) : null
                ]
              }),
              jsx('div', { className: 'flex shrink-0 items-center gap-0.5', children: jsx(PanelAction, { icon: 'circle-slash', onClick: onRevoke, children: t('revoke') }) })
            ]
          }),
          jsx(PanelMeta, {
            rows: [
              { label: t('metaProfile'), value: agent.profile },
              { label: t('metaProvider'), value: agent.provider },
              { label: t('metaActions'), value: jsx(Tip, { label: t('metaActionsTip'), children: jsx('span', { tabIndex: 0, children: String(tot.actions || 0) }) }) },
              { label: t('metaChecked'), value: String(tot.checked || 0) },
              { label: t('metaAlone'), value: String(tot.alone || 0) },
              { label: t('metaFaults'), value: String(tot.faults || 0) },
              { label: t('metaPreset'), value: t('presetValue', s.preset || 'balanced', s.spot, s.pending) }
            ]
          })
        ]
      }),
      jsxs('section', {
        className: 'space-y-1.5',
        children: [jsx(PanelSectionLabel, { children: t('types') }), jsx('div', { className: 'flex flex-col', children: (agent.types || []).map(ty => jsx(TypeRow, { type: ty, t }, ty.type)) })]
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
        searchLabel: t('search'),
        searchPlaceholder: t('search'),
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
                    menuItems: [{ icon: 'circle-slash', label: t('revoke'), onSelect: () => setPending(a), tone: 'danger' }],
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
          visible.length === 0 ? jsx('p', { className: 'px-2 py-4 text-center text-xs text-muted-foreground', children: t('noMatch') }, 'nomatch') : null
        ]
      }),
      agent ? jsx(AgentDetail, { agent, t, onRevoke: () => setPending(agent) }) : jsx(PanelEmpty, { description: q ? t('noMatch') : t('pickAgent'), icon: q ? 'search' : 'shield' }),
      jsx(ConfirmDialog, {
        busyLabel: t('revoking'),
        confirmLabel: t('revokeConfirm'),
        description: pending
          ? jsxs('span', { children: [t('revokeDescBefore'), jsx('span', { className: 'font-medium text-foreground', children: displayName(pending.model) }), t('revokeDescAfter')] })
          : null,
        destructive: true,
        onClose: () => setPending(null),
        onConfirm: async () => {
          await revokeAgent(pending, t)
          qc.invalidateQueries({ queryKey: ['tenure'] })
        },
        open: pending !== null,
        title: t('revokeTitle')
      })
    ]
  })
}

function BenchmarkView({ t }) {
  const profile = useValue(host.state.profile)
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['tenure', profile, 'models'], queryFn: () => rest('/models') })
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  if (isLoading) return jsx(PanelEmpty, { description: t('loading'), icon: 'loading~spin' })
  if (error)
    return jsx(ErrorState, {
      description: error.message || String(error),
      title: t('backendTitle'),
      children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('retry') })
    })
  const rows = (data && data.rows) || []
  if (!rows.length) return jsx(PanelEmpty, { description: t('emptyDesc'), icon: 'graph', title: t('emptyTitle') })
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
        searchLabel: t('searchTypes'),
        searchPlaceholder: t('searchTypes'),
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
          visibleTypes.length === 0 ? jsx('p', { className: 'px-2 py-4 text-center text-xs text-muted-foreground', children: t('noMatch') }, 'nomatch') : null
        ]
      }),
      !type
        ? jsx(PanelEmpty, { description: t('noMatch'), icon: 'search' })
        : jsxs(PanelDetail, {
            className: 'max-w-3xl',
            children: [
              jsxs('header', {
                className: 'space-y-2',
                children: [
                  jsx('h3', { className: 'font-mono text-[0.95rem] font-semibold tracking-tight text-foreground', children: type }),
                  jsx('p', { className: 'text-xs leading-relaxed text-muted-foreground/80', children: t('benchmarkNote') })
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
                      jsx(PanelSectionLabel, { className: 'w-24 text-right', children: t('colFaults') }),
                      jsx(PanelSectionLabel, { className: 'w-24', children: t('colRange') }),
                      jsx(PanelSectionLabel, { className: 'w-28', children: t('colRate') }),
                      jsx(PanelSectionLabel, { className: 'w-12 text-right', children: t('colPublic') })
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
                            jsx('span', { className: 'w-24 whitespace-nowrap text-right font-mono text-[0.72rem] tabular-nums', children: t('faults', r.faults, r.successes + r.faults) }),
                            jsx(Tip, { label: t('rangeTip'), children: jsx('span', { className: 'inline-flex', tabIndex: 0, children: jsx(Range, { rate: r.rate, low: r.low, high: r.high, enough: r.enough }) }) }),
                            jsx('span', { className: 'w-28 text-[0.7rem] tabular-nums text-muted-foreground/80', children: r.enough ? t('rate', pct(r.rate), pct(r.low), pct(r.high)) : t('notEnough') }),
                            jsx(Tip, {
                              label: pub ? t('publicScore', pub.benchmark, pub.source) : '',
                              children: jsx('span', {
                                className: 'w-12 text-right text-[0.7rem] tabular-nums text-muted-foreground/80',
                                children: r.public && r.public.new != null ? `${Number(r.public.new).toFixed(1)}%` : t('noPublic')
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
              pub ? jsx('p', { className: 'text-[0.7rem] text-muted-foreground/70', children: `${t('publicScore', pub.benchmark, pub.source)}, ${pub.accessed}.` }) : null
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
  if (isLoading && !data) body = jsx(PanelEmpty, { description: t('loading'), icon: 'loading~spin' })
  else if (error && !data)
    body = jsx(ErrorState, {
      description: t('backendDesc', error.message || String(error)),
      title: t('backendTitle'),
      children: jsx(Button, { onClick: () => refetch(), size: 'sm', children: t('retry') })
    })
  else if (!agents.length) body = jsx(PanelEmpty, { description: t('emptyDesc'), icon: 'shield', title: t('emptyTitle') })
  else if (view === 'benchmark') body = jsx(BenchmarkView, { t })
  else body = jsx(AgentsView, { data, t })
  return jsxs('div', {
    className: 'relative flex h-full flex-col overflow-hidden bg-(--ui-surface-background)',
    children: [
      jsxs('header', {
        className: 'flex shrink-0 flex-wrap items-center gap-2 px-4 py-2',
        children: [
          jsx('h1', { className: 'text-sm font-semibold text-foreground', children: t('title') }),
          agents.length
            ? jsx('span', { className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 py-px text-[0.625rem] tabular-nums text-(--ui-text-tertiary)', children: String(agents.length) })
            : null,
          agents.length
            ? jsx(WorkspacePageHeaderControl, {
                id: 'tenure:view',
                children: jsx('div', {
                  className: 'ml-auto',
                  children: jsx(SegmentedControl, {
                    onChange: setView,
                    options: [
                      { id: 'agents', label: t('viewAgents') },
                      { id: 'benchmark', label: t('viewBenchmark') }
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
  const tip = t('chipTip', displayName(a.model), n, total)
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
    ctx.i18n.register({ en: EN })
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
        message: tr('actedToast', payload.type, n, name),
        detail: tr('actedDetail'),
        action: {
          label: tr('undo'),
          onClick: async () => {
            try {
              await ctx.rest('/undo' + (payload.profile ? '?of=' + encodeURIComponent(payload.profile) : ''), { method: 'POST', body: { id: payload.undo_id } })
              host.notify({ kind: 'success', message: tr('undone') })
              bus.dispatchEvent(new Event('changed'))
            } catch (e) {
              host.notifyError(e, tr('undoFailed'))
            }
          }
        }
      })
    })

    const contributions = () => [
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(TenurePage, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, order: 60, data: { codicon: 'shield', label: tr('nav'), path: ROUTE } },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 85, render: () => jsx(Chip, {}) },
      { id: 'open', area: PALETTE_AREA, data: { id: 'tenure.open', label: tr('paletteOpen'), keywords: ['tenure', 'autonomy', 'tier', 'trust'], run: () => host.navigate(ROUTE) } },
      {
        id: 'passport',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.passport',
          label: tr('palettePassport'),
          keywords: ['tenure', 'passport', 'verify'],
          run: () => {
            const a = current()
            if (!a) return host.notify({ kind: 'info', message: tr('noCurrent') })
            focus(a.key, false)
          }
        }
      },
      {
        id: 'revoke',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.revoke',
          label: tr('paletteRevoke'),
          keywords: ['tenure', 'revoke', 'trust'],
          run: () => {
            const a = current()
            if (!a) return host.notify({ kind: 'info', message: tr('noCurrent') })
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
            return tier === 'ask' || tier === 'cap' ? null : { badge: tr('menuBadge', TIER_SHORT[tier]) }
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
