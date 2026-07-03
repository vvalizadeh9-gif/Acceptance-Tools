import { useEffect, useState } from 'react'
import { getMe } from './api.js'

const ROLE_LABELS = {
  admin: 'Admin', project_manager: 'Project Manager', dt_coordinator: 'DT Coordinator',
  field_subcontractor: 'Field Subcontractor', regional_manager: 'Regional Manager', viewer: 'Viewer',
}

export default function Layout({ token, onLogout, active, onNavigate, children }) {
  const [me, setMe] = useState(null)

  useEffect(() => {
    getMe(token).then(setMe).catch(err => {
      if (err.message === 'SESSION_EXPIRED') onLogout()
    })
  }, [token])

  const nav = [
    { key: 'command', label: 'Command Center', roles: 'all' },
    { key: 'sites', label: 'Sites & Villages', roles: 'all' },
    { key: 'drivetests', label: 'Drive Tests', roles: 'all' },
    { key: 'acceptance', label: 'Acceptance', roles: 'all' },
    { key: 'letters', label: 'Letters', roles: 'all' },
    { key: 'users', label: 'User Management', roles: ['admin'] },
  ]

  const visibleNav = nav.filter(n => n.roles === 'all' || (me && n.roles.includes(me.role)))

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '230px 1fr', minHeight: '100vh' }}>
      <aside style={{ background: 'var(--navy)', borderRight: '1px solid var(--line)', padding: '22px 16px', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 30, padding: '0 6px' }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14.5 }}>USO Platform</div>
            <div style={{ fontSize: 10, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 1 }}>Delivery &amp; Acceptance</div>
          </div>
        </div>

        {visibleNav.map(n => (
          <div key={n.key} onClick={() => onNavigate(n.key)}
            style={{
              padding: '9px 12px', borderRadius: 8, fontSize: 13.5, marginBottom: 4, cursor: 'pointer',
              background: active === n.key ? 'var(--panel2)' : 'transparent',
              color: active === n.key ? 'var(--ink)' : 'var(--muted)',
            }}>
            {n.label}
          </div>
        ))}

        {me && (
          <div style={{ position: 'absolute', bottom: 22, left: 16, right: 16, background: 'var(--navy2)', border: '1px solid var(--line)', borderRadius: 10, padding: 12 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>{me.full_name}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>{ROLE_LABELS[me.role] || me.role}</div>
            <button onClick={onLogout} style={{ width: '100%', padding: '7px 0', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 12, cursor: 'pointer' }}>Sign out</button>
          </div>
        )}
      </aside>

      <main style={{ padding: '28px 34px' }}>
        {children}
      </main>
    </div>
  )
}

export { ROLE_LABELS }
