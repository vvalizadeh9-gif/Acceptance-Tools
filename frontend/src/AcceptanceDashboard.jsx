import { useEffect, useState } from 'react'
import { getAcceptanceDashboard } from './api.js'
import Chart from './Chart.jsx'

// ICT = blue, CRA = purple (per the design). Kept side by side; the two are
// independent processes and never mixed.
const ICT = { accent: '#2563eb', soft: 'rgba(37,99,235,.10)' }
const CRA = { accent: '#7c3aed', soft: 'rgba(124,58,237,.10)' }

const TABLE_PAGE = 5

export default function AcceptanceDashboard({ token, onLogout, onManage }) {
  const [tech, setTech] = useState('all')
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getAcceptanceDashboard(token, tech)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') { onLogout(); return }; setError(err.message) })
  }, [token, tech])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  const r = d.site_rollup

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>Acceptance Dashboard</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>
            ICT and CRA — two independent processes, side by side. Current month: <strong style={{ color: 'var(--ink)' }}>{d.months.current_label}</strong>.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>Technology</span>
          <select value={tech} onChange={e => setTech(e.target.value)} style={input}>
            <option value="all">All</option><option value="2g">2G</option>
            <option value="3g">3G</option><option value="4g">4G</option>
          </select>
          {onManage && <button onClick={onManage} style={manageBtn}>Manage village data →</button>}
        </div>
      </div>

      {/* Site-level rollups across the whole project */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 12, marginBottom: 22 }}>
        <RollupCard label="Sites Fully ICT Approved" value={r.fully_ict} color={ICT.accent} />
        <RollupCard label="Sites Fully CRA Approved" value={r.fully_cra} color={CRA.accent} />
        <RollupCard label="Sites Fully Approved (Both)" value={r.fully_both} color="var(--green)" />
        <RollupCard label="Sites Partially Approved" value={r.partial} color="var(--amber)" />
        <RollupCard label="ICT Approved / CRA Not" value={r.ict_not_cra} color="var(--muted)" />
        <RollupCard label="CRA Approved / ICT Not" value={r.cra_not_ict} color="var(--muted)" />
      </div>

      {/* Two independent columns */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
        <SideColumn title="ICT Approval" data={d.ict} theme={ICT} months={d.months} />
        <SideColumn title="CRA Approval" data={d.cra} theme={CRA} months={d.months} />
      </div>
    </div>
  )
}

function SideColumn({ title, data, theme, months }) {
  const s = data.summary
  const [expanded, setExpanded] = useState(false)
  const [sortKey, setSortKey] = useState('approved')
  const [search, setSearch] = useState('')

  let rows = data.by_province.filter(p => !search || p.province.toLowerCase().includes(search.toLowerCase()))
  rows = [...rows].sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0) || a.province.localeCompare(b.province))
  const shown = expanded ? rows : rows.slice(0, TABLE_PAGE)

  const donut = donutOption(s, theme)
  const line = lineOption(data.current_month, months, theme)

  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <div style={{ width: 9, height: 9, borderRadius: '50%', background: theme.accent }} />
        <div style={{ fontWeight: 700, fontSize: 15 }}>{title}</div>
      </div>

      {/* Summary numbers + donut */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 150px', gap: 12, alignItems: 'center', marginBottom: 8 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <SummaryRow label="Total Villages" value={s.total} bold />
          <SummaryRow label="Approved" value={s.approved} pct={s.approved_pct} color="var(--green)" />
          <SummaryRow label="Remaining" value={s.remaining} pct={s.remaining_pct} color="var(--amber)" />
          <SummaryRow label="Rejected" value={s.rejected} pct={s.rejected_pct} color="var(--red)" />
          <SummaryRow label="No Feedback" value={s.no_feedback} pct={s.no_feedback_pct} color="var(--muted2)" />
        </div>
        <Chart option={donut} height={150} />
      </div>

      {/* Current-month progress */}
      <div style={{ background: theme.soft, borderRadius: 10, padding: '10px 12px', margin: '10px 0 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>Current month approvals ({months.current_label})</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              +{data.current_month.approved_this_month}
              <span style={{ fontSize: 12, fontWeight: 600, marginLeft: 8, color: deltaColor(data.current_month.delta) }}>
                {deltaText(data.current_month)}
              </span>
            </div>
          </div>
        </div>
        <Chart option={line} height={90} />
      </div>

      {/* Per-province table */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600 }}>Per province</div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search province…" style={{ ...input, fontSize: 12, padding: '5px 9px' }} />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Province</Th>
              <Th align="right" onClick={() => setSortKey('total_with_dt')} active={sortKey === 'total_with_dt'}>Villages w/ DT</Th>
              <Th align="right" onClick={() => setSortKey('approved')} active={sortKey === 'approved'}>Approved</Th>
              <Th align="right" onClick={() => setSortKey('remaining')} active={sortKey === 'remaining'}>Remain</Th>
              <Th align="right" onClick={() => setSortKey('rejected')} active={sortKey === 'rejected'}>Reject</Th>
              <Th align="right" onClick={() => setSortKey('no_feedback')} active={sortKey === 'no_feedback'}>No FB</Th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr><td colSpan={6} style={{ padding: 14, color: 'var(--muted)' }}>No provinces.</td></tr>
            ) : shown.map(p => (
              <tr key={p.province} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={td}>{p.province}</td>
                <td style={{ ...td, textAlign: 'right' }}>{p.total_with_dt}</td>
                <NumCell n={p.approved} pct={p.approved_pct} />
                <NumCell n={p.remaining} pct={p.remaining_pct} />
                <NumCell n={p.rejected} pct={p.rejected_pct} />
                <NumCell n={p.no_feedback} pct={p.no_feedback_pct} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > TABLE_PAGE && (
        <button onClick={() => setExpanded(x => !x)} style={linkBtn}>
          {expanded ? 'Show top 5' : `View all provinces (${rows.length})`}
        </button>
      )}
    </div>
  )
}

// ---- chart options ----
function donutOption(s, theme) {
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['58%', '82%'], center: ['50%', '50%'], avoidLabelOverlap: false,
      label: { show: true, position: 'center', formatter: `${s.approved_pct}%`, fontSize: 18, fontWeight: 700, color: '#152238' },
      labelLine: { show: false },
      data: [
        { value: s.approved, name: 'Approved', itemStyle: { color: theme.accent } },
        { value: s.remaining, name: 'Remaining', itemStyle: { color: '#f59e0b' } },
        { value: s.rejected, name: 'Rejected', itemStyle: { color: '#dc2626' } },
        { value: s.no_feedback, name: 'No Feedback', itemStyle: { color: '#cbd5e1' } },
      ],
    }],
  }
}
function lineOption(cm, months, theme) {
  const data = cm.daily_cumulative || []
  return {
    grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: false },
    xAxis: { type: 'category', show: false, data: data.map((_, i) => i + 1) },
    yAxis: { type: 'value', show: false },
    tooltip: { trigger: 'axis', formatter: p => `Day ${p[0].dataIndex + 1}: ${p[0].data} approved` },
    series: [{
      type: 'line', data, smooth: true, symbol: 'none',
      lineStyle: { color: theme.accent, width: 2 },
      areaStyle: { color: theme.soft },
    }],
  }
}

// ---- small pieces ----
function RollupCard({ label, value, color }) {
  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '13px 15px' }}>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value.toLocaleString()}</div>
      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3, lineHeight: 1.3 }}>{label}</div>
    </div>
  )
}
function SummaryRow({ label, value, pct, color, bold }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 12, color: 'var(--muted)' }}>{label}</span>
      <span style={{ fontSize: bold ? 15 : 13, fontWeight: bold ? 700 : 600, color: color || 'var(--ink)' }}>
        {value.toLocaleString()}{pct != null && <span style={{ fontSize: 10.5, color: 'var(--muted2)', marginLeft: 4 }}>{pct}%</span>}
      </span>
    </div>
  )
}
function NumCell({ n, pct }) {
  return <td style={{ ...td, textAlign: 'right' }}>{n}<span style={{ color: 'var(--muted2)', marginLeft: 4, fontSize: 10 }}>{pct}%</span></td>
}
function Th({ children, align, onClick, active }) {
  return (
    <th onClick={onClick}
      style={{ textAlign: align || 'left', padding: '7px 8px', fontSize: 10, color: active ? 'var(--accent)' : 'var(--muted2)',
        textTransform: 'uppercase', letterSpacing: 0.4, fontWeight: 600, cursor: onClick ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
      {children}{onClick && <span style={{ marginLeft: 2 }}>{active ? '▾' : '⇅'}</span>}
    </th>
  )
}
function deltaText(cm) {
  if (cm.delta_pct == null) return `vs ${cm.last_month} last month`
  const sign = cm.delta >= 0 ? '↑' : '↓'
  return `${sign} ${Math.abs(cm.delta_pct)}% vs last month`
}
function deltaColor(delta) { return delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--muted)' }

const input = { padding: '7px 11px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none', fontSize: 12.5 }
const manageBtn = { padding: '7px 14px', borderRadius: 8, border: '1px solid var(--accent)', background: 'transparent', color: 'var(--accent)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }
const td = { padding: '7px 8px' }
const linkBtn = { marginTop: 8, background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12, cursor: 'pointer', padding: 0 }
const errBox = { padding: '12px 16px', borderRadius: 10, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
