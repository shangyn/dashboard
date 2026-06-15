<template>
  <div class="dashboard-page">
    <div class="dashboard-topbar">
      <el-button text @click="router.back()">
        <el-icon><ArrowLeft /></el-icon> 返回
      </el-button>
      <span class="dashboard-title">{{ moduleInfo?.name || '看板' }}</span>
      <span class="dashboard-subtitle" v-if="moduleInfo?.description">{{ moduleInfo.description }}</span>
    </div>
    <div class="iframe-container" v-loading="loading">
      <iframe v-if="iframeUrl" :src="iframeUrl" class="dashboard-iframe" frameborder="0" />
      <el-empty v-else description="看板未配置或不可用" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getMyModules } from '../api/modules'

const props = defineProps(['id'])
const route = useRoute()
const router = useRouter()

const moduleInfo = ref(null)
const iframeUrl = ref('')
const loading = ref(false)

onMounted(async () => {
  const moduleId = props.id || route.params.id
  loading.value = true
  try {
    const res = await getMyModules()
    const mod = (res.data || []).find(m => String(m.id) === String(moduleId))
    if (mod) {
      moduleInfo.value = mod
      iframeUrl.value = mod.url || ''
    }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard-page { height: calc(100vh - 50px - 56px); display: flex; flex-direction: column; }
.dashboard-topbar {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 12px;
}
.dashboard-title { font-weight: 600; font-size: 15px; color: #1a1a2e; }
.dashboard-subtitle { font-size: 12px; color: #999; }
.iframe-container { flex: 1; background: #fff; border-radius: 12px; overflow: hidden; }
.dashboard-iframe { width: 100%; height: 100%; border: none; }
</style>
