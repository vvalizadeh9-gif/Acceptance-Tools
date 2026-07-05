import { useEffect, useState } from 'react'
import { listPendingChanges, resolvePendingChange } from './api.js'

const TABS = [
  { key: 'pending', label: 'Pending' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'ignored', label: 'Ignored' },
  { key: 'flagged', label: 'Flagged' },
]

export default function CpmReview({ token, onLogout }) {
  const [tab, setTab] = useState('pending')
  const [changes, setChanges] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  function reload() {
    listPendingChanges(token, tab)
      .then(c => { setChanges(c); setError('') })
      .catch(err => { if (err.message === 'SESSION_EXPIRED') { onLogout(); return }; setError(err.message) })
  }
  useEffect(reload, [token, tab])

  async function resolve(id, decision) {
    setBusy(id)
    try {
      await resolvePendingChange(token, id, decision)
      reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>CPM Change Review</h1>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3, marginBottom: 20 }}>
        When a re-imported CPM file disagrees with a value already approved in the app, it lands here instead of silently overwriting it.
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
                  style={{ ...tabBtn, ...(tab === t.key ? tabBtnActive : {}) }}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <div style={errBox}>{error}</div>}

      {changes === null ? (
        <div style={{ color: 'var(--muted)' }}>Loading…</div>
      ) : changes.length === 0 ? (
        <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--muted)', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12 }}>
          Nothing here.
        </div>
      ) : (
        <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: 'var(--panel2)' }}>
                <Th>Site</Th><Th>Village</Th><Th>Field</Th><Th>App value</Th><Th>CPM value</Th>
                {tab === 'pending' && <Th align="right">Action</Th>}
              </tr>
            </thead>
            <tbody>
              {changes.map(c => (
                <tr key={c.id} style={{ borderTop: '1px solid var(--line)' }}>
                  <td style={{ ...td, fontWeight: 600 }}>{c.site_business_id || '—'}</td>
                  <td style={td}>{c.village_id || '—'}</td>
                  <td style={td}><code style={{ fontSize: 11.5 }}>{c.field_name}</code></td>
                  <td style={td}>{c.old_value ?? <em style={{ color: 'var(--muted2)' }}>empty</em>}</td>
                  <td style={td}>{c.new_value ?? <em style={{ color: 'var(--muted2)' }}>empty</em>}</td>
                  {tab === 'pending' && (
                    <td style={{ ...td, textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button disabled={busy === c.id} onClick={() => resolve(c.id, 'accepted')} style={{ ...smallBtn, background: 'var(--accent)', color: 'white', border: 'none' }}>
                          Accept CPM
                        </button>
                        <button disabled={busy === c.id} onClick={() => resolve(c.id, 'ignored')} style={smallBtn}>
                          Keep app value
                        </button>
                        <button disabled={busy === c.id} onClick={() => resolve(c.id, 'flagged')} style={{ ...smallBtn, color: 'var(--amber)', borderColor: 'var(--amber)' }}>
                          Flag
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Th({ children, align }) {
  return <th style={{ textAlign: align || 'left', padding: '10px 14px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>{children}</th>
}

const td = { padding: '10px 14px' }
const tabBtn = { padding: '7px 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 12.5, cursor: 'pointer' }
const tabBtnActive = { background: 'var(--panel2)', color: 'var(--ink)', fontWeight: 600 }
const smallBtn = { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 11.5, cursor: 'pointer' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 12.5, marginBottom: 16 }
