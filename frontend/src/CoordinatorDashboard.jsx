import { useEffect, useState } from 'react'
import { getCoordinatorDashboard } from './api.js'
import {
  fmt, ago, Section, Kpi, ScopeBar, StatusTable, CrossGaps, MonthlyBox,
  cards, freshness, freshDot, errBox,
} from './RoleDashboardParts.jsx'

export default function CoordinatorDashboard({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getCoordinatorDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>My Area</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>Scoped to the provinces you coordinate.</div>
        </div>
        <div style={freshness}><span style={freshDot} />Data as of&nbsp;<strong style={{ color: 'var(--ink)' }}>{ago(d.generated_at)}</strong></div>
      </div>

      <div style={{ marginTop: 16 }}><ScopeBar who={d.scope.who} provinces={d.scope.provinces} /></div>

      <div style={cards}>
        <Kpi label="Sites in area" value={d.sites} />
        <Kpi label="Villages in area" value={d.villages} />
        <Kpi label="Pending ICT" value={d.pending_ict.total} sub={`${d.pending_ict.pct_of_scope}% of scope`} amber />
        <Kpi label="Pending CRA" value={d.pending_cra.total} sub={`${d.pending_cra.pct_of_scope}% of scope`} amber />
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
