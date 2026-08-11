import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requireAdmin: true },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      { path: 'dashboard', component: () => import('../views/admin/AdminDashboard.vue') },
      { path: 'user-manage', component: () => import('../views/admin/UserManage.vue') },
      { path: 'role-manage', component: () => import('../views/admin/RoleManage.vue') },
      { path: 'module-manage', component: () => import('../views/admin/ModuleManage.vue') },
      { path: 'upload-config-manage', component: () => import('../views/admin/UploadConfigManage.vue') },
      { path: 'operation-logs', component: () => import('../views/admin/OperationLogs.vue') },
      { path: 'contract-completion', component: () => import('../views/ContractCompletion.vue') },
      { path: 'two-year-comparison', component: () => import('../views/TwoYearComparison.vue') },
      { path: 'dashboard-view/:id', component: () => import('../views/Dashboard.vue'), props: true, meta: { hideHeader: true } },
    ],
  },
  {
    path: '/',
    component: () => import('../layouts/UserLayout.vue'),
    meta: { requireAuth: true },
    children: [
      { path: '', redirect: '/home' },
      { path: 'home', component: () => import('../views/Home.vue') },
      { path: 'dashboard/:id', component: () => import('../views/Dashboard.vue'), props: true, meta: { hideHeader: true } },
      { path: 'upload-console', component: () => import('../views/UploadConsole.vue') },
      { path: 'upload-console/:code', component: () => import('../views/UploadConsole.vue') },
      { path: 'contract-completion', component: () => import('../views/ContractCompletion.vue') },
      { path: 'two-year-comparison', component: () => import('../views/TwoYearComparison.vue') },
    ],
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('../views/common/403.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/home',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 公开页面直接放行
  if (to.meta.public) {
    if (to.path === '/login' && authStore.isLoggedIn) {
      next(authStore.isAdmin ? '/admin/dashboard' : '/home')
      return
    }
    next()
    return
  }

  // 未登录 → 跳转登录页
  if (!authStore.isLoggedIn) {
    next('/login')
    return
  }

  // 已登录但无用户信息 → 拉取用户信息
  if (!authStore.userInfo) {
    try {
      await authStore.fetchCurrentUser()
    } catch {
      next('/login')
      return
    }
  }

  // 需要管理员权限
  if (to.meta.requireAdmin && !authStore.isAdmin) {
    next('/403')
    return
  }

  // 管理员访问普通用户首页 → 重定向到管理员首页
  if (authStore.isAdmin && !to.meta.requireAdmin && to.path === '/home') {
    next('/admin/dashboard')
    return
  }

  next()
})

export default router
