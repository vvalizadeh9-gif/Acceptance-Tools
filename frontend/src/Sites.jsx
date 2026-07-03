import { useEffect, useState } from 'react'
import { listSites, getSiteFilterOptions, getMe, listContractors, assignSite } from './api.js'

const PAGE_SIZE = 50

export default function Sites({ token, onLogout }) {
  const [data, setData] = useState(null)
  const [filterOptions, setFilterOptions] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [me, setMe] = useState(null)
  const [assigningSite, setAssigningSite] = useState(null) // site row being assigned

  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [province, setProvince] = useState('')
  const [region, setRegion] = useState('')
  const [onAir, setOnAir] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    getMe(token).then(setMe).catch(() => {})
  }, [token])

  const canAssign = me && (me.role === 'admin' || me.role === 'project_manager')

  function reload() {
    setLoading(true)
    listSites(token, { page, page_size: PAGE_SIZE, search, province, region, on_air: onAir })
      .then(d => { setData(d); setError('') })
      .catch(err => {
        if (err.message === 'SESSION_EXPIRED') { onLogout(); return }
        setError(err.message)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    getSiteFilterOptions(token).then(setFilterOptions).catch(() => {})
  }, [token])

  useEffect(reload, [token, page, search, province, region, onAir])

  function handleSearchSubmit(e) {
    e.preventDefault()
    setPage(1)
    setSearch(searchInput.trim())
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>Sites & Villages</h1>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3, marginBottom: 22 }}>
        {data ? `${data.total.toLocaleString()} sites` : 'Loading…'}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap', alignItems: 'center' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: 6 }}>
          <input
            value={searchInput} onChange={e => setSearchInput(e.target.value)}
            placeholder="Search site ID…" style={input}
          />
          <button type="submit" style={ghostBtn}>Search</button>
        </form>

        <select value={province} onChange={e => { setProvince(e.target.value); setPage(1) }} style={input}>
          <option value="">All provinces</option>
          {filterOptions?.provinces.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        <select value={region} onChange={e => { setRegion(e.target.value); setPage(1) }} style={input}>
          <option value="">All regions</option>
          {filterOptions?.regions.map(r => <option key={r} value={r}>{r}</option>)}
        </select>

        <select value={onAir} onChange={e => { setOnAir(e.target.value); setPage(1) }} style={input}>
          <option value="">On-air: any</option>
          <option value="true">On-air only</option>
          <option value="false">Not on-air</option>
        </select>

        {(search || province || region || onAir) && (
          <button
            onClick={() => { setSearch(''); setSearchInput(''); setProvince(''); setRegion(''); setOnAir(''); setPage(1) }}
            style={ghostBtn}
          >
            Clear filters
          </button>
        )}
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ background: 'var(--panel2)' }}>
              <Th>Site ID</Th>
              <Th>Official ID</Th>
              <Th>Province</Th>
              <Th>Region</Th>
              <Th align="right">Villages</Th>
              <Th align="right">Work Items</Th>
              <Th>Status</Th>
              <Th>Assigned To</Th>
              {canAssign && <Th></Th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={canAssign ? 8 : 7} style={{ padding: 20, color: 'var(--muted)' }}>Loading…</td></tr>
            ) : !data || data.items.length === 0 ? (
              <tr><td colSpan={canAssign ? 8 : 7} style={{ padding: 20, color: 'var(--muted)' }}>No sites match these filters.</td></tr>
            ) : data.items.map(s => (
              <tr key={s.id} style={{ borderTop: '1px solid var(--line)' }}>
                <td style={{ ...td, fontWeight: 600 }}>{s.site_id}</td>
                <td style={{ ...td, color: 'var(--muted)' }}>{s.official_site_id || '—'}</td>
                <td style={td}>{s.province_name || '—'}</td>
                <td style={td}>{s.region_name || '—'}</td>
                <td style={{ ...td, textAlign: 'right' }}>{s.village_count}</td>
                <td style={{ ...td, textAlign: 'right' }}>{s.on_air_work_item_count}/{s.work_item_count}</td>
                <td style={td}>
                  <span style={{
                    fontSize: 11, padding: '3px 9px', borderRadius: 12,
                    background: s.is_on_air ? 'rgba(34,197,94,.15)' : 'rgba(148,163,184,.15)',
                    color: s.is_on_air ? '#4ade80' : 'var(--muted)',
                  }}>
                    {s.is_on_air ? 'On-air' : 'Not on-air'}
                  </span>
                </td>
                <td style={{ ...td, color: 'var(--muted)' }}>{s.assigned_contractor || '—'}</td>
                {canAssign && (
                  <td style={td}>
                    <button onClick={() => setAssigningSite(s)} style={smallBtn}>
                      {s.assigned_contractor ? 'Reassign' : 'Assign'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>
            Page {data.page} of {totalPages} &middot; {data.total.toLocaleString()} total
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ ...ghostBtn, opacity: page <= 1 ? 0.4 : 1 }}>Previous</button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} style={{ ...ghostBtn, opacity: page >= totalPages ? 0.4 : 1 }}>Next</button>
          </div>
        </div>
      )}
      {assigningSite && (
        <AssignModal
          token={token} site={assigningSite}
          onClose={() => setAssigningSite(null)}
          onAssigned={() => { setAssigningSite(null); reload() }}
        />
      )}
    </div>
  )
}

function AssignModal({ token, site, onClose, onAssigned }) {
  const [contractors, setContractors] = useState(null)
  const [contractorId, setContractorId] = useState('')
  const [remark, setRemark] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    listContractors(token).then(setContractors).catch(err => setError(err.message))
  }, [token])

  async function save() {
    if (!contractorId) { setError('Choose a contractor first.'); return }
    setSaving(true); setError('')
    try {
      await assignSite(token, site.id, { contractor_id: contractorId, remark: remark || undefined })
      onAssigned()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Assign site {site.site_id}</h3>
        <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 20 }}>
          This assigns all {site.work_item_count} work item(s) under this site to one contractor.
          {site.assigned_contractor && ` Currently assigned to ${site.assigned_contractor}.`}
        </div>

        <label style={fieldLabel}>Contractor</label>
        {contractors === null ? (
          <div style={{ color: 'var(--muted)', fontSize: 13 }}>Loading contractors…</div>
        ) : contractors.length === 0 ? (
          <div style={{ color: 'var(--muted)', fontSize: 13 }}>No active Field Subcontractor accounts yet — create one in User Management first.</div>
        ) : (
          <select value={contractorId} onChange={e => setContractorId(e.target.value)} style={{ ...input, width: '100%' }}>
            <option value="">Select a contractor…</option>
            {contractors.map(c => <option key={c.id} value={c.id}>{c.full_name} ({c.email})</option>)}
          </select>
        )}

        <label style={{ ...fieldLabel, marginTop: 14 }}>Remark (optional)</label>
        <input value={remark} onChange={e => setRemark(e.target.value)} style={{ ...input, width: '100%' }} placeholder="e.g. Assigned via email 2026-07-03" />

        {error && <div style={{ ...errBox, marginTop: 14 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={ghostBtn}>Cancel</button>
          <button onClick={save} disabled={saving || !contractors?.length} style={{ ...ghostBtn, background: 'var(--accent)', color: 'white', border: 'none', opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Assigning…' : 'Assign'}
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
const ghostBtn = { padding: '8px 14px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12.5, cursor: 'pointer' }
const smallBtn = { padding: '5px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12, cursor: 'pointer' }
const errBox = { padding: '10px 14px', borderRadius: 8, background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5', fontSize: 12.5, marginBottom: 16 }
const overlay = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }
const modal = { background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 14, padding: '26px 28px', width: 440, maxHeight: '90vh', overflowY: 'auto' }
const fieldLabel = { fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 6 }
