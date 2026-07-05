const BASE = '/api'

export async function getCaptcha() {
  const res = await fetch(`${BASE}/auth/captcha`)
  if (!res.ok) throw new Error('Could not load the security code. Try again.')
  return res.json() // { captcha_token, image }
}

export async function login(email, password, captchaToken, captchaCode) {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)
  body.set('captcha_token', captchaToken)
  body.set('captcha_code', captchaCode)
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Login failed — check your email and password.')
  }
  return res.json() // { access_token, token_type }
}

async function authed(path, token, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${token}` },
  })
  if (res.status === 401) {
    throw new Error('SESSION_EXPIRED')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export function getMe(token) {
  return authed('/users/me', token)
}

export function getSites(token) {
  return authed('/sites', token)
}

export function getSummary(token) {
  return authed('/summary', token)
}

export function getActionCenter(token) {
  return authed('/action-center', token)
}

export function getPmDashboard(token) {
  return authed('/dashboard/pm', token)
}

export function getProjectDeliveryDashboard(token) {
  return authed('/dashboard/delivery', token)
}

export function getCoordinatorDashboard(token) {
  return authed('/dashboard/coordinator', token)
}

export function getContractorDashboard(token) {
  return authed('/dashboard/contractor', token)
}

export function getRegionalDashboard(token) {
  return authed('/dashboard/regional', token)
}

export function listProvinces(token) {
  return authed('/provinces', token)
}

export function updateProvince(token, provinceId, payload) {
  return authed(`/provinces/${provinceId}`, token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function importCpm(token, fileObj) {
  const form = new FormData()
  form.append('file', fileObj)
  const res = await fetch(`${BASE}/import/cpm`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Import failed')
  }
  return res.json()
}

export function resetImportedData(token) {
  return authed('/import/reset', token, { method: 'POST' })
}

export function listUsers(token) {
  return authed('/users', token)
}

export function createUser(token, payload) {
  return authed('/users', token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateUser(token, userId, payload) {
  return authed(`/users/${userId}`, token, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listSites(token, params = {}) {
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null))
  ).toString()
  return authed(`/sites?${qs}`, token)
}

export function getSiteFilterOptions(token) {
  return authed('/sites/filter-options', token)
}

export function listContractors(token) {
  return authed('/contractors', token)
}

export function getSiteAssignments(token, siteId) {
  return authed(`/sites/${siteId}/assignments`, token)
}

export function assignSite(token, siteId, payload) {
  return authed(`/sites/${siteId}/assign`, token, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
