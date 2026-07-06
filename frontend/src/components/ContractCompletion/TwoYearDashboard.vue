<template>
  <div class="tyd-dashboard" v-loading="loading">
    <!-- Section A: 7 Growth Rate KPI Cards -->
    <div class="tyd-kpi-row">
      <div
        class="tyd-kpi-card"
        v-for="mk in dashboardMetricKeys"
        :key="mk.id"
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
              <th v-for="mk in dashboardMetricKeys" :key="mk.id">
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
                class="tyd-hm-cell"
              >
                {{ fmtGrowth(row[mk.id]) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Section C: Best/Worst Ranking Bars (only when "all regions" selected) -->
    <div class="tyd-rank-row" v-if="!selectedRegion">
      <div class="tyd-rank-card">
        <div class="tyd-rank-title">🏆 签订额增长最快</div>
        <div
          class="tyd-rank-item"
          v-for="item in topGainers"
          :key="'gain-' + item.region"
        >
          <span class="tyd-rank-name">{{ item.region }}</span>
          <span class="tyd-rank-bar-wrap">
            <span
              class="tyd-rank-bar tyd-rank-bar-up"
              :style="{ width: item.barPct + '%' }"
            >
              {{ fmtGrowth(item.growth) }}
            </span>
          </span>
        </div>
        <div v-if="!topGainers.length" class="tyd-rank-empty">暂无数据</div>
      </div>
      <div class="tyd-rank-card">
        <div class="tyd-rank-title">⚠️ 签订额下降</div>
        <div
          class="tyd-rank-item"
          v-for="item in topLosers"
          :key="'lose-' + item.region"
        >
          <span class="tyd-rank-name">{{ item.region }}</span>
          <span class="tyd-rank-bar-wrap">
            <span
              class="tyd-rank-bar tyd-rank-bar-down"
              :style="{ width: item.barPct + '%' }"
            >
              {{ fmtGrowth(item.growth) }}
            </span>
          </span>
        </div>
        <div v-if="!topLosers.length" class="tyd-rank-empty">暂无下降</div>
      </div>
    </div>

    <el-empty v-if="!heatmapRows.length && !loading" description="暂无数据" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

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

// ── Ranking bars (for sign_amount) ──

const signAmountRanking = computed(() => {
  const list = []
  for (const region of props.regionOrder) {
    const agg = regionAggregates.value[region]
    if (!agg) continue
    list.push({ region, growth: agg.sign_amount.growth })
  }
  list.sort((a, b) => (b.growth ?? -Infinity) - (a.growth ?? -Infinity))
  return list
})

const topGainers = computed(() => {
  const positive = signAmountRanking.value.filter(r => r.growth !== null && r.growth > 0)
  const top3 = positive.slice(0, 3)
  const maxGrowth = top3.length ? Math.max(...top3.map(r => Math.abs(r.growth)), 1) : 1
  return top3.map(r => ({ ...r, barPct: Math.round(Math.abs(r.growth) / maxGrowth * 100) }))
})

const topLosers = computed(() => {
  const negative = signAmountRanking.value.filter(r => r.growth !== null && r.growth < 0)
  const bottom3 = negative.slice(-3).reverse()
  const maxGrowth = bottom3.length ? Math.max(...bottom3.map(r => Math.abs(r.growth)), 1) : 1
  return bottom3.map(r => ({ ...r, barPct: Math.round(Math.abs(r.growth) / maxGrowth * 100) }))
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

/* ── Ranking Bars ── */
.tyd-rank-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.tyd-rank-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.tyd-rank-title { font-weight: 700; font-size: 13px; color: #1a1a2e; margin-bottom: 8px; }
.tyd-rank-item { display: flex; align-items: center; margin-bottom: 6px; gap: 8px; }
.tyd-rank-name { width: 45px; font-weight: 600; font-size: 11px; text-align: right; flex-shrink: 0; }
.tyd-rank-bar-wrap { flex: 1; background: #eee; height: 22px; border-radius: 4px; overflow: hidden; }
.tyd-rank-bar {
  height: 100%;
  border-radius: 4px;
  display: flex;
  align-items: center;
  padding-left: 8px;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  min-width: fit-content;
  white-space: nowrap;
}
.tyd-rank-bar-up { background: #4C78A8; }
.tyd-rank-bar-down { background: #D4645C; }
.tyd-rank-empty { font-size: 11px; color: #aaa; padding: 8px 0; }

/* ── Responsive ── */
@media (max-width: 1200px) {
  .tyd-kpi-row { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 768px) {
  .tyd-kpi-row { grid-template-columns: repeat(2, 1fr); }
  .tyd-rank-row { grid-template-columns: 1fr; }
}
</style>
