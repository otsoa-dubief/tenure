/**
 * tenure, desktop half: a Tenure page (agents and their earned tiers, your own benchmark, the signed passport), a
 * status-bar chip for the model in use, and ⌘K commands.
 *
 * Built only from the app's own components (the Panel family the Scheduled jobs page uses, Button, ConfirmDialog,
 * SegmentedControl, CopyButton, Tip, Codicon) and its theme variables. Every number comes from the agent half's
 * backend (`dashboard/plugin_api.py`, reached through `ctx.rest`), the same one the web dashboard tab reads.
 * Plain ESM, loaded uncompiled: UI is jsx() calls; only @hermes/plugin-sdk, react and react/jsx-runtime are imported.
 */

import {
  Button,
  Codicon,
  ConfirmDialog,
  CopyButton,
  cn,
  haptic,
  host,
  PALETTE_AREA,
  PanelAction,
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
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'tenure'
const ROUTE = '/tenure'
const POLL_MS = 15000

const EN = {
  nav: 'Tenure',
  title: 'Tenure',
  subtitle: 'Autonomy earned per action type, on verified evidence',
  agentsCount: n => `${n} ${n === 1 ? 'agent' : 'agents'}`,
  viewAgents: 'Agents',
  viewModels: 'Your benchmark',
  refresh: 'Refresh',
  search: 'Search agents',
  searchTypes: 'Search action types',
  loading: 'Reading the evidence…',
  backendTitle: 'The agent half is not answering',
  backendDesc: err => `Enable tenure in this profile (Capabilities → Plugins, Agent column), then refresh. ${err}`,
  emptyTitle: 'No agent has acted yet',
  emptyDesc: 'Work as usual. Every change asks first, and each action type earns its tier from the approvals you give.',
  pickAgent: 'Pick an agent to see what it has earned.',
  provisional: 'provisional',
  provisionalTip: 'Carried over from a previous model, halved; confirmed by its own successes.',
  trial: 'on trial',
  trialTip: 'A medium or high fault opened a trial of 3 verified successes.',
  fault: 'fault on record',
  suspended: 'suspended',
  suspendedTip: 'A session read external content: it asks for everything until it ends.',
  passport: 'Passport',
  revoke: 'Revoke',
  revokeTitle: agent => `Revoke ${agent}?`,
  revokeDesc: 'Every action type of this agent will ask first again. Its record stays in the ledger.',
  revoking: 'Revoking…',
  revoked: agent => `${agent} asks first again on every action type.`,
  revokeFailed: 'Could not revoke',
  metaProfile: 'Profile',
  metaProvider: 'Provider',
  metaActions: 'Actions',
  metaChecked: 'Checked',
  metaAlone: 'Ran alone',
  metaFaults: 'Faults',
  metaPreset: 'Preset',
  covered: n => `${n} covered`,
  byYou: n => `${n} by you`,
  without: n => `${n} without asking`,
  caught: n => `${n} caught`,
  presetValue: (p, spot) => `${p} · 1 in ${Math.round(1 / (spot || 0.1))} spot-checked`,
  types: 'Action types',
  stakes: s => `${s} stakes`,
  inARow: (s, r) => `${s} / ${r} in a row`,
  sessions: n => `${n} ${n === 1 ? 'session' : 'sessions'}`,
  alwaysAsks: 'always asks',
  guarantee: (a, w) => `Guarantee: at most ${a}% of this type's actions run with an error nobody approved (worst case ${w}%).`,
  conditional: ' Conditional on the carried-over evidence.',
  tierAsk: 'Asks first',
  tierNotify: 'Acts, then notifies with an undo',
  tierAlone: 'Acts alone, spot-checked',
  tierCap: 'Capped: always asks',
  passportSection: 'Signed passport',
  verifying: 'Verifying…',
  verified: 'Verified: signature valid, hash chain intact, replaying the ledger gives the same tiers',
  problems: p => `Does not verify: ${p}`,
  unavailable: e => `Not available: ${e}`,
  protocol: 'Protocol',
  rule: 'Rule',
  ledger: 'Ledger',
  generated: 'Generated',
  ledgerValue: (c, h) => `${c} events · head ${h}`,
  copyPassport: 'Copy passport',
  verifyHint: 'Anyone can check it: hermes tenure verify passport.json ledger.jsonl',
  modelsNote: "Each model's verified record on your work, per action type, with a 95% interval on its fault rate. Ranked by the interval's upper bound. The public measure is information: capability on their tasks, not reliability on yours.",
  faultsChecks: (f, n) => `${f} / ${n}`,
  notEnough: 'not enough evidence',
  intervalTip: '95% interval of the fault rate, on a 0 to 70% axis',
  rate: (r, lo, hi) => `${r}% · 95% ${lo}–${hi}%`,
  publicMeasure: 'Public measure',
  noPublic: 'no public measure',
  chipTip: (agent, a, n, k) => `${agent}: ${a} alone · ${n} notify · ${k} ask. Open Tenure.`,
  paletteOpen: 'Tenure: open',
  palettePassport: 'Tenure: passport of the current model',
  paletteRevoke: 'Tenure: revoke the current model',
  noCurrent: 'The current model has no record yet: every change asks first.',
  legend: 'T1 asks first · T2 acts, then notifies with an undo · T3 acts alone, spot-checked · CAP always asks'
}

// ------------------------------------------------------------------------------------------------ shared data
const store = { agents: null, error: null, loading: true, listeners: new Set() }

function publish(patch) {
  Object.assign(store, patch)
  for (const fn of store.listeners) fn()
}

let rest = null

async function refresh() {
  if (!rest) return
  try {
    publish({ agents: await rest('/agents'), error: null, loading: false })
  } catch (e) {
    publish({ error: (e && e.message) || 'no answer', loading: false })
  }
}

function useStore() {
  const [, tick] = useState(0)
  useEffect(() => {
    const fn = () => tick(n => n + 1)
    store.listeners.add(fn)
    return () => store.listeners.delete(fn)
  }, [])
  return store
}

function allAgents(data) {
  const out = []
  for (const p of (data && data.profiles) || []) {
    for (const a of p.agents || []) out.push({ ...a, profile: p.profile, settings: p.settings, key: `${p.profile}|${a.agent}` })
  }
  return out
}

function agentForModel(data, model) {
  if (!model) return null
  const tail = String(model).split('/').pop().toLowerCase()
  const list = allAgents(data).filter(a => String(a.model || '').split('/').pop().toLowerCase() === tail)
  return list.find(a => a.profile === (data && data.current)) || list[0] || null
}

function tierKey(t) {
  if (t.capped) return 'cap'
  return t.effective_tier || t.tier || 'ask'
}

const TIER_SHORT = { ask: 'T1', notify: 'T2', alone: 'T3', cap: 'CAP' }
const TIER_TONE = { ask: 'muted', notify: 'warn', alone: 'good', cap: 'muted' }
const TIER_RANK = { cap: 0, ask: 1, notify: 2, alone: 3 }
const TIER_DOT = { ask: 'bg-muted-foreground/40', notify: 'bg-amber-500', alone: 'bg-primary', cap: 'bg-muted-foreground/40' }

function bestTier(agent) {
  let best = 'ask'
  for (const t of agent.types || []) if (TIER_RANK[tierKey(t)] > TIER_RANK[best]) best = tierKey(t)
  return best
}

function counts(agent) {
  const n = { alone: 0, notify: 0, ask: 0 }
  for (const t of agent.types || []) {
    const k = tierKey(t)
    if (k in n) n[k]++
  }
  return n
}

const pct = x => (x * 100).toFixed(1)
const shortModel = m => String(m || '').split('/').pop()

// ------------------------------------------------------------------------------------------------ pieces
function TierPill({ tier, t }) {
  const label = { ask: t('tierAsk'), notify: t('tierNotify'), alone: t('tierAlone'), cap: t('tierCap') }[tier]
  return jsx(Tip, { label, children: jsx('span', { children: jsx(PanelPill, { tone: TIER_TONE[tier], children: TIER_SHORT[tier] }) }) })
}

function Progress({ value, max }) {
  const width = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0
  return jsx('span', {
    'aria-hidden': true,
    className: 'relative inline-block h-1 overflow-hidden rounded-full bg-foreground/10',
    style: { width: 72 },
    children: jsx('span', { className: 'absolute inset-y-0 left-0 rounded-full bg-primary', style: { width: `${width}%` } })
  })
}

function Interval({ low, high }) {
  const scale = 0.7
  const l = Math.min(100, (100 * low) / scale)
  const h = Math.min(100, (100 * high) / scale)
  return jsx('span', {
    'aria-hidden': true,
    className: 'relative inline-block h-1 rounded-full bg-foreground/10',
    style: { width: 96 },
    children: jsx('span', { className: 'absolute inset-y-0 rounded-full bg-primary', style: { left: `${l}%`, width: `${Math.max(2, h - l)}%` } })
  })
}

function TypeRow({ type, t }) {
  const tier = tierKey(type)
  const g = type.guarantee
  return jsxs('div', {
    className: 'flex items-center gap-3 rounded-md px-2 py-1.5 text-[0.78rem] hover:bg-(--ui-row-hover-background)',
    children: [
      jsx(TierPill, { tier, t }),
      jsx('span', { className: 'min-w-0 flex-1 truncate font-mono text-[0.75rem] text-foreground/85', children: type.type }),
      jsx('span', { className: 'shrink-0 text-[0.68rem] text-muted-foreground/60', children: t('stakes', type.stakes) }),
      type.capped
        ? jsx('span', { className: 'shrink-0 text-[0.68rem] text-muted-foreground/60', children: t('alwaysAsks') })
        : jsx(Tip, {
            label: g ? t('guarantee', pct(g.aoql), pct(g.worst_case)) + (g.conditional ? t('conditional') : '') : t('inARow', type.series, type.required),
            children: jsxs('span', {
              className: 'flex shrink-0 items-center gap-2 text-[0.68rem] tabular-nums text-muted-foreground/70',
              children: [
                jsx(Progress, { value: type.series, max: type.required }),
                jsx('span', { children: t('inARow', type.series, type.required) }),
                jsx('span', { className: 'text-muted-foreground/45', children: t('sessions', type.sessions) })
              ]
            })
          })
    ]
  })
}

function PassportSection({ agent, ctx, t }) {
  const [doc, setDoc] = useState(null)
  useEffect(() => {
    let live = true
    setDoc(null)
    ctx
      .rest(`/passport?agent=${encodeURIComponent(agent.agent)}&of=${encodeURIComponent(agent.profile)}`)
      .then(d => live && setDoc(d), e => live && setDoc({ error: (e && e.message) || 'unreadable' }))
    return () => {
      live = false
    }
  }, [agent.key, store.agents])
  const ok = doc && !doc.error && Array.isArray(doc.verify) && doc.verify.length === 0
  const p = doc && doc.passport
  return jsxs('section', {
    className: 'space-y-2',
    id: 'tenure-passport',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between gap-2',
        children: [
          jsx(PanelSectionLabel, { children: t('passportSection') }),
          p ? jsx(CopyButton, { appearance: 'button', buttonSize: 'xs', label: t('copyPassport'), showLabel: true, text: JSON.stringify(p, null, 2) }) : null
        ]
      }),
      doc === null
        ? jsxs('p', { className: 'flex items-center gap-1.5 text-xs text-muted-foreground/70', children: [jsx(Codicon, { name: 'loading', size: '0.8rem', spinning: true }), t('verifying')] })
        : jsxs('div', {
            className: cn('flex items-start gap-1.5 rounded p-2 text-[0.72rem]', ok ? 'bg-primary/10 text-primary' : 'bg-destructive/10 text-destructive'),
            children: [
              jsx(Codicon, { name: ok ? 'verified-filled' : 'warning', size: '0.85rem', className: 'mt-px shrink-0' }),
              jsx('span', { className: 'min-w-0 break-words', children: doc.error ? t('unavailable', doc.error) : ok ? t('verified') : t('problems', doc.verify.join('; ')) })
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
      p ? jsx('p', { className: 'font-mono text-[0.65rem] text-muted-foreground/55', children: t('verifyHint') }) : null
    ]
  })
}

function AgentDetail({ agent, ctx, t, onRevoke }) {
  const tot = agent.totals || {}
  const s = agent.settings || {}
  return jsxs(PanelDetail, {
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
                  jsx('h3', { className: 'text-[0.95rem] font-semibold tracking-tight text-foreground', children: agent.model }),
                  jsx(TierPill, { tier: bestTier(agent), t }),
                  agent.provisional ? jsx(Tip, { label: t('provisionalTip'), children: jsx('span', { children: jsx(PanelPill, { tone: 'warn', children: t('provisional') }) }) }) : null,
                  agent.trial ? jsx(Tip, { label: t('trialTip'), children: jsx('span', { children: jsx(PanelPill, { tone: 'warn', children: t('trial') }) }) }) : null,
                  agent.unresolved_fault ? jsx(PanelPill, { tone: 'bad', children: agent.unresolved_fault_label || t('fault') }) : null,
                  agent.suspended ? jsx(Tip, { label: t('suspendedTip'), children: jsx('span', { children: jsx(PanelPill, { tone: 'bad', children: t('suspended') }) }) }) : null
                ]
              }),
              jsxs('div', {
                className: 'flex shrink-0 items-center gap-0.5',
                children: [
                  jsx(PanelAction, {
                    icon: 'verified',
                    onClick: () => document.getElementById('tenure-passport')?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
                    children: t('passport')
                  }),
                  jsx(PanelAction, { icon: 'circle-slash', onClick: onRevoke, children: t('revoke') })
                ]
              })
            ]
          }),
          jsx(PanelMeta, {
            rows: [
              { label: t('metaProfile'), value: agent.profile },
              { label: t('metaProvider'), value: agent.provider },
              { label: t('metaActions'), value: t('covered', tot.actions || 0) },
              { label: t('metaChecked'), value: t('byYou', tot.checked || 0) },
              { label: t('metaAlone'), value: t('without', tot.alone || 0) },
              { label: t('metaFaults'), value: t('caught', tot.faults || 0) },
              { label: t('metaPreset'), value: t('presetValue', s.preset || 'balanced', s.spot) }
            ]
          })
        ]
      }),
      jsxs('section', {
        className: 'space-y-1.5',
        children: [
          jsx(PanelSectionLabel, { children: t('types') }),
          jsx('div', { className: 'flex flex-col', children: (agent.types || []).map(ty => jsx(TypeRow, { type: ty, t }, ty.type)) })
        ]
      }),
      jsx(PassportSection, { agent, ctx, t }),
      jsx('p', { className: 'text-[0.65rem] text-muted-foreground/45', children: t('legend') })
    ]
  })
}

function AgentsView({ data, ctx, t, initial }) {
  const agents = allAgents(data)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(initial || (agents[0] && agents[0].key) || null)
  const [pending, setPending] = useState(null)
  const visible = agents.filter(a => !query.trim() || a.agent.toLowerCase().includes(query.trim().toLowerCase()))
  const agent = agents.find(a => a.key === selected) || visible[0] || null
  const profiles = [...new Set(visible.map(a => a.profile))]
  return jsxs(PanelBody, {
    className: 'px-4 pb-4',
    children: [
      jsx(PanelList, {
        onSearchChange: setQuery,
        searchLabel: t('search'),
        searchPlaceholder: t('search'),
        searchValue: query,
        children: profiles.flatMap(profile => [
          profiles.length > 1 || profile !== data.current
            ? jsx(PanelSectionLabel, { className: 'mt-2 px-2', children: profile }, 'label-' + profile)
            : null,
          ...visible
            .filter(a => a.profile === profile)
            .map(a => {
              const n = counts(a)
              return jsx(
                PanelListRow,
                {
                  active: !!agent && agent.key === a.key,
                  dotClassName: TIER_DOT[bestTier(a)],
                  meta: TIER_SHORT[bestTier(a)],
                  menuItems: [
                    { icon: 'verified', label: t('passport'), onSelect: () => setSelected(a.key) },
                    { icon: 'circle-slash', label: t('revoke'), onSelect: () => setPending(a), tone: 'danger' }
                  ],
                  menuLabel: a.agent,
                  onSelect: () => setSelected(a.key),
                  rowKey: a.key,
                  title: shortModel(a.model)
                },
                a.key
              )
            })
        ])
      }),
      agent
        ? jsx(AgentDetail, { agent, ctx, t, onRevoke: () => setPending(agent) })
        : jsx(PanelEmpty, { description: t('pickAgent'), icon: 'shield' }),
      jsx(ConfirmDialog, {
        busyLabel: t('revoking'),
        confirmLabel: t('revoke'),
        description: t('revokeDesc'),
        destructive: true,
        onClose: () => setPending(null),
        onConfirm: async () => {
          const a = pending
          await ctx.rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
          haptic('success')
          host.notify({ kind: 'success', message: t('revoked', a.agent) })
          refresh()
        },
        open: pending !== null,
        title: pending ? t('revokeTitle', pending.model) : ''
      })
    ]
  })
}

function ModelsView({ ctx, t }) {
  const [rows, setRows] = useState(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  useEffect(() => {
    let live = true
    ctx.rest('/models').then(d => live && setRows(d.rows || []), () => live && setRows([]))
    return () => {
      live = false
    }
  }, [store.agents])
  const types = useMemo(() => [...new Set((rows || []).map(r => r.type))], [rows])
  if (rows === null) return jsx(PanelEmpty, { description: t('loading'), icon: 'loading' })
  if (!rows.length) return jsx(PanelEmpty, { description: t('emptyDesc'), icon: 'graph', title: t('emptyTitle') })
  const visibleTypes = types.filter(x => !query.trim() || x.includes(query.trim()))
  const type = selected && types.includes(selected) ? selected : visibleTypes[0]
  const ranked = rows.filter(r => r.type === type)
  const withPublic = ranked.find(r => r.public)
  const pub = withPublic ? withPublic.public : null
  return jsxs(PanelBody, {
    className: 'px-4 pb-4',
    children: [
      jsx(PanelList, {
        onSearchChange: setQuery,
        searchLabel: t('searchTypes'),
        searchPlaceholder: t('searchTypes'),
        searchValue: query,
        children: visibleTypes.map(x =>
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
        )
      }),
      jsxs(PanelDetail, {
        children: [
          jsxs('header', {
            className: 'space-y-2',
            children: [
              jsx('h3', { className: 'font-mono text-[0.95rem] font-semibold tracking-tight text-foreground', children: type }),
              jsx('p', { className: 'max-w-2xl text-xs leading-relaxed text-muted-foreground/70', children: t('modelsNote') })
            ]
          }),
          jsx('div', {
            className: 'flex flex-col',
            children: ranked.map((r, i) =>
              jsxs(
                'div',
                {
                  className: 'grid items-center gap-3 rounded-md px-2 py-1.5 text-[0.78rem] hover:bg-(--ui-row-hover-background)',
                  style: { gridTemplateColumns: '1.25rem minmax(0,1fr) 4.5rem 6.5rem 9rem' },
                  children: [
                    jsx('span', { className: 'tabular-nums text-muted-foreground/50', children: String(i + 1) }),
                    jsxs('span', {
                      className: 'min-w-0',
                      children: [
                        jsx('span', { className: 'block truncate text-foreground/85', children: r.model }),
                        jsx('span', { className: 'block truncate text-[0.65rem] text-muted-foreground/50', children: `${r.provider} · ${r.profile}` })
                      ]
                    }),
                    jsx('span', { className: 'text-right font-mono text-[0.72rem] tabular-nums', children: t('faultsChecks', r.faults, r.successes + r.faults) }),
                    jsx(Tip, { label: t('intervalTip'), children: jsx('span', { className: 'inline-flex', children: jsx(Interval, { low: r.low, high: r.high }) }) }),
                    jsx('span', {
                      className: 'text-[0.68rem] tabular-nums text-muted-foreground/70',
                      children: r.enough ? t('rate', pct(r.rate), pct(r.low), pct(r.high)) : t('notEnough')
                    })
                  ]
                },
                r.agent + r.profile
              )
            )
          }),
          pub
            ? jsxs('section', {
                className: 'space-y-1.5',
                children: [
                  jsx(PanelSectionLabel, { children: `${t('publicMeasure')} · ${pub.benchmark}` }),
                  jsx('div', {
                    className: 'flex flex-col',
                    children: ranked.map(r =>
                      jsxs(
                        'div',
                        {
                          className: 'flex items-center justify-between gap-3 px-2 py-1 text-[0.72rem]',
                          children: [
                            jsx('span', { className: 'min-w-0 truncate text-foreground/80', children: r.model }),
                            r.public && r.public.new != null
                              ? jsx('span', { className: 'shrink-0 tabular-nums text-foreground/85', children: `${r.public.new}%` })
                              : jsx('span', { className: 'shrink-0 text-muted-foreground/55', children: t('noPublic') })
                          ]
                        },
                        'pub' + r.agent + r.profile
                      )
                    )
                  }),
                  jsx('p', { className: 'text-[0.65rem] text-muted-foreground/45', children: `${pub.source}, accessed ${pub.accessed}` })
                ]
              })
            : null
        ]
      })
    ]
  })
}

let pendingOpen = null

function TenurePage({ ctx }) {
  const t = usePluginI18n(ID)
  const s = useStore()
  const [view, setView] = useState('agents')
  const [initial] = useState(pendingOpen)
  useEffect(() => {
    pendingOpen = null
    refresh()
  }, [])
  const agents = allAgents(s.agents)
  let body
  if (s.loading && !s.agents) body = jsx(PanelEmpty, { description: t('loading'), icon: 'loading' })
  else if (s.error && !s.agents)
    body = jsx(PanelEmpty, {
      action: jsx(Button, { onClick: () => refresh(), size: 'sm', children: t('refresh') }),
      description: t('backendDesc', s.error),
      icon: 'plug',
      title: t('backendTitle')
    })
  else if (!agents.length) body = jsx(PanelEmpty, { description: t('emptyDesc'), icon: 'shield', title: t('emptyTitle') })
  else if (view === 'models') body = jsx(ModelsView, { ctx, t })
  else body = jsx(AgentsView, { data: s.agents, ctx, t, initial })
  return jsxs('div', {
    className: 'relative flex h-full flex-col overflow-hidden bg-(--ui-surface-background)',
    children: [
      jsxs('header', {
        className: 'flex shrink-0 flex-wrap items-center gap-2 px-4 py-2',
        children: [
          jsx('h1', { className: 'text-sm font-semibold text-foreground', children: t('title') }),
          agents.length
            ? jsx('span', {
                className: 'rounded-full bg-(--ui-bg-quaternary) px-1.5 py-px text-[0.625rem] tabular-nums text-(--ui-text-tertiary)',
                children: t('agentsCount', agents.length)
              })
            : null,
          jsx('span', { className: 'min-w-0 truncate text-xs text-muted-foreground/70', children: t('subtitle') }),
          jsxs('div', {
            className: 'ml-auto flex items-center gap-1',
            children: [
              agents.length
                ? jsx(SegmentedControl, {
                    onChange: setView,
                    options: [
                      { id: 'agents', label: t('viewAgents') },
                      { id: 'models', label: t('viewModels') }
                    ],
                    sizing: 'content',
                    value: view
                  })
                : null,
              jsx(Tip, {
                label: t('refresh'),
                children: jsx(Button, {
                  'aria-label': t('refresh'),
                  onClick: () => refresh(),
                  size: 'icon-xs',
                  variant: 'ghost',
                  children: jsx(Codicon, { name: 'refresh', size: '0.85rem' })
                })
              })
            ]
          })
        ]
      }),
      body
    ]
  })
}

// ------------------------------------------------------------------------------------------------ status-bar chip
function Chip() {
  const t = usePluginI18n(ID)
  const s = useStore()
  const model = useValue(host.state.model)
  const a = agentForModel(s.agents, model)
  if (!a) return null
  const tier = bestTier(a)
  const n = counts(a)
  return jsx(Tip, {
    label: t('chipTip', a.model, n.alone, n.notify, n.ask),
    children: jsxs('button', {
      type: 'button',
      'aria-label': t('chipTip', a.model, n.alone, n.notify, n.ask),
      className: cn(
        'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] tabular-nums transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      onClick: () => {
        haptic('tap')
        host.navigate(ROUTE)
      },
      children: [
        jsx(Codicon, { name: 'shield', size: '0.75rem', className: tier === 'alone' ? 'text-primary' : tier === 'notify' ? 'text-amber-500' : undefined }),
        TIER_SHORT[tier]
      ]
    })
  })
}

// ------------------------------------------------------------------------------------------------ registration
export default {
  id: ID,
  name: 'Tenure',
  register(ctx) {
    ctx.i18n.register({ en: EN })
    rest = ctx.rest
    refresh()
    ctx.setInterval(refresh, POLL_MS)
    ctx.onDispose(() => {
      rest = null
      store.listeners.clear()
    })
    const tr = (key, ...args) => ctx.i18n.t(key, ...args)
    const current = () => agentForModel(store.agents, host.state.model.get())

    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(TenurePage, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, order: 60, data: { codicon: 'shield', label: tr('nav'), path: ROUTE } },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 85, render: () => jsx(Chip, {}) },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: { id: 'tenure.open', label: tr('paletteOpen'), keywords: ['tenure', 'autonomy', 'tier', 'trust'], run: () => host.navigate(ROUTE) }
      },
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
            pendingOpen = a.key
            host.navigate(ROUTE)
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
            host.notify({
              kind: 'warning',
              message: tr('revokeTitle', a.model) + ' ' + tr('revokeDesc'),
              action: {
                label: tr('revoke'),
                onClick: async () => {
                  try {
                    await ctx.rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
                    host.notify({ kind: 'success', message: tr('revoked', a.agent) })
                    refresh()
                  } catch (e) {
                    host.notifyError(e, tr('revokeFailed'))
                  }
                }
              }
            })
          }
        }
      }
    ])
  }
}
