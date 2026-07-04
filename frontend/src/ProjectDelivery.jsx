import { useEffect, useState } from 'react'
import { getProjectDeliveryDashboard } from './api.js'

const CAT_LABELS = {
  project_responsibility: 'Project Responsibility', temp_power: 'Temp Power', ms_responsibility: 'MS Responsibility',
  nwg_responsibility: 'NWG Responsibility', other: 'Other',
}
const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function fmt(n) { return n === null || n === undefined ? '—' : n.toLocaleString() }
function ago(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function ProjectDelivery({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [popup, setPopup] = useState(null) // {title, rows, exportLabel}

  useEffect(() => {
    getProjectDeliveryDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  const scMax = Math.max(1, ...d.ongoing_by_subcontractor.map(r => r.count))
  const catMax = Math.max(1, ...d.problematic_by_category.map(r => r.count))
  const yearMax = Math.max(1, ...d.yearly_delivery.map(r => r.count))
  const monthMax = Math.max(1, ...d.monthly_this_year.map(r => r.count))
  const scTotalMax = Math.max(1, ...d.by_subcontractor_total.map(r => r.count))
  const thisMonthLabel = `${MONTH_LABELS[d.current_month.month - 1]} ${d.current_month.year}`

  function openBreakdown(title, rows, exportLabel) {
    setPopup({ title, rows, exportLabel })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>Project Delivery</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>Site-grain delivery progress across the whole project.</div>
        </div>
        <div style={freshness}><span style={freshDot} />Data as of&nbsp;<strong style={{ color: 'var(--ink)' }}>{ago(d.generated_at)}</strong></div>
      </div>

      {/* KPIs */}
      <div style={{ ...cards, marginTop: 18 }}>
        <Kpi label="Total On-Air" value={d.kpis.on_air.count} pct={d.kpis.on_air.pct_of_total} pctLabel="of all sites"
             delta={d.kpis.on_air.delta} goodUp />
        <Kpi label="Total Drive Test" value={d.kpis.drive_test.count} pct={d.kpis.drive_test.pct_of_on_air} pctLabel="of on-air"
             delta={d.kpis.drive_test.delta} goodUp />
        <Kpi label="Total Remained" value={d.kpis.remained.count} pct={d.kpis.remained.pct_of_on_air} pctLabel="of on-air"
             delta={d.kpis.remained.delta} amber goodDown />
      </div>

      {/* Ongoing per subcontractor */}
      <Section title="Ongoing Sites" note="per subcontractor — click a bar for the province breakdown"
                action={<ExportBtn onClick={() => openBreakdown('Ongoing sites — all subcontractors, by province',
                  mergeProvinces(d.ongoing_by_subcontractor), 'Ongoing sites (all subcontractors, per province)')} />}>
        <div style={{ padding: '16px 22px' }}>
          {d.ongoing_by_subcontractor.length === 0 ? <Empty text="No ongoing sites right now." /> :
            d.ongoing_by_subcontractor.map(r => (
              <ClickBar key={r.subcontractor} label={r.subcontractor} value={r.count} max={scMax} color="var(--amber)"
                        onClick={() => openBreakdown(`Ongoing — ${r.subcontractor}, by province`, r.by_province,
                          `Ongoing sites — ${r.subcontractor}`)} />
            ))}
        </div>
      </Section>

      {/* Problematic per category */}
      <Section title="Problematic Sites" note="per category — click a bar for the province breakdown"
                action={<ExportBtn onClick={() => openBreakdown('Problematic sites — all categories, by province',
                  mergeProvinces(d.problematic_by_category.map(r => ({ ...r, subcontractor: CAT_LABELS[r.category] || r.category }))),
                  'Problematic sites (all categories, per province)')} />}>
        <div style={{ padding: '16px 22px' }}>
          {d.problematic_by_category.length === 0 ? <Empty text="No problematic sites right now." /> :
            d.problematic_by_category.map(r => (
              <ClickBar key={r.category} label={CAT_LABELS[r.category] || r.category} value={r.count} max={catMax} color="var(--red)"
                        onClick={() => openBreakdown(`Problematic — ${CAT_LABELS[r.category] || r.category}, by province`, r.by_province,
                          `Problematic sites — ${CAT_LABELS[r.category] || r.category}`)} />
            ))}
        </div>
      </Section>

      {/* Yearly delivery */}
      <Section title="DT Delivery — Yearly">
        <div style={{ padding: '18px 22px' }}>
          <ColumnChart items={d.yearly_delivery.map(y => ({ label: String(y.year), value: y.count }))} max={yearMax} color="var(--accent)" />
        </div>
      </Section>

      {/* Monthly this year */}
      <Section title={`DT Delivery — ${d.current_month.year}, by Month`}>
        <div style={{ padding: '16px 22px 4px' }}>
          <div style={{ display: 'flex', gap: 22, alignItems: 'baseline', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 32, fontWeight: 800 }}>{fmt(d.current_month.count)}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>{thisMonthLabel} so far</div>
            </div>
            {d.current_month.delta !== 0 && (
              <div style={{ fontSize: 12, fontWeight: 600, color: d.current_month.delta > 0 ? 'var(--green)' : 'var(--red)' }}>
                {d.current_month.delta > 0 ? '▲' : '▼'} {Math.abs(d.current_month.delta)} vs last month
              </div>
            )}
          </div>
        </div>
        <div style={{ padding: '0 22px 18px' }}>
          <ColumnChart items={d.monthly_this_year.map(m => ({ label: MONTH_LABELS[m.month - 1], value: m.count }))} max={monthMax} color="var(--accent)" />
        </div>
        <div style={{ padding: '0 22px 16px' }}>
          <div style={footnote}>
            Yearly/monthly charts only include drive tests with a recorded DT Date — {fmt(d.dt_delivery_dated_count)} of {fmt(d.kpis.drive_test.count)} completed
            drive tests have one. The rest are historical records completed without a dated entry, so these charts undercount the true total on purpose
            rather than guess a date.
          </div>
        </div>
      </Section>

      {/* Per subcontractor total */}
      <Section title="DT Delivery — per Subcontractor" note="total, all time">
        <div style={{ padding: '16px 22px' }}>
          {d.by_subcontractor_total.map(r => (
            <Bar key={r.subcontractor} label={r.subcontractor} value={r.count} max={scTotalMax} color="var(--green)" />
          ))}
        </div>
      </Section>

      {popup && <BreakdownModal {...popup} onClose={() => setPopup(null)} />}
    </div>
  )
}

function mergeProvinces(groups) {
  const totals = {}
  for (const g of groups) for (const p of g.by_province) totals[p.province] = (totals[p.province] || 0) + p.count
  return Object.entries(totals).map(([province, count]) => ({ province, count })).sort((a, b) => b.count - a.count)
}

function BreakdownModal({ title, rows, exportLabel, onClose }) {
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <div style={{ fontSize: 14.5, fontWeight: 700 }}>{title}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--muted)' }}>×</button>
        </div>
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          <table style={table}>
            <thead><tr style={{ background: 'var(--panel2)' }}><Th>Province</Th><Th right>Sites</Th></tr></thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={2} style={{ ...td, color: 'var(--muted)' }}>No data.</td></tr>
              ) : rows.map(r => (
                <tr key={r.province} style={{ borderTop: '1px solid var(--line-soft)' }}>
                  <td style={td}>{r.province}</td>
                  <td style={{ ...td, textAlign: 'right' }}>{r.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'flex-end' }}>
          <ExportBtn label="Export Excel" onClick={() => alert('Generating Excel: ' + exportLabel)} />
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, value, pct, pctLabel, delta, amber, goodUp, goodDown }) {
  let deltaEl = null
  if (delta !== null && delta !== undefined && delta !== 0) {
    const up = delta > 0
    const good = up ? goodUp : goodDown
    deltaEl = <div style={{ fontSize: 11, fontWeight: 600, marginTop: 7, color: good ? 'var(--green)' : 'var(--red)' }}>
      {up ? '▲' : '▼'} {Math.abs(delta)} vs last month
    </div>
  } else if (delta === null || delta === undefined) {
    deltaEl = <div style={{ fontSize: 11, color: 'var(--muted2)', marginTop: 7 }}>no baseline yet</div>
  }
  return (
    <div style={card}>
      <div style={cardLabel}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8, color: amber ? 'var(--amber)' : 'var(--ink)' }}>{fmt(value)}</div>
      {deltaEl}
      <div style={{ fontSize: 11.5, color: 'var(--muted2)', marginTop: 4 }}>{pct}% {pctLabel}</div>
    </div>
  )
}

function Section({ title, note, action, children }) {
  return (
    <section style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, marginTop: 18, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px 22px', borderBottom: '1px solid var(--line)' }}>
        <div style={{ fontSize: 13.5, fontWeight: 700 }}>
          {title}{note && <span style={{ color: 'var(--muted)', fontWeight: 500 }}> — {note}</span>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function Bar({ label, value, max, color }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 44px', alignItems: 'center', gap: 10, fontSize: 12, marginBottom: 9 }}>
      <div style={{ color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
      <div style={{ height: 8, borderRadius: 5, background: 'var(--panel2)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.max(4, (value / max) * 100)}%`, background: color, borderRadius: 5 }} />
      </div>
      <div style={{ textAlign: 'right', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function ClickBar({ label, value, max, color, onClick }) {
  return (
    <div onClick={onClick} style={clickBarWrap}
         onMouseEnter={e => e.currentTarget.style.background = 'var(--panel2)'}
         onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 44px', alignItems: 'center', gap: 10, fontSize: 12 }}>
        <div style={{ color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label} ▾</div>
        <div style={{ height: 8, borderRadius: 5, background: 'var(--panel2)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${Math.max(4, (value / max) * 100)}%`, background: color, borderRadius: 5 }} />
        </div>
        <div style={{ textAlign: 'right', fontWeight: 600 }}>{value}</div>
      </div>
    </div>
  )
}

function ColumnChart({ items, max, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, height: 140 }}>
      {items.map(it => (
        <div key={it.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>{it.value || ''}</div>
          <div style={{
            width: '100%', maxWidth: 34, borderRadius: '4px 4px 0 0', background: color,
            height: `${Math.max(it.value ? 3 : 0, (it.value / max) * 100)}%`,
            minHeight: it.value ? 3 : 0,
          }} />
          <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 6 }}>{it.label}</div>
        </div>
      ))}
    </div>
  )
}

function Empty({ text }) {
  return <div style={{ color: 'var(--muted)', fontSize: 12.5, textAlign: 'center', padding: '10px 0' }}>{text}</div>
}

function ExportBtn({ label, onClick }) {
  return <button style={exportBtn} onClick={onClick}>↓ {label || 'Export Excel'}</button>
}

function Th({ children, right }) {
  return <th style={{ textAlign: right ? 'right' : 'left', padding: '9px 20px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: .6, fontWeight: 600 }}>{children}</th>
}

const cards = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 14 }
const card = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }
const cardLabel = { fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .7 }
const table = { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }
const td = { padding: '9px 20px' }
const clickBarWrap = { cursor: 'pointer', padding: '5px 8px', borderRadius: 8, margin: '-5px -8px -5px -8px', marginBottom: 4 }
const exportBtn = { fontSize: 11.5, color: 'var(--muted)', background: 'transparent', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 11px', cursor: 'pointer', fontWeight: 600 }
const footnote = { fontSize: 11.5, color: 'var(--muted2)', lineHeight: 1.6, background: 'var(--panel2)', borderRadius: 8, padding: '10px 14px' }
const freshness = { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--muted)', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 20, padding: '7px 14px', whiteSpace: 'nowrap' }
const freshDot = { width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 0 3px var(--green-soft)', marginRight: 4 }
const errBox = { padding: '12px 16px', borderRadius: 10, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, width: 460, maxWidth: '92vw' }
