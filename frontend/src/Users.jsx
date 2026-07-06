import { useEffect, useState } from 'react'
import { toJalaali } from 'jalaali-js'
import { listUsers, createUser, updateUser, getSiteFilterOptions, listProvinces, updateProvince } from './api.js'
import { ROLE_LABELS } from './Layout.jsx'

const ROLES = ['admin', 'project_manager', 'dt_coordinator', 'field_subcontractor', 'regional_manager', 'finance', 'viewer']

// Business priority for the sorted list — Admin at the top, Viewer at the
// bottom. Anything unexpected sorts after the known roles.
const ROLE_ORDER = Object.fromEntries(ROLES.map((r, i) => [r, i]))

const JMONTHS = ['Farvardin', 'Ordibehesht', 'Khordad', 'Tir', 'Mordad', 'Shahrivar',
  'Mehr', 'Aban', 'Azar', 'Dey', 'Bahman', 'Esfand']

// Gregorian ISO timestamp -> Shamsi "12 Tir 1405", matching the dashboards.
function shamsiDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const { jy, jm, jd } = toJalaali(d.getFullYear(), d.getMonth() + 1, d.getDate())
  return `${jd} ${JMONTHS[jm - 1]} ${jy}`
}

function fieldForRole(role) {
  if (role === 'regional_manager') return 'regional_manager_id'
  if (role === 'dt_coordinator') return 'pso_coordinator_id'
  return null
}

export default function Users({ token, onLogout }) {
  const [users, setUsers] = useState(null)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState(null) // user object being edited
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')

  async function load() {
    try {
      setUsers(await listUsers(token))
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') { onLogout(); return }
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [token])

  // Sorted by role priority, then by name — so all the Admins group together,
  // then PMs, and so on. Search matches name/email; the dropdown filters role.
  const visible = (users || [])
    .filter(u => roleFilter === 'all' || u.role === roleFilter)
    .filter(u => {
      if (!search) return true
      const q = search.toLowerCase()
      return (u.full_name || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
    })
    .sort((a, b) =>
      (ROLE_ORDER[a.role] ?? 99) - (ROLE_ORDER[b.role] ?? 99) ||
      (a.full_name || '').localeCompare(b.full_name || '')
    )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 20, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>User Management</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>
            Create and manage accounts across all roles. Edit a Regional Manager or DT Coordinator to choose which provinces they cover.
          </div>
        </div>
        <button onClick={() => setShowCreate(true)} style={primaryBtn}>+ New user</button>
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or email…"
          style={{ ...input, width: 240, padding: '7px 11px' }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)} style={{ ...input, width: 'auto', padding: '7px 11px' }}>
          <option value="all">All roles</option>
          {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
        </select>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
          {users === null ? '' : `${visible.length} of ${users.length}`}
        </span>
      </div>

      {/* The table body scrolls on its own so a long list never pushes the
          page around — the header row stays pinned. */}
      <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ maxHeight: 'calc(100vh - 250px)', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'var(--panel2)' }}>
                <Th>Name</Th><Th>Email</Th><Th>Phone</Th><Th>Role</Th><Th>Created</Th><Th>Status</Th><Th></Th>
              </tr>
            </thead>
            <tbody>
              {users === null ? (
                <tr><td colSpan={7} style={{ padding: 20, color: 'var(--muted)' }}>Loading…</td></tr>
              ) : visible.length === 0 ? (
                <tr><td colSpan={7} style={{ padding: 20, color: 'var(--muted)' }}>No matching users.</td></tr>
              ) : visible.map(u => (
                <tr key={u.id} style={{ borderTop: '1px solid var(--line)' }}>
                  <td style={td}>{u.full_name}</td>
                  <td style={{ ...td, color: 'var(--muted)' }}>{u.email}</td>
                  <td style={{ ...td, color: 'var(--muted)' }}>{u.phone || '—'}</td>
                  <td style={td}>{ROLE_LABELS[u.role] || u.role}</td>
                  <td style={{ ...td, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{shamsiDate(u.created_at)}</td>
                  <td style={td}>
                    <span style={{
                      fontSize: 11.5, padding: '3px 9px', borderRadius: 12,
                      background: u.is_active ? 'var(--green-soft)' : 'var(--red-soft)',
                      color: u.is_active ? 'var(--green)' : 'var(--red)',
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
  const [firstName, setFirstName] = useState(user?.first_name || '')
  const [lastName, setLastName] = useState(user?.last_name || '')
  const [phone, setPhone] = useState(user?.phone || '')
  const [role, setRole] = useState(user?.role || 'viewer')
  const [regionName, setRegionName] = useState(user?.region_name || '')
  const [regions, setRegions] = useState([])
  const [isActive, setIsActive] = useState(user?.is_active ?? true)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const [provinces, setProvinces] = useState([])
  const [selectedProvinceIds, setSelectedProvinceIds] = useState([])
  const needsProvinces = role === 'regional_manager' || role === 'dt_coordinator'

  useEffect(() => {
    getSiteFilterOptions(token).then(o => setRegions(o.regions)).catch(() => {})
    listProvinces(token).then(setProvinces).catch(() => {})
  }, [token])

  // Pre-check whichever provinces this user already owns for the currently
  // selected role — recomputes if the admin switches the role dropdown.
  useEffect(() => {
    const field = fieldForRole(role)
    if (mode === 'edit' && user && field) {
      setSelectedProvinceIds(provinces.filter(p => p[field] === user.id).map(p => p.id))
    } else {
      setSelectedProvinceIds([])
    }
  }, [role, provinces, mode])

  async function save() {
    setError(''); setSaving(true)
    try {
      let savedUser
      if (mode === 'create') {
        const payload = { email, first_name: firstName, last_name: lastName, phone, role, password }
        if (role === 'regional_manager' && regionName) payload.region_name = regionName
        savedUser = await createUser(token, payload)
      } else {
        const payload = { first_name: firstName, last_name: lastName, phone, role, is_active: isActive }
        if (password) payload.password = password
        if (role === 'regional_manager' && regionName) payload.region_name = regionName
        savedUser = await updateUser(token, user.id, payload)
      }

      // Apply add/remove province diffs for the CURRENT role.
      const field = fieldForRole(role)
      if (field) {
        const originallyAssigned = mode === 'edit' ? provinces.filter(p => p[field] === user.id).map(p => p.id) : []
        const toAdd = selectedProvinceIds.filter(id => !originallyAssigned.includes(id))
        const toRemove = originallyAssigned.filter(id => !selectedProvinceIds.includes(id))
        const otherField = field === 'regional_manager_id' ? 'pso_coordinator_id' : 'regional_manager_id'
        for (const pid of toAdd) {
          const prov = provinces.find(p => p.id === pid)
          await updateProvince(token, pid, { [field]: savedUser.id, [otherField]: prov[otherField] })
        }
        for (const pid of toRemove) {
          const prov = provinces.find(p => p.id === pid)
          await updateProvince(token, pid, { [field]: null, [otherField]: prov[otherField] })
        }
      }
      // If the role just changed AWAY from a province-scoped one, clear any
      // stale assignments left over from the PREVIOUS role.
      if (mode === 'edit' && user) {
        const prevField = fieldForRole(user.role)
        if (prevField && prevField !== field) {
          const otherField = prevField === 'regional_manager_id' ? 'pso_coordinator_id' : 'regional_manager_id'
          for (const prov of provinces.filter(p => p[prevField] === user.id)) {
            await updateProvince(token, prov.id, { [prevField]: null, [otherField]: prov[otherField] })
          }
        }
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
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label="First name">
            <input value={firstName} onChange={e => setFirstName(e.target.value)} style={input} />
          </Field>
          <Field label="Last name">
            <input value={lastName} onChange={e => setLastName(e.target.value)} style={input} />
          </Field>
        </div>
        <Field label="Phone">
          <input value={phone} onChange={e => setPhone(e.target.value)} style={input} placeholder="09xxxxxxxxx" />
        </Field>
        <Field label="Role">
          <select value={role} onChange={e => setRole(e.target.value)} style={input}>
            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
        </Field>
        {role === 'regional_manager' && (
          <Field label="Region (legacy — scopes the Sites & Villages list)">
            <select value={regionName} onChange={e => setRegionName(e.target.value)} style={input}>
              <option value="">Select a region…</option>
              {regions.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
        )}
        {needsProvinces && (
          <Field label={`Provinces covered (${role === 'regional_manager' ? 'Regional Manager' : 'PSO Coordinator'} dashboards)`}>
            <select
              multiple
              value={selectedProvinceIds}
              onChange={e => setSelectedProvinceIds(Array.from(e.target.selectedOptions, o => o.value))}
              style={{ ...input, height: 168 }}
            >
              {provinces.map(p => (
                <option key={p.id} value={p.id}>{p.name} — {p.cra_region}</option>
              ))}
            </select>
            <div style={{ fontSize: 11, color: 'var(--muted2)', marginTop: 5 }}>
              Ctrl/Cmd-click (or Shift-click) to select multiple. This is what scopes their dashboard, separate from Region above.
            </div>
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
  return <th style={{ textAlign: 'left', padding: '11px 16px', fontSize: 11, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600, position: 'sticky', top: 0, background: 'var(--panel2)', zIndex: 1 }}>{children}</th>
}

const td = { padding: '12px 16px' }
const primaryBtn = { padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'white', fontWeight: 600, fontSize: 13, cursor: 'pointer' }
const ghostBtn = { padding: '9px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 13, cursor: 'pointer' }
const smallBtn = { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12, cursor: 'pointer' }
const input = { width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 12.5, marginBottom: 16 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: '26px 28px', width: 440, maxHeight: '90vh', overflowY: 'auto' }
