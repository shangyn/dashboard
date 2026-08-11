import request from './request'

export function uploadFile(code, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/api/upload/${code}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
  })
}

export function getUploadHistory(params) {
  return request.get('/api/upload-history', { params })
}

export function getUploadStats() {
  return request.get('/api/upload-stats')
}

export function getFileTimes(parentId) {
  return request.get(`/api/upload-file-times/${parentId}`)
}

export function generateDashboard(parentCode, data = null) {
  return request.post(`/api/generate-dashboard/${parentCode}`, data, {
    timeout: 300000,
  })
}
