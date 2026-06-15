import request from './request'

export function getModules() {
  return request.get('/api/modules')
}

export function createModule(data) {
  return request.post('/api/modules', data)
}

export function updateModule(id, data) {
  return request.put(`/api/modules/${id}`, data)
}

export function deleteModule(id) {
  return request.delete(`/api/modules/${id}`)
}

export function getMyModules() {
  return request.get('/api/my-modules')
}
