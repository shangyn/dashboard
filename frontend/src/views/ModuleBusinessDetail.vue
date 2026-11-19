<template>
  <div class="mbd-page">
    <div class="page-head">
      <div>
        <div class="title-line">
          <h2>模块经营明细</h2>
          <el-tag :type="context.scoped ? 'info' : 'success'" effect="plain">
            {{ context.scoped ? '仅本人模块' : '全部模块' }}
          </el-tag>
        </div>
        <p>合同、梯号、签排发、回款与计划明细（只读）</p>
      </div>
      <el-button :loading="loading.export" @click="handleExport">导出 Excel</el-button>
    </div>

    <div class="filter-card">
      <div class="filter-item">
        <span>月份</span>
        <el-select v-model="filters.month" style="width: 150px" @change="handleFilterChange">
          <el-option label="全部月份" value="" />
          <el-option v-for="item in context.months" :key="item" :label="item" :value="item" />
        </el-select>
      </div>
      <div class="filter-item">
        <span>模块</span>
        <el-select v-model="filters.module" clearable filterable style="width: 200px" @change="handleFilterChange">
          <el-option label="全部模块" value="" />
          <el-option v-for="item in context.modules" :key="item" :label="item" :value="item" />
        </el-select>
      </div>
      <div class="filter-item grow">
        <span>搜索</span>
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="合同号 / 梯号 / 项目 / 业务员"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
      </div>
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="loadAll">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div v-for="item in statCards" :key="item.key" class="stat-card">
        <div class="stat-label">{{ item.label }}</div>
        <div class="stat-value">{{ formatAmount(item.metric.actual) }}<span>万元</span></div>
        <div class="stat-foot">
          目标 {{ formatAmount(item.metric.target) }} 万元
          <b>{{ formatRatio(item.metric.ratio) }}</b>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="detail-tabs">
      <el-tab-pane label="经营概览" name="overview">
        <el-table :data="overview?.modules || []" border stripe size="small" v-loading="loading.overview">
          <el-table-column prop="module_name" label="模块" fixed width="150" />
          <el-table-column prop="region" label="大区" width="90" />
          <el-table-column label="年度签单额" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.annual.sign_amount.actual) }}</template>
          </el-table-column>
          <el-table-column label="年度排产额" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.annual.schedule_amount.actual) }}</template>
          </el-table-column>
          <el-table-column label="年度发货额" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.annual.ship_amount.actual) }}</template>
          </el-table-column>
          <el-table-column label="年度回款额" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.annual.payment_amount.actual) }}</template>
          </el-table-column>
          <el-table-column label="年签单完成率" align="right" width="120">
            <template #default="{ row }">{{ formatRatio(row.annual.sign_amount.ratio) }}</template>
          </el-table-column>
          <el-table-column label="本月计划签单" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_plan.sign_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月计划排产" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_plan.prod_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月计划发货" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_plan.ship_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月计划回款" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_plan.payment_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月实际签单" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_actual.sign_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月实际排产" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_actual.prod_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月实际发货" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_actual.ship_amount) }}</template>
          </el-table-column>
          <el-table-column label="本月实际回款" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.month_actual.payment_amount) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="梯号明细" name="ladders">
        <div class="summary-line">
          <el-tag effect="plain">共 {{ ladderState.summary.total || 0 }} 个梯号</el-tag>
          <el-tag type="success" effect="plain">已发货 {{ ladderState.summary.shipped || 0 }}</el-tag>
          <el-tag type="warning" effect="plain">逾期 {{ ladderState.summary.overdue || 0 }}</el-tag>
          <el-tag effect="plain">台数 {{ formatNumber(ladderState.summary.units) }}</el-tag>
        </div>
        <el-table :data="ladderState.rows" border stripe size="small" v-loading="loading.ladders">
          <el-table-column prop="module_name" label="模块" fixed width="140" />
          <el-table-column prop="contract_no" label="合同号" width="150" />
          <el-table-column prop="ladder_no" label="梯号" width="170" />
          <el-table-column prop="project_name" label="项目名称" min-width="190" show-overflow-tooltip />
          <el-table-column label="国家 / 大区" min-width="150">
            <template #default="{ row }">{{ row.country || '—' }} / {{ row.region || '—' }}</template>
          </el-table-column>
          <el-table-column prop="salesperson" label="业务员" width="100" />
          <el-table-column prop="unit_count" label="台数" align="right" width="80" />
          <el-table-column label="金额(万元)" align="right" width="110">
            <template #default="{ row }">{{ formatAmount(row.amount_wan) }}</template>
          </el-table-column>
          <el-table-column label="回款比例" align="right" width="100">
            <template #default="{ row }">{{ row.payment_ratio_label || '—' }}</template>
          </el-table-column>
          <el-table-column prop="plan_month" label="计划月份" width="100" />
          <el-table-column prop="expected_ship_date" label="预计发货" width="110" />
          <el-table-column prop="actual_ship_date" label="实际发货" width="110" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
                {{ row.status_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="commit_label" label="提交" width="90" />
          <el-table-column prop="booking_status" label="订舱" width="90" />
          <el-table-column prop="business_remark" label="业务备注" min-width="160" show-overflow-tooltip />
        </el-table>
        <div class="pager-line">
          <el-pagination
            v-model:current-page="ladderState.page"
            :page-size="ladderState.pageSize"
            :total="ladderState.summary.total || 0"
            layout="total, prev, pager, next"
            @current-change="loadLadders"
          />
        </div>
      </el-tab-pane>

      <el-tab-pane label="回款明细" name="payments">
        <div class="summary-line">
          <el-tag effect="plain">共 {{ paymentState.summary.total || 0 }} 笔</el-tag>
          <el-tag type="success" effect="plain">人民币 {{ formatAmount(paymentState.summary.amount_wan) }} 万元</el-tag>
          <el-tag v-if="paymentState.summary.unmatched" type="warning" effect="plain">
            未匹配 {{ paymentState.summary.unmatched }} 笔
          </el-tag>
        </div>
        <el-table :data="paymentState.rows" border stripe size="small" v-loading="loading.payments">
          <el-table-column prop="module_name" label="模块" fixed width="140" />
          <el-table-column prop="contract_no" label="合同号" width="150" />
          <el-table-column prop="ladder_no" label="梯号" width="170" />
          <el-table-column prop="project_name" label="项目名称" min-width="190" show-overflow-tooltip />
          <el-table-column prop="payment_date" label="回款日期" width="110" />
          <el-table-column label="原币金额" align="right" width="120">
            <template #default="{ row }">{{ formatNumber(row.payment_amount_orig) }}</template>
          </el-table-column>
          <el-table-column prop="currency" label="币种" width="80" />
          <el-table-column label="人民币(万元)" align="right" width="130">
            <template #default="{ row }">{{ formatAmount(row.payment_amount_wan) }}</template>
          </el-table-column>
          <el-table-column prop="node_type" label="节点" width="120" />
          <el-table-column prop="payment_method" label="付款方式" width="120" />
          <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        </el-table>
        <div class="pager-line">
          <el-pagination
            v-model:current-page="paymentState.page"
            :page-size="paymentState.pageSize"
            :total="paymentState.summary.total || 0"
            layout="total, prev, pager, next"
            @current-change="loadPayments"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  downloadExport,
  getContext,
  getLadders,
  getOverview,
  getPayments,
} from '../api/moduleBusinessDetail'

const context = reactive({
  modules: [],
  months: [],
  default_month: '',
  scoped: true,
  year: 2026,
})
const filters = reactive({ month: '', module: '', keyword: '' })
const activeTab = ref('overview')
const overview = ref(null)
const loading = reactive({ overview: false, ladders: false, payments: false, export: false })
const ladderState = reactive({ rows: [], summary: {}, page: 1, pageSize: 20 })
const paymentState = reactive({ rows: [], summary: {}, page: 1, pageSize: 20 })

const statCards = computed(() => {
  const annual = overview.value?.totals?.annual || {}
  return [
    { key: 'sign_amount', label: '年度签单额', metric: annual.sign_amount || {} },
    { key: 'schedule_amount', label: '年度排产额', metric: annual.schedule_amount || {} },
    { key: 'ship_amount', label: '年度发货额', metric: annual.ship_amount || {} },
    { key: 'payment_amount', label: '年度回款额', metric: annual.payment_amount || {} },
  ]
})

function formatNumber(value) {
  const number = Number(value || 0)
  return number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatAmount(value) {
  return formatNumber(value)
}

function formatRatio(value) {
  return `${((Number(value || 0)) * 100).toFixed(2)}%`
}

function statusTagType(status) {
  if (status === 'shipped') return 'success'
  if (status === 'overdue') return 'danger'
  if (status === 'removed') return 'info'
  if (status === 'committed') return 'warning'
  return ''
}

async function loadContext() {
  const response = await getContext()
  const data = response.data || {}
  context.modules = data.modules || []
  context.months = data.months || []
  context.default_month = data.default_month || ''
  context.scoped = Boolean(data.scoped)
  context.year = data.year || context.year
  filters.month = context.default_month
  if (context.modules.length === 1) filters.module = context.modules[0]
}

async function loadOverview() {
  loading.overview = true
  try {
    const response = await getOverview({
      month: filters.month || context.default_month,
      module: filters.module,
    })
    overview.value = response.data
  } finally {
    loading.overview = false
  }
}

async function loadLadders() {
  loading.ladders = true
  try {
    const response = await getLadders({
      month: filters.month,
      module: filters.module,
      q: filters.keyword,
      page: ladderState.page,
      page_size: ladderState.pageSize,
    })
    const data = response.data || {}
    ladderState.rows = data.rows || []
    ladderState.summary = data.summary || {}
  } finally {
    loading.ladders = false
  }
}

async function loadPayments() {
  loading.payments = true
  try {
    const response = await getPayments({
      month: filters.month,
      year: context.year,
      module: filters.module,
      q: filters.keyword,
      page: paymentState.page,
      page_size: paymentState.pageSize,
    })
    const data = response.data || {}
    paymentState.rows = data.rows || []
    paymentState.summary = data.summary || {}
  } finally {
    loading.payments = false
  }
}

async function loadAll() {
  await Promise.all([loadOverview(), loadLadders(), loadPayments()])
}

function handleFilterChange() {
  ladderState.page = 1
  paymentState.page = 1
  loadAll()
}

function handleSearch() {
  ladderState.page = 1
  paymentState.page = 1
  loadLadders()
  loadPayments()
}

async function handleExport() {
  loading.export = true
  try {
    await downloadExport(
      { month: filters.month || context.default_month, module: filters.module, q: filters.keyword },
      `模块经营明细_${filters.month || context.default_month || '全部'}.xlsx`,
    )
    ElMessage.success('导出已开始')
  } finally {
    loading.export = false
  }
}

onMounted(async () => {
  await loadContext()
  await loadAll()
})
</script>

<style scoped>
.mbd-page {
  max-width: 1800px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-line h2 {
  margin: 0;
  color: #172554;
  font-size: 24px;
}

.page-head p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
}

.filter-card {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 14px;
  padding: 16px 18px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 14px rgba(15, 42, 76, 0.06);
  margin-bottom: 16px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-item > span {
  color: #64748b;
  font-size: 12px;
}

.filter-item.grow {
  flex: 1;
  min-width: 220px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.stat-card {
  padding: 18px 20px;
  background: linear-gradient(135deg, #fff 0%, #f7fbff 100%);
  border: 1px solid #e4edf8;
  border-radius: 12px;
}

.stat-label {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  margin: 8px 0 6px;
  color: #17365d;
  font-size: 26px;
  font-weight: 800;
}

.stat-value span {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
}

.stat-foot {
  color: #7b8ba3;
  font-size: 12px;
}

.stat-foot b {
  margin-left: 8px;
  color: #1a73e8;
}

.detail-tabs {
  padding: 18px 20px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 14px rgba(15, 42, 76, 0.06);
}

.summary-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.pager-line {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

@media (max-width: 1100px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .page-head {
    flex-direction: column;
  }

  .stat-grid {
    grid-template-columns: 1fr;
  }

  .filter-item.grow {
    min-width: 100%;
  }
}
</style>
