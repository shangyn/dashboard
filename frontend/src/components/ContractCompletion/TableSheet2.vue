<template>
  <div class="sheet-wrap" v-loading="loading">
    <div class="sheet-title">模块明细（单位：台/万元）</div>

    <div class="table-scroll">
      <table class="cc-table">
        <thead>
          <tr>
            <th rowspan="2">序号</th>
            <th rowspan="2">大区</th>
            <th rowspan="2">模块</th>
            <th rowspan="2">负责人</th>
            <template v-for="mc in metricConfig" :key="mc.id">
              <th colspan="3">{{ mc.name }}</th>
            </template>
            <th rowspan="2">2021年前<br/>排产未发货台</th>
          </tr>
          <tr>
            <template v-for="mc in metricConfig" :key="'h-' + mc.id">
              <th class="sub-h">指标</th>
              <th class="sub-h">实际</th>
              <th class="sub-h">完成%</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in modules"
            :key="ri"
            :class="{
              'row-subtotal': row.row_type === 'subtotal',
              'row-grand': row.row_type === 'grand',
            }"
            :style="rowBgStyle(row)"
          >
            <td>{{ row.row_type === 'data' ? ri + 1 : '' }}</td>
            <td>{{ row.region }}</td>
            <td :class="{ 'text-left': true, 'fw-bold': row.row_type === 'subtotal' }">
              {{ row.module_name }}
            </td>
            <td>{{ row.module_manager || '' }}</td>
            <template v-for="mc in metricConfig" :key="mc.id">
              <td class="num">{{ fmt(row.metrics?.[mc.id]?.target) }}</td>
              <td class="num">{{ fmt(row.metrics?.[mc.id]?.actual) }}</td>
              <td class="num" :style="ratioTextStyle(row.metrics?.[mc.id]?.ratio)">
                {{ pct(row.metrics?.[mc.id]?.ratio) }}
              </td>
            </template>
            <td class="num">{{ row.prev_schedule_not_shipped || 0 }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-empty v-if="!modules.length" description="暂无数据" />
  </div>
</template>

<script setup>
const props = defineProps({
  modules: { type: Array, default: () => [] },
  metricConfig: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
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

function rowBgStyle(row) {
  if (row.row_type === 'subtotal') return { background: '#D6E4F0', fontWeight: 'bold' }
  return {}
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
.fw-bold { font-weight: 700; }
.row-subtotal td { font-weight: 600; }
</style>
