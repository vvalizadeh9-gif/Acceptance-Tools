import { useEffect, useState } from 'react'
import { listAcceptance, getAcceptance, updateAcceptanceIct, updateAcceptanceCra, getSiteFilterOptions, getMe } from './api.js'

const PAGE_SIZE = 50
const STATUS_LABEL = { not_submitted: 'Not submitted', submitted: 'Submitted', approved: 'Approved', rejected: 'Rejected' }
const STATUS_COLOR = {
  approved: { bg: 'var(--green-soft)', fg: 'var(--green)' },
  rejected: { bg: 'var(--red-soft)', fg: 'var(--red)' },
  submitted: { bg: 'var(--amber-soft)', fg: 'var(--amber)' },
  not_submitted: { bg: 'var(--panel2)', fg: 'var(--muted2)' },
}

export default function Acceptance({ token, onLogout, onBack }) {
  const [data, setData] = useState(null)
  const [filterOptions, setFilterOptions] = useState(null)
  const [me, setMe] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(null) // acceptance list-row being edited

  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [province, setProvince] = useState('')
  const [ictFinal, setIctFinal] = useState('')
  const [craFinal, setCraFinal] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => { getMe(token).then(setMe).catch(() => {}) }, [token])
  useEffect(() => { getSiteFilterOptions(token).then(setFilterOptions).catch(() => {}) }, [token])

  function reload() {
    setLoading(true)
    listAcceptance(token, { page, page_size: PAGE_SIZE, search, province, ict_final: ictFinal, cra_final: craFinal })
      .then(d => { setData(d); setError('') })
      .catch(err => { if (err.message === 'SESSION_EXPIRED') { onLogout(); return }; setError(err.message) })
      .finally(() => setLoading(false))
  }
  useEffect(reload, [token, page, search, province, ictFinal, craFinal])

  function handleSearchSubmit(e) {
    e.preventDefault()
    setPage(1)
    setSearch(searchInput.trim())
  }

  const canEdit = me && (me.role === 'admin' || me.role === 'dt_coordinator')
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div>
      {onBack && <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: 12.5, cursor: 'pointer', padding: 0, marginBottom: 10 }}>← Back to dashboard</button>}
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>Manage Village Acceptance</h1>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3, marginBottom: 22 }}>
        {data ? `${data.total.toLocaleString()} villages` : 'Loading…'} &mdash; ICT and CRA are independent processes, tracked side by side.
      </div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap', alignItems: 'center' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: 6 }}>
          <input value={searchInput} onChange={e => setSearchInput(e.target.value)} placeholder="Search village…" style={input} />
          <button type="submit" style={ghostBtn}>Search</button>
        </form>
        <select value={province} onChange={e => { setProvince(e.target.value); setPage(1) }} style={input}>
          <option value="">All provinces</option>
          {filterOptions?.provinces.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={ictFinal} onChange={e => { setIctFinal(e.target.value); setPage(1) }} style={input}>
          <option value="">ICT: any</option>
          <option value="true">ICT final</option>
          <option value="false">ICT not final</option>
        </select>
        <select value={craFinal} onChange={e => { setCraFinal(e.target.value); setPage(1) }} style={input}>
          <option value="">CRA: any</option>
          <option value="true">CRA final</option>
          <option value="false">CRA not final</option>
        </select>
        {(search || province || ictFinal || craFinal) && (
          <button onClick={() => { setSearch(''); setSearchInput(''); setProvince(''); setIctFinal(''); setCraFinal(''); setPage(1) }} style={ghostBtn}>
            Clear filters
          </button>
        )}
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Site</Th><Th>Province</Th><Th>Village</Th>
              <Th>ICT (2G/3G/4G)</Th><Th>ICT Final</Th>
              <Th>CRA (2G/3G/4G)</Th><Th>CRA Final</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ padding: 20, color: 'var(--muted)' }}>Loading…</td></tr>
            ) : !data || data.items.length === 0 ? (
              <tr><td colSpan={8} style={{ padding: 20, color: 'var(--muted)' }}>No villages match these filters.</td></tr>
            ) : data.items.map(v => (
              <tr key={v.id} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={{ ...td, fontWeight: 600 }}>{v.site_business_id}</td>
                <td style={td}>{v.province_name || '—'}</td>
                <td style={td}>{v.village_name ? `${v.village_id} (${v.village_name})` : v.village_id}</td>
                <td style={td}><TechRow g2={v.ict_2g} g3={v.ict_3g} g4={v.ict_4g} /></td>
                <td style={td}><FinalBadge value={v.ict_final} /></td>
                <td style={td}><TechRow g2={v.cra_2g} g3={v.cra_3g} g4={v.cra_4g} /></td>
                <td style={td}><FinalBadge value={v.cra_final} /></td>
                <td style={{ ...td, textAlign: 'right' }}>
                  <button onClick={() => setEditing(v)} style={smallBtn}>{canEdit ? 'Edit' : 'View'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Page {data.page} of {totalPages} &middot; {data.total.toLocaleString()} total</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ ...ghostBtn, opacity: page <= 1 ? 0.4 : 1 }}>Previous</button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} style={{ ...ghostBtn, opacity: page >= totalPages ? 0.4 : 1 }}>Next</button>
          </div>
        </div>
      )}

      {editing && (
        <EditModal
          token={token} row={editing} canEdit={canEdit}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reload() }}
        />
      )}
    </div>
  )
}

function TechRow({ g2, g3, g4 }) {
  return (
    <div style={{ display: 'flex', gap: 5 }}>
      <TechChip label="2G" value={g2} /><TechChip label="3G" value={g3} /><TechChip label="4G" value={g4} />
    </div>
  )
}
function TechChip({ label, value }) {
  if (value === null || value === undefined) return <span style={{ fontSize: 10.5, color: 'var(--muted2)' }}>{label}: n/a</span>
  const c = STATUS_COLOR[value] || STATUS_COLOR.not_submitted
  return <span style={{ fontSize: 10.5, padding: '2px 6px', borderRadius: 8, background: c.bg, color: c.fg }}>{label}</span>
}
function FinalBadge({ value }) {
  return (
    <span style={{
      fontSize: 11, padding: '3px 9px', borderRadius: 12,
      background: value ? 'var(--green-soft)' : 'var(--panel2)',
      color: value ? 'var(--green)' : 'var(--muted2)',
    }}>
      {value ? 'Final' : 'Pending'}
    </span>
  )
}

function EditModal({ token, row, canEdit, onClose, onSaved }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getAcceptance(token, row.id).then(setDetail).catch(err => setError(err.message))
  }, [token, row.id])

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 620 }} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
          {row.site_business_id} &middot; {row.village_name ? `${row.village_id} (${row.village_name})` : row.village_id}
        </h3>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 20 }}>{row.province_name}</div>

        {error && <div style={errBox}>{error}</div>}
        {!detail ? (
          <div style={{ color: 'var(--muted)' }}>Loading…</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
            <SideForm
              side="ict" title="ICT" token={token} acceptanceId={row.id}
              detail={detail} canEdit={canEdit}
              updateFn={updateAcceptanceIct}
              onSaved={onSaved} onError={setError}
            />
            <SideForm
              side="cra" title="CRA" token={token} acceptanceId={row.id}
              detail={detail} canEdit={canEdit}
              updateFn={updateAcceptanceCra}
              onSaved={onSaved} onError={setError}
            />
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 22 }}>
          <button onClick={onClose} style={ghostBtn}>Close</button>
        </div>
      </div>
    </div>
  )
}

function SideForm({ side, title, token, acceptanceId, detail, canEdit, updateFn, onSaved, onError }) {
  const requested = ['2g', '3g', '4g'].filter(g => detail[`${side}_${g}`] !== null && detail[`${side}_${g}`] !== undefined)
  const [values, setValues] = useState(() => Object.fromEntries(requested.map(g => [g, detail[`${side}_${g}`]])))
  const [comment, setComment] = useState(detail[`${side}_comment`] || '')
  const [letterNumber, setLetterNumber] = useState(detail[`${side}_letter_number`] || '')
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    try {
      const payload = { comment: comment || undefined, letter_number: letterNumber || undefined }
      for (const g of requested) payload[`g${g[0]}`] = values[g]
      await updateFn(token, acceptanceId, payload)
      onSaved()
    } catch (err) {
      onError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ border: '1px solid var(--line)', borderRadius: 10, padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ fontWeight: 700, fontSize: 13.5 }}>{title}</div>
        <FinalBadge value={detail[`${side}_final`]} />
      </div>

      {requested.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--muted2)' }}>No technology requested for this side.</div>
      ) : requested.map(g => (
        <div key={g} style={{ marginBottom: 10 }}>
          <label style={fieldLabel}>{g.toUpperCase()}</label>
          <select
            disabled={!canEdit} value={values[g]}
            onChange={e => setValues(v => ({ ...v, [g]: e.target.value }))}
            style={{ ...input, width: '100%' }}
          >
            <option value="not_submitted">{STATUS_LABEL.not_submitted}</option>
            <option value="submitted">{STATUS_LABEL.submitted}</option>
            <option value="approved">{STATUS_LABEL.approved}</option>
            <option value="rejected">{STATUS_LABEL.rejected}</option>
          </select>
        </div>
      ))}

      <label style={fieldLabel}>Letter number</label>
      <input disabled={!canEdit} value={letterNumber} onChange={e => setLetterNumber(e.target.value)} style={{ ...input, width: '100%', marginBottom: 10 }} />

      <label style={fieldLabel}>Comment</label>
      <textarea disabled={!canEdit} value={comment} onChange={e => setComment(e.target.value)} rows={2}
                style={{ ...input, width: '100%', resize: 'vertical', fontFamily: 'inherit' }} />

      {canEdit && requested.length > 0 && (
        <button onClick={save} disabled={saving} style={{ ...ghostBtn, marginTop: 10, width: '100%', background: 'var(--accent)', color: 'white', border: 'none', opacity: saving ? 0.6 : 1 }}>
          {saving ? 'Saving…' : `Save ${title}`}
        </button>
      )}
    </div>
  )
}

function Th({ children }) {
  return <th style={{ textAlign: 'left', padding: '10px 14px', fontSize: 10.5, color: 'var(--muted2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>{children}</th>
}

const td = { padding: '10px 14px' }
const input = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel2)', color: 'var(--ink)', outline: 'none', fontSize: 12.5 }
const ghostBtn = { padding: '8px 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12.5, cursor: 'pointer' }
const smallBtn = { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12, cursor: 'pointer' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 12.5, marginBottom: 16 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(21,34,56,.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: '26px 28px', maxHeight: '90vh', overflowY: 'auto' }
const fieldLabel = { fontSize: 11.5, color: 'var(--muted)', display: 'block', marginBottom: 5 }
