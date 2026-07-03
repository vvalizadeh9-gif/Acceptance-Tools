import { useEffect, useState } from 'react'
import { listUsers, createUser, updateUser, getSiteFilterOptions } from './api.js'
import { ROLE_LABELS } from './Layout.jsx'

const ROLES = ['admin', 'project_manager', 'dt_coordinator', 'field_subcontractor', 'regional_manager', 'viewer']

export default function Users({ token, onLogout }) {
  const [users, setUsers] = useState(null)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null) // user object being edited

  async function load() {
    try {
      setUsers(await listUsers(token))
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') { onLogout(); return }
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [token])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>User Management</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>
            Create and manage accounts across all roles.
          </div>
        </div>
        <button onClick={() => setShowCreate(true)} style={primaryBtn}>+ New user</button>
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Name</Th><Th>Email</Th><Th>Role</Th><Th>Status</Th><Th></Th>
            </tr>
          </thead>
          <tbody>
            {users === null ? (
              <tr><td colSpan={5} style={{ padding: 20, color: 'var(--muted)' }}>Loading…</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: 20, color: 'var(--muted)' }}>No users yet.</td></tr>
            ) : users.map(u => (
              <tr key={u.id} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={td}>{u.full_name}</td>
                <td style={{ ...td, color: 'var(--muted)' }}>{u.email}</td>
                <td style={td}>{ROLE_LABELS[u.role] || u.role}</td>
                <td style={td}>
                  <span style={{
                    fontSize: 11.5, padding: '3px 9px', borderRadius: 12,
                    background: u.is_active ? 'rgba(34,197,94,.15)' : 'rgba(239,68,68,.15)',
                    color: u.is_active ? '#4ade80' : '#f87171',
                  }}>
                    {u.is_active ? 'Active' : 'Disabled'}
                  </span>
                </td>
                <td style={{ ...td, textAlign: 'right' }}>
                  <button onClick={() => setEditing(u)} style={smallBtn}>Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <UserForm
          token={token} mode="create"
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); load() }}
        />
      )}
      {editing && (
        <UserForm
          token={token} mode="edit" user={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load() }}
        />
      )}
    </div>
  )
}

function UserForm({ token, mode, user, onClose, onSaved }) {
  const [email, setEmail] = useState(user?.email || '')
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [role, setRole] = useState(user?.role || 'viewer')
  const [regionName, setRegionName] = useState(user?.region_name || '')
  const [regions, setRegions] = useState([])
  const [isActive, setIsActive] = useState(user?.is_active ?? true)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getSiteFilterOptions(token).then(o => setRegions(o.regions)).catch(() => {})
  }, [token])

  async function save() {
    setError(''); setSaving(true)
    try {
      if (mode === 'create') {
        const payload = { email, full_name: fullName, role, password }
        if (role === 'regional_manager' && regionName) payload.region_name = regionName
        await createUser(token, payload)
      } else {
        const payload = { full_name: fullName, role, is_active: isActive }
        if (password) payload.password = password
        if (role === 'regional_manager' && regionName) payload.region_name = regionName
        await updateUser(token, user.id, payload)
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
          {mode === 'create' ? 'Create new user' : 'Edit user'}
        </h3>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 20 }}>
          {mode === 'edit' ? user.email : 'They will sign in with this email and password.'}
        </div>

        {mode === 'create' && (
          <Field label="Email">
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} style={input} placeholder="name@mtnirancell.ir" />
          </Field>
        )}
        <Field label="Full name">
          <input value={fullName} onChange={e => setFullName(e.target.value)} style={input} />
        </Field>
        <Field label="Role">
          <select value={role} onChange={e => setRole(e.target.value)} style={input}>
            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </Field>
        {role === 'regional_manager' && (
          <Field label="Region (required for Regional Manager)">
            <select value={regionName} onChange={e => setRegionName(e.target.value)} style={input}>
              <option value="">Select a region…</option>
              {regions.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
        )}
        <Field label={mode === 'create' ? 'Password' : 'New password (leave blank to keep current)'}>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={input} placeholder="At least 8 characters" />
        </Field>
        {mode === 'edit' && (
          <Field label="Status">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--muted)' }}>
              <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
              Account active (uncheck to disable login)
            </label>
          </Field>
        )}

        {error && <div style={{ ...errBox, marginTop: 8 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={ghostBtn}>Cancel</button>
          <button onClick={save} disabled={saving} style={{ ...primaryBtn, opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Saving…' : mode === 'create' ? 'Create user' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  )
}
function Th({ children }) {
  return <th style={{ textAlign: 'left', padding: '11px 16px', fontSize: 11, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>{children}</th>
}

const td = { padding: '12px 16px' }
const primaryBtn = { padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'white', fontWeight: 600, fontSize: 13, cursor: 'pointer' }
const ghostBtn = { padding: '9px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 13, cursor: 'pointer' }
const smallBtn = { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12, cursor: 'pointer' }
const input = { width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5', fontSize: 12.5, marginBottom: 16 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: '26px 28px', width: 440, maxHeight: '90vh', overflowY: 'auto' }
