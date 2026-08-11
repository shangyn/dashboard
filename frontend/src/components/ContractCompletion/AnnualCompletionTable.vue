<template>
  <div class="ac-wrap" v-loading="loading">
    <!-- Column toggle buttons -->
    <div class="col-toggle-bar">
      <span class="col-toggle-label">列组：</span>
      <button class="col-toggle-btn" :class="{ 'col-toggle-btn--hidden': showExtra }" @click="showExtra = !showExtra">
        {{ showExtra ? '👁' : '👁‍🗨' }} 改造/积压/负责人
      </button>
    </div>
    <div class="ac-scroll" v-if="rows.length">
      <table class="ac-table">
        <thead>
          <tr>
            <th rowspan="2" class="fixed" style="width:40px">序号</th>
            <th rowspan="2" class="fixed" style="width:44px">类别</th>
            <th rowspan="2" class="fixed" style="width:130px">模块</th>
            <th v-for="mk in metricKeys" :key="mk.id" :colspan="3" class="group-header">
              {{ mk.label }}
            </th>
            <template v-if="showExtra">
              <th :colspan="6" class="group-header gaizao-hdr">改造</th>
              <th rowspan="2" style="width:60px">积压<br/>台数</th>
              <th rowspan="2" style="width:52px">负责人</th>
            </template>
          </tr>
          <tr>
            <template v-for="mk in metricKeys" :key="mk.id + '_s'">
              <th class="sub">指标</th>
              <th class="sub">实际完成</th>
              <th class="sub">完成全年比</th>
            </template>
            <template v-if="showExtra">
              <th class="sub gaizao-sub">签单台数</th>
              <th class="sub gaizao-sub">签单额</th>
              <th class="sub gaizao-sub">排产台数</th>
              <th class="sub gaizao-sub">排产额</th>
              <th class="sub gaizao-sub">发货台数</th>
              <th class="sub gaizao-sub">发货额</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in rows"
            :key="idx"
            :class="rowClass(row.type)"
          >
            <template v-if="row.type === 'data' || row.type === 'trade'">
              <td class="fixed ac-ctr">{{ row.seq || '' }}</td>
              <td class="fixed ac-ctr">{{ row.category || '' }}</td>
              <td class="fixed">{{ row.module }}</td>
            </template>
            <template v-else>
              <td class="fixed fw-bold" colspan="3">{{ row.module }}</td>
            </template>

            <template v-for="mk in metricKeys" :key="mk.id">
              <td class="val">{{ fmtNum(row[mk.id + '_target']) }}</td>
              <td class="val">{{ fmtNum(row[mk.id + '_actual']) }}</td>
              <td class="val" :style="ratioColor(row[mk.id + '_ratio'])">{{ showRatio(row, mk.id) }}</td>
            </template>
            <template v-if="showExtra">
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_sign_units) }}</td>
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_sign_amount) }}</td>
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_schedule_units) }}</td>
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_schedule_amount) }}</td>
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_ship_units) }}</td>
              <td class="val gaizao-val">{{ fmtNum(row.gaizao_ship_amount) }}</td>
              <td class="val">{{ fmtNum(row.backlog_units) }}</td>
              <td class="ac-ctr">{{ row.person || '' }}</td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!rows.length && !loading" class="ac-empty">暂无数据</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const showExtra = ref(false)

defineExpose({ showExtra })

const metricKeys = [
  { id: 'sign_units', label: '签订台数' },
  { id: 'sign_amount', label: '签订额' },
  { id: 'schedule_units', label: '排产台数' },
  { id: 'schedule_amount', label: '排产额' },
  { id: 'ship_units', label: '发货台数' },
  { id: 'ship_amount', label: '发货额' },
  { id: 'payment', label: '回款' },
]

function fmtNum(v) {
  if (v == null || v === '') return ''
  if (typeof v === 'number') return Math.round(v).toLocaleString('zh-CN')
  return v
}

function fmtPct(v) {
  if (v == null) return ''
  return (v * 100).toFixed(1) + '%'
}

function showRatio(row, mkId) {
  // 商贸行的台数指标，目标为0，完成比无意义，显示 '-'
  if (row.type === 'trade' && ['sign_units', 'schedule_units', 'ship_units'].includes(mkId)) {
    return '-'
  }
  return fmtPct(row[mkId + '_ratio'])
}

function ratioColor(v) {
  if (v == null) return {}
  if (v * 100 >= 50) return { color: '#ef4444', fontWeight: '700' }
  return { color: '#16a34a', fontWeight: '700' }
}

function rowClass(type) {
  if (type === 'subtotal') return 'row-subtotal'
  if (type === 'grand_total') return 'row-grand'
  return ''
}
</script>

<style scoped>
.ac-wrap {
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 1px 8px rgba(0,0,0,.05);
}
.col-toggle-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.col-toggle-label {
  font-size: 11px;
  color: #888;
}
.col-toggle-btn {
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #555;
}
.col-toggle-btn:hover {
  background: #f0f5ff;
  border-color: #409EFF;
}
.col-toggle-btn--hidden {
  color: #aaa;
  border-color: #e8eaed;
}
.ac-scroll {
  overflow: auto;
  max-height: 75vh;
}
.ac-table {
  border-collapse: collapse;
  font-size: 11px;
  white-space: nowrap;
  font-family: 'Microsoft YaHei', sans-serif;
}
.ac-table th,
.ac-table td {
  border: 1px solid #d0d5dd;
  padding: 4px 6px;
  text-align: center;
}
.ac-table thead th {
  background: #eef2f7;
  font-weight: 600;
  color: #333;
  position: sticky;
  z-index: 3;
}
.ac-table thead tr:first-child th { top: 0; }
.ac-table thead tr:last-child th { top: 24px; }
.ac-table .sub {
  font-weight: 500;
  color: #555;
  font-size: 10px;
}
.ac-table .fixed {
  position: sticky;
  left: 0;
  z-index: 2;
}
.ac-table thead .fixed {
  background: #eef2f7;
  z-index: 4;
}
.ac-table tbody .fixed {
  background: #fff;
}
.ac-table .val {
  text-align: center;
  min-width: 60px;
}
.ac-table .group-header {
  font-weight: 600;
  color: #333;
}
.ac-ctr { text-align: center; }
.fw-bold { font-weight: 700; }

/* Row colors */
.row-subtotal td {
  background: #D6E4F0;
  font-weight: 600;
}
.row-subtotal .fixed {
  background: #D6E4F0;
}
.row-grand td {
  background: #B4C6E7;
  font-weight: 700;
}
.row-grand .fixed {
  background: #B4C6E7;
}

/* Extra columns - subdued when shown */
.gaizao-hdr { color: #999; }
.gaizao-sub { color: #aaa; font-weight: 400; }
.gaizao-val { color: #777; }

.ac-empty {
  text-align: center;
  padding: 40px;
  color: #999;
}
</style>
