<template>
  <div class="tyd-dashboard" v-loading="loading">
    <!-- Section A: 7 Growth Rate KPI Cards -->
    <div class="tyd-kpi-row">
      <div
        class="tyd-kpi-card"
        :class="{ 'tyd-kpi-card--active': selectedMetric === mk.id }"
        v-for="mk in dashboardMetricKeys"
        :key="mk.id"
        @click="selectedMetric = mk.id"
      >
        <div class="tyd-kpi-icon">{{ mk.icon }}</div>
        <div class="tyd-kpi-label">{{ mk.label }}</div>
        <div
          class="tyd-kpi-growth"
          :style="{ color: growthColor(grandGrowth[mk.id]) }"
        >
          {{ fmtGrowth(grandGrowth[mk.id]) }}
        </div>
        <div class="tyd-kpi-abs">
          {{ fmtNum(grandPrev[mk.id]) }} → {{ fmtNum(grandCurr[mk.id]) }}
        </div>
      </div>
    </div>

    <!-- Section B: Heatmap (all regions) or Module Detail (single region) -->
    <div class="tyd-heatmap-card">
      <div class="tyd-heatmap-header">
        <span class="tyd-heatmap-title">
          {{ selectedRegion ? `${selectedRegion} — 模块增长率明细` : '📊 同比增长率总览（大区 × 指标）' }}
        </span>
        <span class="tyd-heatmap-legend">
          <span class="tyd-legend-dot tyd-legend-up"></span> 增长
          <span class="tyd-legend-dot tyd-legend-down"></span> 下降
          <span class="tyd-legend-dot tyd-legend-flat"></span> 无数据
        </span>
      </div>
      <div class="tyd-heatmap-scroll">
        <table class="tyd-heatmap-table">
          <thead>
            <tr>
              <th class="tyd-hm-rowhead">{{ selectedRegion ? '模块' : '大区' }}</th>
              <th
                v-for="mk in dashboardMetricKeys"
                :key="mk.id"
                :class="{ 'tyd-hm-col-active': selectedMetric === mk.id }"
              >
                {{ mk.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in heatmapRows"
              :key="row.label"
            >
              <td class="tyd-hm-rowhead" style="font-weight: 600">
                {{ row._emoji }} {{ row.label }}
              </td>
              <td
                v-for="mk in dashboardMetricKeys"
                :key="mk.id"
                :style="cellStyle(row[mk.id])"
                :class="{ 'tyd-hm-col-active': selectedMetric === mk.id, 'tyd-hm-cell': true }"
              >
                {{ fmtGrowth(row[mk.id]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Section C: ECharts Diverging Bar Chart (only when "all regions" selected) -->
    <div class="tyd-chart-card" v-if="!selectedRegion">
      <div class="tyd-chart-title">
        📊 {{ selectedMetricLabel }} 大区增长率
      </div>
      <div ref="chartRef" class="tyd-chart-body"></div>
      <el-empty v-if="!rankingData.length" description="暂无数据" />
    </div>

    <el-empty v-if="!heatmapRows.length && !loading" description="暂无数据" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

// ── Constants ──
const REGION_EMOJI = {
  '俄罗斯': '🇷🇺', '中亚': '🏔️', '亚洲1': '🌏', '亚洲2': '🌐',
  '美洲': '🌎', '中东': '🌍', '非洲': '🌍', '欧洲': '🇪🇺',
}

const dashboardMetricKeys = [
  { id: 'sign_units',      label: '签订台数', icon: '📝' },
  { id: 'sign_amount',     label: '签订额',   icon: '📝' },
  { id: 'schedule_units',  label: '排产台数', icon: '🏭' },
  { id: 'schedule_amount', label: '排产额',   icon: '🏭' },
  { id: 'ship_units',      label: '发货台数', icon: '🚚' },
  { id: 'ship_amount',     label: '发货额',   icon: '🚚' },
  { id: 'payment',         label: '回款',     icon: '💰' },
]

// ── Props ──
const props = defineProps({
  rows: { type: Array, default: () => [] },
  regionOrder: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  selectedRegion: { type: String, default: null },
})

// ── Selected metric (drives heatmap highlight + chart) ──
const selectedMetric = ref('sign_amount')

// ── Data helpers ──

function getRegionDataRows() {
  return props.rows.filter(r => r.type === 'data')
}

// Aggregate data rows by region
const regionAggregates = computed(() => {
  const map = {}
  const dataRows = getRegionDataRows()
  for (const r of dataRows) {
    const region = r.region
    if (!region) continue
    if (!map[region]) {
      map[region] = {}
      for (const mk of dashboardMetricKeys) {
        map[region][mk.id] = { prev: 0, curr: 0 }
      }
    }
    for (const mk of dashboardMetricKeys) {
      map[region][mk.id].prev += (r[mk.id + '_prev'] || 0)
      map[region][mk.id].curr += (r[mk.id + '_curr'] || 0)
    }
  }
  // Compute growth
  for (const region of Object.keys(map)) {
    for (const mk of dashboardMetricKeys) {
      const d = map[region][mk.id]
      if (d.prev === 0) {
        d.growth = null
      } else {
        d.growth = Math.round((d.curr - d.prev) / d.prev * 100)
      }
    }
  }
  return map
})

// Grand totals for KPI cards
const grandPrev = computed(() => {
  const totals = {}
  const dataRows = getRegionDataRows()
  for (const mk of dashboardMetricKeys) {
    totals[mk.id] = dataRows.reduce((sum, r) => sum + (r[mk.id + '_prev'] || 0), 0)
  }
  return totals
})

const grandCurr = computed(() => {
  const totals = {}
  const dataRows = getRegionDataRows()
  for (const mk of dashboardMetricKeys) {
    totals[mk.id] = dataRows.reduce((sum, r) => sum + (r[mk.id + '_curr'] || 0), 0)
  }
  return totals
})

const grandGrowth = computed(() => {
  const g = {}
  for (const mk of dashboardMetricKeys) {
    const p = grandPrev.value[mk.id]
    const c = grandCurr.value[mk.id]
    if (p === 0) { g[mk.id] = null }
    else { g[mk.id] = Math.round((c - p) / p * 100) }
  }
  return g
})

// ── Heatmap rows ──

const heatmapRows = computed(() => {
  if (props.selectedRegion) {
    // Single region → module-level detail
    const region = props.selectedRegion
    const dataRows = getRegionDataRows().filter(r => r.region === region)
    // Group by module
    const modMap = {}
    for (const r of dataRows) {
      const mod = r.module || '未分类'
      if (!modMap[mod]) {
        modMap[mod] = { _emoji: '' }
        for (const mk of dashboardMetricKeys) {
          modMap[mod][mk.id] = { prev: 0, curr: 0 }
        }
      }
      for (const mk of dashboardMetricKeys) {
        modMap[mod][mk.id].prev += (r[mk.id + '_prev'] || 0)
        modMap[mod][mk.id].curr += (r[mk.id + '_curr'] || 0)
      }
    }
    const result = Object.entries(modMap).map(([mod, d]) => {
      const row = { label: mod, _emoji: '' }
      for (const mk of dashboardMetricKeys) {
        const prev = d[mk.id].prev
        const curr = d[mk.id].curr
        row[mk.id] = prev === 0 ? null : Math.round((curr - prev) / prev * 100)
      }
      return row
    })
    // Sort by sign_amount growth desc
    result.sort((a, b) => (b.sign_amount ?? -Infinity) - (a.sign_amount ?? -Infinity))
    return result
  }

  // All regions → region-level heatmap
  const result = []
  for (const region of props.regionOrder) {
    const agg = regionAggregates.value[region]
    if (!agg) continue
    const row = { label: region, _emoji: REGION_EMOJI[region] || '' }
    for (const mk of dashboardMetricKeys) {
      row[mk.id] = agg[mk.id].growth
    }
    result.push(row)
  }
  return result
})

// ── Ranking data for the selected metric ──

const selectedMetricLabel = computed(() => {
  return dashboardMetricKeys.find(mk => mk.id === selectedMetric.value)?.label || ''
})

const rankingData = computed(() => {
  const list = []
  for (const region of props.regionOrder) {
    const agg = regionAggregates.value[region]
    if (!agg) continue
    list.push({ region, growth: agg[selectedMetric.value]?.growth ?? null })
  }
  list.sort((a, b) => (b.growth ?? -Infinity) - (a.growth ?? -Infinity))
  return list
})

// ── ECharts Diverging Bar Chart ──

const chartRef = ref(null)
let chart = null
let echarts = null

async function initChart() {
  if (!chartRef.value) return
  if (!echarts) {
    const mod = await import('echarts')
    echarts = mod.default || mod
  }
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  chart.setOption(buildChartOption(), true)
}

function buildChartOption() {
  const data = [...rankingData.value].reverse()
  if (!data.length) return {}

  const names = data.map(d => (REGION_EMOJI[d.region] || '') + ' ' + d.region)
  const values = data.map(d => d.growth ?? 0)
  const maxAbs = Math.max(...values.map(v => Math.abs(v)), 1)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const p = params[0]
        const v = p.value
        const label = v > 0 ? `+${v}%` : v < 0 ? `${v}%` : '-'
        return `<b>${p.name}</b><br/>增长率: ${label}`
      },
    },
    grid: {
      left: '3%', right: '8%', top: '5%', bottom: '5%',
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      min: -maxAbs - 5,
      max: maxAbs + 5,
      axisLabel: {
        formatter: (v) => (v > 0 ? '+' : '') + v + '%',
        fontSize: 10,
        color: '#888',
      },
      splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } },
      axisLine: { lineStyle: { color: '#ccc' } },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: '#333' },
    },
    series: [
      {
        type: 'bar',
        data: values.map(v => ({
          value: v,
          itemStyle: {
            color: v > 0 ? '#4caf50' : v < 0 ? '#ef5350' : '#bbb',
            borderRadius: v > 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
          },
        })),
        barWidth: Math.max(18, Math.min(26, 280 / data.length)),
        label: {
          show: true,
          position: 'right',
          formatter: (p) => {
            const v = p.value
            return v > 0 ? '+' + v + '%' : v < 0 ? v + '%' : '-'
          },
          fontSize: 11,
          fontWeight: 'bold',
          color: '#555',
        },
        emphasis: { itemStyle: { opacity: 0.8 } },
      },
    ],
  }
}

onMounted(() => nextTick(() => initChart()))

watch(
  () => [selectedMetric.value, rankingData.value],
  () => {
    if (chart) {
      chart.setOption(buildChartOption(), true)
    }
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (chart) { chart.dispose(); chart = null }
})

// ── Formatting ──

function fmtNum(v) {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN')
}

function fmtGrowth(v) {
  if (v == null) return '-'
  if (v > 0) return '+' + v + '%'
  return v + '%'
}

function growthColor(v) {
  if (v == null) return '#999'
  if (v > 0) return '#059669'
  if (v < 0) return '#dc2626'
  return '#999'
}

function cellStyle(v) {
  if (v == null) return { background: '#f5f5f5', color: '#999' }
  if (v > 0) return { background: '#d4edda', color: '#155724', fontWeight: '700' }
  if (v < 0) return { background: '#f8d7da', color: '#721c24', fontWeight: '700' }
  return { background: '#f5f5f5', color: '#999' }
}
</script>

<style scoped>
.tyd-dashboard { padding: 0; }

/* ── KPI Cards ── */
.tyd-kpi-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.tyd-kpi-card {
  background: #fff;
  border-radius: 10px;
  padding: 12px 10px;
  text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
  cursor: pointer;
  transition: all .2s;
  border: 2px solid transparent;
}
.tyd-kpi-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,.1);
  transform: translateY(-1px);
}
.tyd-kpi-card--active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59,130,246,.2), 0 2px 8px rgba(0,0,0,.08);
}
.tyd-kpi-icon { font-size: 16px; margin-bottom: 2px; }
.tyd-kpi-label { font-size: 10px; color: #999; margin-bottom: 4px; }
.tyd-kpi-growth { font-size: 24px; font-weight: 800; }
.tyd-kpi-abs { font-size: 9px; color: #bbb; margin-top: 3px; white-space: nowrap; }

/* ── Heatmap ── */
.tyd-heatmap-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.tyd-heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.tyd-heatmap-title { font-weight: 700; font-size: 14px; color: #1a1a2e; }
.tyd-heatmap-legend { font-size: 10px; color: #888; display: flex; align-items: center; gap: 4px; }
.tyd-legend-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.tyd-legend-up { background: #d4edda; }
.tyd-legend-down { background: #f8d7da; }
.tyd-legend-flat { background: #f5f5f5; }
.tyd-heatmap-scroll { overflow-x: auto; }
.tyd-heatmap-table { border-collapse: collapse; font-size: 11px; width: 100%; min-width: 700px; }
.tyd-heatmap-table th {
  padding: 10px 8px;
  font-size: 10px;
  color: #555;
  background: #f8fafc;
  border-bottom: 2px solid #e8eaed;
  white-space: nowrap;
}
.tyd-heatmap-table td { padding: 9px 8px; border-bottom: 1px solid #f0f0f0; }
.tyd-hm-rowhead { text-align: left; padding-left: 12px; min-width: 70px; white-space: nowrap; }
.tyd-hm-cell { text-align: center; border-radius: 4px; font-size: 12px; }

/* heatmap column highlight */
.tyd-hm-col-active {
  background: #eff6ff !important;
}

/* ── Chart Card ── */
.tyd-chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.tyd-chart-title {
  font-weight: 700;
  font-size: 14px;
  color: #1a1a2e;
  margin-bottom: 8px;
}
.tyd-chart-body {
  width: 100%;
  height: 360px;
}

/* ── Responsive ── */
@media (max-width: 1200px) {
  .tyd-kpi-row { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 768px) {
  .tyd-kpi-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
