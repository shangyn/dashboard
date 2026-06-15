import request from './request'

export function login(username, password) {
  return request.post('/api/login', { username, password })
}

export function getCurrentUser() {
  return request.get('/api/current-user')
}

export function changePassword(oldPassword, newPassword) {
  return request.put('/api/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  })
}
