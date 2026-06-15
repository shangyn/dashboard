<template>
  <div class="home-page">
    <!-- 欢迎区 -->
    <div class="welcome-section">
      <h2>欢迎回来，{{ authStore.userInfo?.real_name }}</h2>
      <p>请选择您要查看的看板</p>
    </div>

    <!-- 统计行 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--blue"><el-icon :size="20"><DataAnalysis /></el-icon></div>
          <div>
            <div class="stat-value">{{ modules.length }}</div>
            <div class="stat-label">可用看板</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--green"><el-icon :size="20"><TrendCharts /></el-icon></div>
          <div>
            <div class="stat-value">8</div>
            <div class="stat-label">监控指标</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card">
          <div class="stat-icon stat-icon--orange"><el-icon :size="20"><Grid /></el-icon></div>
          <div>
            <div class="stat-value">12</div>
            <div class="stat-label">数据维度</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 模块卡片网格 -->
    <el-row :gutter="16" v-loading="loading">
      <el-col :span="8" v-for="m in modules" :key="m.id" style="margin-bottom: 16px;">
        <div class="module-card" @click="goDashboard(m)">
          <div class="module-card-header">
            <span class="module-dot" :style="{ background: dotColors[m.id % dotColors.length] }"></span>
            <span class="module-title">{{ m.name }}</span>
          </div>
          <p class="module-desc">{{ m.description }}</p>
          <div class="module-card-footer">
            <span class="module-link">查看看板 →</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && modules.length === 0" description="暂无可查看的看板" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis, TrendCharts, Grid } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { getMyModules } from '../api/modules'

const authStore = useAuthStore()
const router = useRouter()

const modules = ref([])
const loading = ref(false)
const dotColors = ['#1a73e8', '#4caf50', '#ff9800', '#9c27b0', '#00bcd4', '#e91e63']

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
  router.push(`/dashboard/${module.id}`)
}
</script>

<style scoped>
.welcome-section { margin-bottom: 24px; }
.welcome-section h2 { margin: 0; font-size: 20px; color: #1a1a2e; }
.welcome-section p { margin: 6px 0 0; color: #888; font-size: 13px; }

.stats-row { margin-bottom: 28px; }
.stat-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  display: flex; align-items: center; gap: 14px; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.stat-icon--blue { background: #e8f0fe; color: #1a73e8; }
.stat-icon--green { background: #e6f7ee; color: #4caf50; }
.stat-icon--orange { background: #fff3e0; color: #ff9800; }
.stat-value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 11px; color: #888; }

.module-card {
  background: #fff; border-radius: 12px; padding: 20px;
  border: 1px solid #eef0f2; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  cursor: pointer; transition: box-shadow 0.2s; height: 100%;
  display: flex; flex-direction: column;
}
.module-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.module-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.module-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.module-title { font-weight: 600; font-size: 14px; color: #1a1a2e; }
.module-desc { font-size: 11px; color: #999; line-height: 1.6; flex: 1; margin: 0 0 14px; }
.module-card-footer { text-align: right; }
.module-link { font-size: 11px; color: #1a73e8; border: 1px solid #1a73e8; padding: 4px 14px; border-radius: 4px; }
</style>
