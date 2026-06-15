<template>
  <div class="page-card">
    <h3>欢迎回来，{{ authStore.userInfo?.real_name || '管理员' }}</h3>
    <p style="color:#999; margin-top: 8px;">管理系统用户、角色、模块和上传配置</p>
  </div>
</template>
<script setup>
import { useAuthStore } from '../../stores/auth'
const authStore = useAuthStore()
</script>
<style scoped>.page-card { background: #fff; border-radius: 12px; padding: 32px; }</style>