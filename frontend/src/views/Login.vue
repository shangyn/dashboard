<template>
  <div class="login-container">
    <div class="login-bg-circle login-bg-circle--top"></div>
    <div class="login-bg-circle login-bg-circle--bottom"></div>

    <el-card class="login-card">
      <div class="login-header">
        <h2>企业管理系统</h2>
        <p>Enterprise Management</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="请输入工号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" :prefix-icon="Lock"
            show-password @keyup.enter="handleLogin" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="rememberMe">记住密码</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const rememberMe = ref(false)
const formRef = ref(null)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

onMounted(() => {
  const savedUsername = localStorage.getItem('rememberedUsername')
  const savedPassword = localStorage.getItem('rememberedPassword')
  if (savedUsername) {
    form.username = savedUsername
    form.password = savedPassword || ''
    rememberMe.value = true
  }
})

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form.username, form.password)

    if (rememberMe.value) {
      localStorage.setItem('rememberedUsername', form.username)
      localStorage.setItem('rememberedPassword', form.password)
    } else {
      localStorage.removeItem('rememberedUsername')
      localStorage.removeItem('rememberedPassword')
    }

    ElMessage.success('登录成功')
    router.push(authStore.isAdmin ? '/admin/dashboard' : '/home')
  } catch {
    // 错误已在拦截器中处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 60%, #0a2e6e 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.04);
}

.login-bg-circle--top {
  width: 200px;
  height: 200px;
  top: -50px;
  right: -50px;
}

.login-bg-circle--bottom {
  width: 160px;
  height: 160px;
  bottom: -40px;
  left: -40px;
}

.login-card {
  width: 380px;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.login-header h2 {
  color: #1a1a2e;
  font-size: 22px;
  margin: 0;
}

.login-header p {
  color: #999;
  font-size: 12px;
  margin: 6px 0 0;
}

.login-btn {
  width: 100%;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  border: none;
  font-size: 15px;
  letter-spacing: 4px;
}
</style>
