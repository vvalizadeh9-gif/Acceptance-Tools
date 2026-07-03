import { useEffect, useState } from 'react'
import { getPmDashboard } from './api.js'

const CAT_LABELS = {
  on_site_issue: 'On-Site Issue', temp_power: 'Temp Power', ms_responsibility: 'MS Responsibility',
  nwg_responsibility: 'NWG Responsibility', other: 'Other',
}

function fmt(n) { return n === null || n === undefined ? '—' : n.toLocaleString() }
function ago(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function PmDashboard({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [breakdown, setBreakdown] = useState(null) // {title, rows}

  useEffect(() => {
    getPmDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading dashboard…</div>

  const catMax = Math.max(1, ...d.gap.problematic_by_category.map(c => c.count))
  const provMax = Math.max(1, ...d.assignable.by_province.map(p => p.count))

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>Project Manager — Command Center</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>The seven gaps, live from your data.</div>
        </div>
        <div style={freshness}>
          <span style={freshDot} />
          Data as of <strong style={{ color: 'var(--ink)' }}>&nbsp;{ago(d.generated_at)}</strong>
          <span style={{ color: 'var(--line)' }}>&nbsp;·&nbsp;</span>
          last CPM import {ago(d.last_cpm_import)}
        </div>
      </div>

      {/* KPIs */}
      <div style={{ ...cards, marginTop: 18 }}>
        <Kpi label="Total On-Air" value={d.kpis.on_air.sites} delta={d.kpis.on_air.delta}
             sub={`Site + Site Type · ${fmt(d.kpis.on_air.villages)} hadaf villages on-air`} goodUp />
        <Kpi label="Total Drive Test" value={d.kpis.drive_test.sites} delta={d.kpis.drive_test.delta}
             sub={`Site + Site Type · ${fmt(d.kpis.drive_test.villages)} hadaf villages DT done`} goodUp />
        <Kpi label="Total Remained" value={d.kpis.remained.sites} delta={d.kpis.remained.delta}
             sub={`Ongoing + Problematic · ${fmt(d.kpis.remained.villages)} hadaf villages remained`} amber goodDown />
      </div>

      {/* 1. Gap */}
      <Section n="1" title="On-Air vs. Drive Test Done" note="the core delivery gap"
               action={<ExportBtn label="Export Excel" />}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 28, padding: '20px 22px' }}>
          <div>
            <div style={{ fontSize: 40, fontWeight: 800, color: 'var(--amber)', letterSpacing: -1 }}>{fmt(d.gap.total_remained)}</div>
            <div style={{ color: 'var(--muted)', fontSize: 12.5, maxWidth: 240 }}>on-air sites still waiting on a completed drive test</div>
          </div>
          <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--line)' }} />
          <div style={{ display: 'flex', gap: 20 }}>
            <ClickStat value={d.gap.ongoing} label="Ongoing ▾" color="var(--amber)"
                       onClick={() => setBreakdown({ title: 'Ongoing — by province', rows: null, kind: 'ongoing' })} />
            <ClickStat value={d.gap.problematic} label="Problematic ▾" color="var(--red)"
                       onClick={() => setBreakdown({ title: 'Problematic — by province', rows: null, kind: 'problematic' })} />
          </div>
        </div>
        <div style={{ padding: '0 22px 18px' }}>
          {d.gap.problematic_by_category.map(c => (
            <Bar key={c.category} label={CAT_LABELS[c.category] || c.category} value={c.count} max={catMax} color="var(--red)" />
          ))}
        </div>
      </Section>

      {/* 2. Assignable */}
      <Section n="2" title="Assignable Queue" note="on-air, not ongoing, not problematic, unassigned">
        <div style={{ padding: '18px 22px', display: 'grid', gridTemplateColumns: '1fr 200px', gap: 18, alignItems: 'center' }}>
          <div>
            {d.assignable.by_province.slice(0, 6).map(p => (
              <Bar key={p.province} label={p.province} value={p.count} max={provMax} color="var(--accent)" />
            ))}
          </div>
          <div style={{ background: 'var(--panel2)', borderRadius: 10, padding: 20, textAlign: 'center' }}>
            <div style={{ fontSize: 38, fontWeight: 800 }}>{fmt(d.assignable.total)}</div>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>sites ready to assign</div>
            <div style={{ color: 'var(--muted2)', fontSize: 11, marginTop: 6 }}>across {d.assignable.by_province.length} provinces</div>
          </div>
        </div>
      </Section>

      {/* 3 & 4. Pending ICT / CRA */}
      <div style={split}>
        <PendingBlock n="3" org="ICT" total={d.pending_ict.total} rows={d.pending_ict.by_coordinator} />
        <PendingBlock n="4" org="CRA" total={d.pending_cra.total} rows={d.pending_cra.by_coordinator} />
      </div>

      {/* 5 & 6. Cross gaps */}
      <div style={split}>
        <Section n="5" title="ICT approved, CRA not yet" action={<ExportBtn iconOnly />}>
          <CrossGap value={d.ict_approved_cra_not} copy="villages — CRA is the blocker on final acceptance" />
        </Section>
        <Section n="6" title="CRA approved, ICT not yet" action={<ExportBtn iconOnly />}>
          <CrossGap value={d.cra_approved_ict_not} copy="villages — ICT is the blocker on final acceptance" />
        </Section>
      </div>

      {/* 7. Monthly approvals */}
      <Section n="7" title="This Month's Approvals" note="per person, month-to-date">
        <table style={table}>
          <thead><tr style={{ background: 'var(--panel2)' }}>
            <Th>Person</Th><Th right>ICT approved</Th><Th right>CRA approved</Th><Th right>Total</Th>
          </tr></thead>
          <tbody>
            {d.monthly_approvals.length === 0 ? (
              <tr><td colSpan={4} style={{ ...td, color: 'var(--muted)' }}>No approvals recorded yet this month.</td></tr>
            ) : d.monthly_approvals.map(p => (
              <tr key={p.name} style={{ borderTop: '1px solid var(--line-soft)' }}>
                <td style={td}>{p.name}</td>
                <td style={{ ...td, textAlign: 'right' }}>{p.ict}</td>
                <td style={{ ...td, textAlign: 'right' }}>{p.cra}</td>
                <td style={{ ...td, textAlign: 'right', fontWeight: 700 }}>{p.total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {breakdown && (
        <BreakdownModal token={token} title={breakdown.title} kind={breakdown.kind}
                        data={breakdown.kind === 'ongoing'
                          ? null : null}
                        provinceRows={d.assignable.by_province}
                        onClose={() => setBreakdown(null)} />
      )}
    </div>
  )
}

/* The Ongoing/Problematic per-province breakdown is a dedicated endpoint we
   add next; for now the modal explains that and offers the export hook. */
function BreakdownModal({ title, onClose }) {
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 22px', borderBottom: '1px solid var(--line)' }}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--muted)' }}>×</button>
        </div>
        <div style={{ padding: '20px 22px', color: 'var(--muted)', fontSize: 13 }}>
          Per-province breakdown with Excel export is the next endpoint — the query is ready on the backend,
          this popup gets wired to it in the following step.
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, value, sub, delta, amber, goodUp, goodDown }) {
  let deltaEl = null
  if (delta !== null && delta !== undefined && delta !== 0) {
    const up = delta > 0
    const good = up ? goodUp : goodDown
    deltaEl = <div style={{ fontSize: 11, fontWeight: 600, marginTop: 7, color: good ? 'var(--green)' : 'var(--red)' }}>
      {up ? '▲' : '▼'} {Math.abs(delta)} vs last month
    </div>
  }
  return (
    <div style={card}>
      <div style={cardLabel}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8, color: amber ? 'var(--amber)' : 'var(--ink)' }}>{fmt(value)}</div>
      {deltaEl}
      <div style={{ fontSize: 11.5, color: 'var(--muted2)', marginTop: 4 }}>{sub}</div>
    </div>
  )
}

function PendingBlock({ n, org, total, rows }) {
  return (
    <Section n={n} title={`Pending ${org} Approval`} action={<ExportBtn label="Export" />} noMargin>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '16px 22px 4px' }}>
        <div style={{ fontSize: 34, fontWeight: 800 }}>{fmt(total)}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>villages pending {org}, all coordinators</div>
      </div>
      <div style={{ fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: .6, padding: '10px 22px 0' }}>Per PSO coordinator</div>
      <table style={table}>
        <thead><tr style={{ background: 'var(--panel2)' }}><Th>Coordinator</Th><Th right>Pending</Th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.name} style={{ borderTop: '1px solid var(--line-soft)' }}>
              <td style={td}>{r.name}</td>
              <td style={{ ...td, textAlign: 'right' }}>{r.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  )
}

function CrossGap({ value, copy }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 22, padding: '20px 22px' }}>
      <div style={{ fontSize: 34, fontWeight: 800 }}>{fmt(value)}</div>
      <div style={{ color: 'var(--muted)', fontSize: 12.5, maxWidth: 220 }}>{copy}</div>
    </div>
  )
}

function Section({ n, title, note, action, children, noMargin }) {
  return (
    <section style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, marginTop: noMargin ? 0 : 18, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px 22px', borderBottom: '1px solid var(--line)' }}>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>
          {n && <span style={{ color: 'var(--muted)' }}>{n} · </span>}{title}
          {note && <span style={{ color: 'var(--muted)', fontWeight: 500 }}> — {note}</span>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function Bar({ label, value, max, color }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 44px', alignItems: 'center', gap: 10, fontSize: 12, marginBottom: 9 }}>
      <div style={{ color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
      <div style={{ height: 8, borderRadius: 5, background: 'var(--panel2)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.max(4, (value / max) * 100)}%`, background: color, borderRadius: 5 }} />
      </div>
      <div style={{ textAlign: 'right', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function ClickStat({ value, label, color, onClick }) {
  return (
    <div onClick={onClick} style={{ cursor: 'pointer', padding: '6px 10px', borderRadius: 8, margin: '-6px -10px' }}
         onMouseEnter={e => e.currentTarget.style.background = 'var(--panel2)'}
         onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{fmt(value)}</div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function ExportBtn({ label, iconOnly }) {
  return (
    <button style={exportBtn} title="Export to Excel"
            onClick={() => alert('Excel export is the next step to wire up.')}>
      ↓{iconOnly ? '' : ` ${label}`}
    </button>
  )
}

function Th({ children, right }) {
  return <th style={{ textAlign: right ? 'right' : 'left', padding: '9px 22px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: .6, fontWeight: 600 }}>{children}</th>
}

const cards = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 14 }
const card = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }
const cardLabel = { fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .7 }
const split = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 18 }
const table = { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }
const td = { padding: '10px 22px' }
const exportBtn = { fontSize: 11.5, color: 'var(--muted)', background: 'transparent', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 11px', cursor: 'pointer', fontWeight: 600 }
const freshness = { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--muted)', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 20, padding: '7px 14px', whiteSpace: 'nowrap' }
const freshDot = { width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 0 3px var(--green-soft)', marginRight: 4 }
const errBox = { padding: '12px 16px', borderRadius: 10, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, width: 440, maxWidth: '92vw' }
