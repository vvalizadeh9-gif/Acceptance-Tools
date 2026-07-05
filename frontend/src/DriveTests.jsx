import { useEffect, useState } from 'react'
import { getActionCenter, getMe, submitDriveTest, validateDriveTest, approveDriveTest, rejectDriveTest } from './api.js'

// Drive Test has no generic "list all work items" endpoint — the queues here
// come from the same live, role-scoped Action Center data (dt_validation /
// dt_pm_approval / awaiting_dt / returned_dt), just with the workflow buttons
// attached directly instead of only a summary count.
export default function DriveTests({ token, onLogout }) {
  const [me, setMe] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => { getMe(token).then(setMe).catch(() => {}) }, [token])

  function reload() {
    getActionCenter(token)
      .then(d => { setData(d); setError('') })
      .catch(err => { if (err.message === 'SESSION_EXPIRED') { onLogout(); return }; setError(err.message) })
  }
  useEffect(reload, [token])

  const card = key => data?.cards.find(c => c.key === key)

  return (
    <div>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>Drive Tests</h1>
      <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 3, marginBottom: 22 }}>
        Subcontractor submits &rarr; Coordinator validates &rarr; PM approves or rejects.
      </div>

      {error && <div style={errBox}>{error}</div>}
      {!data ? <div style={{ color: 'var(--muted)' }}>Loading…</div> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          {me?.role === 'field_subcontractor' && (
            <>
              <QueueSection title="New assignments — submit a drive test" empty="Nothing waiting on you.">
                {card('awaiting_dt')?.items.map(it => (
                  <SubmitRow key={it.work_item_id} token={token} item={it} busy={busy} setBusy={setBusy} onDone={reload} />
                ))}
              </QueueSection>
              <QueueSection title="Returned — resubmit" empty="No returned drive tests.">
                {card('returned_dt')?.items.map(it => (
                  <SubmitRow key={it.work_item_id} token={token} item={it} busy={busy} setBusy={setBusy} onDone={reload} resubmit />
                ))}
              </QueueSection>
            </>
          )}

          {me?.role === 'dt_coordinator' && (
            <QueueSection title="Drive tests to validate" empty="Nothing waiting on you.">
              {card('dt_validation')?.items.map(it => (
                <ReviewRow key={it.drive_test_id} token={token} item={it} busy={busy} setBusy={setBusy} onDone={reload}
                           onApprove={id => validateDriveTest(token, id, { approve: true })}
                           onReject={(id, comment) => validateDriveTest(token, id, { approve: false, comment })}
                           approveLabel="Validate" />
              ))}
            </QueueSection>
          )}

          {(me?.role === 'admin' || me?.role === 'project_manager') && (
            <QueueSection title="Drive tests awaiting your approval" empty="Nothing waiting on you.">
              {card('dt_pm_approval')?.items.map(it => (
                <ReviewRow key={it.drive_test_id} token={token} item={it} busy={busy} setBusy={setBusy} onDone={reload}
                           onApprove={id => approveDriveTest(token, id, { comment: '' })}
                           onReject={(id, comment) => rejectDriveTest(token, id, { comment })}
                           approveLabel="Approve" />
              ))}
            </QueueSection>
          )}

          {!['field_subcontractor', 'dt_coordinator', 'admin', 'project_manager'].includes(me?.role) && (
            <div style={{ padding: '13px 16px', borderRadius: 10, fontSize: 13, color: 'var(--muted)', background: 'var(--accent-soft)', border: '1px solid var(--accent-dim)' }}>
              Your role doesn't take action on drive tests.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function QueueSection({ title, empty, children }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : (children ? [children] : [])
  return (
    <div style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, padding: '16px 18px' }}>
      <div style={{ fontWeight: 700, fontSize: 13.5, marginBottom: 12 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ fontSize: 12.5, color: 'var(--muted2)' }}>{empty}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{items}</div>
      )}
    </div>
  )
}

function SubmitRow({ token, item, busy, setBusy, onDone, resubmit }) {
  const [open, setOpen] = useState(false)
  const [deliveryDate, setDeliveryDate] = useState('')
  const [reportUrl, setReportUrl] = useState('')
  const [error, setError] = useState('')
  const key = item.work_item_id

  async function submit() {
    if (!deliveryDate || !reportUrl) { setError('Delivery date and report link are both required.'); return }
    setBusy(key); setError('')
    try {
      await submitDriveTest(token, { work_item_id: item.work_item_id, delivery_date: deliveryDate, report_url: reportUrl })
      onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div style={rowBox}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 12.5 }}><strong>{item.site_business_id}</strong> &middot; {item.site_type}</div>
        <button onClick={() => setOpen(o => !o)} style={smallBtn}>{open ? 'Cancel' : (resubmit ? 'Resubmit' : 'Submit')}</button>
      </div>
      {open && (
        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input type="date" value={deliveryDate} onChange={e => setDeliveryDate(e.target.value)} style={input} />
          <input placeholder="Report link (URL)" value={reportUrl} onChange={e => setReportUrl(e.target.value)} style={{ ...input, flex: 1, minWidth: 180 }} />
          <button onClick={submit} disabled={busy === key} style={{ ...smallBtn, background: 'var(--accent)', color: 'white', border: 'none' }}>
            {busy === key ? 'Submitting…' : 'Send'}
          </button>
        </div>
      )}
      {error && <div style={{ ...errBox, marginTop: 8 }}>{error}</div>}
    </div>
  )
}

function ReviewRow({ token, item, busy, setBusy, onDone, onApprove, onReject, approveLabel }) {
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const key = item.drive_test_id

  async function doApprove() {
    setBusy(key); setError('')
    try { await onApprove(item.drive_test_id); onDone() }
    catch (err) { setError(err.message) }
    finally { setBusy('') }
  }
  async function doReject() {
    if (comment.trim().length < 3) { setError('A short reason is required to reject.'); return }
    setBusy(key); setError('')
    try { await onReject(item.drive_test_id, comment); onDone() }
    catch (err) { setError(err.message) }
    finally { setBusy('') }
  }

  return (
    <div style={rowBox}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontSize: 12.5 }}>
          <strong>{item.site_business_id}</strong> &middot; {item.site_type} &middot; rev {item.revision_no} &middot; {item.delivery_date || '—'}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={doApprove} disabled={busy === key} style={{ ...smallBtn, background: 'var(--green)', color: 'white', border: 'none' }}>
            {busy === key ? '…' : approveLabel}
          </button>
          <button onClick={() => setRejecting(r => !r)} style={{ ...smallBtn, color: 'var(--red)', borderColor: 'var(--red)' }}>Reject</button>
        </div>
      </div>
      {rejecting && (
        <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
          <input placeholder="Reason for rejection…" value={comment} onChange={e => setComment(e.target.value)} style={{ ...input, flex: 1 }} />
          <button onClick={doReject} disabled={busy === key} style={{ ...smallBtn, background: 'var(--red)', color: 'white', border: 'none' }}>
            Confirm reject
          </button>
        </div>
      )}
      {error && <div style={{ ...errBox, marginTop: 8 }}>{error}</div>}
    </div>
  )
}

const rowBox = { background: 'var(--panel2)', border: '1px solid var(--line)', borderRadius: 9, padding: '10px 12px' }
const input = { padding: '8px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--ink)', outline: 'none', fontSize: 12.5 }
const smallBtn = { padding: '6px 12px', borderRadius: 7, border: '1px solid var(--line)', background: 'transparent', color: 'var(--ink)', fontSize: 12, cursor: 'pointer' }
const errBox = { padding: '8px 12px', borderRadius: 8, background: 'var(--red-soft)', border: '1px solid var(--red)', color: 'var(--red)', fontSize: 12 }
