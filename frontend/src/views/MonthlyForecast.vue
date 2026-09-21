<template>
  <div class="mf-page" v-loading="loading">
    <!-- 顶部控制栏 -->
    <div class="mf-topbar">
      <div class="mf-topbar-left">
        <h2 class="mf-title">单月签排发填报</h2>
        <span class="mf-mode" :class="isScoped ? 'is-scoped' : 'is-readonly'">
          {{ isScoped ? '填报模式' : '只读汇总' }}
        </span>
        <span v-if="isScoped && statusText" class="mf-meta">{{ statusText }}</span>
      </div>
      <div class="mf-topbar-right">
        <el-select v-model="month" size="small" style="width:118px" @change="onMonthChange">
          <el-option v-for="m in context.months" :key="m" :label="m" :value="m" />
        </el-select>
        <el-select
          v-if="isScoped && context.my_modules.length > 1"
          v-model="moduleName"
          size="small"
          style="width:170px"
          @change="onModuleChange"
        >
          <el-option v-for="m in context.my_modules" :key="m" :label="m" :value="m" />
        </el-select>
        <template v-if="isScoped">
          <el-button size="small" @click="handleSave" :loading="saving">保存草稿</el-button>
          <el-button size="small" type="primary" @click="handleSubmit" :loading="submitting">提交</el-button>
        </template>
        <el-button size="small" type="success" plain @click="handleExportForecast">导出预计签排发</el-button>
        <el-button v-if="!isScoped" size="small" type="success" plain @click="handleExportShipping">
          导出预计发货明细
        </el-button>
        <el-button v-if="context.can_import_scope" size="small" plain @click="triggerImport">导入名单</el-button>
        <input
          ref="fileInput"
          type="file"
          accept=".xlsx,.xls,.csv"
          style="display:none"
          @change="handleImportScope"
        />
      </div>
    </div>

    <!-- 填报模式 -->
    <div class="mf-content" v-if="isScoped">
      <div class="mf-cards">
        <div class="mf-card">
          <div class="mf-card-title">签单预计</div>
          <div class="mf-field">
            <span>台数</span>
            <el-input-number v-model="form.sign_units" :min="0" :controls="false" size="small" class="mf-num" />
          </div>
          <div class="mf-field">
            <span>金额(万元)</span>
            <el-input-number v-model="form.sign_amount" :min="0" :controls="false" size="small" class="mf-num" />
          </div>
        </div>
        <div class="mf-card">
          <div class="mf-card-title">排产预计</div>
          <div class="mf-field">
            <span>台数</span>
            <el-input-number v-model="form.prod_units" :min="0" :controls="false" size="small" class="mf-num" />
          </div>
          <div class="mf-field">
            <span>金额(万元)</span>
            <el-input-number v-model="form.prod_amount" :min="0" :controls="false" size="small" class="mf-num" />
          </div>
        </div>
        <div class="mf-card mf-card-ship">
          <div class="mf-card-title">发货预计（候选勾选 + 手工添加）</div>
          <div class="mf-ship-total">
            <span class="mf-ship-num">{{ shipUnits }}</span> 台
            <span class="mf-ship-sep">/</span>
            <span class="mf-ship-num">{{ shipAmount }}</span> 万元
          </div>
          <div class="mf-hint">已选 {{ selectedCount }} 个梯号，默认全部不勾选</div>
        </div>
      </div>

      <div class="mf-panel">
        <div class="mf-panel-head">
          <span class="mf-panel-title">发货候选（组A日期为空 且 已排产）</span>
          <span class="mf-panel-count">共 {{ candidates.length }} 条</span>
          <el-input
            v-model="keyword"
            size="small"
            placeholder="搜索合同号 / 梯号 / 项目名称"
            clearable
            style="width:240px"
          />
        </div>

        <div class="mf-manual">
          <el-input
            v-model="manualLadder"
            size="small"
            placeholder="输入梯号手工添加"
            style="width:240px"
            @keyup.enter="handleManualAdd"
          />
          <el-button size="small" @click="handleManualAdd" :loading="addingManual">添加</el-button>
          <span class="mf-hint">梯号需在台账中存在且属于本模块，否则无效</span>
        </div>

        <el-table :data="pagedCandidates" size="small" :height="tableHeight" class="mf-table">
          <el-table-column label="可发货" width="72" align="center">
            <template #default="{ row }">
              <el-checkbox
                :model-value="isSelected(row.ladder_no)"
                @change="(val) => toggleSelect(row, val)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="contract_no" label="合同号" width="150" />
          <el-table-column prop="ladder_no" label="梯号" width="180" />
          <el-table-column prop="project_name" label="项目名称" min-width="220" show-overflow-tooltip />
          <el-table-column prop="unit_count" label="台数" width="70" align="right" />
          <el-table-column prop="amount_wan" label="金额(万元)" width="110" align="right" />
          <el-table-column prop="schedule_date" label="排产日期" width="110" align="center" />
          <el-table-column label="来源" width="90" align="center">
            <template #default="{ row }">
              <span v-if="selections[row.ladder_no] && selections[row.ladder_no].is_manual" class="mf-tag-manual">
                手工
              </span>
              <span v-else-if="isSelected(row.ladder_no)" class="mf-tag-picked">已选</span>
              <span v-else class="mf-tag-none">-</span>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          class="mf-pager"
          layout="total, prev, pager, next"
          :total="filteredCandidates.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="(p) => (page = p)"
        />
      </div>

      <div class="mf-panel" v-if="manualOnly.length">
        <div class="mf-panel-head">
          <span class="mf-panel-title">手工添加的梯号</span>
          <span class="mf-panel-count">共 {{ manualOnly.length }} 条</span>
        </div>
        <el-table :data="manualOnly" size="small" class="mf-table">
          <el-table-column label="操作" width="72" align="center">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="removeSelection(row.ladder_no)">移除</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="contract_no" label="合同号" width="150" />
          <el-table-column prop="ladder_no" label="梯号" width="180" />
          <el-table-column prop="project_name" label="项目名称" min-width="220" show-overflow-tooltip />
          <el-table-column prop="unit_count" label="台数" width="70" align="right" />
          <el-table-column prop="amount_wan" label="金额(万元)" width="110" align="right" />
          <el-table-column prop="schedule_date" label="排产日期" width="110" align="center" />
        </el-table>
      </div>
    </div>

    <!-- 只读汇总模式 -->
    <div class="mf-content" v-else>
      <div class="mf-panel">
        <div class="mf-panel-head">
          <span class="mf-panel-title">{{ month }} 各模块签排发预计汇总</span>
          <span class="mf-panel-count">共 {{ summaryRows.length }} 个模块</span>
        </div>
        <el-table :data="summaryWithTotal" size="small" class="mf-table" :row-class-name="summaryRowClass">
          <el-table-column prop="module_name" label="模块" width="200" fixed />
          <el-table-column prop="sign_units" label="签单台数" width="100" align="right" />
          <el-table-column prop="sign_amount" label="签单金额(万元)" width="130" align="right" />
          <el-table-column prop="prod_units" label="排产台数" width="100" align="right" />
          <el-table-column prop="prod_amount" label="排产金额(万元)" width="130" align="right" />
          <el-table-column prop="ship_units" label="发货台数" width="100" align="right" />
          <el-table-column prop="ship_amount" label="发货金额(万元)" width="130" align="right" />
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <span v-if="row.status === 'submitted'" class="mf-tag-picked">已提交</span>
              <span v-else-if="row.status === 'draft'" class="mf-tag-manual">草稿</span>
              <span v-else class="mf-tag-none">未填</span>
            </template>
          </el-table-column>
          <el-table-column prop="updated_by_name" label="填报人" width="100" align="center" />
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getContext,
  getEntry,
  saveEntry,
  submitEntry,
  getCandidates,
  validateLadder,
  getSummary,
  importScope,
  downloadExport,
} from '../api/monthly-forecast'

const loading = ref(false)
const saving = ref(false)
const submitting = ref(false)
const addingManual = ref(false)

const context = ref({
  months: [],
  default_month: '',
  my_modules: [],
  all_modules: [],
  can_export_shipping: false,
  can_import_scope: false,
  scoped: false,
})
const month = ref('')
const moduleName = ref('')
const keyword = ref('')
const manualLadder = ref('')
const page = ref(1)
const pageSize = ref(20)
// 候选表格高度跟随窗口，避免表格下方留一大片空白
const tableHeight = ref(360)

function syncTableHeight() {
  const viewport = window.innerHeight || 900
  tableHeight.value = Math.max(320, Math.min(640, viewport - 430))
}
const fileInput = ref(null)
const statusText = ref('')

const form = ref({ sign_units: 0, sign_amount: 0, prod_units: 0, prod_amount: 0 })
const candidates = ref([])
// 已选发货梯号的唯一数据源：{ 梯号: 行数据(含 is_manual) }
const selections = ref({})

const summaryRows = ref([])
const summaryTotal = ref(null)

const isScoped = computed(() => !!context.value.scoped)

function round2(value) {
  return Math.round((Number(value) || 0) * 100) / 100
}

const selectedCount = computed(() => Object.keys(selections.value).length)
const shipUnits = computed(() =>
  round2(Object.values(selections.value).reduce((sum, row) => sum + (Number(row.unit_count) || 0), 0))
)
const shipAmount = computed(() =>
  round2(Object.values(selections.value).reduce((sum, row) => sum + (Number(row.amount_wan) || 0), 0))
)
const manualOnly = computed(() => Object.values(selections.value).filter((row) => row.is_manual))

const filteredCandidates = computed(() => {
  const text = (keyword.value || '').trim().toLowerCase()
  if (!text) return candidates.value
  return candidates.value.filter((row) =>
    `${row.contract_no || ''} ${row.ladder_no || ''} ${row.project_name || ''}`.toLowerCase().includes(text)
  )
})
const pagedCandidates = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredCandidates.value.slice(start, start + pageSize.value)
})
const summaryWithTotal = computed(() =>
  summaryTotal.value ? [...summaryRows.value, summaryTotal.value] : summaryRows.value
)

watch(keyword, () => {
  page.value = 1
})

function summaryRowClass({ row }) {
  return row && row.is_total ? 'mf-total-row' : ''
}

function isSelected(ladderNo) {
  return !!selections.value[ladderNo]
}

function toggleSelect(row, checked) {
  if (checked) {
    selections.value[row.ladder_no] = { ...row, is_manual: false }
  } else {
    delete selections.value[row.ladder_no]
  }
}

function removeSelection(ladderNo) {
  delete selections.value[ladderNo]
}

function applyEntry(data) {
  form.value = {
    sign_units: data.sign_units || 0,
    sign_amount: data.sign_amount || 0,
    prod_units: data.prod_units || 0,
    prod_amount: data.prod_amount || 0,
  }
  const map = {}
  for (const row of data.ship_selections || []) {
    if (row.ladder_no) map[row.ladder_no] = { ...row }
  }
  selections.value = map

  const status = data.status || ''
  if (status === 'submitted') {
    statusText.value = `已提交 · ${data.submitted_at || ''} · ${data.updated_by_name || ''}`
  } else if (status === 'draft' && data.updated_at) {
    statusText.value = `草稿 · ${data.updated_at} · ${data.updated_by_name || ''}`
  } else {
    statusText.value = '未填报'
  }
}

async function loadCandidates() {
  const res = await getCandidates(moduleName.value)
  candidates.value = res.data || []
  page.value = 1
}

async function loadEntry() {
  if (!moduleName.value) return
  const res = await getEntry(month.value, moduleName.value)
  applyEntry(res.data || {})
}

async function loadSummary() {
  const res = await getSummary(month.value)
  summaryRows.value = res.data?.rows || []
  summaryTotal.value = res.data?.total || null
}

async function loadPage() {
  loading.value = true
  try {
    if (isScoped.value) {
      await Promise.all([loadEntry(), loadCandidates()])
    } else {
      await loadSummary()
    }
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    loading.value = false
  }
}

function onMonthChange() {
  loadPage()
}

function onModuleChange() {
  loadPage()
}

async function handleManualAdd() {
  const ladder = (manualLadder.value || '').trim()
  if (!ladder) {
    ElMessage.warning('请输入梯号')
    return
  }
  addingManual.value = true
  try {
    const res = await validateLadder({ month: month.value, module: moduleName.value, ladder_no: ladder })
    const result = res.data || {}
    if (!result.ok) {
      ElMessage.error(result.msg || '该梯号无效')
      return
    }
    selections.value[result.row.ladder_no] = { ...result.row }
    manualLadder.value = ''
    ElMessage.success(result.msg || '已添加')
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    addingManual.value = false
  }
}

function buildPayload() {
  return {
    month: month.value,
    module: moduleName.value,
    sign_units: form.value.sign_units,
    sign_amount: form.value.sign_amount,
    prod_units: form.value.prod_units,
    prod_amount: form.value.prod_amount,
    ship_selections: Object.values(selections.value).map((row) => ({
      ladder_no: row.ladder_no,
      is_manual: !!row.is_manual,
    })),
  }
}

function notifyRejected(rejected) {
  if (!rejected || !rejected.length) return
  const text = rejected.map((item) => `${item.ladder_no}（${item.reason}）`).join('、')
  ElMessage.warning(`以下梯号未保存：${text}`)
}

async function handleSave() {
  saving.value = true
  try {
    const res = await saveEntry(buildPayload())
    const data = res.data || {}
    applyEntry(data)
    notifyRejected(data.rejected)
    ElMessage.success('已保存')
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    saving.value = false
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const res = await submitEntry(buildPayload())
    const data = res.data || {}
    applyEntry(data)
    notifyRejected(data.rejected)
    ElMessage.success(`已提交，留存版本 v${data.version || 1}`)
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    submitting.value = false
  }
}

async function handleExportForecast() {
  try {
    await downloadExport('forecast', month.value, `${month.value}_预计签排发台数金额.xlsx`)
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

async function handleExportShipping() {
  try {
    await downloadExport('shipping', month.value, `${month.value}_预计发货合同梯号明细.xlsx`)
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

function triggerImport() {
  if (fileInput.value) fileInput.value.click()
}

async function handleImportScope(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  try {
    const res = await importScope(file)
    const data = res.data || {}
    ElMessage.success(data.message || '导入完成')
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    event.target.value = ''
  }
}

onMounted(async () => {
  syncTableHeight()
  window.addEventListener('resize', syncTableHeight)
  loading.value = true
  try {
    const res = await getContext()
    context.value = res.data || context.value
    const months = context.value.months || []
    month.value = context.value.default_month || months[months.length - 1] || ''
    moduleName.value = (context.value.my_modules || [])[0] || ''
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    loading.value = false
  }
  await loadPage()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncTableHeight)
})
</script>

<style scoped>
.mf-page {
  min-height: calc(100vh - 56px);
  background: #f0f2f5;
}

.mf-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
  flex-wrap: wrap;
  gap: 10px;
}
.mf-topbar-left,
.mf-topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mf-title {
  margin: 0;
  font-size: 18px;
  color: #1a1a2e;
}
.mf-mode {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}
.mf-mode.is-scoped {
  color: #1d7a46;
  background: #e8f6ee;
}
.mf-mode.is-readonly {
  color: #8a6d1f;
  background: #fdf5e2;
}
.mf-meta {
  font-size: 12px;
  color: #888;
}

.mf-content {
  padding: 16px;
}

.mf-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.mf-card {
  flex: 1;
  min-width: 220px;
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 6px;
  padding: 12px 14px;
}
.mf-card-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 10px;
}
.mf-card-ship {
  border-color: #cfe3d6;
  background: #f7fcf9;
}
.mf-field {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #666;
}
.mf-field:last-child {
  margin-bottom: 0;
}
.mf-num {
  width: 130px;
}
.mf-ship-total {
  font-size: 13px;
  color: #1a1a2e;
  margin-bottom: 6px;
}
.mf-ship-num {
  font-size: 18px;
  font-weight: 600;
  color: #1d7a46;
}
.mf-ship-sep {
  margin: 0 6px;
  color: #ccc;
}
.mf-hint {
  font-size: 12px;
  color: #999;
}

.mf-panel {
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 6px;
  padding: 12px 14px 6px;
  margin-bottom: 12px;
}
.mf-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.mf-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
}
.mf-panel-count {
  font-size: 12px;
  color: #888;
}
.mf-manual {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
  min-height: 52px;
  padding: 8px 12px;
  background: #f7f9fc;
  border: 1px solid #e8eef5;
  border-radius: 6px;
}
.mf-table {
  width: 100%;
}
.mf-pager {
  margin: 10px 0;
  justify-content: flex-end;
}

.mf-tag-manual,
.mf-tag-picked,
.mf-tag-none {
  font-size: 12px;
}
.mf-tag-manual {
  color: #b8860b;
}
.mf-tag-picked {
  color: #1d7a46;
}
.mf-tag-none {
  color: #bbb;
}

:deep(.mf-total-row) {
  font-weight: 600;
  background: #f5f7fa;
}

@media (max-width: 480px) {
  .mf-topbar {
    padding: 10px 12px;
  }
  .mf-title {
    font-size: 15px;
  }
  .mf-content {
    padding: 10px 8px;
  }
  .mf-card {
    min-width: 100%;
  }
}
</style>
