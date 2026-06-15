<template>
  <el-container class="user-layout">
    <el-header class="user-header">
      <span class="header-brand">系统控制台</span>
      <div class="header-actions">
        <el-button class="console-btn" @click="router.push('/upload-console')">
          用户控制台
        </el-button>
        <el-icon :size="18"><Bell /></el-icon>
        <el-dropdown trigger="click" @command="handleCommand">
          <span class="user-info">
            <el-avatar :size="30" class="user-avatar">
              {{ authStore.userInfo?.real_name?.charAt(0) || '用' }}
            </el-avatar>
            <span>{{ authStore.userInfo?.real_name || '用户' }}</span>
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

    <el-main class="user-main">
      <router-view />
    </el-main>
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
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { changePassword } from '../api/auth'

const router = useRouter()
const authStore = useAuthStore()

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
.user-layout { height: 100vh; display: flex; flex-direction: column; }
.user-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
  height: 50px;
  padding: 0 24px;
  flex-shrink: 0;
}
.header-brand { font-weight: 600; font-size: 14px; color: #1a1a2e; }
.header-actions { display: flex; align-items: center; gap: 16px; }
.console-btn {
  font-size: 12px;
  color: #1a73e8;
  border-color: #1a73e8;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #555;
}
.user-avatar { background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; font-size: 12px; }
.user-main { background: #f0f2f5; padding: 28px 32px; flex: 1; }
</style>
