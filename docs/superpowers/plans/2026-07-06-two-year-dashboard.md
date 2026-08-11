# 两年对比看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder chart view in TwoYearComparison with a growth-rate-driven dashboard and refactor the page layout from left-sidebar to top-bar navigation.

**Architecture:** `TwoYearComparison.vue` (page shell: fetch data + top bar + view switching) delegates dashboard rendering to a new child `TwoYearDashboard.vue` (growth cards + heatmap + ranking bars). Table view reuses existing `TwoYearTable.vue`. All data sharing via props; no Pinia/store needed. Pure CSS for charts — zero new dependencies.

**Tech Stack:** Vue 3 Composition API, Element Plus (dropdown, button), CSS Grid/Flexbox

---

## File Structure

| File | Role |
|------|------|
| `frontend/src/views/TwoYearComparison.vue` | Page shell: fetch API, top bar, view toggle, pass data to children |
| `frontend/src/components/ContractCompletion/TwoYearDashboard.vue` | **New** — Dashboard view: aggregates rows → growth cards + heatmap + ranking |
| `frontend/src/components/ContractCompletion/TwoYearTable.vue` | Unchanged — existing Excel table |

Data flow:
```
TwoYearComparison.vue  (fetch → allRows, metricGroups, regions)
  ├─ props → TwoYearDashboard.vue  (computed: regionAggregates, moduleDetail)
  └─ props → TwoYearTable.vue      (filteredRows)
```

---

### Task 1: Create TwoYearDashboard.vue — growth cards, heatmap, ranking bars

**Files:**
- Create: `frontend/src/components/ContractCompletion/TwoYearDashboard.vue`

- [ ] **Step 1: Write the component with full template, script, and styles**

Create `frontend/src/components/ContractCompletion/TwoYearDashboard.vue`:

```vue
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
              :style="row._isSubtotal ? { background: '#D6E4F0', fontWeight: '700' } : {}"
            >
              <td
                class="tyd-hm-rowhead"
                :style="row._isSubtotal ? { fontWeight: '700' } : { fontWeight: '600' }"
              >
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
  yearPrev: { type: Number, default: 2025 },
  yearCurr: { type: Number, default: 2026 },
  loading: { type: Boolean, default: false },
  selectedRegion: { type: String, default: null },
})

// ── Data helpers ──

function getRegionDataRows() {
  return props.rows.filter(r => r.type === 'data')
}

// Aggregate data rows by region: { '俄罗斯': { sign_units: { prev, curr, growth }, ... } }
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
      const row = { label: mod, _emoji: '', _isSubtotal: false }
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
    const row = { label: region, _emoji: REGION_EMOJI[region] || '', _isSubtotal: false }
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
  const bottom3 = negative.slice(0, 3)
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
.tyd-rank-bar { height: 100%; border-radius: 4px; display: flex; align-items: center; padding-left: 8px; color: #fff; font-size: 10px; font-weight: 700; min-width: fit-content; }
.tyd-rank-bar-up { background: #4C78A8; }
.tyd-rank-bar-down { background: #D4645C; }
.tyd-rank-empty { font-size: 11px; color: #aaa; padding: 8px 0; }

/* ── Responsive: narrower screens stack KPI cards ── */
@media (max-width: 1200px) {
  .tyd-kpi-row { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 768px) {
  .tyd-kpi-row { grid-template-columns: repeat(2, 1fr); }
  .tyd-rank-row { grid-template-columns: 1fr; }
}
</style>
```

- [ ] **Step 2: Verify the file was created and has no syntax errors**

Run: `npx vue-tsc --noEmit --skipLibCheck frontend/src/components/ContractCompletion/TwoYearDashboard.vue 2>&1 || echo "Check manually — .vue files may not be checked by vue-tsc alone"`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ContractCompletion/TwoYearDashboard.vue
git commit -m "feat: add TwoYearDashboard component — growth cards, heatmap, ranking bars"
```

---

### Task 2: Refactor TwoYearComparison.vue — new top-bar layout with segmented control

**Files:**
- Modify: `frontend/src/views/TwoYearComparison.vue`

- [ ] **Step 1: Rewrite the template section**

Replace the entire `<template>` block in `frontend/src/views/TwoYearComparison.vue` with:

```vue
<template>
  <div class="tyc-page">
    <!-- Top Control Bar -->
    <div class="tyc-topbar">
      <div class="tyc-topbar-left">
        <h2 class="tyc-title">{{ title }}</h2>
        <div class="tyc-segmented">
          <button
            class="tyc-seg-btn"
            :class="{ active: view === 'dashboard' }"
            @click="view = 'dashboard'"
          >
            📈 增长看板
          </button>
          <button
            class="tyc-seg-btn"
            :class="{ active: view === 'table' }"
            @click="view = 'table'"
          >
            📋 数据表格
          </button>
        </div>
      </div>
      <div class="tyc-topbar-right">
        <span class="tyc-date">{{ datePrev }} ~ {{ dateCurr }}</span>
        <el-select
          v-model="selectedRegion"
          size="small"
          style="width:120px"
          clearable
          placeholder="全部大区"
        >
          <el-option v-for="r in regions" :key="r" :label="r" :value="r" />
        </el-select>
        <el-button size="small" type="primary" @click="exportExcel">导出Excel</el-button>
      </div>
    </div>

    <!-- Content Area -->
    <div class="tyc-content">
      <!-- Dashboard View -->
      <div v-show="view === 'dashboard'">
        <TwoYearDashboard
          :rows="allRows"
          :regionOrder="regionOrder"
          :yearPrev="yearPrev"
          :yearCurr="yearCurr"
          :loading="loading"
          :selectedRegion="selectedRegion || null"
        />
      </div>

      <!-- Table View -->
      <div v-show="view === 'table'">
        <TwoYearTable
          :rows="filteredRows"
          :metricGroups="metricGroups"
          :yearPrev="yearPrev"
          :yearCurr="yearCurr"
          :loading="loading"
        />
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Update the script section**

Replace the `<script setup>` block with:

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTwoYearComparison } from '../api/contract-completion'
import TwoYearTable from '../components/ContractCompletion/TwoYearTable.vue'
import TwoYearDashboard from '../components/ContractCompletion/TwoYearDashboard.vue'

const loading = ref(false)
const view = ref('dashboard')
const selectedRegion = ref(null)

const title = ref('')
const datePrev = ref('')
const dateCurr = ref('')
const yearPrev = ref(2025)
const yearCurr = ref(2026)
const metricGroups = ref([])
const allRows = ref([])
const regions = ref([])
const regionOrder = ref([])

const filteredRows = computed(() => {
  if (!selectedRegion.value) return allRows.value
  return allRows.value.filter(r =>
    r.region === selectedRegion.value || (r.type !== 'data' && r.type !== 'trade')
  )
})

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await getTwoYearComparison()
    const d = res.data
    title.value = d.title
    datePrev.value = d.date_prev_end
    dateCurr.value = d.date_curr_end
    yearPrev.value = d.year_prev
    yearCurr.value = d.year_curr
    metricGroups.value = d.metric_groups || []
    allRows.value = d.rows || []
    regions.value = d.region_order || []
    regionOrder.value = d.region_order || []
  } catch (e) {
    ElMessage.error('数据加载失败')
  } finally {
    loading.value = false
  }
}

function exportExcel() {
  const token = localStorage.getItem('token')
  const url = '/api/contract-completion/two-year-comparison/export'
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(res => res.blob())
    .then(blob => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = '两年对比表.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => ElMessage.error('导出失败'))
}
</script>
```

- [ ] **Step 3: Replace the styles**

Replace the entire `<style scoped>` block with:

```css
<style scoped>
.tyc-page { min-height: calc(100vh - 56px); background: #f0f2f5; }

/* ── Top Control Bar ── */
.tyc-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 52px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #e8eaed;
}
.tyc-topbar-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.tyc-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #1a1a2e;
  white-space: nowrap;
}

/* ── Segmented Control ── */
.tyc-segmented {
  display: flex;
  background: #f1f5f9;
  border-radius: 8px;
  padding: 3px;
}
.tyc-seg-btn {
  padding: 5px 16px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #888;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all .2s;
  white-space: nowrap;
}
.tyc-seg-btn.active {
  background: #fff;
  color: #1a73e8;
  font-weight: 700;
  box-shadow: 0 1px 3px rgba(0,0,0,.1);
}
.tyc-seg-btn:hover:not(.active) { color: #555; }

/* ── Topbar Right ── */
.tyc-topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.tyc-date { font-size: 11px; color: #999; white-space: nowrap; }

/* ── Content ── */
.tyc-content {
  padding: 14px 20px;
  min-width: 0;
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .tyc-topbar {
    flex-wrap: wrap;
    height: auto;
    padding: 8px 12px;
    gap: 8px;
  }
  .tyc-topbar-left { gap: 10px; }
  .tyc-title { font-size: 14px; }
}
</style>
```

- [ ] **Step 4: Verify the refactored file**

Visual check: ensure imports are correct, component names match registration (TwoYearDashboard is imported and used in template), all removed code (sidebar, old `view` values 'chart') is fully replaced.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/TwoYearComparison.vue
git commit -m "refactor: TwoYearComparison — top bar layout with segmented control, integrate dashboard view"
```

---

### Task 3: Smoke test — verify the app builds and renders

**Files:**
- None (verification only)

- [ ] **Step 1: Build the frontend to check for compilation errors**

```bash
cd frontend && npx vite build 2>&1 | tail -30
```

Expected: Build succeeds with no errors. If errors appear, fix them before proceeding.

- [ ] **Step 2: Start the dev server and verify visually**

```bash
cd frontend && npx vite --host 0.0.0.0 &
```

Navigate to the TwoYearComparison page. Verify:
- Top bar renders with title, segmented control, date, region dropdown, export button
- Default view is "增长看板" (dashboard)
- 7 KPI cards appear with growth rates
- Heatmap shows regions × metrics with green/red cells
- Ranking bars appear at bottom (best/worst)
- Click "数据表格" → table view renders full-width
- Select a region → dashboard switches to module detail, table filters
- Select "全部大区" → returns to region-level heatmap

- [ ] **Step 3: Commit any fixes if needed**

```bash
git add -A && git commit -m "chore: fix issues found during smoke test"
```
