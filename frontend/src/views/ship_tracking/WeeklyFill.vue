<template>
  <div class="st-page" v-loading="loading">
    <div class="st-hero">
      <div>
        <h2 class="st-title">发货梯号明细</h2>
        <div class="st-subtitle">
          业务计划填报
          <el-tag size="small" type="primary" effect="plain">
            {{ fillMonth }}
          </el-tag>
          <span class="st-hint">{{ fillStart }} 至 {{ fillEnd }}</span>
        </div>
      </div>
      <div class="st-hero-actions">
        <el-select
          v-if="myModules.length > 1"
          v-model="moduleName"
          size="small"
          placeholder="全部我的模块"
          style="width: 260px"
          @change="loadData"
        >
          <el-option label="全部我的模块" value="" />
          <el-option
            v-for="name in myModules"
            :key="name"
            :label="moduleOptionLabel(name)"
            :value="name"
          />
        </el-select>
        <span class="st-module" v-else>{{ moduleName }}</span>
        <el-button size="small" plain @click="openManualDialog">手工添加梯号</el-button>
        <el-button size="small" :loading="saving" @click="handleSave">保存草稿</el-button>
        <el-button size="small" type="primary" :loading="submitting" @click="handleSubmit">
          提交计划
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="待填报区只显示尚未进入整体发货明细的梯号；已有预计发货日期、已提交或已发货的梯号会进入下方整体发货明细，不会上下重复。"
    />

    <div class="st-panel">
      <div class="st-panel-head">
        <div>
          <span class="st-panel-title">待填报梯号</span>
          <span class="st-count">共 {{ filteredCandidates.length }} 条</span>
          <span class="st-selected">已选 {{ selectedRows.length }} 条</span>
        </div>
        <div class="st-toolbar">
          <el-input
            v-model="keyword"
            size="small"
            clearable
            placeholder="合同号 / 梯号 / 项目"
            style="width: 220px"
          />
        </div>
      </div>

      <div class="st-batchbar">
        <span class="st-batch-label">批量设置选中梯号日期</span>
        <el-date-picker
          v-model="batchDate"
          size="small"
          type="date"
          value-format="YYYY-MM-DD"
          :disabled-date="disableOutsideFillWindow"
          :default-value="fillDefaultDate"
          placeholder="选择日期"
          style="width: 150px"
        />
        <el-button size="small" :disabled="!batchDate" @click="applyBatchDate">套用</el-button>
        <el-button
          v-for="item in quickDates"
          :key="item.label"
          size="small"
          text
          type="primary"
          :disabled="!selectedRows.length"
          @click="applyQuickDate(item.value)"
        >
          {{ item.label }}
        </el-button>
        <el-button size="small" :disabled="!selectedRows.length" @click="clearSelection">
          清空选择
        </el-button>
        <span class="st-hint">也可逐行选择日期</span>
      </div>

      <el-table
        ref="candidateTableRef"
        :data="pagedCandidates"
        row-key="ladder_key"
        size="small"
        border
        max-height="calc(100vh - 430px)"
        class="st-table"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="42" reserve-selection />
        <el-table-column prop="module_name" label="模块" width="110" show-overflow-tooltip />
        <el-table-column prop="ladder_no" label="梯号" width="165" />
        <el-table-column prop="contract_no" label="合同号" width="120" show-overflow-tooltip />
        <el-table-column prop="project_name" label="项目名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="unit_count" label="台数" width="55" align="right" />
        <el-table-column prop="amount_wan" label="金额(万元)" width="90" align="right" />
        <el-table-column label="订舱状态" width="96" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.booking_status === '已订舱' ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.booking_status || '未订舱' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="预计发货日期" width="165">
          <template #default="{ row }">
            <el-date-picker
              v-model="dateMap[row.ladder_key]"
              size="small"
              type="date"
              value-format="YYYY-MM-DD"
              :disabled-date="disableOutsideFillWindow"
              :default-value="fillDefaultDate"
              placeholder="请选择"
              style="width: 148px"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="92" align="center">
          <template #default="{ row }">
            <el-tag v-if="dateMap[row.ladder_key]" size="small" type="success" effect="plain">
              已填日期
            </el-tag>
            <el-tag v-else size="small" type="warning" effect="plain">待填日期</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="st-pager"
        layout="total, prev, pager, next"
        :total="filteredCandidates.length"
        :page-size="pageSize"
        :current-page="candidatePage"
        @current-change="(value) => (candidatePage = value)"
      />
    </div>

    <div class="st-panel">
      <div class="st-panel-head">
        <div>
          <span class="st-panel-title">整体发货明细</span>
          <span class="st-count">共 {{ filteredSubmitted.length }} 条</span>
          <span class="st-selected">已选 {{ remarkSelectedRows.length }} 条</span>
        </div>
        <div class="st-toolbar">
          <el-input
            v-model="remarkKeyword"
            size="small"
            clearable
            placeholder="搜索合同号 / 梯号 / 项目"
            style="width: 240px"
          />
        </div>
      </div>
      <div class="st-batchbar">
        <span class="st-batch-label">批量填写备注</span>
        <el-button
          size="small"
          :disabled="!pendingSubmittedRows.length"
          @click="selectAllFilteredRemarks"
        >
          选中筛选结果（{{ pendingSubmittedRows.length }}）
        </el-button>
        <el-button size="small" :disabled="!remarkSelectedRows.length" @click="clearRemarkSelection">
          清空选择
        </el-button>
        <el-button
          size="small"
          type="primary"
          :disabled="!remarkSelectedRows.length"
          @click="openBatchRemarkDialog"
        >
          批量填写备注
        </el-button>
        <span class="st-hint">可按合同号搜索后，一次选中所有未发货梯号；已发货不可选</span>
      </div>
      <el-table
        ref="submittedTableRef"
        :data="pagedSubmitted"
        row-key="ladder_key"
        size="small"
        border
        class="st-table"
        @selection-change="handleRemarkSelectionChange"
      >
        <el-table-column
          type="selection"
          width="42"
          reserve-selection
          :selectable="canSelectRemarkRow"
        />
        <el-table-column prop="ladder_no" label="梯号" width="185" />
        <el-table-column prop="project_name" label="项目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="module_name" label="模块" width="150" />
        <el-table-column prop="expected_ship_date" label="预计发货日期" width="126" align="center" />
        <el-table-column label="订舱状态" width="96" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.booking_status === '已订舱' ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.booking_status || '未订舱' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="committed_week_start" label="提交周" width="110" align="center" />
        <el-table-column prop="committed_by_name" label="填报人" width="90" align="center" />
        <el-table-column label="当前状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="plain">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="同周调整" min-width="250">
          <template #default="{ row }">
            <div v-if="row.actual_ship_date" class="st-hint">已发货，只读</div>
            <div v-else-if="row.commit_status === 'committed'" class="st-adjust-cell">
              <el-date-picker
                v-model="editDates[row.ladder_key]"
                size="small"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled-date="disableOutsideFillWindow"
                :default-value="fillDefaultDate"
                style="width: 145px"
              />
              <el-button size="small" text type="primary" @click="handleAdjust(row)">改期</el-button>
              <el-button size="small" text type="danger" @click="handleWithdraw(row)">撤回</el-button>
            </div>
            <span v-else class="st-hint">—</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="220">
          <template #default="{ row }">
            <div class="st-remark-cell">
              <span class="st-remark-text" :title="row.business_remark || ''">
                {{ row.business_remark || '—' }}
              </span>
              <el-button
                v-if="!row.actual_ship_date"
                size="small"
                text
                type="primary"
                @click="openRemarkDialog(row)"
              >
                {{ row.business_remark ? '编辑备注' : '添加备注' }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="st-pager"
        layout="total, prev, pager, next"
        :total="filteredSubmitted.length"
        :page-size="pageSize"
        :current-page="submittedPage"
        @current-change="(value) => (submittedPage = value)"
      />
    </div>

    <el-dialog
      v-model="remarkDialog.visible"
      :title="remarkDialog.rows.length ? '批量填写备注' : '填写备注'"
      width="520px"
    >
      <div v-if="!remarkDialog.rows.length" class="st-remark-target">
        <strong>{{ remarkDialog.row?.ladder_no || '' }}</strong>
        <span>{{ remarkDialog.row?.project_name || '' }}</span>
      </div>
      <div v-else class="st-remark-target">
        <strong>已选择 {{ remarkDialog.rows.length }} 条未发货梯号</strong>
        <span>{{ batchRemarkPreview }}</span>
      </div>
      <el-alert
        v-if="remarkDialog.rows.length"
        type="warning"
        :closable="false"
        show-icon
        title="保存后将用同一段内容覆盖选中梯号的现有业务备注。"
        style="margin-bottom: 12px"
      />
      <el-input
        v-model="remarkDialog.value"
        type="textarea"
        :rows="5"
        maxlength="500"
        show-word-limit
        placeholder="请填写未按时发货的原因或补充说明"
      />
      <template #footer>
        <el-button @click="remarkDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="remarkDialog.saving" @click="saveRemark">
          {{ remarkDialog.rows.length ? '批量保存' : '保存备注' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="manualDialog.visible" title="手工添加合同号 / 梯号" width="480px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="梯号必须已在台账中；系统按台账归属模块校验你的填报范围。添加后请在本页填写预计发货日期。"
        style="margin-bottom: 14px"
      />
      <el-form label-width="80px" @submit.prevent>
        <el-form-item label="完整梯号">
          <el-input
            v-model="manualDialog.ladderNo"
            placeholder="例如 DHT-261102T/1#"
            clearable
            @keyup.enter="submitManualLadder(false)"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="manualDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="manualDialog.loading" @click="submitManualLadder(false)">
          添加
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addWeeklyLadder,
  adjustWeeklyPlan,
  getWeeklyPlan,
  saveWeeklyDraft,
  saveWeeklyRemark,
  saveWeeklyRemarks,
  submitWeeklyPlan,
  withdrawWeeklyPlan,
} from '../../api/shipTracking'
import { useTableRepaint } from './useTableRepaint'

const props = defineProps({
  context: { type: Object, required: true },
})
const emit = defineEmits(['refresh-context'])

const loading = ref(false)
const saving = ref(false)
const submitting = ref(false)
const moduleName = ref('')
const keyword = ref('')
const remarkKeyword = ref('')
const candidates = ref([])
const submitted = ref([])
const draftRows = ref([])
const selectedRows = ref([])
const remarkSelectedRows = ref([])
const dateMap = reactive({})
const editDates = reactive({})
const batchDate = ref('')
const candidatePage = ref(1)
const submittedPage = ref(1)
const pageSize = 50
const candidateTableRef = ref(null)
const submittedTableRef = ref(null)
const { nudge: nudgeCandidates } = useTableRepaint(() => candidateTableRef.value)
const { nudge: nudgeSubmitted } = useTableRepaint(() => submittedTableRef.value)
watch([candidates, submitted], () =>
  nextTick(() => {
    nudgeCandidates()
    nudgeSubmitted()
  })
)
const quickDates = ref([])
const moduleCounts = ref({})
const manualDialog = reactive({ visible: false, ladderNo: '', loading: false })
const remarkDialog = reactive({
  visible: false,
  row: null,
  rows: [],
  value: '',
  saving: false,
})

const myModules = computed(() => props.context.my_modules || [])
const fillStart = computed(() => props.context.fill_start || props.context.today || props.context.target_week_start || '')
const fillEnd = computed(() => props.context.fill_end || props.context.target_week_end || fillStart.value)
const fillMonth = computed(() => props.context.fill_month || fillStart.value.slice(0, 7))
const fillDefaultDate = computed(() => {
  const value = props.context.fill_default_date || (fillMonth.value ? `${fillMonth.value}-01` : fillStart.value)
  if (!value) return undefined
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
})

function moduleOptionLabel(name) {
  const entry = moduleCounts.value[name] || {}
  const count = entry.candidates || 0
  return `${name}（${count} 条待填）`
}
const filteredCandidates = computed(() => {
  const text = keyword.value.trim().toUpperCase()
  if (!text) return candidates.value
  return candidates.value.filter((row) =>
    [row.contract_no, row.ladder_no, row.project_name, row.module_name]
      .join(' ').toUpperCase().includes(text)
  )
})
const filteredSubmitted = computed(() => {
  const text = remarkKeyword.value.trim().toUpperCase()
  if (!text) return submitted.value
  return submitted.value.filter((row) =>
    [row.contract_no, row.ladder_no, row.project_name, row.module_name, row.business_remark]
      .join(' ').toUpperCase().includes(text)
  )
})
const pendingSubmittedRows = computed(() => filteredSubmitted.value.filter(canSelectRemarkRow))
const batchRemarkPreview = computed(() => {
  const rows = remarkDialog.rows || []
  if (!rows.length) return ''
  const ladders = rows.slice(0, 6).map((row) => row.ladder_no).join('、')
  const contracts = new Set(rows.map((row) => row.contract_no).filter(Boolean))
  return `${rows.length} 条：${ladders}${rows.length > 6 ? ' 等' : ''}${contracts.size ? `；涉及 ${contracts.size} 个合同` : ''}`
})
const pagedCandidates = computed(() => {
  const start = (candidatePage.value - 1) * pageSize
  return filteredCandidates.value.slice(start, start + pageSize)
})
const pagedSubmitted = computed(() => {
  const start = (submittedPage.value - 1) * pageSize
  return filteredSubmitted.value.slice(start, start + pageSize)
})

function isoDate(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

function statusTagType(status) {
  if (status === 'shipped') return 'success'
  if (status === 'overdue') return 'danger'
  if (status === 'pending') return 'warning'
  if (status === 'removed') return 'info'
  return 'primary'
}

function formatLocalDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function monthEndOf(dateText) {
  const [year, month] = dateText.split('-').map(Number)
  return formatLocalDate(new Date(year, month, 0))
}

function buildQuickDates() {
  const start = fillStart.value
  const end = fillEnd.value
  if (!start || !end) {
    quickDates.value = []
    return
  }
  const currentMonth = start.slice(0, 7)
  const currentMonthEnd = monthEndOf(start)
  const candidates = [{ label: '今天', value: start }]
  if (currentMonthEnd >= start && currentMonthEnd <= end && currentMonthEnd !== start) {
    candidates.push({ label: '本月末', value: currentMonthEnd })
  }
  const defaultDate = props.context.fill_default_date || ''
  if (fillMonth.value !== currentMonth && defaultDate >= start && defaultDate <= end) {
    candidates.push({ label: '下月初', value: defaultDate })
  }
  if (end !== currentMonthEnd) {
    candidates.push({ label: fillMonth.value !== currentMonth ? '下月末' : '窗口末', value: end })
  }
  const seen = new Set()
  quickDates.value = candidates.filter((item) => {
    if (!item.value || seen.has(item.value)) return false
    seen.add(item.value)
    return true
  })
}

function disableOutsideFillWindow(date) {
  const value = formatLocalDate(date)
  return !fillStart.value || !fillEnd.value || value < fillStart.value || value > fillEnd.value
}

async function loadData() {
  loading.value = true
  try {
    const res = await getWeeklyPlan({ module: moduleName.value })
    candidates.value = res.data.candidates || []
    submitted.value = res.data.submitted || []
    draftRows.value = res.data.drafts || []
    moduleCounts.value = res.data.module_counts || {}
    // 先清掉上一次（含其他模块）留下的日期，避免把旧日期再次提交出去。
    Object.keys(dateMap).forEach((key) => delete dateMap[key])
    Object.keys(editDates).forEach((key) => delete editDates[key])
    draftRows.value.forEach((row) => {
      if (row.draft_expected_ship_date) dateMap[row.ladder_key] = row.draft_expected_ship_date
    })
    submitted.value.forEach((row) => {
      if (row.commit_status === 'committed' && !row.actual_ship_date) {
        editDates[row.ladder_key] = row.committed_expected_ship_date || row.expected_ship_date
      }
    })
    selectedRows.value = []
    remarkSelectedRows.value = []
    candidatePage.value = 1
    submittedPage.value = 1
    if (candidateTableRef.value) candidateTableRef.value.clearSelection()
    if (submittedTableRef.value) submittedTableRef.value.clearSelection()
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function openManualDialog() {
  manualDialog.ladderNo = ''
  manualDialog.visible = true
}

function openRemarkDialog(row) {
  if (row.actual_ship_date) {
    ElMessage.warning('已发货梯号不能修改备注')
    return
  }
  remarkDialog.row = row
  remarkDialog.rows = []
  remarkDialog.value = row.business_remark || ''
  remarkDialog.visible = true
}

function openBatchRemarkDialog() {
  const rows = remarkSelectedRows.value.filter(canSelectRemarkRow)
  if (!rows.length) {
    ElMessage.warning('请先选择未发货梯号')
    return
  }
  const remarks = [...new Set(rows.map((row) => row.business_remark || ''))]
  remarkDialog.row = null
  remarkDialog.rows = rows
  remarkDialog.value = remarks.length === 1 ? remarks[0] : ''
  remarkDialog.visible = true
}

async function saveRemark() {
  if (!remarkDialog.row && !remarkDialog.rows.length) return
  remarkDialog.saving = true
  try {
    if (remarkDialog.rows.length) {
      const rows = remarkDialog.rows.slice()
      const res = await saveWeeklyRemarks({
        module_name: moduleName.value,
        ladder_keys: rows.map((row) => row.ladder_key),
        remark: remarkDialog.value,
      })
      const savedRemark = res.data?.remark ?? remarkDialog.value
      rows.forEach((row) => {
        row.business_remark = savedRemark
      })
      remarkDialog.visible = false
      remarkDialog.rows = []
      clearRemarkSelection()
      const unchanged = Number(res.data?.unchanged || 0)
      ElMessage.success(
        `备注已批量保存：更新 ${res.data?.saved || 0} 条${unchanged ? `，${unchanged} 条内容未变化` : ''}`
      )
      return
    }
    const res = await saveWeeklyRemark({
      module_name: moduleName.value,
      ladder_key: remarkDialog.row.ladder_key,
      remark: remarkDialog.value,
    })
    if (remarkDialog.row) {
      remarkDialog.row.business_remark = res.data?.business_remark || ''
    }
    remarkDialog.visible = false
    remarkDialog.rows = []
    ElMessage.success('备注已保存')
  } catch (error) {
    // 拦截器已提示
  } finally {
    remarkDialog.saving = false
  }
}

async function submitManualLadder(reactivate) {
  const ladderNo = manualDialog.ladderNo.trim()
  if (!ladderNo) {
    ElMessage.warning('请输入完整梯号')
    return
  }
  manualDialog.loading = true
  try {
    const res = await addWeeklyLadder({
      module_name: moduleName.value,
      ladder_no: ladderNo,
      reactivate: Boolean(reactivate),
    })
    const row = res.data || {}
    ElMessage.success(`已加入发货明细：${row.module_name || ''} ${row.ladder_no || ladderNo}`)
    manualDialog.visible = false
    // 直接把关键字设为新梯号，确保它立刻出现在候选池里，便于填写日期。
    keyword.value = row.ladder_no || ladderNo
    await loadData()
  } catch (error) {
    const detail = error?.response?.data?.data
    if (detail?.code === 'removed' && !reactivate) {
      try {
        await ElMessageBox.confirm(
          `该梯号曾在计划中，后被移除。是否恢复到「${detail.module_name || '当前模块'}」并保留原有日期？`,
          '恢复已移除梯号',
          { type: 'warning', confirmButtonText: '恢复', cancelButtonText: '取消' }
        )
        await submitManualLadder(true)
      } catch {
        // 用户取消恢复
      }
    }
  } finally {
    manualDialog.loading = false
  }
}

function handleSelectionChange(rows) {
  selectedRows.value = rows
}

function clearSelection() {
  selectedRows.value = []
  if (candidateTableRef.value) candidateTableRef.value.clearSelection()
}

function canSelectRemarkRow(row) {
  return !row.actual_ship_date
}

function handleRemarkSelectionChange(rows) {
  remarkSelectedRows.value = rows
}

function clearRemarkSelection() {
  remarkSelectedRows.value = []
  if (submittedTableRef.value) submittedTableRef.value.clearSelection()
}

async function selectAllFilteredRemarks() {
  const rows = pendingSubmittedRows.value
  if (!rows.length) {
    ElMessage.warning('当前筛选结果没有可填写备注的未发货梯号')
    return
  }
  await nextTick()
  rows.forEach((row) => submittedTableRef.value?.toggleRowSelection(row, true))
  ElMessage.success(`已选择 ${rows.length} 条未发货梯号`)
}

// 待填报关键字只影响上方候选池，避免合同搜索时清空下方的批量备注选择。
watch(keyword, () => {
  candidatePage.value = 1
  clearSelection()
})

watch(remarkKeyword, () => {
  submittedPage.value = 1
  clearRemarkSelection()
})

function applyBatchDate() {
  if (!selectedRows.value.length) {
    ElMessage.warning('请先勾选梯号')
    return
  }
  selectedRows.value.forEach((row) => {
    dateMap[row.ladder_key] = batchDate.value
  })
  ElMessage.success(`已为 ${selectedRows.value.length} 条梯号设置日期`)
}

function applyQuickDate(value) {
  batchDate.value = value
  applyBatchDate()
}

function collectSelectedItems() {
  if (!selectedRows.value.length) {
    ElMessage.warning('请先勾选要提交的梯号')
    return null
  }
  const missing = selectedRows.value.filter((row) => !dateMap[row.ladder_key])
  if (missing.length) {
    ElMessage.warning(`还有 ${missing.length} 条梯号未选择预计发货日期`)
    return null
  }
  return selectedRows.value.map((row) => ({
    ladder_key: row.ladder_key,
    expected_ship_date: dateMap[row.ladder_key],
  }))
}

async function handleSave() {
  const items = collectSelectedItems()
  if (!items) return
  saving.value = true
  try {
    await saveWeeklyDraft({
      module_name: moduleName.value,
      items,
    })
    ElMessage.success('草稿已保存')
    await loadData()
  } catch (error) {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function handleSubmit() {
  const items = collectSelectedItems()
  if (!items) return
  try {
    await ElMessageBox.confirm(
      `将提交 ${items.length} 条梯号，提交后进入排产并从此后的填报候选池隐藏。确认提交？`,
      '提交计划',
      { type: 'warning', confirmButtonText: '确认提交', cancelButtonText: '再检查一下' }
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    const res = await submitWeeklyPlan({
      module_name: moduleName.value,
      items,
    })
    ElMessage.success(`已提交 ${res.data.submitted} 条梯号`)
    await loadData()
    emit('refresh-context')
  } catch (error) {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

async function handleAdjust(row) {
  const date = editDates[row.ladder_key]
  if (!date) {
    ElMessage.warning('请选择调整后的日期')
    return
  }
  try {
    await adjustWeeklyPlan({
      module_name: moduleName.value,
      items: [{ ladder_key: row.ladder_key, expected_ship_date: date }],
    })
    ElMessage.success('日期已调整')
    await loadData()
  } catch (error) {
    // 拦截器已提示
  }
}

async function handleWithdraw(row) {
  try {
    await ElMessageBox.confirm(
      `确认撤回梯号 ${row.ladder_no}？撤回后该梯号会重新回到候选池。跨周撤回需要管理员解锁。`,
      '撤回提交',
      { type: 'warning', confirmButtonText: '确认撤回', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await withdrawWeeklyPlan({
      module_name: moduleName.value,
      ladder_keys: [row.ladder_key],
    })
    ElMessage.success('已撤回')
    await loadData()
  } catch (error) {
    // 拦截器已提示
  }
}

onMounted(async () => {
  moduleName.value = myModules.value.length > 1 ? '' : (myModules.value[0] || '')
  buildQuickDates()
  await loadData()
})
</script>

<style scoped>
.st-page { max-width: 1680px; margin: 0 auto; padding: 22px 24px 42px; }
.st-hero { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 18px; }
.st-title { margin: 0 0 8px; font-size: 25px; color: #172554; }
.st-subtitle { display: flex; align-items: center; gap: 10px; color: #64748b; font-size: 13px; }
.st-hero-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.st-module { font-size: 14px; font-weight: 700; color: #1d4ed8; padding: 7px 12px; border-radius: 8px; background: #eff6ff; }
.st-panel { margin-top: 18px; background: #fff; border: 1px solid #e5eaf2; border-radius: 12px; padding: 16px; box-shadow: 0 5px 18px rgba(30, 64, 175, 0.05); }
.st-panel-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 12px; flex-wrap: wrap; }
.st-panel-title { font-size: 16px; font-weight: 700; color: #1e293b; }
.st-count, .st-hint { margin-left: 10px; font-size: 12px; color: #94a3b8; }
.st-selected { margin-left: 14px; font-size: 12px; color: #2563eb; font-weight: 600; }
.st-toolbar { display: flex; align-items: center; gap: 12px; }
.st-batchbar { display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 12px; border-radius: 8px; background: #f8fafc; border: 1px dashed #cbd5e1; flex-wrap: wrap; }
.st-batch-label { font-size: 13px; color: #475569; font-weight: 600; }
.st-table { width: 100%; }
.st-table :deep(.el-table__body-wrapper) { transform: translateZ(0); }
.st-adjust-cell { display: flex; align-items: center; gap: 6px; }
.st-remark-cell { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.st-remark-text { color: #475569; font-size: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; }
.st-remark-target { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; color: #334155; }
.st-remark-target span { color: #64748b; font-size: 12px; }
.st-pager { margin-top: 14px; justify-content: flex-end; }
@media (max-width: 760px) {
  .st-page { padding: 12px; }
  .st-hero { display: block; }
  .st-hero-actions { justify-content: flex-start; margin-top: 14px; }
  .st-batchbar { align-items: flex-start; }
}
</style>
