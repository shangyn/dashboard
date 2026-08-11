<template>
  <div class="sheet-wrap" v-loading="loading">
    <div class="sheet-title">大区汇总（单位：台/万元）</div>

    <div class="table-scroll">
      <table class="cc-table">
        <thead>
          <tr>
            <th rowspan="2" class="fixed-col">序号</th>
            <th rowspan="2" class="fixed-col">大区</th>
            <template v-for="mc in metricConfig" :key="mc.id">
              <th colspan="3">{{ mc.name }}</th>
            </template>
          </tr>
          <tr>
            <template v-for="mc in metricConfig" :key="'h-' + mc.id">
              <th class="sub-h">指标</th>
              <th class="sub-h">实际完成</th>
              <th class="sub-h">完成全年%</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in tableRows"
            :key="ri"
            :class="{
              'row-total': row.is_total,
              'row-trade': row.region === '商贸合计'
            }"
            :style="row.is_total ? { background: '#B4C6E7', fontWeight: 'bold' } : {}"
          >
            <td class="fixed-col">{{ row.is_total ? '' : ri + 1 }}</td>
            <td class="fixed-col">{{ row.region }}</td>
            <template v-for="mc in metricConfig" :key="mc.id">
              <td class="num">{{ fmt(row.metrics?.[mc.id]?.target) }}</td>
              <td class="num">{{ fmt(row.metrics?.[mc.id]?.actual) }}</td>
              <td class="num" :style="ratioTextStyle(row.metrics?.[mc.id]?.ratio)">
                {{ pct(row.metrics?.[mc.id]?.ratio) }}
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>

    <el-empty v-if="!tableRows.length" description="暂无数据" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  regions: { type: Array, default: () => [] },
  grandTotal: { type: Object, default: null },
  metricConfig: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const tableRows = computed(() => {
  const rows = [...props.regions]
  if (props.grandTotal) {
    rows.push(props.grandTotal)
  }
  return rows
})

function fmt(v) {
  if (v == null || v === '') return '-'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  return v
}

function pct(r) {
  if (r == null) return '-'
  return (r * 100).toFixed(1) + '%'
}

function ratioTextStyle(r) {
  if (r == null) return {}
  if (r >= 1) return { color: '#059669', fontWeight: '600' }
  if (r >= 0.5) return { color: '#2563eb', fontWeight: '600' }
  return { color: '#dc2626', fontWeight: '600' }
}
</script>

<style scoped>
.sheet-wrap { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,.05); }
.sheet-title { font-size: 15px; font-weight: 700; color: #1a1a2e; margin-bottom: 12px; text-align: center; }
.table-scroll { overflow-x: auto; }
.cc-table { width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }
.cc-table th, .cc-table td { border: 1px solid #d0d5dd; padding: 6px 8px; text-align: center; }
.cc-table thead th { background: #eef2f7; font-weight: 600; color: #333; }
.cc-table .sub-h { font-weight: 500; color: #555; font-size: 11px; }
.cc-table .fixed-col { position: sticky; left: 0; background: #eef2f7; z-index: 1; }
.cc-table tbody .fixed-col { background: #fff; }
.cc-table .num { text-align: right; }
.row-total td { font-weight: 700; }
</style>
