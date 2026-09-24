import request from './request'

export function getContext() {
  return request.get('/api/monthly-forecast/context')
}

export function getEntry(month, module) {
  return request.get('/api/monthly-forecast/entry', { params: { month, module } })
}

export function saveEntry(payload) {
  return request.put('/api/monthly-forecast/entry', payload)
}

export function submitEntry(payload) {
  return request.post('/api/monthly-forecast/entry/submit', payload)
}

export function getCandidates(module, month, q) {
  return request.get('/api/monthly-forecast/candidates', { params: { module, month, q } })
}

export function validateLadder(payload) {
  return request.post('/api/monthly-forecast/ladder/validate', payload)
}

export function getSummary(month) {
  return request.get('/api/monthly-forecast/summary', { params: { month } })
}

export function getSubmissions(month, module) {
  return request.get('/api/monthly-forecast/submissions', { params: { month, module } })
}

export function getScope() {
  return request.get('/api/monthly-forecast/scope')
}

export function importScope(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/api/monthly-forecast/scope', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

export function getScopeOptions() {
  return request.get('/api/monthly-forecast/scope/options')
}

export function addScopeItem(payload) {
  return request.post('/api/monthly-forecast/scope/item', payload)
}

export function removeScopeItem(id) {
  return request.delete(`/api/monthly-forecast/scope/item/${id}`)
}

export function cleanupScope() {
  return request.post('/api/monthly-forecast/scope/cleanup')
}

/** 下载导出的 Excel（需带 Authorization 头，故用 fetch 取 blob） */
export function downloadExport(kind, month, filename) {
  const token = localStorage.getItem('token')
  const url = `/api/monthly-forecast/export/${kind}?month=${encodeURIComponent(month)}`

  if (window.navigator.msSaveOrOpenBlob) {
    const xhr = new XMLHttpRequest()
    xhr.open('GET', url, true)
    xhr.responseType = 'blob'
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.onload = function () {
      if (xhr.status === 200) {
        window.navigator.msSaveOrOpenBlob(xhr.response, filename)
      }
    }
    xhr.send()
    return Promise.resolve()
  }

  return fetch(url, { headers: { Authorization: `Bearer ${token}` } }).then((res) => {
    if (!res.ok) throw new Error('export failed')
    return res.blob()
  }).then((blob) => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    URL.revokeObjectURL(link.href)
  })
}
