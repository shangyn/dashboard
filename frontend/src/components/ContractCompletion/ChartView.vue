<template>
  <div class="chart-view" v-loading="loading">
    <!-- 汇总卡片 -->
    <div class="summary-cards" v-if="metricConfig.length">
      <div
        class="summary-card"
        v-for="(mc, idx) in metricConfig"
        :key="mc.id"
        :style="{ borderTop: `3px solid ${cardColors[idx % cardColors.length]}` }"
      >
        <div class="sc-label">{{ mc.name }}</div>
        <div class="sc-value">
          {{ fmt(grandTotal?.metrics?.[mc.id]?.actual) }}
          <span class="sc-unit">{{ mc.unit }}</span>
        </div>
        <div class="sc-target">
          指标 {{ fmt(grandTotal?.metrics?.[mc.id]?.target) }}
        </div>
        <div
          class="sc-ratio"
          :style="ratioStyle(grandTotal?.metrics?.[mc.id]?.ratio)"
        >
          {{ pct(grandTotal?.metrics?.[mc.id]?.ratio) }}
        </div>
      </div>
    </div>

    <!-- 图表网格 -->
    <div class="chart-grid" v-if="metricConfig.length">
      <div class="chart-card" v-for="mc in metricConfig" :key="'chart-' + mc.id">
        <div class="chart-card-title">{{ mc.name }}（{{ mc.unit }}）</div>
        <CompletionChart
          :regions="regions"
          :grandTotal="grandTotal"
          :metricKey="mc.id"
          :metricName="mc.name"
          :unit="mc.unit"
          :height="320"
        />
      </div>
    </div>

    <!-- 图例 -->
    <div class="legend-bar">
      <span
        v-for="(r, i) in regions"
        :key="r.region"
        class="legend-item"
      >
        <span class="legend-dot" :style="{ background: regionColors[i % regionColors.length] }"></span>
        {{ r.region }}
      </span>
    </div>

    <el-empty v-if="!regions.length" description="暂无数据，请先上传数据源文件" />
  </div>
</template>

<script setup>
import CompletionChart from './CompletionChart.vue'

const props = defineProps({
  regions: { type: Array, default: () => [] },
  grandTotal: { type: Object, default: null },
  metricConfig: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const regionColors = ['#4C78A8', '#54A867', '#C8963C', '#D4645C', '#5AA3AE', '#7BA868', '#E07B42', '#8C6DB8', '#C86C8A']
const cardColors = ['#4C78A8', '#54A867', '#C8963C', '#5AA3AE', '#7BA868', '#8C6DB8', '#E07B42']

function fmt(v) {
  if (v == null) return '-'
  if (typeof v === 'number' && (String(v).includes('.') || v >= 1e6))
    return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  return v.toLocaleString('zh-CN')
}

function pct(r) {
  if (r == null) return '-'
  return (r * 100).toFixed(1) + '%'
}

function ratioStyle(r) {
  if (r == null) return {}
  if (r >= 1) return { background: '#ecfdf5', color: '#059669' }
  if (r >= 0.5) return { background: '#eff6ff', color: '#2563eb' }
  return { background: '#fef2f2', color: '#dc2626' }
}
</script>

<style scoped>
.chart-view { padding: 8px 0; }
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  text-align: center;
  box-shadow: 0 1px 6px rgba(0,0,0,.06);
}
.sc-label { font-size: 12px; color: #888; margin-bottom: 2px; }
.sc-value { font-size: 22px; font-weight: 700; color: #1a73e8; }
.sc-unit { font-size: 12px; font-weight: 400; color: #666; }
.sc-target { font-size: 11px; color: #aaa; margin-top: 2px; }
.sc-ratio { font-size: 12px; font-weight: 600; margin-top: 6px; padding: 2px 10px; border-radius: 10px; display: inline-block; }

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}
.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 8px rgba(0,0,0,.05);
}
.chart-card-title {
  font-size: 14px; font-weight: 600; color: #1a1a2e; margin-bottom: 4px;
}

.legend-bar {
  display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; padding: 10px 0;
}
.legend-item { font-size: 11px; color: #555; display: flex; align-items: center; gap: 4px; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
</style>
