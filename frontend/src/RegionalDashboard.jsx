import { useEffect, useState } from 'react'
import { getRegionalDashboard } from './api.js'
import {
  fmt, ago, Section, Kpi, ScopeBar, StatusTable, CrossGaps, MonthlyBox,
  cards, freshness, freshDot, errBox,
} from './RoleDashboardParts.jsx'

export default function RegionalDashboard({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getRegionalDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>My Region</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>Scoped to the provinces in your region.</div>
        </div>
        <div style={freshness}><span style={freshDot} />Data as of&nbsp;<strong style={{ color: 'var(--ink)' }}>{ago(d.generated_at)}</strong></div>
      </div>

      <div style={{ marginTop: 16 }}><ScopeBar who={d.scope.who} provinces={d.scope.provinces} /></div>

      <div style={cards}>
        <Kpi label="Total On-Air" value={d.totals.on_air} />
        <Kpi label="Total Drive Test" value={d.totals.dt_done} />
        <Kpi label="Total ICT Approved" value={d.totals.ict_approved} />
        <Kpi label="Total CRA Approved" value={d.totals.cra_approved} />
      </div>

      <Section title="Full Status of ICT" note="per province">
        <StatusTable rows={d.ict_status_by_province} keyName="province" keyLabel="Province" />
      </Section>
      <Section title="Full Status of CRA" note="per CRA region">
        <StatusTable rows={d.cra_status_by_region} keyName="cra_region" keyLabel="CRA Region" />
      </Section>

      <CrossGaps ictNotCra={d.ict_approved_cra_not} craNotIct={d.cra_approved_ict_not} />
      <MonthlyBox monthly={d.monthly_approvals} />
    </div>
  )
}
