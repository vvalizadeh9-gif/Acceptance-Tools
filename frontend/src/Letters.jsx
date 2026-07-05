import { useEffect, useState } from 'react'
import { listLetters, createLetter, listAcceptance, getMe } from './api.js'

const ORGANIZATIONS = ['ICT Province', 'ICT HQ', 'CRA Region', 'CRA HQ']

export default function Letters({ token, onLogout }) {
  const [letters, setLetters] = useState(null)
  const [me, setMe] = useState(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => { getMe(token).then(setMe).catch(() => {}) }, [token])

  function reload() {
    listLetters(token, search)
      .then(l => { setLetters(l); setError('') })
      .catch(err => { if (err.message === 'SESSION_EXPIRED') { onLogout(); return }; setError(err.message) })
  }
  useEffect(reload, [token, search])

  const canCreate = me && (me.role === 'admin' || me.role === 'dt_coordinator')

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 22 }}>
        <div>
          <h1 style={{ fontSize: 21, fontWeight: 700 }}>Letters</h1>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3 }}>
            One official letter can clear one village or thousands at once.
          </div>
        </div>
        {canCreate && <button onClick={() => setShowCreate(true)} style={primaryBtn}>+ New letter</button>}
      </div>

      <div style={{ marginBottom: 16 }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by letter number…" style={{ ...input, width: 260 }} />
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Letter Number</Th><Th>Date</Th><Th>Organization</Th><Th align="right">Villages</Th><Th>Comment</Th>
            </tr>
          </thead>
          <tbody>
            {letters === null ? (
              <tr><td colSpan={5} style={{ padding: 20, color: 'var(--muted)' }}>Loading…</td></tr>
            ) : letters.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: 20, color: 'var(--muted)' }}>No letters yet.</td></tr>
            ) : letters.map(l => (
              <tr key={l.id} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={{ ...td, fontWeight: 600 }}>{l.letter_number}</td>
                <td style={td}>{l.letter_date}</td>
                <td style={td}>
                  <span style={{
                    fontSize: 11, padding: '3px 9px', borderRadius: 12,
                    background: l.organization.startsWith('ICT') ? 'var(--accent-soft)' : 'rgba(147,51,234,.12)',
                    color: l.organization.startsWith('ICT') ? 'var(--accent)' : '#9333ea',
                  }}>
                    {l.organization}
                  </span>
                </td>
                <td style={{ ...td, textAlign: 'right' }}>{l.village_count.toLocaleString()}</td>
                <td style={{ ...td, color: 'var(--muted)' }}>{l.comment || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateLetterModal token={token} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); reload() }} />
      )}
    </div>
  )
}

function CreateLetterModal({ token, onClose, onCreated }) {
  const [letterNumber, setLetterNumber] = useState('')
  const [letterDate, setLetterDate] = useState('')
  const [organization, setOrganization] = useState(ORGANIZATIONS[0])
  const [comment, setComment] = useState('')
  const [villageSearch, setVillageSearch] = useState('')
  const [villages, setVillages] = useState(null)
  const [selected, setSelected] = useState({}) // id -> village row
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const side = organization.startsWith('ICT') ? 'ict_final' : 'cra_final'
    listAcceptance(token, { search: villageSearch, page_size: 50, [side]: 'false' })
      .then(d => setVillages(d.items))
      .catch(err => setError(err.message))
  }, [token, villageSearch, organization])

  function toggle(v) {
    setSelected(s => {
      const next = { ...s }
      if (next[v.id]) delete next[v.id]
      else next[v.id] = v
      return next
    })
  }

  async function save() {
    const chosen = Object.values(selected)
    if (!letterNumber || !letterDate) { setError('Letter number and date are required.'); return }
    if (chosen.length === 0) { setError('Select at least one village.'); return }
    setSaving(true); setError('')
    try {
      await createLetter(token, {
        letter_number: letterNumber, letter_date: letterDate, organization,
        province_or_region_id: chosen[0].province_id, comment: comment || undefined,
        village_acceptance_ids: chosen.map(v => v.id),
      })
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const side = organization.startsWith('ICT') ? 'ICT' : 'CRA'

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 640 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>New letter</h3>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 18 }}>
          Approves every requested {side} technology for each selected village.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={fieldLabel}>Letter number</label>
            <input value={letterNumber} onChange={e => setLetterNumber(e.target.value)} style={{ ...input, width: '100%' }} />
          </div>
          <div>
            <label style={fieldLabel}>Letter date</label>
            <input type="date" value={letterDate} onChange={e => setLetterDate(e.target.value)} style={{ ...input, width: '100%' }} />
          </div>
        </div>

        <label style={fieldLabel}>Organization</label>
        <select value={organization} onChange={e => { setOrganization(e.target.value); setSelected({}) }} style={{ ...input, width: '100%', marginBottom: 12 }}>
          {ORGANIZATIONS.map(o => <option key={o} value={o}>{o}</option>)}
        </select>

        <label style={fieldLabel}>Comment (optional)</label>
        <input value={comment} onChange={e => setComment(e.target.value)} style={{ ...input, width: '100%', marginBottom: 14 }} />

        <label style={fieldLabel}>Villages ({Object.keys(selected).length} selected)</label>
        <input
          value={villageSearch} onChange={e => setVillageSearch(e.target.value)}
          placeholder="Search villages still waiting on this side…" style={{ ...input, width: '100%', marginBottom: 8 }}
        />
        <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid var(--line)', borderRadius: 8 }}>
          {villages === null ? (
            <div style={{ padding: 14, color: 'var(--muted)', fontSize: 12.5 }}>Loading…</div>
          ) : villages.length === 0 ? (
            <div style={{ padding: 14, color: 'var(--muted)', fontSize: 12.5 }}>No matching villages waiting on {side}.</div>
          ) : villages.map(v => (
            <label key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderBottom: '1px solid var(--line)', fontSize: 12, cursor: 'pointer' }}>
              <input type="checkbox" checked={!!selected[v.id]} onChange={() => toggle(v)} />
              <span style={{ fontWeight: 600 }}>{v.site_business_id}</span>
              <span style={{ color: 'var(--muted)' }}>{v.village_name ? `${v.village_id} (${v.village_name})` : v.village_id}</span>
              <span style={{ color: 'var(--muted2)', marginLeft: 'auto' }}>{v.province_name}</span>
            </label>
          ))}
        </div>

        {error && <div style={{ ...errBox, marginTop: 14 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={ghostBtn}>Cancel</button>
          <button onClick={save} disabled={saving} style={{ ...primaryBtn, opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Creating…' : `Create letter (${Object.keys(selected).length})`}
          </button>
        </div>
      </div>
    </div>
  )
}

function Th({ children, align }) {
  return <th style={{ textAlign: align || 'left', padding: '10px 14px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>{children}</th>
}

const td = { padding: '10px 14px' }
const input = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none', fontSize: 12.5 }
const ghostBtn = { padding: '9px 18px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--muted)', fontSize: 13, cursor: 'pointer' }
const primaryBtn = { padding: '9px 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'white', fontWeight: 600, fontSize: 13, cursor: 'pointer' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 12.5, marginBottom: 16 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: '26px 28px', maxHeight: '90vh', overflowY: 'auto' }
const fieldLabel = { fontSize: 11.5, color: 'var(--muted)', display: 'block', marginBottom: 5 }
