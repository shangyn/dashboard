import request from './request'

export function getContext() {
  return request.get('/api/module-business-detail/context')
}

export function getOverview(params) {
  return request.get('/api/module-business-detail/overview', { params })
}

export function getLadders(params) {
  return request.get('/api/module-business-detail/ladders', { params })
}

export function getPayments(params) {
  return request.get('/api/module-business-detail/payments', { params })
}

export function downloadExport(params, filename) {
  const token = localStorage.getItem('token')
  const query = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value)
    }
  })
  return fetch(`/api/module-business-detail/export?${query.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then((response) => {
    if (!response.ok) throw new Error('导出失败')
    return response.blob()
  }).then((blob) => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    URL.revokeObjectURL(link.href)
  })
}
