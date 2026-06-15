<template>
  <el-container class="admin-layout">
    <!-- 侧边栏 -->
    <el-aside v-if="!hideHeader" :width="sidebarCollapsed ? '64px' : '200px'" class="admin-aside">
      <div class="logo-area">
        <div class="logo-icon"></div>
        <span v-show="!sidebarCollapsed" class="logo-text">系统控制台</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="sidebarCollapsed"
        :collapse-transition="false"
        router
        background-color="#fff"
        text-color="#555"
        active-text-color="#1a73e8"
      >
        <el-menu-item index="/admin/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>首页看板</span>
        </el-menu-item>
        <el-menu-item index="/admin/user-manage" v-if="authStore.hasPermission('user_manage')">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/role-manage" v-if="authStore.hasPermission('role_manage')">
          <el-icon><Lock /></el-icon>
          <span>角色管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/module-manage" v-if="authStore.hasPermission('module_manage')">
          <el-icon><Grid /></el-icon>
          <span>模块管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/upload-config-manage" v-if="authStore.hasPermission('upload_manage')">
          <el-icon><UploadFilled /></el-icon>
          <span>上传配置管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧 -->
    <el-container>
      <el-header v-if="!hideHeader" class="admin-header">
        <div class="header-left">
          <el-icon class="collapse-icon" @click="appStore.toggleSidebar()" :size="20">
            <Fold v-if="!sidebarCollapsed" />
            <Expand v-else />
          </el-icon>
        </div>
        <div class="header-right">
          <el-icon :size="18"><Bell /></el-icon>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="30" class="user-avatar">
                {{ authStore.userInfo?.real_name?.charAt(0) || '管' }}
              </el-avatar>
              <span>{{ authStore.userInfo?.real_name || '管理员' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="changePassword">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main :class="hideHeader ? 'admin-main--full' : 'admin-main'">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 修改密码弹窗 -->
  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="420px">
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="80px">
      <el-form-item label="旧密码" prop="oldPassword">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="pwdForm.newPassword" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="handleChangePassword">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, User, Lock, Grid, UploadFilled, Bell, ArrowDown, Fold, Expand } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { changePassword } from '../api/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const appStore = useAppStore()

const sidebarCollapsed = computed(() => appStore.sidebarCollapsed)
const hideHeader = computed(() => route.meta.hideHeader === true)

const pwdDialogVisible = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ oldPassword: '', newPassword: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, min: 6, message: '新密码不少于6位', trigger: 'blur' }],
}

function handleCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'changePassword') {
    pwdForm.oldPassword = ''
    pwdForm.newPassword = ''
    pwdDialogVisible.value = true
  }
}

async function handleChangePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  try {
    await changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch { /* 已在拦截器处理 */ }
}
</script>

<style scoped>
.admin-layout { height: 100vh; }
.admin-aside {
  background: #fff;
  border-right: 1px solid #eef0f2;
  transition: width 0.3s;
  overflow: hidden;
}
.logo-area {
  display: flex;
  align-items: center;
  padding: 16px;
  gap: 8px;
}
.logo-icon {
  width: 32px; height: 32px;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  border-radius: 6px;
  flex-shrink: 0;
}
.logo-text { font-weight: 600; font-size: 14px; color: #1a1a2e; white-space: nowrap; }
.admin-aside :deep(.el-menu) { border-right: none; }
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 50px;
  padding: 0 20px;
}
.header-left { display: flex; align-items: center; }
.collapse-icon { cursor: pointer; color: #666; }
.header-right { display: flex; align-items: center; gap: 16px; }
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #555;
}
.user-avatar { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; font-size: 12px; }
.admin-main { background: #f0f2f5; padding: 20px; }
.admin-main--full { background: #f0f2f5; padding: 0 !important; overflow: hidden; }
</style>
