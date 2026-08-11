<template>
  <div class="sheet-wrap" v-loading="loading">
    <div class="sheet-title">业务员对比表（单位：台/万元）</div>

    <div class="table-scroll">
      <table class="cc-table">
        <thead>
          <tr>
            <th rowspan="2">模块</th>
            <th rowspan="2">业务员</th>
            <th colspan="3">签单台数</th>
            <th colspan="3">签单额</th>
            <th colspan="3">排产台数</th>
            <th colspan="3">排产额</th>
            <th colspan="3">发货台数</th>
            <th colspan="3">发货额</th>
            <th colspan="2">回款</th>
          </tr>
          <tr>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th><th class="sub-h">增减%</th>
            <th class="sub-h">2025</th><th class="sub-h">2026</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in salespersons" :key="ri">
            <td class="text-left">{{ row.module }}</td>
            <td class="text-left fw-bold">{{ row.salesperson }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.sign_units) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.sign_units) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.sign_units)">{{ changeText(row.yoy_change?.sign_units) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.sign_amount) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.sign_amount) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.sign_amount)">{{ changeText(row.yoy_change?.sign_amount) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.schedule_units) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.schedule_units) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.schedule_units)">{{ changeText(row.yoy_change?.schedule_units) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.schedule_amount) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.schedule_amount) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.schedule_amount)">{{ changeText(row.yoy_change?.schedule_amount) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.ship_units) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.ship_units) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.ship_units)">{{ changeText(row.yoy_change?.ship_units) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.ship_amount) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.ship_amount) }}</td>
            <td class="num" :style="changeStyle(row.yoy_change?.ship_amount)">{{ changeText(row.yoy_change?.ship_amount) }}</td>

            <td class="num">{{ fmt(row.metrics_prev?.payment_amount) }}</td>
            <td class="num">{{ fmt(row.metrics_curr?.payment_amount) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-empty v-if="!salespersons.length" description="暂无数据" />
  </div>
</template>

<script setup>
const props = defineProps({
  salespersons: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

function fmt(v) {
  if (v == null || v === '') return '-'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  return v
}

function changeText(v) {
  if (v == null || v === '') return '-'
  if (v > 0) return '+' + v.toFixed(1) + '%'
  return v.toFixed(1) + '%'
}

function changeStyle(v) {
  if (v == null) return {}
  if (v > 0) return { color: '#059669', fontWeight: '600' }
  if (v < 0) return { color: '#dc2626', fontWeight: '600' }
  return { color: '#888' }
}
</script>

<style scoped>
.sheet-wrap { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,.05); }
.sheet-title { font-size: 15px; font-weight: 700; color: #1a1a2e; margin-bottom: 12px; text-align: center; }
.table-scroll { overflow-x: auto; max-height: 70vh; overflow-y: auto; }
.cc-table { width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }
.cc-table th, .cc-table td { border: 1px solid #d0d5dd; padding: 5px 7px; text-align: center; }
.cc-table thead th { background: #eef2f7; font-weight: 600; color: #333; position: sticky; top: 0; z-index: 2; }
.cc-table .sub-h { font-weight: 500; color: #555; font-size: 11px; }
.cc-table .num { text-align: right; }
.text-left { text-align: left; }
.fw-bold { font-weight: 600; color: #1a1a2e; }
</style>
