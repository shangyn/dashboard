<template>
  <el-container class="user-layout">
    <el-header v-if="!hideHeader" class="user-header">
      <span class="header-brand">系统控制台</span>
      <div class="header-actions">
        <span class="header-username">{{ authStore.userInfo?.real_name || '用户' }}</span>
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
import { ref, reactive, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { changePassword } from '../api/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const hideHeader = computed(() => route.meta.hideHeader === true)

const pwdDialogVisible = ref(false)
const pwdFormRef = ref(null)
const pwdForm = reactive({ oldPassword: '', newPassword: '' })
const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [{ required: true, min: 6, message: '新密码不少于6位', trigger: 'blur' }],
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
  padding: 0 24px;
  flex-shrink: 0;
}
.header-brand {
  font-weight: 700;
  font-size: 20px;
  color: #1a73e8;
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