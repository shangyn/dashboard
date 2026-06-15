import request from './request'

export function getUploadConfigs() {
  return request.get('/api/upload-configs')
}

export function createUploadConfig(data) {
  return request.post('/api/upload-configs', data)
}

export function updateUploadConfig(id, data) {
  return request.put(`/api/upload-configs/${id}`, data)
}

export function deleteUploadConfig(id) {
  return request.delete(`/api/upload-configs/${id}`)
}

export function getMyUploadConfigs() {
  return request.get('/api/my-upload-configs')
}
