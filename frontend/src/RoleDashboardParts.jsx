// Shared building blocks for the three scoped role dashboards (Coordinator,
// Contractor, Regional Manager) — their payloads share the same
// ict_status_by_province / cra_status_by_region / cross-gap / monthly shape
// (see dashboards.py's _acceptance_summary), so the rendering is shared too.

export function fmt(n) { return n === null || n === undefined ? '—' : n.toLocaleString() }

export function ago(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function Section({ title, note, action, children }) {
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

export function Kpi({ label, value, sub, amber }) {
  return (
    <div style={card}>
      <div style={cardLabel}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, marginTop: 8, color: amber ? 'var(--amber)' : 'var(--ink)' }}>{fmt(value)}</div>
      {sub && <div style={{ fontSize: 11.5, color: 'var(--muted2)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export function ScopeBar({ who, provinces }) {
  return (
    <div style={scopeBar}>
      <strong style={{ color: 'var(--ink)' }}>{who}</strong>
      {provinces && provinces.length > 0 && <>&nbsp;·&nbsp;{provinces.length} provinces: {provinces.join('، ')}</>}
    </div>
  )
}

export function StatusTable({ rows, keyName, keyLabel }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={table}>
        <thead>
          <tr style={{ background: 'var(--panel2)' }}>
            <Th>{keyLabel}</Th><Th right>Total</Th><Th right>Approved</Th><Th right>Rejected</Th><Th right>Pending</Th><Th>Mix</Th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr><td colSpan={6} style={{ ...td, color: 'var(--muted)' }}>No data in scope.</td></tr>
          ) : rows.map(r => (
            <tr key={r[keyName]} style={{ borderTop: '1px solid var(--line-soft)' }}>
              <td style={td}>{r[keyName]}</td>
              <td style={{ ...td, textAlign: 'right' }}>{r.total}</td>
              <td style={{ ...td, textAlign: 'right' }}>{r.approved} <span style={pctStyle}>{r.approved_pct}%</span></td>
              <td style={{ ...td, textAlign: 'right' }}>{r.rejected} <span style={pctStyle}>{r.rejected_pct}%</span></td>
              <td style={{ ...td, textAlign: 'right' }}>{r.pending} <span style={pctStyle}>{r.pending_pct}%</span></td>
              <td style={{ ...td, width: 130 }}>
                <div style={mixTrack}>
                  <div style={{ background: 'var(--green)', width: `${r.approved_pct}%` }} />
                  <div style={{ background: 'var(--red)', width: `${r.rejected_pct}%` }} />
                  <div style={{ background: 'var(--amber)', width: `${r.pending_pct}%` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CrossGaps({ ictNotCra, craNotIct }) {
  return (
    <div style={split}>
      <section style={{ ...gapCard, marginTop: 0 }}>
        <div style={gapHead}>ICT approved, CRA not yet</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '18px 20px' }}>
          <div style={{ fontSize: 30, fontWeight: 800 }}>{fmt(ictNotCra)}</div>
          <div style={{ color: 'var(--muted)', fontSize: 12, maxWidth: 200 }}>villages — CRA is the blocker</div>
        </div>
      </section>
      <section style={{ ...gapCard, marginTop: 0 }}>
        <div style={gapHead}>CRA approved, ICT not yet</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, padding: '18px 20px' }}>
          <div style={{ fontSize: 30, fontWeight: 800 }}>{fmt(craNotIct)}</div>
          <div style={{ color: 'var(--muted)', fontSize: 12, maxWidth: 200 }}>villages — ICT is the blocker</div>
        </div>
      </section>
    </div>
  )
}

export function MonthlyBox({ monthly }) {
  return (
    <Section title="This Month's Approvals" note="month-to-date, within scope">
      <div style={{ ...cards, padding: '16px 20px' }}>
        <Kpi label="ICT approved" value={monthly.ict} sub="this month" />
        <Kpi label="CRA approved" value={monthly.cra} sub="this month" />
        <Kpi label="Total" value={monthly.total} sub="this month" />
      </div>
    </Section>
  )
}

export function Th({ children, right }) {
  return <th style={{ textAlign: right ? 'right' : 'left', padding: '9px 20px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: .6, fontWeight: 600, whiteSpace: 'nowrap' }}>{children}</th>
}

export const cards = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(180px,1fr))', gap: 14 }
export const card = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }
export const cardLabel = { fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .7 }
export const split = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 18 }
export const table = { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }
export const td = { padding: '9px 20px' }
export const pctStyle = { fontSize: 10.5, color: 'var(--muted2)' }
export const mixTrack = { display: 'flex', height: 8, borderRadius: 5, overflow: 'hidden', background: 'var(--panel2)' }
export const gapCard = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }
export const gapHead = { padding: '13px 20px', borderBottom: '1px solid var(--line)', fontSize: 13, fontWeight: 700 }
export const freshness = { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--muted)', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 20, padding: '7px 14px', whiteSpace: 'nowrap' }
export const freshDot = { width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 0 3px var(--green-soft)', marginRight: 4 }
export const scopeBar = { display: 'inline-block', fontSize: 12.5, color: 'var(--muted)', background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 20, padding: '8px 16px', marginBottom: 18 }
export const errBox = { padding: '12px 16px', borderRadius: 10, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
