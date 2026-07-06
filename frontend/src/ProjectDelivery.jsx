import { useEffect, useState } from 'react'
import { getProjectDeliveryDashboard } from './api.js'
import { exportXlsx } from './xlsxExport.js'
import Chart from './Chart.jsx'

const CAT_LABELS = {
  project_responsibility: 'Project Responsibility', temp_power: 'Temp Power', ms_responsibility: 'MS Responsibility',
  nwg_responsibility: 'NWG Responsibility', other: 'Other',
}
const TABLE_PAGE = 5
const THEME = { accent: '#2563eb', soft: 'rgba(37,99,235,.10)' }

function fmt(n) { return n === null || n === undefined ? '—' : n.toLocaleString() }
function ago(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function ProjectDelivery({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')
  const [popup, setPopup] = useState(null) // {title, rows, exportName}

  useEffect(() => {
    getProjectDeliveryDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  const isContractor = d.scope.hide_problematic
  const scMax = Math.max(1, ...d.ongoing_by_subcontractor.map(r => r.count))
  const catMax = Math.max(1, ...d.problematic_by_category.map(r => r.count))
  const yearMax = Math.max(1, ...d.yearly_delivery.map(r => r.count))
  const monthMax = Math.max(1, ...d.monthly_this_year.map(r => r.count))
  const scTotalMax = Math.max(1, ...d.by_subcontractor_total.map(r => r.count))

  function openBreakdown(title, rows, exportName) {
    setPopup({ title, rows, exportName })
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>Project Delivery</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>
            {isContractor ? 'Your assigned sites only.' : 'Site-grain delivery progress across the whole project.'}
          </div>
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
                  mergeProvinces(d.ongoing_by_subcontractor), 'ongoing_sites_by_province')} />}>
        <div style={{ padding: '16px 22px' }}>
          {d.ongoing_by_subcontractor.length === 0 ? <Empty text="No ongoing sites right now." /> :
            d.ongoing_by_subcontractor.map(r => (
              <ClickBar key={r.subcontractor} label={r.subcontractor} value={r.count} max={scMax} color="var(--amber)"
                        onClick={() => openBreakdown(`Ongoing — ${r.subcontractor}, by province`, r.by_province,
                          `ongoing_${r.subcontractor}`)} />
            ))}
        </div>
      </Section>

      {/* Problematic per category — never shown to Field Subcontractor */}
      {!isContractor && (
        <Section title="Problematic Sites" note="per category — click a bar for the province breakdown"
                  action={<ExportBtn onClick={() => openBreakdown('Problematic sites — all categories, by province',
                    mergeProvinces(d.problematic_by_category.map(r => ({ ...r, subcontractor: CAT_LABELS[r.category] || r.category }))),
                    'problematic_sites_by_province')} />}>
          <div style={{ padding: '16px 22px' }}>
            {d.problematic_by_category.length === 0 ? <Empty text="No problematic sites right now." /> :
              d.problematic_by_category.map(r => (
                <ClickBar key={r.category} label={CAT_LABELS[r.category] || r.category} value={r.count} max={catMax} color="var(--red)"
                          onClick={() => openBreakdown(`Problematic — ${CAT_LABELS[r.category] || r.category}, by province`, r.by_province,
                            `problematic_${r.category}`)} />
              ))}
          </div>
        </Section>
      )}

      {/* Per-province progress — one compact sortable table instead of a
          long scrolling list */}
      <PerProvinceSection rows={d.per_province} />

      {/* Yearly delivery (Shamsi years) */}
      <Section title="DT Delivery — Yearly" note="Shamsi years">
        <div style={{ padding: '18px 22px' }}>
          <ColumnChart items={d.yearly_delivery.map(y => ({ label: String(y.year), value: y.count }))} max={yearMax} color="var(--accent)" />
        </div>
      </Section>

      {/* Monthly this year + current-month progress (Shamsi) */}
      <Section title={`DT Delivery — ${d.current_month.year}, by Month`} note="Shamsi months">
        <div style={{ padding: '16px 22px 4px' }}>
          <div style={{ background: THEME.soft, borderRadius: 10, padding: '10px 12px', marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>Current month ({d.current_month.period_label})</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>
                  {fmt(d.current_month.count)}
                  <span style={{ fontSize: 12, fontWeight: 600, marginLeft: 8, color: deltaColor(d.current_month.delta) }}>
                    {deltaText(d.current_month)}
                  </span>
                </div>
              </div>
            </div>
            <Chart option={lineOption(d.current_month)} height={90} />
          </div>
        </div>
        <div style={{ padding: '0 22px 18px' }}>
          <ColumnChart items={d.monthly_this_year.map(m => ({ label: m.month_label, value: m.count }))} max={monthMax} color="var(--accent)" />
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

function lineOption(cm) {
  const data = cm.daily_cumulative || []
  return {
    grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: false },
    xAxis: { type: 'category', show: false, data: data.map((_, i) => i + 1) },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', formatter: p => `Day ${p[0].dataIndex + 1}: ${p[0].data} delivered` },
    series: [{
      type: 'line', data, smooth: true, symbol: 'none',
      lineStyle: { color: THEME.accent, width: 2 },
      areaStyle: { color: THEME.soft },
    }],
  }
}
function deltaText(cm) {
  if (cm.delta_pct == null) return `vs ${fmt(cm.last_month)} last month`
  const sign = cm.delta >= 0 ? '↑' : '↓'
  return `${sign} ${Math.abs(cm.delta_pct)}% vs last month`
}
function deltaColor(delta) { return delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--muted)' }

function PerProvinceSection({ rows }) {
  const [expanded, setExpanded] = useState(false)
  const [sortKey, setSortKey] = useState('on_air')
  const [search, setSearch] = useState('')

  let filtered = rows.filter(r => !search || r.province.toLowerCase().includes(search.toLowerCase()))
  filtered = [...filtered].sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0) || a.province.localeCompare(b.province))
  const shown = expanded ? filtered : filtered.slice(0, TABLE_PAGE)

  function doExport() {
    exportXlsx('project_delivery_per_province.xlsx', [{
      name: 'Per Province',
      rows: [
        ['Province', 'On-Air', 'DT Done', 'Remained', 'DT %'],
        ...filtered.map(r => [r.province, r.on_air, r.dt_done, r.remained, r.dt_pct]),
      ],
    }])
  }

  return (
    <Section title="Progress per Province" note="click a column to sort" action={<ExportBtn onClick={doExport} />}>
      <div style={{ padding: '14px 22px 8px', display: 'flex', justifyContent: 'flex-end' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search province…"
               style={{ ...input, fontSize: 12, padding: '5px 9px', width: 200 }} />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={table}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Province</Th>
              <Th align="right" onClick={() => setSortKey('on_air')} active={sortKey === 'on_air'}>On-Air</Th>
              <Th align="right" onClick={() => setSortKey('dt_done')} active={sortKey === 'dt_done'}>DT Done</Th>
              <Th align="right" onClick={() => setSortKey('remained')} active={sortKey === 'remained'}>Remained</Th>
              <Th align="right" onClick={() => setSortKey('dt_pct')} active={sortKey === 'dt_pct'}>DT %</Th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr><td colSpan={5} style={{ ...td, color: 'var(--muted)' }}>No provinces.</td></tr>
            ) : shown.map(r => (
              <tr key={r.province} style={{ borderTop: '1px solid var(--line-soft)' }}>
                <td style={td}>{r.province}</td>
                <td style={{ ...td, textAlign: 'right' }}>{fmt(r.on_air)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{fmt(r.dt_done)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{fmt(r.remained)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{r.dt_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > TABLE_PAGE && (
        <div style={{ padding: '4px 22px 16px' }}>
          <button onClick={() => setExpanded(x => !x)} style={linkBtn}>
            {expanded ? 'Show top 5' : `View all provinces (${filtered.length})`}
          </button>
        </div>
      )}
    </Section>
  )
}

function BreakdownModal({ title, rows, exportName, onClose }) {
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <div style={{ fontSize: 14.5, fontWeight: 700 }}>{title}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--muted)' }}>×</button>
        </div>
        <div style={{ maxHeight: 360, overflowY: 'auto' }}>
          <table style={table}>
            <thead><tr style={{ background: 'var(--panel2)' }}><Th>Province</Th><Th align="right">Sites</Th></tr></thead>
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
          <ExportBtn label="Export Excel" onClick={() => exportXlsx(`${exportName}.xlsx`, [{
            name: 'Breakdown', rows: [['Province', 'Sites'], ...rows.map(r => [r.province, r.count])],
          }])} />
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

function Th({ children, align, onClick, active }) {
  return (
    <th onClick={onClick}
      style={{ textAlign: align || 'left', padding: '9px 20px', fontSize: 10.5, color: active ? 'var(--accent)' : 'var(--muted2)',
        textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600, cursor: onClick ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
      {children}{onClick && <span style={{ marginLeft: 2 }}>{active ? '▾' : '⇅'}</span>}
    </th>
  )
}

const cards = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 14 }
const card = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }
const cardLabel = { fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .7 }
const table = { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }
const td = { padding: '9px 20px' }
const input = { padding: '7px 11px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none', fontSize: 12.5 }
const linkBtn = { background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', padding: 0 }
const clickBarWrap = { cursor: 'pointer', padding: '5px 8px', borderRadius: 8, margin: '-5px -8px -5px -8px', marginBottom: 4 }
const exportBtn = { fontSize: 11.5, color: 'var(--muted)', background: 'transparent', border: '1px solid var(--line)', borderRadius: 7, padding: '5px 11px', cursor: 'pointer', fontWeight: 600 }
const footnote = { fontSize: 11.5, color: 'var(--muted2)', lineHeight: 1.6, background: 'var(--panel2)', borderRadius: 8, padding: '10px 14px' }
const freshness = { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--muted)', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 20, padding: '7px 14px', whiteSpace: 'nowrap' }
const freshDot = { width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 0 3px var(--green-soft)', marginRight: 4 }
const errBox = { padding: '12px 16px', borderRadius: 10, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, width: 460, maxWidth: '92vw' }
