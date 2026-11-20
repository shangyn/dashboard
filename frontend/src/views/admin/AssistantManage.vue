<template>
  <div class="assistant-admin">
    <div class="page-head">
      <div>
        <h2>经营助手管理</h2>
        <p>检查模型是否真实可用，并查看助手的每次查询和失败原因。</p>
      </div>
      <el-button :loading="statusLoading" @click="loadAll">刷新</el-button>
    </div>

    <div class="status-grid">
      <div class="status-card">
        <div class="status-card-title">助手入口</div>
        <el-tag :type="statusData.assistant_enabled ? 'success' : 'info'" effect="plain">
          {{ statusData.assistant_enabled ? '已显示' : '已隐藏' }}
        </el-tag>
        <p>控制所有用户页面中的经营助手悬浮入口。</p>
      </div>

      <div class="status-card">
        <div class="status-card-title">模型配置</div>
        <el-tag :type="modelTagType" effect="plain">
          {{ modelTagLabel }}
        </el-tag>
        <dl class="status-list">
          <div><dt>开关</dt><dd>{{ statusData.enabled ? '已开启' : '未开启' }}</dd></div>
          <div><dt>模型</dt><dd>{{ statusData.model || '—' }}</dd></div>
          <div><dt>接口</dt><dd>{{ statusData.base_url || '未配置' }}</dd></div>
          <div><dt>答复整理</dt><dd>{{ statusData.answer_enabled ? '已开启' : '固定模板' }}</dd></div>
          <div><dt>超时</dt><dd>{{ statusData.timeout || 0 }} 秒</dd></div>
        </dl>
      </div>

      <div class="status-card test-card">
        <div class="status-card-title">
          连通性检测
          <el-tag v-if="testResult" :type="testTagType" effect="plain">{{ testResult.success ? '可用' : '异常' }}</el-tag>
        </div>
        <el-button type="primary" :loading="testing" @click="runModelTest">测试模型连接</el-button>
        <div v-if="testResult" class="test-result">
          <div class="test-meta">
            <span>耗时 {{ testResult.latency_ms }} ms</span>
            <span>HTTP {{ testResult.status_code || '—' }}</span>
            <span>{{ testResult.checked_at }}</span>
          </div>
          <div class="test-message">{{ testResult.message }}</div>
          <div v-if="testResult.action" class="test-action">
            识别动作：{{ actionLabel(testResult.action) }}
            <span v-if="testResult.action_ok" class="ok-text">符合预期</span>
            <span v-else class="warn-text">与预期不一致</span>
          </div>
          <div v-if="testResult.answer_checked" class="test-action">
            答复整理：{{ testResult.answer_ok ? '通过' : '失败' }}
            <span class="test-message">{{ testResult.answer_message }}</span>
          </div>
          <pre v-if="testResult.response_preview" class="test-preview">{{ testResult.response_preview }}</pre>
        </div>
        <p v-else>点击后会真实调用一次模型，并验证它能否返回合法的经营助手动作。</p>
      </div>
    </div>

    <div class="logs-card">
      <div class="logs-head">
        <div>
          <h3>查询日志</h3>
          <p>“意图来源”为模型，表示该次请求实际由模型完成路由；rule_fallback 表示模型调用失败或输出无效后回退到规则。</p>
        </div>
        <div class="logs-actions">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 130px" @change="loadLogs">
            <el-option label="成功" value="success" />
            <el-option label="需补充" value="needs_input" />
            <el-option label="部分成功" value="partial_success" />
            <el-option label="无权限" value="forbidden" />
            <el-option label="业务外" value="unsupported" />
            <el-option label="异常" value="error" />
          </el-select>
          <el-select v-model="filters.limit" style="width: 100px" @change="loadLogs">
            <el-option label="50 条" :value="50" />
            <el-option label="100 条" :value="100" />
            <el-option label="200 条" :value="200" />
          </el-select>
          <el-button :loading="logsLoading" @click="loadLogs">刷新</el-button>
        </div>
      </div>

      <el-table :data="logs" border stripe v-loading="logsLoading" row-key="id">
        <el-table-column type="expand" width="42">
          <template #default="{ row }">
            <div class="log-detail">
              <div class="detail-block">
                <div class="detail-label">完整问题</div>
                <div>{{ row.question || '—' }}</div>
              </div>
              <div class="detail-block" v-if="row.failure_reason">
                <div class="detail-label">失败原因</div>
                <div class="danger-text">{{ row.failure_reason }}</div>
              </div>
              <div class="detail-grid">
                <div><span>Trace</span>{{ row.trace_id || '—' }}</div>
                <div><span>会话</span>{{ row.conversation_id || '—' }}</div>
                <div><span>模型开关</span>{{ row.model_enabled ? '已启用' : '未启用' }}</div>
                <div><span>权限范围</span>{{ row.scope_label || '—' }}</div>
              </div>
              <div class="detail-block">
                <div class="detail-label">执行步骤</div>
                <pre>{{ pretty(row.steps) }}</pre>
              </div>
              <div class="detail-block">
                <div class="detail-label">结果摘要</div>
                <pre>{{ pretty(row.result_summary) }}</pre>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="username" label="用户" width="105" />
        <el-table-column prop="question" label="问题" min-width="260" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="95">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" width="130">
          <template #default="{ row }">{{ actionLabel(row.action) }}</template>
        </el-table-column>
        <el-table-column prop="intent_source" label="意图来源" width="120">
          <template #default="{ row }">{{ intentLabel(row.intent_source) }}</template>
        </el-table-column>
        <el-table-column label="答复来源" width="100">
          <template #default="{ row }">{{ answerLabel(row.result_summary) }}</template>
        </el-table-column>
        <el-table-column prop="failure_code" label="失败编码" width="145" show-overflow-tooltip />
        <el-table-column prop="duration_ms" label="耗时(ms)" width="90" />
      </el-table>
      <el-empty v-if="!logsLoading && logs.length === 0" description="暂无查询日志" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getAssistantModelStatus,
  getAssistantQueryLogs,
  testAssistantModelConnection,
} from '../../api/businessAssistant'

const statusLoading = ref(false)
const logsLoading = ref(false)
const testing = ref(false)
const logs = ref([])
const testResult = ref(null)

const statusData = reactive({
  assistant_enabled: false,
  configured: false,
  enabled: false,
  model: '',
  base_url: '',
  timeout: 0,
  answer_enabled: false,
})

const filters = reactive({
  status: '',
  limit: 100,
})

const STATUS_META = {
  success: { label: '成功', type: 'success' },
  needs_input: { label: '需补充', type: 'warning' },
  partial_success: { label: '部分成功', type: 'warning' },
  forbidden: { label: '无权限', type: 'danger' },
  unsupported: { label: '业务外', type: 'info' },
  error: { label: '异常', type: 'danger' },
}

const ACTION_LABELS = {
  performance: '经营情况',
  ladders: '梯号明细',
  ladder_status: '合同/梯号状态',
  diagnose: '候选池诊断',
  contract_payment: '合同回款',
  submission_status: '填报提交',
  data_source: '数据来源',
  multi: '多查询联动',
  unsupported: '未识别',
}

const testTagType = computed(() => {
  if (!testResult.value) return 'info'
  if (testResult.value.success) return 'success'
  return testResult.value.reachable ? 'warning' : 'danger'
})

const modelTagType = computed(() => {
  if (statusData.configured) return 'success'
  return statusData.enabled ? 'warning' : 'info'
})

const modelTagLabel = computed(() => {
  if (statusData.configured) return '已配置'
  return statusData.enabled ? '配置不完整' : '未启用'
})

function statusLabel(status) {
  return STATUS_META[status]?.label || status || '—'
}

function statusTagType(status) {
  return STATUS_META[status]?.type || 'info'
}

function actionLabel(action) {
  return ACTION_LABELS[action] || action || '—'
}

function intentLabel(intent) {
  if (intent === 'model') return '模型'
  if (intent === 'rule') return '固定规则'
  if (intent === 'rule_fallback') return '模型回退规则'
  return intent || '—'
}

function answerLabel(resultSummary) {
  const source = resultSummary && resultSummary.answer_source
  if (source === 'model') return '模型整理'
  if (source === 'template') return '固定模板'
  return '—'
}

function pretty(value) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch {
    return String(value || '')
  }
}

async function loadStatus() {
  statusLoading.value = true
  try {
    const response = await getAssistantModelStatus()
    Object.assign(statusData, response.data || {})
  } finally {
    statusLoading.value = false
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const response = await getAssistantQueryLogs({
      status: filters.status || undefined,
      limit: filters.limit,
    })
    logs.value = response.data || []
  } finally {
    logsLoading.value = false
  }
}

async function runModelTest() {
  testing.value = true
  try {
    const response = await testAssistantModelConnection()
    testResult.value = response.data || null
  } finally {
    testing.value = false
  }
}

async function loadAll() {
  await Promise.all([loadStatus(), loadLogs()])
}

onMounted(loadAll)
</script>

<style scoped>
.assistant-admin { display: flex; flex-direction: column; gap: 16px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.page-head h2 { margin: 0; color: #1a2b45; font-size: 22px; }
.page-head p, .logs-head p { margin: 6px 0 0; color: #7b8798; font-size: 12px; line-height: 1.6; }
.status-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.status-card { min-height: 150px; padding: 18px; border: 1px solid #e8edf4; border-radius: 12px; background: #fff; }
.status-card-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; color: #243b5a; font-size: 15px; font-weight: 700; }
.status-card p { margin: 12px 0 0; color: #8794a6; font-size: 12px; line-height: 1.6; }
.status-list { display: flex; flex-direction: column; gap: 8px; margin: 12px 0 0; }
.status-list div { display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 8px; font-size: 12px; }
.status-list dt { color: #8a96a8; }
.status-list dd { margin: 0; color: #40526a; word-break: break-all; }
.test-card .el-button { width: 100%; }
.test-result { margin-top: 12px; padding-top: 12px; border-top: 1px solid #edf2f8; }
.test-meta { display: flex; flex-wrap: wrap; gap: 10px; color: #8794a6; font-size: 11px; }
.test-message { margin-top: 8px; color: #40526a; font-size: 12px; line-height: 1.6; }
.test-action { margin-top: 7px; color: #52657d; font-size: 12px; }
.ok-text { margin-left: 7px; color: #18a058; }
.warn-text { margin-left: 7px; color: #d48806; }
.test-preview, .log-detail pre { max-height: 180px; overflow: auto; margin: 8px 0 0; padding: 9px; border-radius: 7px; background: #f5f8fc; color: #596a80; font-size: 11px; white-space: pre-wrap; word-break: break-all; }
.logs-card { padding: 18px; border: 1px solid #e8edf4; border-radius: 12px; background: #fff; }
.logs-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
.logs-head h3 { margin: 0; color: #243b5a; font-size: 17px; }
.logs-actions { display: flex; align-items: center; gap: 9px; flex-shrink: 0; }
.log-detail { padding: 6px 20px 14px; color: #53657c; font-size: 12px; }
.detail-block { margin-bottom: 12px; }
.detail-label { margin-bottom: 4px; color: #8a96a8; font-size: 11px; font-weight: 700; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 20px; margin-bottom: 12px; }
.detail-grid span { display: inline-block; min-width: 70px; color: #8a96a8; }
.danger-text { color: #d4380d; line-height: 1.6; }
@media (max-width: 1100px) {
  .status-grid { grid-template-columns: 1fr; }
  .logs-head { flex-direction: column; }
  .logs-actions { width: 100%; flex-wrap: wrap; }
}
</style>
