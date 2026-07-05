import { useEffect, useState } from 'react'
import { login, getCaptcha } from './api.js'

export default function Login({ onLoggedIn }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [captchaCode, setCaptchaCode] = useState('')
  const [captcha, setCaptcha] = useState(null) // { captcha_token, image }
  const [captchaLoading, setCaptchaLoading] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function loadCaptcha() {
    setCaptchaLoading(true)
    setCaptchaCode('')
    try {
      setCaptcha(await getCaptcha())
    } catch (err) {
      setError(err.message)
    } finally {
      setCaptchaLoading(false)
    }
  }
  useEffect(() => { loadCaptcha() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { access_token } = await login(email, password, captcha?.captcha_token, captchaCode)
      onLoggedIn(access_token)
    } catch (err) {
      setError(err.message)
      loadCaptcha() // any failure -> a fresh code, so a stale/used one never blocks the next try
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={page}>
      <div style={card}>
        {/* Brand panel */}
        <div style={brandPanel}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={logoDot} />
              <div style={{ fontWeight: 700, fontSize: 18, color: '#fff' }}>USO Tools</div>
            </div>
            <div style={{ color: 'rgba(255,255,255,.82)', fontSize: 13, marginTop: 10, lineHeight: 1.6 }}>
              Operations Command Center for the nationwide USO deployment —
              Drive Test, Acceptance, and delivery in one place.
            </div>
          </div>
          <div style={{ color: 'rgba(255,255,255,.6)', fontSize: 11.5 }}>
            MTN Irancell · Universal Service Obligation
          </div>
        </div>

        {/* Form panel */}
        <form onSubmit={handleSubmit} style={formPanel}>
          <div style={{ fontWeight: 700, fontSize: 17 }}>Sign in</div>
          <div style={{ color: 'var(--muted)', fontSize: 12.5, marginTop: 4, marginBottom: 22 }}>
            Use your work account to continue.
          </div>

          <Label>Email</Label>
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
                 placeholder="you@mtnirancell.ir" style={input} autoComplete="username" />

          <Label style={{ marginTop: 16 }}>Password</Label>
          <input type="password" required value={password} onChange={e => setPassword(e.target.value)}
                 placeholder="••••••••" style={input} autoComplete="current-password" />

          <Label style={{ marginTop: 16 }}>Security code</Label>
          <div style={{ display: 'flex', gap: 10, alignItems: 'stretch' }}>
            <input required value={captchaCode} onChange={e => setCaptchaCode(e.target.value)}
                   placeholder="Type the code" style={{ ...input, flex: 1 }} autoComplete="off"
                   autoCapitalize="characters" spellCheck={false} />
            <div style={captchaBox} title="Security code">
              {captcha
                ? <img src={captcha.image} alt="security code" style={{ display: 'block', height: 40 }} />
                : <span style={{ color: 'var(--muted2)', fontSize: 11 }}>…</span>}
            </div>
            <button type="button" onClick={loadCaptcha} disabled={captchaLoading}
                    title="Get a new code" style={refreshBtn}>
              {captchaLoading ? '…' : '↻'}
            </button>
          </div>

          {error && <div style={errorBox}>{error}</div>}

          <button type="submit" disabled={loading} style={{ ...submitBtn, opacity: loading ? 0.7 : 1 }}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

function Label({ children, style }) {
  return <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6, ...style }}>{children}</label>
}

const page = {
  minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
  background: 'radial-gradient(1200px 600px at 20% -10%, #e8efff 0%, var(--canvas) 55%)',
  padding: 20,
}
const card = {
  display: 'grid', gridTemplateColumns: 'minmax(0, 300px) minmax(0, 380px)',
  background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 18,
  overflow: 'hidden', boxShadow: '0 24px 60px -24px rgba(21,34,56,.28)', maxWidth: '94vw',
}
const brandPanel = {
  background: 'linear-gradient(160deg, #2563eb 0%, #1e3a8a 100%)',
  padding: '34px 30px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
  minHeight: 420,
}
const logoDot = { width: 12, height: 12, borderRadius: '50%', background: '#fff', boxShadow: '0 0 0 4px rgba(255,255,255,.25)' }
const formPanel = { padding: '38px 34px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }
const input = {
  width: '100%', padding: '11px 13px', borderRadius: 9,
  border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none',
}
const captchaBox = {
  width: 120, display: 'flex', alignItems: 'center', justifyContent: 'center',
  border: '1px solid var(--line)', borderRadius: 9, background: 'var(--panel2)',
}
const refreshBtn = {
  width: 42, borderRadius: 9, border: '1px solid var(--line)', background: 'var(--panel2)',
  color: 'var(--accent)', fontSize: 18, cursor: 'pointer',
}
const errorBox = {
  marginTop: 16, padding: '10px 12px', borderRadius: 9, fontSize: 12.5,
  background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)',
}
const submitBtn = {
  width: '100%', marginTop: 22, padding: '12px 0', borderRadius: 10, border: 'none',
  background: 'var(--accent)', color: 'white', fontWeight: 600, cursor: 'pointer', fontSize: 14,
}
