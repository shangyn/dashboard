<template>
  <el-container class="user-layout">
    <el-header v-if="!hideHeader" class="user-header">
      <span class="header-brand">
        <span class="brand-icon"><el-icon :size="20"><Trophy /></el-icon></span>
        系统控制台
      </span>
      <div class="header-actions">
        <span class="header-username" @click="openPwdDialog">{{ authStore.userInfo?.real_name || '用户' }}</span>
        <el-button class="console-btn" @click="router.push('/upload-console')">
          用户控制台
        </el-button>
        <el-button class="logout-btn" @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </el-header>

    <el-main :class="hideHeader ? 'user-main--full' : 'user-main'">
      <router-view />
    </el-main>
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
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { changePassword } from '../api/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

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
.user-layout { height: 100vh; display: flex; flex-direction: column; }
.user-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 56px;
  padding: 0 50px;
  flex-shrink: 0;
}
.header-brand {
  font-weight: 700;
  font-size: 20px;
  color: #1a73e8;
  display: flex;
  align-items: center;
  gap: 8px;
}
.brand-icon {
  width: 34px; height: 34px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 22px;
}
.header-username {
  font-size: 13px;
  color: #555;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.2s;
}
.header-username:hover {
  color: #1a73e8;
}
.console-btn {
  font-size: 12px;
  color: #fff;
  background: #1a73e8;
  border-color: #1a73e8;
}
.console-btn:hover {
  background: #1557b0;
  border-color: #1557b0;
  color: #fff;
}
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
.user-main {
  background: #f8fafc;
  padding: 28px 32px;
  flex: 1;
  max-width: 1920px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  overflow-y: auto;
}
.user-main--full {
  background: #f8fafc;
  padding: 0 !important;
  flex: 1;
  overflow: hidden;
}
</style>

<style>
/* 修改密码弹窗 — 全局样式 */
.pwd-dialog.el-dialog {
  border-radius: 25px;
  overflow: hidden;
  padding: 0 !important;
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
}
.confirm-btn:hover {
  opacity: 0.9;
}
</style>