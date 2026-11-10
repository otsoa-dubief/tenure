/**
 * tenure, desktop half: a Tenure page in the sidebar, a status-bar chip for the model in use, and ⌘K commands.
 *
 * It reads the same backend as the web dashboard tab (`dashboard/plugin_api.py`, reached through `ctx.rest`), so every
 * number on screen comes from the plugin's own database. Plain ESM, loaded uncompiled: UI is jsx() calls.
 * Only @hermes/plugin-sdk, react and react/jsx-runtime are imported, as the catalog requires.
 */

import { haptic, host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, Tip, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'tenure'
const ROUTE = '/tenure'
const POLL_MS = 15000

const TIER = {
  ask: { short: 'T1', label: 'asks first' },
  notify: { short: 'T2', label: 'acts, then notifies with an undo' },
  alone: { short: 'T3', label: 'acts alone, 1 in 10 spot-checked' }
}

// ------------------------------------------------------------------------------------------------ shared data
// One poll for every surface (page, chip, commands); components subscribe to it.
const store = { agents: null, error: null, at: 0, listeners: new Set() }

function publish(patch) {
  Object.assign(store, patch)
  for (const fn of store.listeners) fn()
}

let restRef = null

async function refresh() {
  if (!restRef) return
  try {
    publish({ agents: await restRef('/agents'), error: null, at: Date.now() })
  } catch (e) {
    publish({ error: e && e.message ? e.message : 'tenure backend not reachable', at: Date.now() })
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
  for (const p of (data && data.profiles) || []) for (const a of p.agents || []) out.push({ ...a, profile: p.profile })
  return out
}

// The model string the app shows may or may not carry the vendor prefix: match on the part after the last slash.
function agentForModel(data, model) {
  if (!model) return null
  const tail = String(model).split('/').pop().toLowerCase()
  const list = allAgents(data).filter(a => String(a.model || '').split('/').pop().toLowerCase() === tail)
  return list.find(a => a.profile === (data && data.current)) || list[0] || null
}

function tierOf(t) {
  if (t.capped) return { short: 'CAP', label: 'capped: always asks' }
  return TIER[t.effective_tier || t.tier] || TIER.ask
}

// ------------------------------------------------------------------------------------------------ small UI pieces
const muted = 'text-(--ui-text-tertiary)'
const card = 'rounded-md border border-(--ui-border) p-3'

function Badge({ text, strong }) {
  return jsx('span', {
    className: `rounded border px-1.5 py-0.5 font-mono text-[0.6875rem] ${strong ? '' : 'border-(--ui-border) ' + muted}`,
    style: { display: 'inline-flex', justifyContent: 'center', minWidth: 32, ...(strong ? { borderColor: '#22c55e', color: '#22c55e' } : {}) },
    children: text
  })
}

function Stat({ value, label, sub }) {
  return jsxs('div', {
    style: { display: 'flex', flexDirection: 'column', minWidth: 120 },
    children: [
      jsx('span', { className: 'text-2xl font-semibold', children: String(value) }),
      jsx('span', { className: 'text-sm', children: label }),
      jsx('span', { className: `text-xs ${muted}`, children: sub })
    ]
  })
}

function TabButton({ active, onClick, children }) {
  return jsx('button', {
    type: 'button',
    onClick,
    className: `border-b-2 px-2 py-1 text-sm ${active ? 'border-current font-medium' : 'border-transparent ' + muted}`,
    children
  })
}

// ------------------------------------------------------------------------------------------------ the page
function MapView({ data, ctx }) {
  const [confirm, setConfirm] = useState(null)
  const agents = allAgents(data)
  if (!agents.length) return jsx('p', { className: muted, children: 'No agent has acted yet. Work as usual: every change asks first.' })
  return jsx('div', {
    className: 'flex flex-col gap-3',
    children: agents.map(a =>
      jsxs('div', {
        key: a.profile + a.agent,
        className: card,
        children: [
          jsxs('div', {
            className: 'flex items-baseline justify-between gap-2',
            children: [
              jsxs('div', {
                children: [
                  jsx('div', { className: 'font-medium', children: a.agent }),
                  jsx('div', {
                    className: `text-xs ${muted}`,
                    children: `${a.profile} · ${a.totals.actions} actions · ${a.totals.checked} checked by you · ${a.totals.alone} alone · ${a.totals.faults} faults${a.provisional ? ' · provisional' : ''}`
                  })
                ]
              }),
              jsx('button', {
                type: 'button',
                className: `rounded border px-2 py-0.5 text-xs ${confirm === a.agent ? 'border-red-500 text-red-500' : 'border-(--ui-border) ' + muted}`,
                onClick: async () => {
                  if (confirm !== a.agent) return setConfirm(a.agent)
                  setConfirm(null)
                  haptic('tap')
                  try {
                    await ctx.rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
                    host.notify({ kind: 'info', message: `Tenure revoked for ${a.agent}: every type asks again.` })
                    refresh()
                  } catch (e) {
                    host.notifyError(e, 'Could not revoke')
                  }
                },
                children: confirm === a.agent ? 'Confirm: revoke all' : 'Revoke'
              })
            ]
          }),
          jsx('div', {
            className: 'mt-2 flex flex-col gap-1',
            children: (a.types || []).map(t => {
              const tier = tierOf(t)
              return jsxs('div', {
                key: t.type,
                className: 'flex items-center gap-2 text-sm',
                children: [
                  jsx(Tip, { label: tier.label, children: jsx('span', { children: jsx(Badge, { text: tier.short, strong: tier.short === 'T3' }) }) }),
                  jsx('span', { className: 'font-mono', children: t.type }),
                  jsx('span', { className: `text-xs ${muted}`, children: `${t.stakes} stakes` }),
                  jsx('span', {
                    className: `ml-auto text-xs ${muted}`,
                    children: t.capped ? 'always asks' : `${t.series}/${t.required} in a row · ${t.sessions} session${t.sessions === 1 ? '' : 's'}`
                  })
                ]
              })
            })
          })
        ]
      })
    )
  })
}

function ModelsView({ ctx }) {
  const [rows, setRows] = useState(null)
  useEffect(() => {
    ctx.rest('/models').then(d => setRows(d.rows || []), () => setRows([]))
  }, [store.at])
  if (rows === null) return jsx('p', { className: muted, children: 'Loading…' })
  if (!rows.length) return jsx('p', { className: muted, children: 'No verified outcome yet.' })
  return jsxs('div', {
    className: 'flex flex-col gap-2',
    children: [
      jsx('p', {
        className: `text-sm ${muted}`,
        children: "Your own benchmark: each model's verified record on your work, per action type, with a 95% interval on its fault rate. Beside it, the public measure is information: public capability on their tasks, not reliability on yours."
      }),
      jsx('div', {
        className: card,
        children: rows.map(r =>
          jsxs('div', {
            key: r.profile + r.agent + r.type,
            className: 'border-b border-(--ui-border) text-sm',
            style: { display: 'grid', gridTemplateColumns: '1fr 90px 260px', alignItems: 'center', gap: 12, padding: '6px 0' },
            children: [
              jsxs('div', { children: [jsx('div', { children: r.agent }), jsx('div', { className: `font-mono text-xs ${muted}`, children: r.type })] }),
              jsx('span', { className: 'font-mono text-xs', children: `${r.faults} / ${r.successes + r.faults}` }),
              jsx('span', {
                className: `text-xs ${muted}`,
                children: r.enough
                  ? `${(r.rate * 100).toFixed(1)}% faults · 95%: ${(r.low * 100).toFixed(1)}–${(r.high * 100).toFixed(1)}%`
                  : 'not enough evidence'
              })
            ]
          })
        )
      })
    ]
  })
}

function PassportView({ data, ctx, initial }) {
  const agents = allAgents(data)
  const [pick, setPick] = useState(initial || (agents[0] && agents[0].profile + '|' + agents[0].agent) || '')
  const [doc, setDoc] = useState(null)
  useEffect(() => {
    if (!pick) return
    const [profile, agent] = pick.split('|')
    setDoc(null)
    ctx.rest(`/passport?agent=${encodeURIComponent(agent)}&of=${encodeURIComponent(profile)}`).then(setDoc, e => setDoc({ error: e.message || 'unreadable' }))
  }, [pick])
  if (!agents.length) return jsx('p', { className: muted, children: 'No agent yet, so no passport.' })
  const ok = doc && !doc.error && Array.isArray(doc.verify) && doc.verify.length === 0
  return jsxs('div', {
    className: 'flex flex-col gap-3',
    children: [
      jsx('select', {
        className: 'w-fit rounded border border-(--ui-border) bg-transparent px-2 py-1 text-sm',
        value: pick,
        onChange: e => setPick(e.target.value),
        children: agents.map(a => jsx('option', { value: a.profile + '|' + a.agent, children: `${a.agent} · ${a.profile}` }, a.profile + a.agent))
      }),
      doc === null
        ? jsx('p', { className: muted, children: 'Verifying…' })
        : jsxs('div', {
            className: card,
            children: [
              jsx('div', {
                className: `font-medium ${ok ? 'text-emerald-500' : 'text-red-500'}`,
                children: doc.error ? `Not available: ${doc.error}` : ok ? '● Verified: signature valid, hash chain intact, replaying the ledger gives the same tiers' : '● Problems: ' + doc.verify.join('; ')
              }),
              doc.passport &&
                jsx('div', {
                  className: `mt-2 font-mono text-xs ${muted}`,
                  style: { display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 16, rowGap: 2 },
                  children: [
                    ['protocol', doc.passport.protocol],
                    ['rule', doc.passport.rule && `${doc.passport.rule.name} · ${String(doc.passport.rule.fingerprint || '').slice(0, 16)}`],
                    ['ledger', doc.passport.ledger && `${doc.passport.ledger.count} events · head ${String(doc.passport.ledger.head || '').slice(0, 12)}`],
                    ['generated', doc.passport.generated_at]
                  ].flatMap(([k, v]) => [jsx('span', { children: k }, k), jsx('span', { children: String(v ?? '') }, k + 'v')])
                }),
              doc.passport &&
                jsx('button', {
                  type: 'button',
                  className: `mt-3 rounded border border-(--ui-border) px-2 py-0.5 text-xs ${muted}`,
                  onClick: async () => {
                    const done = await ctx.os.writeClipboard(JSON.stringify(doc.passport, null, 2))
                    host.notify({ kind: 'info', message: done ? 'Passport copied. Anyone can check it with `hermes tenure verify`.' : 'Could not copy' })
                  },
                  children: 'Copy passport JSON'
                })
            ]
          })
    ]
  })
}

let pendingTab = null

function TenurePage({ ctx }) {
  const s = useStore()
  const [tab, setTab] = useState(pendingTab ? pendingTab.tab : 'map')
  const [initial] = useState(pendingTab ? pendingTab.agent : null)
  useEffect(() => {
    pendingTab = null
    refresh()
  }, [])
  const data = s.agents
  const agents = allAgents(data)
  const sum = k => agents.reduce((n, a) => n + ((a.totals && a.totals[k]) || 0), 0)
  return jsxs('div', {
    className: 'flex h-full flex-col gap-4 overflow-auto p-5',
    children: [
      jsxs('div', {
        children: [
          jsx('h1', { className: 'text-lg font-semibold', children: 'Tenure' }),
          jsx('p', { className: `text-sm ${muted}`, children: 'Autonomy earned per action type, on verified evidence' })
        ]
      }),
      s.error && !data
        ? jsx('div', { className: card, children: `The tenure backend did not answer (${s.error}). Is the agent half enabled in this profile?` })
        : null,
      data &&
        jsxs('div', {
          className: card,
          style: { display: 'flex', flexWrap: 'wrap', gap: 40 },
          children: [
            jsx(Stat, { value: sum('actions'), label: 'actions', sub: 'covered' }),
            jsx(Stat, { value: sum('checked'), label: 'checked', sub: 'by you' }),
            jsx(Stat, { value: sum('alone'), label: 'earned alone', sub: 'ran without asking' }),
            jsx(Stat, { value: sum('faults'), label: 'faults caught', sub: 'each one drops the type back' })
          ]
        }),
      data &&
        jsxs('div', {
          className: 'flex gap-2 border-b border-(--ui-border)',
          children: [
            jsx(TabButton, { active: tab === 'map', onClick: () => setTab('map'), children: 'Map' }),
            jsx(TabButton, { active: tab === 'models', onClick: () => setTab('models'), children: 'Models' }),
            jsx(TabButton, { active: tab === 'passport', onClick: () => setTab('passport'), children: 'Passport' })
          ]
        }),
      data && tab === 'map' && jsx(MapView, { data, ctx }),
      data && tab === 'models' && jsx(ModelsView, { ctx }),
      data && tab === 'passport' && jsx(PassportView, { data, ctx, initial }),
      jsx('p', {
        className: `mt-auto text-xs ${muted}`,
        children: 'T1 asks first · T2 acts, then notifies with an undo (reversible types) · T3 acts alone, 1 in 10 spot-checked · CAP always asks'
      })
    ]
  })
}

// ------------------------------------------------------------------------------------------------ status-bar chip
function Chip() {
  const s = useStore()
  const model = useValue(host.state.model)
  const a = agentForModel(s.agents, model)
  let text = 'tenure'
  let tip = 'Open Tenure'
  if (a) {
    const n = { alone: 0, notify: 0, ask: 0 }
    for (const t of a.types || []) if (!t.capped) n[t.effective_tier || t.tier] = (n[t.effective_tier || t.tier] || 0) + 1
    text = `tenure · ${n.alone} alone · ${n.notify} notify · ${n.ask} ask`
    tip = `${a.agent}: action types per tier on your work. Click for the map.`
  } else if (model && s.agents) {
    text = 'tenure · new model'
    tip = `${model} has no record yet: every change asks first.`
  }
  return jsx(Tip, {
    label: tip,
    children: jsx('button', {
      type: 'button',
      className: `inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] transition-colors ${muted} hover:bg-(--chrome-action-hover) hover:text-foreground`,
      onClick: () => {
        haptic('tap')
        host.navigate(ROUTE)
      },
      children: text
    })
  })
}

// ------------------------------------------------------------------------------------------------ registration
export default {
  id: ID,
  name: 'Tenure',
  register(ctx) {
    restRef = ctx.rest
    refresh()
    ctx.setInterval(refresh, POLL_MS)
    ctx.onDispose(() => {
      restRef = null
      store.listeners.clear()
    })

    const current = () => agentForModel(store.agents, host.state.model.get())

    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(TenurePage, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROUTE, label: 'Tenure', codicon: 'shield' } },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 125, render: () => jsx(Chip, {}) },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: { id: 'tenure.open', label: 'Tenure: open the map', keywords: ['tenure', 'autonomy', 'tier'], run: () => host.navigate(ROUTE) }
      },
      {
        id: 'passport',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.passport',
          label: 'Tenure: passport of the current model',
          keywords: ['tenure', 'passport', 'verify'],
          run: () => {
            const a = current()
            pendingTab = { tab: 'passport', agent: a ? a.profile + '|' + a.agent : null }
            host.navigate(ROUTE)
          }
        }
      },
      {
        id: 'revoke',
        area: PALETTE_AREA,
        data: {
          id: 'tenure.revoke',
          label: 'Tenure: revoke the current model',
          keywords: ['tenure', 'revoke', 'trust'],
          run: () => {
            const a = current()
            if (!a) return host.notify({ kind: 'info', message: 'The current model has no tenure to revoke.' })
            host.notify({
              kind: 'warning',
              message: `Revoke every tenure of ${a.agent}? Every action type will ask again.`,
              action: {
                label: 'Revoke',
                onClick: async () => {
                  try {
                    await ctx.rest('/revoke?of=' + encodeURIComponent(a.profile), { method: 'POST', body: { agent: a.agent, all: true } })
                    host.notify({ kind: 'info', message: `Tenure revoked for ${a.agent}.` })
                    refresh()
                  } catch (e) {
                    host.notifyError(e, 'Could not revoke')
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
