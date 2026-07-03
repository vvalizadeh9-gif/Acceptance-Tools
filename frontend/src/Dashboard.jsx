import { useEffect, useRef, useState } from 'react'
import { getMe, getSummary, importCpm } from './api.js'

export default function Dashboard({ token, onLogout }) {
  const [me, setMe] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const [importMsg, setImportMsg] = useState('')
  const fileRef = useRef(null)

  async function loadData() {
    try {
      const [meData, sumData] = await Promise.all([getMe(token), getSummary(token)])
      setMe(meData); setSummary(sumData)
    } catch (err) {
      if (err.message === 'SESSION_EXPIRED') { onLogout(); return }
      setError(err.message)
    }
  }
  useEffect(() => { loadData() }, [token])

  async function handleFile(e) {
    const f = e.target.files[0]
    if (!f) return
    setImporting(true); setImportMsg('')
    try {
      const res = await importCpm(token, f)
      const c = res.imported
      setImportMsg(`Imported ${c.sites} new sites, ${c.villages} villages, ${c.acceptance} acceptance rows.`)
      await loadData()
    } catch (err) {
      setImportMsg('Error: ' + err.message)
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>Command Center</h1>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3, marginBottom: 26 }}>
        {me ? `Signed in as ${me.email}` : 'Loading...'}
      </div>

      {error && <div style={errBox}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginBottom: 24 }}>
        <Metric label="Sites" value={summary?.sites} />
        <Metric label="Total On-Air" value={summary?.total_on_air} sub="Site+Type combos, on-air" />
        <Metric label="Total Villages" value={summary?.total_villages} sub="Target villages, on-air" />
      </div>

      {me?.role === 'admin' && (
        <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '18px 20px', marginBottom: 22 }}>
          <h3 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 6 }}>Import CPM data</h3>
          <div style={{ color: 'var(--muted)', fontSize: 12.5, marginBottom: 14 }}>
            Upload a CPM Excel file (.xlsx). Re-uploading an updated file is safe &mdash; existing records won't be duplicated.
          </div>
          <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={handleFile} disabled={importing} style={{ display: 'none' }} id="cpmfile" />
          <label htmlFor="cpmfile" style={{ display: 'inline-block', padding: '9px 18px', borderRadius: 8, background: 'var(--accent)', color: 'white', fontWeight: 600, fontSize: 13, opacity: importing ? 0.6 : 1, cursor: importing ? 'default' : 'pointer' }}>
            {importing ? 'Importing...' : 'Choose CPM file'}
          </label>
          {importMsg && (
            <div style={{ marginTop: 14, fontSize: 12.5, color: importMsg.startsWith('Error') ? '#fca5a5' : 'var(--green)' }}>{importMsg}</div>
          )}
        </div>
      )}

      <div style={infoBox}>
        The counts above are live from your database. The bottleneck-focused Command Center is a later chunk &mdash;
        right now we're building out the core features first.
      </div>
    </div>
  )
}

function Metric({ label, value, sub }) {
  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }}>
      <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.8 }}>{label}</div>
      <div style={{ fontSize: 27, fontWeight: 700, marginTop: 6 }}>{value === undefined || value === null ? '...' : value.toLocaleString()}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--muted2)', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}
const errBox = { padding: '12px 16px', borderRadius: 10, marginBottom: 20, background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.35)', color: '#fca5a5', fontSize: 13 }
const infoBox = { padding: '13px 16px', borderRadius: 10, fontSize: 12.5, color: 'var(--muted)', background: 'var(--accent-soft)', border: '1px solid var(--accent-dim)' }
