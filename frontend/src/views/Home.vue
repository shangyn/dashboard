<template>
  <div class="home-page">
    <div class="home-container">
      <div class="welcome-section">
        <h2>欢迎回来，{{ authStore.userInfo?.real_name }}</h2>
        <p>请选择您要查看的看板</p>
      </div>

      <div class="cards-grid" v-loading="loading">
        <div
          class="module-card"
          v-for="m in modules"
          :key="m.id"
          @click="goDashboard(m)"
        >
          <div class="card-icon">
            <el-icon :size="28">
              <component :is="m.icon || 'Grid'" />
            </el-icon>
          </div>
          <h3 class="card-name">{{ m.name }}</h3>
          <p class="card-desc">{{ m.description }}</p>
          <span class="card-link">查看看板 →</span>
        </div>
      </div>

      <el-empty v-if="!loading && modules.length === 0" description="暂无可查看的看板" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { getMyModules } from '../api/modules'

const authStore = useAuthStore()
const router = useRouter()

const modules = ref([])
const loading = ref(false)

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
  // Vue SPA 路由（如 /two-year-comparison）直接跳转，HTML文件走iframe
  if (module.url && module.url.startsWith('/') && !module.url.endsWith('.html')) {
    router.push(module.url)
  } else {
    router.push(`/dashboard/${module.id}`)
  }
}
</script>

<style scoped>
.home-page {
  padding: 28px 0 48px;
  background: #f8fafc;
}

.home-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}

.welcome-section {
  text-align: center;
  margin-bottom: 52px;
}
.welcome-section h2 {
  margin: 0;
  font-size: 30px;
  color: #1a1a2e;
}
.welcome-section p {
  margin: 15px 0 0;
  color: #888;
  font-size: 16px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
}

.module-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 32px;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  text-align: center;
}
.module-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(26, 115, 232, 0.15);
}

.card-icon {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  background: linear-gradient(135deg, #1a73e8, #0d47a1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.card-name {
  font-size: 17px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px;
  line-height: 1.3;
}

.card-desc {
  font-size: 13px;
  color: #777;
  line-height: 1.7;
  margin: 0 0 14px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  min-height: 44px;
  word-break: break-word;
}

.card-link {
  font-size: 13px;
  color: #fff;
  background: #1a73e8;
  border: none;
  padding: 8px 28px;
  border-radius: 6px;
  flex-shrink: 0;
  transition: background 0.2s;
}
.module-card:hover .card-link {
  background: #1557b0;
}
</style>