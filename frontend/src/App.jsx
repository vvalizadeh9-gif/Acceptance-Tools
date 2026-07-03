import { useState } from 'react'
import Login from './Login.jsx'
import Layout from './Layout.jsx'
import Dashboard from './Dashboard.jsx'
import Users from './Users.jsx'
import Sites from './Sites.jsx'
import PmDashboard from './PmDashboard.jsx'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('uso_token'))
  const [page, setPage] = useState('command')

  function handleLoggedIn(newToken) {
    localStorage.setItem('uso_token', newToken)
    setToken(newToken)
    setPage('command')
  }
  function handleLogout() {
    localStorage.removeItem('uso_token')
    setToken(null)
  }

  if (!token) return <Login onLoggedIn={handleLoggedIn} />

  let content
  if (page === 'users') content = <Users token={token} onLogout={handleLogout} />
  else if (page === 'command') content = <Dashboard token={token} onLogout={handleLogout} />
  else if (page === 'pm') content = <PmDashboard token={token} onLogout={handleLogout} />
  else if (page === 'sites') content = <Sites token={token} onLogout={handleLogout} />
  else content = <Placeholder page={page} />

  return (
    <Layout token={token} onLogout={handleLogout} active={page} onNavigate={setPage}>
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
