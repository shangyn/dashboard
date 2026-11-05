<template>
  <div v-loading="loading" class="st-host">
    <template v-if="context">
      <FullTracking v-if="context.can_full_view" :context="context" @refresh-context="loadContext" />
      <WeeklyFill v-else-if="context.my_modules?.length" :context="context" @refresh-context="loadContext" />
      <div v-else class="st-empty">
        <el-empty description="当前账号尚未分配发货明细权限或模块归属">
          <el-button @click="$router.push('/home')">返回首页</el-button>
        </el-empty>
      </div>
    </template>
    <div v-else-if="error" class="st-empty">
      <el-empty :description="error">
        <el-button @click="loadContext">重试</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getShipTrackingContext } from '../../api/shipTracking'
import FullTracking from './FullTracking.vue'
import WeeklyFill from './WeeklyFill.vue'

const loading = ref(false)
const context = ref(null)
const error = ref('')

async function loadContext() {
  loading.value = true
  error.value = ''
  try {
    const res = await getShipTrackingContext()
    context.value = res.data
  } catch (err) {
    error.value = '加载模块信息失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(loadContext)
</script>

<style scoped>
.st-host { min-height: 100%; background: #f8fafc; }
.st-empty { min-height: 520px; display: flex; align-items: center; justify-content: center; }
</style>
