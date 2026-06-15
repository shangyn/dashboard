<template>
  <el-container class="admin-layout">
    <!-- 侧边栏 -->
    <el-aside v-if="!hideHeader" :width="sidebarCollapsed ? '64px' : '200px'" class="admin-aside">
      <div class="logo-area">
        <span class="brand-icon"><el-icon :size="20"><Trophy /></el-icon></span>
        <span v-show="!sidebarCollapsed" class="logo-text">系统控制台</span>
      </div>

      <el-menu
        :default-active="route.path"
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
          <el-icon class="collapse-icon" @click="appStore.toggleSidebar()" :size="18">
            <Fold v-if="!sidebarCollapsed" />
            <Expand v-else />
          </el-icon>
        </div>
        <div class="header-right">
          <span class="header-username" @click="openPwdDialog">{{ authStore.userInfo?.real_name || '管理员' }}</span>
          <el-button class="logout-btn" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main :class="hideHeader ? 'admin-main--full' : 'admin-main'">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 修改密码弹窗 -->
  <el-dialog v-model="pwdDialogVisible" width="460px" :show-close="false" class="pwd-dialog">
    <template #header>
      <div class="dialog-header">
        <div class="dialog-header-icon"><el-icon :size="22"><Lock /></el-icon></div>
        <span>修改密码</span>
      </div>
    </template>

    <div class="dialog-body">
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" size="large">
        <el-form-item prop="oldPassword">
          <div class="field-label">旧密码</div>
          <el-input v-model="pwdForm.oldPassword" type="password" placeholder="请输入旧密码" show-password />
        </el-form-item>
        <el-form-item prop="newPassword">
          <div class="field-label">新密码</div>
          <el-input v-model="pwdForm.newPassword" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <div class="field-label">确认密码</div>
          <el-input v-model="pwdForm.confirmPassword" type="password" placeholder="请再次输入新密码" show-password />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button class="cancel-btn" @click="pwdDialogVisible = false">取消</el-button>
        <el-button class="confirm-btn" @click="handleChangePassword">确认修改</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, User, Lock, Grid, UploadFilled, Trophy, Fold, Expand } from '@element-plus/icons-vue'
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
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const validateConfirm = (rule, value, callback) => {
  if (value !== pwdForm.newPassword) {
    callback(new Error('两次密码输入不一致'))
  } else {
    callback()
  }
}

const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, min: 6, message: '新密码不少于6位', trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

function openPwdDialog() {
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdDialogVisible.value = true
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
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
  gap: 10px;
}
.brand-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.logo-text { font-weight: 700; font-size: 18px; color: #1a73e8; white-space: nowrap; }
.admin-aside :deep(.el-menu) { border-right: none; }

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 56px;
  padding: 0 50px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.collapse-icon { cursor: pointer; color: #888; }
.header-right { display: flex; align-items: center; gap: 22px; }
.header-username {
  font-size: 13px;
  color: #555;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.2s;
}
.header-username:hover { color: #1a73e8; }
.logout-btn {
  font-size: 12px;
  color: #fff;
  background: #e74c3c;
  border-color: #e74c3c;
}
.logout-btn:hover {
  color: #fff;
  background: #c0392b;
  border-color: #c0392b;
}

.admin-main { background: #f0f2f5; padding: 20px; }
.admin-main--full { background: #f0f2f5; padding: 0 !important; overflow: hidden; }
</style>

<style>
/* 修改密码弹窗 — 全局样式 */
.pwd-dialog.el-dialog {
  border-radius: 25px;
  overflow: hidden;
  padding: 0 !important;
  margin-top: 25vh !important;
}
.pwd-dialog .el-dialog__header {
  padding: 0 !important;
  margin: 0 !important;
}
.pwd-dialog .el-dialog__body {
  padding: 0 !important;
}
.pwd-dialog .el-dialog__footer {
  padding: 0 !important;
  margin: 0 !important;
}
.dialog-header {
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 28px;
  color: #fff;
  font-size: 17px;
  font-weight: 600;
}
.dialog-header-icon {
  width: 34px; height: 34px;
  border-radius: 8px;
  background: rgba(255,255,255,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog-body {
  padding: 28px 28px 8px;
}
.dialog-body .el-form-item {
  display: block;
  margin-bottom: 20px;
}
.dialog-body .el-form-item__content {
  display: block;
}
.field-label {
  font-size: 14px;
  color: #333;
  font-weight: 500;
  margin-bottom: 8px;
}
.dialog-footer {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 8px 28px 28px;
}
.cancel-btn {
  width: 45%;
  background: #e8e8e8;
  border-color: #e8e8e8;
  color: #666;
  font-size: 13px;
  padding: 20px 0;
  border-radius: 10px;
}
.cancel-btn:hover {
  background: #d8d8d8;
  border-color: #d8d8d8;
  color: #333;
}
.confirm-btn {
  width: 45%;
  background: linear-gradient(135deg, #1a73e8, #0d47a1) !important;
  border: none !important;
  color: #fff !important;
  font-size: 13px;
  padding: 20px 0;
  border-radius: 10px;
}
.confirm-btn:hover {
  opacity: 0.9;
}
</style>