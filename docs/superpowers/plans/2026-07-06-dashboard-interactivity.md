# 增长看板交互增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make KPI cards clickable as a metric selector, highlight the selected metric column in the heatmap, and replace the bottom CSS ranking bars with an ECharts diverging bar chart.

**Architecture:** All changes are within `TwoYearDashboard.vue`. A new `selectedMetric` ref drives three reactive behaviors: (1) KPI card active state, (2) heatmap column highlight, (3) ECharts chart data. The existing `signAmountRanking`/`topGainers`/`topLosers` computed properties are replaced by a single generic `rankingData` computed that respects `selectedMetric`. ECharts is dynamically imported following the existing `CompletionChart.vue` pattern.

**Tech Stack:** Vue 3 Composition API, ECharts (already in project)

---

## File Structure

| File | Role |
|------|------|
| `frontend/src/components/ContractCompletion/TwoYearDashboard.vue` | Modify — all changes here |

No new files. The chart lives inline as a `<div ref="chartRef">` inside the existing component.

---

### Task 1: Add selectedMetric ref, clickable KPI cards, heatmap column highlight, and ranking data refactor

**Files:**
- Modify: `frontend/src/components/ContractCompletion/TwoYearDashboard.vue`

- [ ] **Step 1: Add `selectedMetric` ref and make KPI cards clickable**

In the `<script setup>`, add after the props block (after line 139):

```js
// ── Selected metric (drives heatmap highlight + chart) ──
const selectedMetric = ref('sign_amount')
```

In the template, replace the KPI card `<div>` (lines 5-9) with:

```html
<div
  class="tyd-kpi-card"
  :class="{ 'tyd-kpi-card--active': selectedMetric === mk.id }"
  v-for="mk in dashboardMetricKeys"
  :key="mk.id"
  @click="selectedMetric = mk.id"
>
```

Add `ref` import at line 115:
```js
import { ref, computed } from 'vue'
```

- [ ] **Step 2: Add heatmap column highlight styles**

In the `<thead>` (lines 41-43), replace the `<th>` for metric keys:

```html
<th
  v-for="mk in dashboardMetricKeys"
  :key="mk.id"
  :class="{ 'tyd-hm-col-active': selectedMetric === mk.id }"
>
  {{ mk.label }}
</th>
```

In the `<tbody>` (lines 54-61), replace the `<td>` for metric cells:

```html
<td
  v-for="mk in dashboardMetricKeys"
  :key="mk.id"
  :style="cellStyle(row[mk.id])"
  :class="{ 'tyd-hm-col-active': selectedMetric === mk.id, 'tyd-hm-cell': true }"
>
  {{ fmtGrowth(row[mk.id]) }}
</td>
```

- [ ] **Step 3: Add CSS for KPI card active state and column highlight**

Add after the `.tyd-kpi-card` styles:

```css
.tyd-kpi-card {
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

/* heatmap column highlight */
.tyd-hm-col-active {
  background: #eff6ff !important;
}
```

- [ ] **Step 4: Replace signAmountRanking/topGainers/topLosers with generic rankingData**

Remove lines 259-284 (the three ranking computed properties) and replace with:

```js
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
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ContractCompletion/TwoYearDashboard.vue
git commit -m "feat: add metric selector — clickable KPI cards, heatmap column highlight, generic ranking data"
```

---

### Task 2: Replace CSS ranking bars with ECharts diverging bar chart

**Files:**
- Modify: `frontend/src/components/ContractCompletion/TwoYearDashboard.vue`

- [ ] **Step 1: Replace the ranking section template with a chart container**

Replace lines 68-108 (the entire `<!-- Section C -->` div) with:

```html
<!-- Section C: ECharts Diverging Bar Chart (only when "all regions" selected) -->
<div class="tyd-chart-card" v-if="!selectedRegion">
  <div class="tyd-chart-title">
    📊 {{ selectedMetricLabel }} 大区增长率
  </div>
  <div ref="chartRef" class="tyd-chart-body"></div>
  <el-empty v-if="!rankingData.length" description="暂无数据" />
</div>
```

- [ ] **Step 2: Add ECharts lifecycle logic in script**

Add to imports:
```js
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
```

Add chart variables and functions after the `rankingData` computed:

```js
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
  const data = [...rankingData.value].reverse() // bottom-to-top for horizontal bar
  if (!data.length) return {}

  const names = data.map(d => (REGION_EMOJI[d.region] || '') + ' ' + d.region)
  const values = data.map(d => d.growth ?? 0)

  const maxAbs = Math.max(...values.map(v => Math.abs(v)), 1)
  const barHeight = Math.max(24, Math.min(32, 280 / data.length))

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
      splitLine: {
        lineStyle: { color: '#f0f0f0', type: 'dashed' },
      },
      axisLine: {
        lineStyle: { color: '#ccc' },
      },
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
        barWidth: barHeight,
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
        emphasis: {
          itemStyle: { opacity: 0.8 },
        },
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
```

- [ ] **Step 3: Add chart card CSS**

Replace all ranking bar CSS (lines 372-401) with:

```css
/* ── ECharts Chart Card ── */
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
```

Remove the responsive rule `.tyd-rank-row { grid-template-columns: 1fr; }` from the `@media (max-width: 768px)` block since `.tyd-rank-row` no longer exists.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ContractCompletion/TwoYearDashboard.vue
git commit -m "feat: replace CSS ranking bars with ECharts diverging bar chart per selected metric"
```

---

### Task 3: Smoke test and verify

**Files:**
- None (verification only)

- [ ] **Step 1: Build the frontend**

```bash
cd frontend && npx vite build 2>&1 | tail -20
```

Expected: Build succeeds with no errors.

- [ ] **Step 2: Visual verification checklist**

Start dev server and verify:
- [ ] Default selected card is "签订额" (blue border)
- [ ] Click other cards → active state moves, heatmap column highlights
- [ ] Bottom chart shows diverging bars for the selected metric
- [ ] Green bars go right (+), red bars go left (-)
- [ ] Chart title updates to match selected metric
- [ ] Select a region → chart hides (single-region drill-down active)
- [ ] Select "全部大区" → chart reappears
- [ ] Switch to table view and back → chart still renders
- [ ] No console errors

- [ ] **Step 3: Commit any fixes if needed**

```bash
git add -A && git commit -m "chore: fix issues found during smoke test"
```
