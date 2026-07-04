import { useEffect, useState } from 'react'
import { getContractorDashboard } from './api.js'
import {
  fmt, ago, Section, Kpi, StatusTable, CrossGaps, MonthlyBox,
  cards, scopeBar, freshness, freshDot, errBox,
} from './RoleDashboardParts.jsx'

export default function ContractorDashboard({ token, onLogout }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getContractorDashboard(token)
      .then(setD)
      .catch(err => { if (err.message === 'SESSION_EXPIRED') onLogout(); else setError(err.message) })
  }, [token])

  if (error) return <div style={errBox}>{error}</div>
  if (!d) return <div style={{ color: 'var(--muted)' }}>Loading…</div>

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>My Work</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>Scoped to sites currently assigned to you.</div>
        </div>
        <div style={freshness}><span style={freshDot} />Data as of&nbsp;<strong style={{ color: 'var(--ink)' }}>{ago(d.generated_at)}</strong></div>
      </div>

      <div style={{ marginTop: 16 }}><div style={scopeBar}><strong style={{ color: 'var(--ink)' }}>{d.scope.who}</strong></div></div>

      <div style={cards}>
        <Kpi label="Total Assignment" value={d.assignment.sites} sub={`${fmt(d.assignment.villages)} villages`} />
        <Kpi label="DT Done" value={d.dt_done.sites} sub={`${fmt(d.dt_done.villages)} villages`} />
        <Kpi label="DT Remain" value={d.dt_remain.sites} sub={`${fmt(d.dt_remain.villages)} villages`} amber />
        <Kpi label="Pending ICT / CRA" value={`${d.pending_ict.total} / ${d.pending_cra.total}`} sub="villages" />
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
