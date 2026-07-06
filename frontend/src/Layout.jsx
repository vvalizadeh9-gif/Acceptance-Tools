const ROLE_LABELS = {
  admin: 'Admin', project_manager: 'Project Manager', dt_coordinator: 'DT Coordinator',
  field_subcontractor: 'Field Subcontractor', regional_manager: 'Regional Manager',
  finance: 'Finance', viewer: 'Viewer',
}

// Where clicking the logo takes each role — their Home. For the field roles
// that's the Action Center (their work queue); everyone else lands on their
// own dashboard. Kept in sync with DEFAULT_PAGE_BY_ROLE in App.jsx.
const HOME_BY_ROLE = {
  admin: 'command', project_manager: 'pm', dt_coordinator: 'action',
  field_subcontractor: 'action', regional_manager: 'regional',
  finance: 'command', viewer: 'command',
}

// Admin is deliberately scoped to just these three areas — everything else on
// the platform is operational and not the Admin's job. Order here is the order
// shown in the sidebar.
const ADMIN_NAV = ['command', 'cpmreview', 'users']

export default function Layout({ me, onLogout, active, onNavigate, children }) {
  // No standalone "Action Center" item: it's the Home page for the field
  // roles (reached via the logo), not a tab.
  const nav = [
    { key: 'command', label: 'Command Center', roles: 'all' },
    { key: 'pm', label: 'PM Dashboard', roles: ['admin', 'project_manager'] },
    { key: 'delivery', label: 'Project Delivery', roles: ['admin', 'project_manager'] },
    { key: 'coordinator', label: 'My Area', roles: ['dt_coordinator'] },
    { key: 'contractor', label: 'My Work', roles: ['field_subcontractor'] },
    { key: 'regional', label: 'My Region', roles: ['regional_manager'] },
    { key: 'sites', label: 'Sites & Villages', roles: 'all' },
    { key: 'drivetests', label: 'Drive Tests', roles: 'all' },
    { key: 'acceptance', label: 'Acceptance', roles: 'all' },
    { key: 'letters', label: 'Letters', roles: 'all' },
    { key: 'cpmreview', label: 'CPM Review', roles: ['admin', 'project_manager'] },
    { key: 'users', label: 'User Management', roles: ['admin'] },
  ]

  const isAdmin = me && me.role === 'admin'
  const visibleNav = isAdmin
    ? ADMIN_NAV.map(k => nav.find(n => n.key === k))
    : nav.filter(n => n.roles === 'all' || (me && n.roles.includes(me.role)))

  const home = (me && HOME_BY_ROLE[me.role]) || 'command'

  function handleSignOut() {
    if (window.confirm('Are you sure you want to sign out?')) onLogout()
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '230px 1fr', minHeight: '100vh' }}>
      <aside style={{ background: 'var(--navy)', borderRight: '1px solid var(--line)', padding: '22px 16px', position: 'relative' }}>
        <div onClick={() => onNavigate(home)} title="Home"
          style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 30, padding: '0 6px', cursor: 'pointer' }}>
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
            <button onClick={handleSignOut} style={{ width: '100%', padding: '7px 0', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 12, cursor: 'pointer' }}>Sign out</button>
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
