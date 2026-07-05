import { useEffect, useState } from 'react'
import { getActionCenter } from './api.js'

// How each card's items render — a small, readable summary line per item so
// the inbox is scannable. Inline actions (approve / validate) land with the
// dedicated workflow screens; this is the "what needs me" overview.
function itemLine(key, it) {
  if (key === 'dt_pm_approval' || key === 'dt_validation')
    return `${it.site_business_id} · ${it.site_type} · rev ${it.revision_no} · ${it.delivery_date || '—'}`
  if (key === 'cpm_conflicts')
    return `${it.site_business_id || '—'} · ${it.village_id || '—'} · ${it.field_name}: ${it.old_value ?? '∅'} → ${it.new_value ?? '∅'}`
  if (key === 'waiting_ict' || key === 'waiting_cra')
    return `${it.site_business_id} · ${it.village_id}${it.province_name ? ' · ' + it.province_name : ''}`
  if (key === 'returned_dt' || key === 'awaiting_dt')
    return `${it.site_business_id} · ${it.site_type}`
  return JSON.stringify(it)
}

export default function ActionCenter({ token, onLogout }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  async function load() {
    try {
      setData(await getActionCenter(token))
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') { onLogout(); return }
      setError(err.message)
    }
  }
  useEffect(() => { load() }, [token])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 6 }}>
        <h1 style={{ fontSize: 21, fontWeight: 700 }}>Action Center</h1>
        <button onClick={load} style={ghostBtn}>Refresh</button>
      </div>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 24 }}>
        Everything waiting on you right now — no searching, the system tells you what to do.
      </div>

      {error && <div style={errBox}>{error}</div>}

      {!data ? (
        <div style={{ color: 'var(--muted)' }}>Loading…</div>
      ) : data.cards.length === 0 ? (
        <EmptyState note="Your role has no pending actions here." />
      ) : data.total === 0 ? (
        <EmptyState note="You're all caught up — nothing pending right now." />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
          {data.cards.map(card => (
            <div key={card.key} style={cardStyle}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>{card.title}</div>
                <span style={{ ...badge, background: card.count ? 'var(--accent-soft)' : 'var(--panel2)', color: card.count ? 'var(--accent)' : 'var(--muted2)' }}>
                  {card.count}
                </span>
              </div>
              {card.count === 0 ? (
                <div style={{ fontSize: 12.5, color: 'var(--muted2)' }}>Nothing here.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {card.items.map((it, i) => (
                    <div key={i} style={row}>{itemLine(card.key, it)}</div>
                  ))}
                  {card.count > card.items.length && (
                    <div style={{ fontSize: 11.5, color: 'var(--muted2)', marginTop: 4 }}>
                      +{card.count - card.items.length} more…
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EmptyState({ note }) {
  return (
    <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--muted)', background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12 }}>
      <div style={{ fontSize: 26, marginBottom: 8 }}>✓</div>
      <div style={{ fontSize: 13 }}>{note}</div>
    </div>
  )
}

const cardStyle = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }
const badge = { fontSize: 12, fontWeight: 700, minWidth: 26, textAlign: 'center', padding: '2px 8px', borderRadius: 20 }
const row = { fontSize: 12.5, color: 'var(--muted)', padding: '7px 10px', background: 'var(--panel2)', borderRadius: 7, fontVariantNumeric: 'tabular-nums' }
const ghostBtn = { padding: '7px 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 12.5, cursor: 'pointer' }
const errBox = { padding: '12px 16px', borderRadius: 10, marginBottom: 20, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 13 }
