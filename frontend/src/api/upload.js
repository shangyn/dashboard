import request from './request'

export function uploadFile(code, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post(`/api/upload/${code}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getUploadHistory(params) {
  return request.get('/api/upload-history', { params })
}

export function getUploadStats() {
  return request.get('/api/upload-stats')
}
