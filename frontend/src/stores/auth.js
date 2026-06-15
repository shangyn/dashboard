import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getCurrentUser } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('userInfo') || 'null'))

  const isAdmin = computed(() => userInfo.value?.role?.is_admin || false)
  const permissions = computed(() => userInfo.value?.role?.permissions || [])
  const isLoggedIn = computed(() => !!token.value)

  function hasPermission(perm) {
    return permissions.value.includes(perm)
  }

  async function login(username, password) {
    const res = await loginApi(username, password)
    token.value = res.data.token
    userInfo.value = res.data.user
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('userInfo', JSON.stringify(res.data.user))
    return res.data
  }

  async function fetchCurrentUser() {
    try {
      const res = await getCurrentUser()
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  return { token, userInfo, isAdmin, permissions, isLoggedIn, hasPermission, login, fetchCurrentUser, logout }
})
