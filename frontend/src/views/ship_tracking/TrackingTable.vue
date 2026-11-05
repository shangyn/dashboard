<template>
  <el-table
    ref="tableRef"
    :data="rows"
    row-key="ladder_key"
    size="small"
    border
    :max-height="height"
    class="st-table"
    v-loading="loading"
    @selection-change="(selection) => emit('selection-change', selection)"
  >
    <el-table-column v-if="selectable" type="selection" width="46" />
    <el-table-column prop="module_name" label="模块" width="110" show-overflow-tooltip />
    <el-table-column label="大区" width="76" align="center">
      <template #default="{ row }">{{ row.region || '—' }}</template>
    </el-table-column>
    <el-table-column prop="ladder_no" label="梯号" width="165" />
    <el-table-column label="合同 / 项目" min-width="220">
      <template #default="{ row }">
        <div class="st-contract" :title="`${row.contract_no || '—'}\n${row.project_name || '—'}`">
          <div class="st-contract-no">{{ row.contract_no || '—' }}</div>
          <div class="st-project">{{ row.project_name || '—' }}</div>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="unit_count" label="台数" width="50" align="right" />
    <el-table-column v-if="optionalColumns.includes('amount')" label="金额(万元)" width="90" align="right">
      <template #default="{ row }">{{ row.amount_wan ?? '—' }}</template>
    </el-table-column>
    <el-table-column v-if="optionalColumns.includes('schedule')" label="排产完工日期" width="110" align="center">
      <template #default="{ row }">{{ row.schedule_finish_date || '—' }}</template>
    </el-table-column>
    <el-table-column v-if="optionalColumns.includes('whole')" label="整梯发货日期" width="110" align="center">
      <template #default="{ row }">{{ row.whole_ship_date || '—' }}</template>
    </el-table-column>
    <el-table-column label="预计发货时间" width="100" align="center">
      <template #default="{ row }">
        <span :class="{ 'st-date-missing': !row.expected_ship_date }">
          {{ row.expected_ship_date || '未定' }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="实际发货时间" width="120" align="center">
      <template #default="{ row }">
        <div class="st-actual">
          <span :class="row.actual_ship_date ? 'st-date-ok' : 'st-date-missing'">
            {{ row.actual_ship_date || '未发' }}
          </span>
          <el-tag
            v-if="row.actual_ship_source_label"
            size="small"
            :type="row.actual_ship_source === 'ledger' ? 'success' : 'info'"
            effect="plain"
          >{{ row.actual_ship_source === 'ledger' ? '台账' : '系统' }}</el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="订舱状态" width="110" align="center">
      <template #default="{ row }">
        <div class="st-book">
          <el-tag
            size="small"
            :type="row.booking_status === '已订舱' ? 'success' : 'info'"
            effect="plain"
          >
            {{ row.booking_status || '未订舱' }}
          </el-tag>
          <span
            v-if="row.booking_audit_status && row.booking_audit_status !== '已完成'"
            class="st-book-audit"
          >{{ row.booking_audit_status }}</span>
          <span
            v-else-if="!row.booking_audit_status && row.booking_status === '已订舱'"
            class="st-book-audit"
          >—</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="回款比例" width="92" align="center">
      <template #default="{ row }">
        <span :class="paymentRatioClass(row)">{{ row.payment_ratio_label || '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="发货状态" width="88" align="center">
      <template #default="{ row }">
        <el-tag :type="statusType(row.status)" size="small" effect="plain">
          {{ row.status_label }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="optionalColumns.includes('flags')" label="变更 / 异常" min-width="180">
      <template #default="{ row }">
        <div v-if="row.plan_change_count" class="st-change-count">计划变更 {{ row.plan_change_count }} 次</div>
        <div v-if="row.flag_labels?.length" class="st-flags" :title="row.flag_labels.join('；')">
          {{ row.flag_labels.join('；') }}
        </div>
        <span v-if="!row.plan_change_count && !row.flag_labels?.length">—</span>
      </template>
    </el-table-column>
    <el-table-column label="详情" width="58" align="center">
      <template #default="{ row }">
        <el-button link type="primary" size="small" @click="emit('detail', row)">详情</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { useTableRepaint } from './useTableRepaint'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectable: { type: Boolean, default: false },
  height: { type: [String, Number], default: 560 },
  optionalColumns: { type: Array, default: () => [] },
})
const emit = defineEmits(['selection-change', 'detail'])

const tableRef = ref(null)
const { nudge } = useTableRepaint(() => tableRef.value)
watch(
  () => props.rows,
  () => nextTick(nudge)
)

function statusType(status) {
  if (status === 'shipped') return 'success'
  if (status === 'overdue') return 'danger'
  if (status === 'committed') return 'primary'
  if (status === 'removed') return 'info'
  return 'warning'
}

function paymentRatioClass(row) {
  if (row.payment_ratio === null || row.payment_ratio === undefined) return 'st-ratio-missing'
  if (row.payment_ratio >= 1) return 'st-ratio-full'
  if (row.payment_ratio > 0) return 'st-ratio-partial'
  return 'st-ratio-zero'
}
</script>

<style scoped>
.st-table { width: 100%; }
/* 让表体滚动视口成为独立合成层，规避 Chrome 滚动后单元格漏绘 */
.st-table :deep(.el-table__body-wrapper) { transform: translateZ(0); }
.st-table :deep(.el-table__cell) { padding: 4px 0; }
.st-table :deep(.cell) { padding: 0 8px; line-height: 1.3; }
.st-contract { min-width: 0; line-height: 1.35; }
.st-contract-no { font-size: 12px; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-project { font-size: 11px; color: #64748b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-book { display: flex; flex-direction: column; align-items: center; gap: 2px; line-height: 1.2; }
.st-book-audit { font-size: 11px; color: #64748b; }
.st-date-ok { color: #15803d; font-weight: 700; }
.st-date-missing { color: #94a3b8; }
.st-actual { display: flex; flex-direction: column; align-items: center; gap: 3px; }
.st-ratio-full { color: #15803d; font-weight: 700; }
.st-ratio-partial { color: #d97706; font-weight: 700; }
.st-ratio-zero { color: #64748b; }
.st-ratio-missing { color: #94a3b8; }
.st-change-count { color: #2563eb; font-size: 12px; }
.st-flags { margin-top: 3px; font-size: 11px; color: #d97706; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
