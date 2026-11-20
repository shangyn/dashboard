import request from './request'

export function getAssistantContext() {
  return request.get('/api/business-assistant/context')
}

export function askBusinessAssistant(data) {
  return request.post('/api/business-assistant/chat', data)
}

export function getAssistantAdminSetting() {
  return request.get('/api/business-assistant/admin/setting')
}

export function updateAssistantAdminSetting(enabled) {
  return request.put('/api/business-assistant/admin/setting', { enabled })
}

export function getAssistantModelStatus() {
  return request.get('/api/business-assistant/admin/model-status')
}

export function testAssistantModelConnection() {
  return request.post('/api/business-assistant/admin/model-test')
}

export function getAssistantQueryLogs(params) {
  return request.get('/api/business-assistant/admin/query-log', { params })
}

export function downloadAssistantExport(token, filename) {
  const authToken = localStorage.getItem('token')
  const query = new URLSearchParams({ token })
  return fetch(`/api/business-assistant/export?${query.toString()}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  }).then((response) => {
    if (!response.ok) throw new Error('导出失败')
    return response.blob()
  }).then((blob) => {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}
