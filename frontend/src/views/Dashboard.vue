<template>
  <div class="dashboard-page">
    <div class="iframe-container" v-loading="loading">
      <iframe v-if="iframeUrl" :src="iframeUrl" class="dashboard-iframe" frameborder="0" />
      <el-empty v-else description="看板未配置或不可用" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getMyModules } from '../api/modules'

const props = defineProps(['id'])
const route = useRoute()

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
.dashboard-page { height: 100vh; margin: 0; overflow: hidden; }
.iframe-container { width: 100%; height: 100%; background: #fff; }
.dashboard-iframe { width: 100%; height: 100%; border: none; display: block; }
</style>