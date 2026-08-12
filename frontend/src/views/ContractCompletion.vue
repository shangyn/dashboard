<template>
  <div class="cc-page">
    <!-- 顶部信息栏 -->
    <div class="cc-topbar">
      <h2 class="cc-title">2026年国际市场运营系统合同完成情况</h2>
      <div class="cc-topbar-right">
        <span class="cc-date">数据截止：{{ dataDate }}</span>
        <el-select v-model="selectedYear" size="small" style="width:90px" @change="onFilterChange">
          <el-option :value="2026" label="2026" />
          <el-option :value="2025" label="2025" />
        </el-select>
        <el-select v-model="selectedRegion" size="small" style="width:120px" clearable placeholder="全部大区" @change="onRegionChange">
          <el-option v-for="r in regions" :key="r" :label="r" :value="r" />
        </el-select>
        <span v-if="unmatchedCount > 0" class="cc-warn">
          <el-icon><WarningFilled /></el-icon>
          {{ unmatchedCount }} 条未匹配
        </span>
      </div>
    </div>

    <div class="cc-body">
      <!-- 左侧切换按钮 -->
      <div class="cc-sidebar">
        <button
          class="cc-toggle-btn"
          :class="{ active: activeView === 'chart' }"
          @click="activeView = 'chart'"
        >
          看 板
        </button>
        <button
          class="cc-toggle-btn"
          :class="{ active: activeView === 'table' }"
          @click="activeView = 'table'"
        >
          图 表
        </button>
        <a
          v-if="unmatchedCount > 0"
          href="/uploads/unmatched_contracts.txt"
          target="_blank"
          class="cc-dl-link"
        >
          下载未匹配报告
        </a>
      </div>

      <!-- 右侧内容区 -->
      <div class="cc-content">
        <!-- 看板视图 -->
        <div v-show="activeView === 'chart'">
          <ChartView
            :regions="regionData?.regions || []"
            :grandTotal="regionData?.grand_total"
            :metricConfig="metricConfig"
            :loading="loading"
          />
        </div>

        <!-- 表格视图 -->
        <div v-show="activeView === 'table'">
          <el-tabs v-model="activeSheet" type="border-card">
            <el-tab-pane label="大区汇总" name="sheet1">
              <TableSheet1
                :regions="regionData?.regions || []"
                :grandTotal="regionData?.grand_total"
                :metricConfig="metricConfig"
                :loading="loading"
              />
            </el-tab-pane>
            <el-tab-pane label="模块明细" name="sheet2">
              <TableSheet2
                :modules="moduleData?.modules || []"
                :metricConfig="metricConfig"
                :loading="loading"
              />
            </el-tab-pane>
            <el-tab-pane label="业务员表" name="sheet3">
              <TableSheet3
                :salespersons="spData?.salespersons || []"
                :loading="loading"
              />
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import {
  getRegionSummary, getModuleDetail, getSalespersonComparison,
  getDataStatus, getRegions,
} from '../api/contract-completion'
import ChartView from '../components/ContractCompletion/ChartView.vue'
import TableSheet1 from '../components/ContractCompletion/TableSheet1.vue'
import TableSheet2 from '../components/ContractCompletion/TableSheet2.vue'
import TableSheet3 from '../components/ContractCompletion/TableSheet3.vue'

const loading = ref(false)
const activeView = ref('chart')
const activeSheet = ref('sheet1')
const selectedRegion = ref(null)
const selectedYear = ref(2026)
const dataDate = ref('--')
const unmatchedCount = ref(0)
const regions = ref(['俄罗斯','亚洲','亚洲1','亚洲2','美洲','中东','非洲','欧洲','商贸合计'])

const regionData = ref(null)
const moduleData = ref(null)
const spData = ref(null)
const metricConfig = ref([])

onMounted(() => fetchAll())

async function fetchAll() {
  loading.value = true
  try {
    const year = selectedYear.value
    const region = selectedRegion.value || undefined

    const [rRes, mRes, sRes, statusRes] = await Promise.all([
      getRegionSummary(year, region),
      getModuleDetail(year, region),
      getSalespersonComparison(year, region),
      getDataStatus(),
    ])

    regionData.value = rRes.data
    moduleData.value = mRes.data
    spData.value = sRes.data
    metricConfig.value = rRes.data?.metric_config || []
    unmatchedCount.value = statusRes.data?.unmatched_count || 0

    const dates = [
      statusRes.data?.last_ledger_upload,
      statusRes.data?.last_payment_upload,
    ].filter(Boolean).sort().reverse()
    dataDate.value = dates[0] || '--'
  } catch (e) {
    ElMessage.error('数据加载失败: ' + (e?.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  fetchAll()
}

function onRegionChange() {
  fetchAll()
}
</script>

<style scoped>
.cc-page {
  min-height: calc(100vh - 56px);
  background: #f0f2f5;
}

.cc-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
  flex-wrap: wrap;
  gap: 10px;
}
.cc-title {
  margin: 0;
  font-size: 18px;
  color: #1a1a2e;
}
.cc-topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.cc-date {
  color: #888;
  font-size: 12px;
}
.cc-warn {
  color: #e6a23c;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.cc-body {
  display: flex;
  min-height: calc(100vh - 110px);
}

.cc-sidebar {
  width: 100px;
  background: #fff;
  border-right: 1px solid #e8eaed;
  padding: 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.cc-toggle-btn {
  width: 100%;
  padding: 12px 8px;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  background: #fafbfc;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #555;
  transition: all .2s;
  text-align: center;
}
.cc-toggle-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}
.cc-toggle-btn.active {
  background: #3b82f6;
  color: #fff;
  border-color: #3b82f6;
}
.cc-dl-link {
  display: block;
  margin-top: 20px;
  font-size: 11px;
  color: #3b82f6;
  text-decoration: underline;
  text-align: center;
}

.cc-content {
  flex: 1;
  padding: 16px;
  min-width: 0;
}

@media (max-width: 480px) {
  .cc-topbar {
    padding: 10px 12px;
  }
  .cc-title {
    font-size: 15px;
    width: 100%;
  }
  .cc-topbar-right {
    gap: 6px;
  }
  .cc-body {
    flex-direction: column;
  }
  .cc-sidebar {
    width: 100%;
    height: auto;
    flex-direction: row;
    flex-wrap: wrap;
    padding: 8px 10px;
    gap: 6px;
  }
  .cc-toggle-btn {
    width: auto;
    flex: 1;
    min-width: 60px;
    padding: 10px 6px;
    font-size: 12px;
  }
  .cc-dl-link {
    margin-top: 0;
    margin-left: auto;
  }
  .cc-content {
    padding: 10px 8px;
  }
}
</style>
