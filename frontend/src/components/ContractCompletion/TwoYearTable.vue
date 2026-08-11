<template>
  <div class="table-wrap" v-loading="loading">
    <!-- Column toggle buttons -->
    <div class="col-toggle-bar" v-if="metricGroups.length">
      <span class="col-toggle-label">列组：</span>
      <button
        v-for="tg in TOGGLE_GROUPS"
        :key="tg.id"
        class="col-toggle-btn"
        :class="{ 'col-toggle-btn--hidden': isGroupHidden(tg.keys) }"
        @click="toggleKeys(tg.keys)"
      >
        {{ isGroupHidden(tg.keys) ? '👁‍🗨' : '👁' }} {{ tg.label }}
      </button>
    </div>
    <div class="table-scroll">
      <table class="cc-table">
        <thead>
          <tr>
            <th rowspan="2" class="fixed" style="width:120px">模块</th>
            <th rowspan="2" class="fixed" style="width:44px">市场<br/>类别</th>
            <template v-for="g in visibleMetricGroups" :key="g.id">
              <th :colspan="g.has_growth ? 3 : 2">{{ g.name }}</th>
            </template>
          </tr>
          <tr>
            <template v-for="g in visibleMetricGroups" :key="'sub-'+g.id">
              <th class="sub">{{ yearPrev }}</th>
              <th class="sub">{{ yearCurr }}</th>
              <th class="sub" v-if="g.has_growth">增长比例</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in rows"
            :key="ri"
            :class="rowClass(row)"
            :style="rowStyle(row)"
          >
            <!-- 模块列：合计行合并A+B，trade行不合并 -->
            <td
              class="fixed module-col"
              :colspan="(row.type === 'subtotal' || row.type === 'grand_total') ? 2 : 1"
              :class="{ 'fw-bold': row.type === 'subtotal' || row.type === 'grand_total' }"
            >
              {{ row.module }}
            </td>
            <td class="fixed cat-col" v-if="row.type === 'data' || row.type === 'trade'">
              {{ row.type === 'trade' ? '' : (row.category || '') }}
            </td>

            <template v-for="g in visibleMetricGroups" :key="g.id">
              <td class="val">{{ fmtVal(row, g.id + '_prev') }}</td>
              <td class="val">{{ fmtVal(row, g.id + '_curr') }}</td>
              <td class="val" v-if="g.has_growth" :style="growthStyle(row, g.id + '_growth')">
                {{ fmtGrowth(row, g.id + '_growth') }}
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty v-if="!rows.length" description="暂无数据，请先上传数据源文件" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  metricGroups: { type: Array, default: () => [] },
  yearPrev: { type: Number, default: 2025 },
  yearCurr: { type: Number, default: 2026 },
  loading: { type: Boolean, default: false },
})

// ── Column toggle ──

const TOGGLE_GROUPS = [
  { id: 'sign',    label: '签订额/差额',   keys: ['sign_amount', 'overseas_diff'] },
  { id: 'schedule', label: '排产额/差额',  keys: ['schedule_amount', 'schedule_overseas_diff'] },
  { id: 'ship',    label: '发货额/差额',  keys: ['ship_amount', 'ship_overseas_diff'] },
  { id: 'payment', label: '回款/海外回款', keys: ['payment', 'overseas_payment'] },
]

// Set of metric IDs currently hidden — default: hide all 额/差额 columns
const hiddenKeys = ref(new Set([
  'sign_amount', 'overseas_diff',
  'schedule_amount', 'schedule_overseas_diff',
  'ship_amount', 'ship_overseas_diff',
  'payment', 'overseas_payment',
]))

function toggleKeys(groupKeys) {
  const s = new Set(hiddenKeys.value)
  const allHidden = groupKeys.every(k => s.has(k))
  if (allHidden) {
    for (const k of groupKeys) s.delete(k)
  } else {
    for (const k of groupKeys) s.add(k)
  }
  hiddenKeys.value = s
}

function isGroupHidden(groupKeys) {
  return groupKeys.every(k => hiddenKeys.value.has(k))
}

// Filtered metric groups — exclude hidden metric IDs
const visibleMetricGroups = computed(() => {
  return props.metricGroups.filter(g => !hiddenKeys.value.has(g.id))
})

// Expose hiddenKeys for parent to read when exporting
defineExpose({ hiddenKeys })

function rowClass(row) {
  return {
    'row-subtotal': row.type === 'subtotal',
    'row-grand': row.type === 'grand_total',
  }
}

function rowStyle(row) {
  if (row.type === 'grand_total') return { background: '#B4C6E7', fontWeight: 'bold' }
  if (row.type === 'subtotal') return { background: '#D6E4F0', fontWeight: 'bold' }
  return {}
}

function fmtVal(row, key) {
  const v = row[key]
  if (v === null || v === undefined) return '-'
  if (typeof v === 'number') {
    if (v === 0) return '-'
    return v.toLocaleString('zh-CN')
  }
  return v
}

function fmtGrowth(row, key) {
  const v = row[key]
  if (v === null || v === undefined) return '-'
  if (v > 0) return '+' + v + '%'
  return v + '%'
}

function growthStyle(row, key) {
  const v = row[key]
  if (v === null || v === undefined) return { color: '#888' }
  if (v > 0) return { color: '#059669', fontWeight: '600' }
  if (v < 0) return { color: '#dc2626', fontWeight: '600' }
  return { color: '#888' }
}
</script>

<style scoped>
.table-wrap { background: #fff; border-radius: 12px; padding: 12px; box-shadow: 0 1px 8px rgba(0,0,0,.05); }
.table-scroll { overflow: auto; max-height: 75vh; }
.cc-table { border-collapse: collapse; font-size: 11px; white-space: nowrap; }
.cc-table th, .cc-table td { border: 1px solid #d0d5dd; padding: 4px 6px; text-align: center; }
.cc-table thead th { background: #eef2f7; font-weight: 600; color: #333; position: sticky; z-index: 3; }
.cc-table thead tr:first-child th { top: 0; }
.cc-table thead tr:last-child th { top: 24px; }
.cc-table .sub { font-weight: 500; color: #555; font-size: 10px; }
.cc-table .fixed { position: sticky; left: 0; z-index: 2; }
.cc-table .module-col { min-width: 120px; text-align: left; padding-left: 8px; }
.cc-table .cat-col { min-width: 44px; }
.cc-table thead .fixed { background: #eef2f7; z-index: 4; }
.cc-table tbody .fixed { background: #fff; }
.cc-table .val { text-align: center; min-width: 60px; }
.fw-bold { font-weight: 700; }
.row-subtotal .fixed { background: #D6E4F0; }
.row-grand .fixed { background: #B4C6E7; }

.col-toggle-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.col-toggle-label {
  font-size: 11px;
  color: #888;
  margin-right: 2px;
}
.col-toggle-btn {
  padding: 4px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fafbfc;
  font-size: 11px;
  cursor: pointer;
  transition: all .2s;
  color: #555;
}
.col-toggle-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}
.col-toggle-btn--hidden {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}
</style>
