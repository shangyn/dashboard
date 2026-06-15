import request from './request'

export function getUsers(params) {
  return request.get('/api/users', { params })
}

export function createUser(data) {
  return request.post('/api/users', data)
}

export function updateUser(id, data) {
  return request.put(`/api/users/${id}`, data)
}

export function deleteUser(id) {
  return request.delete(`/api/users/${id}`)
}

export function resetPassword(id) {
  return request.put(`/api/users/${id}/reset-password`)
}
