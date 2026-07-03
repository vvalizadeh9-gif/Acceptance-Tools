import { useState } from 'react'
import { login } from './api.js'

export default function Login({ onLoggedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await login(email, password)
      onLoggedIn(access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--canvas)',
    }}>
      <form onSubmit={handleSubmit} style={{
        background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14,
        padding: '36px 34px', width: 360,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)' }} />
          <div style={{ fontWeight: 700, fontSize: 16 }}>USO Platform</div>
        </div>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 26 }}>
          Delivery &amp; Acceptance Management
        </div>

        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>Email</label>
        <input
          type="email" required value={email} onChange={e => setEmail(e.target.value)}
          placeholder="you@mtnirancell.ir"
          style={inputStyle}
        />

        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', margin: '16px 0 6px' }}>Password</label>
        <input
          type="password" required value={password} onChange={e => setPassword(e.target.value)}
          placeholder="••••••••"
          style={inputStyle}
        />

        {error && (
          <div style={{
            marginTop: 16, padding: '10px 12px', borderRadius: 8, fontSize: 12.5,
            background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5',
          }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} style={{
          width: '100%', marginTop: 22, padding: '11px 0', borderRadius: 9, border: 'none',
          background: loading ? 'var(--accent-dim)' : 'var(--accent)', color: 'white', fontWeight: 600,
          cursor: loading ? 'default' : 'pointer', fontSize: 14,
        }}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '10px 12px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)',
  outline: 'none',
}
