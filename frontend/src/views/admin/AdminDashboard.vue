<template>
  <div class="admin-dashboard">
    <!-- 欢迎 -->
    <div class="welcome-section">
      <h2>欢迎回来，{{ authStore.userInfo?.real_name || '管理员' }}</h2>
      <p>请选择您要查看的看板</p>
    </div>

    <!-- 模块卡片 -->
    <el-row :gutter="16" v-loading="loading">
      <el-col :span="8" v-for="m in modules" :key="m.id" style="margin-bottom: 16px;">
        <div class="module-card" @click="goDashboard(m)">
          <div class="module-card-header">
            <span class="module-icon" :style="{ background: iconBgColors[m.id % iconBgColors.length] }">
              <el-icon :size="18">
                <component :is="m.icon || 'Grid'" />
              </el-icon>
            </span>
            <span class="module-title">{{ m.name }}</span>
          </div>
          <p class="module-desc">{{ m.description }}</p>
          <div class="module-card-footer">
            <span class="module-link">查看看板 →</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && modules.length === 0" description="暂无可查看的看板，请在模块管理中创建" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { getMyModules } from '../../api/modules'

const authStore = useAuthStore()
const router = useRouter()

const modules = ref([])
const loading = ref(false)
const iconBgColors = ['#e8f0fe', '#e6f7ee', '#fff3e0', '#f3e5f5', '#e0f7fa', '#fce4ec']

onMounted(async () => {
  loading.value = true
  try {
    const res = await getMyModules()
    modules.value = res.data || []
  } finally {
    loading.value = false
  }
})

function goDashboard(module) {
  router.push(`/admin/dashboard-view/${module.id}`)
}
</script>

<style scoped>
.admin-dashboard { }
.welcome-section { margin-bottom: 24px; }
.welcome-section h2 { margin: 0; font-size: 20px; color: #1a1a2e; }
.welcome-section p { margin: 6px 0 0; color: #888; font-size: 13px; }

.module-card {
  background: #fff; border-radius: 12px; padding: 20px;
  border: 1px solid #eef0f2; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  cursor: pointer; transition: box-shadow 0.2s; height: 100%;
  display: flex; flex-direction: column;
}
.module-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.module-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.module-icon {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; color: #1a73e8;
}
.module-title { font-weight: 600; font-size: 14px; color: #1a1a2e; }
.module-desc { font-size: 11px; color: #999; line-height: 1.6; flex: 1; margin: 0 0 14px; }
.module-card-footer { text-align: right; }
.module-link { font-size: 11px; color: #1a73e8; border: 1px solid #1a73e8; padding: 4px 14px; border-radius: 4px; }
</style>