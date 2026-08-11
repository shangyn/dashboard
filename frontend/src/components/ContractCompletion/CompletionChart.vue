<template>
  <div ref="chartRef" :style="{ width: '100%', height: height + 'px' }"></div>
</template>

<script setup>
import { ref, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'

const props = defineProps({
  regions: { type: Array, default: () => [] },
  grandTotal: { type: Object, default: null },
  metricKey: { type: String, required: true },
  metricName: { type: String, default: '' },
  unit: { type: String, default: '台' },
  height: { type: Number, default: 350 },
})

const REGION_COLORS = ['#4C78A8', '#54A867', '#C8963C', '#D4645C', '#5AA3AE', '#7BA868', '#E07B42', '#8C6DB8', '#C86C8A']
const INNER_COLOR_DONE = '#3b82f6'
const INNER_COLOR_REMAIN = '#E8E8E8'

const chartRef = ref(null)
let chart = null
let echarts = null

async function initChart() {
  if (!chartRef.value) return
  // 动态导入 echarts
  if (!echarts) {
    const mod = await import('echarts')
    echarts = mod.default || mod
  }
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }
  chart.setOption(buildOption(), true)
}

function buildOption() {
  if (!props.regions.length) return {}

  const outerData = props.regions.map((r, i) => ({
    name: r.region,
    value: Math.max(r.metrics?.[props.metricKey]?.actual || 0, 0.001),
    target: r.metrics?.[props.metricKey]?.target || 0,
    ratio: r.metrics?.[props.metricKey]?.ratio || 0,
    itemStyle: { color: REGION_COLORS[i % REGION_COLORS.length] },
  }))

  const totalActual = props.grandTotal?.metrics?.[props.metricKey]?.actual || 0
  const totalTarget = props.grandTotal?.metrics?.[props.metricKey]?.target || 0
  const doneVal = Math.max(totalActual, 0.001)
  const remainVal = Math.max(totalTarget - totalActual, 0)

  const innerData = [
    { value: doneVal, name: '已完成', itemStyle: { color: INNER_COLOR_DONE } },
  ]
  if (remainVal > 0.001) {
    innerData.push({ value: remainVal, name: '剩余', itemStyle: { color: INNER_COLOR_REMAIN } })
  }

  return {
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        if (p.seriesName === '大区分布') {
          const d = p.data
          return `<b>${d.name}</b><br/>
            实际: ${d.value.toLocaleString()} ${props.unit}<br/>
            指标: ${d.target.toLocaleString()} ${props.unit}<br/>
            完成比: ${(d.ratio * 100).toFixed(1)}%`
        }
        return `${p.name}: ${p.value.toLocaleString()} ${props.unit}`
      },
    },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      textStyle: { fontSize: 10 },
      data: outerData.map(d => d.name),
    },
    series: [
      {
        name: '大区分布',
        type: 'pie',
        radius: ['50%', '72%'],
        center: ['50%', '43%'],
        avoidLabelOverlap: false,
        padAngle: 2,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: {
          show: false,
        },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold' },
        },
        data: outerData,
      },
      {
        name: '全国完成',
        type: 'pie',
        radius: ['0%', '38%'],
        center: ['50%', '43%'],
        label: {
          show: true,
          position: 'center',
          formatter: () => `{val|${(totalActual || 0).toLocaleString()}}\n{unit|${props.unit}}`,
          rich: {
            val: { fontSize: 18, fontWeight: 'bold', color: INNER_COLOR_DONE },
            unit: { fontSize: 11, color: '#888' },
          },
        },
        labelLine: { show: false },
        data: innerData,
      },
    ],
  }
}

onMounted(() => nextTick(() => initChart()))

watch(
  () => [props.regions, props.metricKey, props.grandTotal],
  () => { if (chart) chart.setOption(buildOption(), true) },
  { deep: true }
)

onBeforeUnmount(() => { if (chart) { chart.dispose(); chart = null } })
</script>
