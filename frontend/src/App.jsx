import { useEffect, useState } from 'react'
import { getMe } from './api.js'
import Login from './Login.jsx'
import Layout from './Layout.jsx'
import ActionCenter from './ActionCenter.jsx'
import Dashboard from './Dashboard.jsx'
import Users from './Users.jsx'
import Sites from './Sites.jsx'
import PmDashboard from './PmDashboard.jsx'
import ProjectDelivery from './ProjectDelivery.jsx'
import CoordinatorDashboard from './CoordinatorDashboard.jsx'
import ContractorDashboard from './ContractorDashboard.jsx'
import RegionalDashboard from './RegionalDashboard.jsx'
import Acceptance from './Acceptance.jsx'
import AcceptanceDashboard from './AcceptanceDashboard.jsx'
import DriveTests from './DriveTests.jsx'
import Letters from './Letters.jsx'
import CpmReview from './CpmReview.jsx'

// Where each role lands right after login — "their area", not a generic
// screen they have to navigate away from.
const DEFAULT_PAGE_BY_ROLE = {
  admin: 'command',
  project_manager: 'pm',
  dt_coordinator: 'action',
  field_subcontractor: 'action',
  regional_manager: 'regional',
  finance: 'command',
  viewer: 'command',
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('uso_token'))
  const [me, setMe] = useState(null)
  const [meError, setMeError] = useState(false)
  const [page, setPage] = useState(null) // null until the role-based default is known

  useEffect(() => {
    if (!token) { setMe(null); return }
    getMe(token).then(user => {
      setMe(user)
      setPage(prev => prev || DEFAULT_PAGE_BY_ROLE[user.role] || 'command')
    }).catch(err => {
      if (err.message === 'SESSION_EXPIRED') handleLogout()
      else setMeError(true)
    })
  }, [token])

  function handleLoggedIn(newToken) {
    localStorage.setItem('uso_token', newToken)
    setPage(null) // land on this account's own default, not whatever page was open before
    setToken(newToken)
  }
  function handleLogout() {
    localStorage.removeItem('uso_token')
    setToken(null)
    setMe(null)
  }

  if (!token) return <Login onLoggedIn={handleLoggedIn} />
  if (meError) return <div style={{ padding: 40, color: 'var(--muted)' }}>Couldn't load your profile. Try refreshing.</div>
  if (!me || !page) return <div style={{ padding: 40, color: 'var(--muted)' }}>Loading…</div>

  let content
  if (page === 'users') content = <Users token={token} onLogout={handleLogout} />
  else if (page === 'action') content = <ActionCenter token={token} onLogout={handleLogout} />
  else if (page === 'command') content = <Dashboard token={token} onLogout={handleLogout} />
  else if (page === 'pm') content = <PmDashboard token={token} onLogout={handleLogout} />
  else if (page === 'delivery') content = <ProjectDelivery token={token} onLogout={handleLogout} />
  else if (page === 'coordinator') content = <CoordinatorDashboard token={token} onLogout={handleLogout} />
  else if (page === 'contractor') content = <ContractorDashboard token={token} onLogout={handleLogout} />
  else if (page === 'regional') content = <RegionalDashboard token={token} onLogout={handleLogout} />
  else if (page === 'sites') content = <Sites token={token} onLogout={handleLogout} />
  else if (page === 'acceptance') content = <AcceptanceDashboard token={token} onLogout={handleLogout} onManage={() => setPage('acceptance_edit')} />
  else if (page === 'acceptance_edit') content = <Acceptance token={token} onLogout={handleLogout} onBack={() => setPage('acceptance')} />
  else if (page === 'drivetests') content = <DriveTests token={token} onLogout={handleLogout} />
  else if (page === 'letters') content = <Letters token={token} onLogout={handleLogout} />
  else if (page === 'cpmreview') content = <CpmReview token={token} onLogout={handleLogout} />
  else content = <Placeholder page={page} />

  return (
    <Layout me={me} onLogout={handleLogout} active={page} onNavigate={setPage}>
      {content}
    </Layout>
  )
}

function Placeholder({ page }) {
  const titles = { sites: 'Sites & Villages', drivetests: 'Drive Tests', acceptance: 'Acceptance', letters: 'Letters' }
  return (
    <div>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{titles[page] || page}</h1>
      <div style={{ marginTop: 20, padding: '13px 16px', borderRadius: 10, fontSize: 13, color: 'var(--muted)', background: 'var(--accent-soft)', border: '1px solid var(--accent-dim)' }}>
        This feature is coming in a later chunk. User Management and the dashboard are live now.
      </div>
    </div>
  )
}
