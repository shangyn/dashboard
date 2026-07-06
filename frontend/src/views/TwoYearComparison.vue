<template>
  <div class="tyc-page">
    <!-- Top Control Bar -->
    <div class="tyc-topbar">
      <div class="tyc-topbar-left">
        <h2 class="tyc-title">{{ title }}</h2>
        <div class="tyc-segmented">
          <button
            class="tyc-seg-btn"
            :class="{ active: view === 'dashboard' }"
            @click="view = 'dashboard'"
          >
            📈 增长看板
          </button>
          <button
            class="tyc-seg-btn"
            :class="{ active: view === 'table' }"
            @click="view = 'table'"
          >
            📋 数据表格
          </button>
        </div>
      </div>
      <div class="tyc-topbar-right">
        <span class="tyc-date">{{ datePrev }} ~ {{ dateCurr }}</span>
        <el-select
          v-model="selectedRegion"
          size="small"
          style="width:120px"
          clearable
          placeholder="全部大区"
        >
          <el-option v-for="r in regions" :key="r" :label="r" :value="r" />
        </el-select>
        <el-button size="small" type="primary" @click="exportExcel">导出Excel</el-button>
      </div>
    </div>

    <!-- Content Area -->
    <div class="tyc-content">
      <!-- Dashboard View -->
      <div v-show="view === 'dashboard'">
        <TwoYearDashboard
          :rows="allRows"
          :regionOrder="regionOrder"
          :loading="loading"
          :selectedRegion="selectedRegion || null"
        />
      </div>

      <!-- Table View -->
      <div v-show="view === 'table'">
        <TwoYearTable
          :rows="filteredRows"
          :metricGroups="metricGroups"
          :yearPrev="yearPrev"
          :yearCurr="yearCurr"
          :loading="loading"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTwoYearComparison } from '../api/contract-completion'
import TwoYearTable from '../components/ContractCompletion/TwoYearTable.vue'
import TwoYearDashboard from '../components/ContractCompletion/TwoYearDashboard.vue'

const loading = ref(false)
const view = ref('dashboard')
const selectedRegion = ref(null)

const title = ref('')
const datePrev = ref('')
const dateCurr = ref('')
const yearPrev = ref(2025)
const yearCurr = ref(2026)
const metricGroups = ref([])
const allRows = ref([])
const regions = ref([])
const regionOrder = ref([])

const filteredRows = computed(() => {
  if (!selectedRegion.value) return allRows.value
  return allRows.value.filter(r =>
    r.region === selectedRegion.value || (r.type !== 'data' && r.type !== 'trade')
  )
})

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await getTwoYearComparison()
    const d = res.data
    title.value = d.title
    datePrev.value = d.date_prev_end
    dateCurr.value = d.date_curr_end
    yearPrev.value = d.year_prev
    yearCurr.value = d.year_curr
    metricGroups.value = d.metric_groups || []
    allRows.value = d.rows || []
    regions.value = d.region_order || []
    regionOrder.value = d.region_order || []
  } catch (e) {
    ElMessage.error('数据加载失败')
  } finally {
    loading.value = false
  }
}

function exportExcel() {
  const token = localStorage.getItem('token')
  const url = '/api/contract-completion/two-year-comparison/export'
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(res => res.blob())
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = '两年对比表.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => ElMessage.error('导出失败'))
}
</script>

<style scoped>
.tyc-page { min-height: calc(100vh - 56px); background: #f0f2f5; }

/* ── Top Control Bar ── */
.tyc-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 52px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
}
.tyc-topbar-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.tyc-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #1a1a2e;
  white-space: nowrap;
}

/* ── Segmented Control ── */
.tyc-segmented {
  display: flex;
  background: #f1f5f9;
  border-radius: 8px;
  padding: 3px;
}
.tyc-seg-btn {
  padding: 5px 16px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #888;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all .2s;
  white-space: nowrap;
}
.tyc-seg-btn.active {
  background: #fff;
  color: #1a73e8;
  font-weight: 700;
  box-shadow: 0 1px 3px rgba(0,0,0,.1);
}
.tyc-seg-btn:hover:not(.active) { color: #555; }

/* ── Topbar Right ── */
.tyc-topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.tyc-date { font-size: 11px; color: #999; white-space: nowrap; }

/* ── Content ── */
.tyc-content {
  padding: 14px 20px;
  min-width: 0;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .tyc-topbar {
    flex-wrap: wrap;
    height: auto;
    padding: 8px 12px;
    gap: 8px;
  }
  .tyc-topbar-left { gap: 10px; }
  .tyc-title { font-size: 14px; }
}
</style>
