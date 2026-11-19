<template>
  <div v-if="context.enabled" class="assistant-root">
    <button v-if="!visible" class="assistant-launcher" type="button" @click="visible = true">
      <el-icon :size="19"><ChatDotRound /></el-icon>
      <span>经营助手</span>
    </button>

    <el-drawer
      v-model="visible"
      direction="rtl"
      size="460px"
      :modal="false"
      :with-header="false"
      append-to-body
      class="assistant-drawer"
    >
      <div class="assistant-panel">
        <header class="assistant-header">
          <div class="assistant-title">
            <span class="assistant-logo"><el-icon><ChatDotRound /></el-icon></span>
            <span>经营助手</span>
            <el-tag size="small" effect="plain">{{ context.scope.label }}</el-tag>
          </div>
          <div class="assistant-header-actions">
            <el-button text circle title="清空对话" @click="clearConversation">
              <el-icon><RefreshRight /></el-icon>
            </el-button>
            <el-button text circle title="关闭" @click="visible = false">
              <el-icon><Close /></el-icon>
            </el-button>
          </div>
        </header>

        <div ref="bodyRef" class="assistant-body">
          <div class="assistant-welcome">
            <div class="welcome-title">可以直接问经营数据</div>
            <div class="welcome-meta">
              {{ context.scope.module_count ? `可见 ${context.scope.module_count} 个模块` : '暂无模块数据权限' }}
              · 数据截止 {{ context.data_date }}
              · {{ context.model_enabled ? '模型意图识别已启用' : '固定查询模式' }}
            </div>
            <div class="assistant-chips">
              <button v-for="item in context.default_questions" :key="item" type="button" class="assistant-chip" @click="send(item)">
                {{ item }}
              </button>
            </div>
          </div>

          <div v-for="(message, index) in messages" :key="index" class="assistant-message" :class="message.role">
            <div class="assistant-bubble">
              <div v-if="message.loading" class="assistant-loading">
                <span class="loading-dot" />
                正在查询，请稍候
              </div>
              <div v-else class="assistant-text">{{ message.message }}</div>

              <div v-if="message.data_date || message.period" class="assistant-meta">
                <span v-if="message.period">{{ message.period }}</span>
                <span v-if="message.data_date">截至 {{ message.data_date }}</span>
              </div>

              <el-table
                v-if="message.columns?.length && message.rows?.length"
                :data="message.rows"
                size="small"
                border
                stripe
                class="assistant-table"
                max-height="300"
              >
                <el-table-column
                  v-for="column in message.columns"
                  :key="column.key"
                  :label="column.label"
                  min-width="100"
                  show-overflow-tooltip
                >
                  <template #default="{ row }">{{ formatCell(cellValue(row, column.key)) }}</template>
                </el-table-column>
              </el-table>

              <div v-if="message.notes?.length" class="assistant-notes">
                <div v-for="note in message.notes" :key="note">{{ note }}</div>
              </div>

              <div v-if="message.export_token" class="assistant-answer-actions">
                <el-button type="primary" size="small" plain @click="downloadExport(message)">
                  <el-icon><Download /></el-icon>
                  导出 Excel
                </el-button>
              </div>

              <div v-if="message.suggestions?.length" class="assistant-chips assistant-followups">
                <button v-for="item in message.suggestions" :key="item" type="button" class="assistant-chip" @click="send(item)">
                  {{ item }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <footer class="assistant-footer">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            resize="none"
            maxlength="1000"
            placeholder="例如：我模块今年签排发回款多少？"
            @keyup.enter.exact.prevent="send()"
          />
          <el-button type="primary" :loading="sending" @click="send()">发送</el-button>
          <div class="assistant-hint">回答只包含当前权限范围内的数据，实际业绩与预计填报分开说明。</div>
        </footer>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Download, RefreshRight } from '@element-plus/icons-vue'
import {
  askBusinessAssistant,
  downloadAssistantExport,
  getAssistantContext,
} from '../../api/businessAssistant'

const route = useRoute()
const visible = ref(false)
const sending = ref(false)
const question = ref('')
const bodyRef = ref(null)
const messages = ref([])
const context = reactive({
  enabled: false,
  scope: { mode: 'none', label: '暂无权限', modules: [], module_count: 0 },
  default_questions: [],
  data_date: '',
  model_enabled: false,
})

const pageContext = computed(() => ({
  path: route.path,
  name: route.name || '',
  query: { ...(route.query || {}) },
}))

function scrollToBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

async function loadContext() {
  try {
    const response = await getAssistantContext()
    Object.assign(context, response.data || {})
  } catch {
    context.enabled = false
  }
}

async function send(text) {
  const content = (text || question.value || '').trim()
  if (!content || sending.value) return
  question.value = ''
  messages.value.push({ role: 'user', message: content })
  const answer = { role: 'assistant', loading: true }
  messages.value.push(answer)
  sending.value = true
  scrollToBottom()
  try {
    const response = await askBusinessAssistant({
      question: content,
      page_context: pageContext.value,
    })
    Object.assign(answer, response.data || {}, { loading: false })
  } catch (error) {
    answer.loading = false
    answer.message = error?.message || '查询失败，请稍后重试。'
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function clearConversation() {
  messages.value = []
  question.value = ''
}

function cellValue(row, path) {
  return String(path || '').split('.').reduce((value, key) => {
    if (value === null || value === undefined) return undefined
    return value[key]
  }, row)
}

function formatCell(value) {
  if (typeof value === 'number') {
    return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  return value === null || value === undefined || value === '' ? '—' : value
}

async function downloadExport(message) {
  if (!message.export_token) return
  const period = String(message.period || '查询结果').replace(/[\\/:*?"<>|]/g, '-')
  try {
    await downloadAssistantExport(message.export_token, `经营助手_${period}.xlsx`)
    ElMessage.success('导出已开始')
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(loadContext)
</script>

<style scoped>
.assistant-launcher {
  position: fixed;
  right: 0;
  top: 43%;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  width: 46px;
  padding: 13px 6px;
  border: 0;
  border-radius: 13px 0 0 13px;
  background: linear-gradient(160deg, #1a73e8, #0d47a1);
  color: #fff;
  font-size: 12px;
  line-height: 1.25;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(26, 115, 232, 0.28);
}
.assistant-launcher span { writing-mode: vertical-rl; letter-spacing: 2px; }
.assistant-launcher:hover { background: linear-gradient(160deg, #2b83f3, #1557b0); }

.assistant-panel {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8fafc;
}
.assistant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  height: 68px;
  padding: 0 18px;
  background: #fff;
  border-bottom: 1px solid #e8edf4;
  flex-shrink: 0;
}
.assistant-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 700; color: #1a2b45; }
.assistant-logo { width: 30px; height: 30px; border-radius: 9px; background: #eaf2ff; color: #1a73e8; display: inline-flex; align-items: center; justify-content: center; }
.assistant-header-actions { display: flex; align-items: center; }
.assistant-body { flex: 1; overflow-y: auto; padding: 16px 14px 24px; }
.assistant-welcome { background: #fff; border: 1px solid #e8edf4; border-radius: 14px; padding: 14px; margin-bottom: 14px; }
.welcome-title { font-size: 14px; font-weight: 700; color: #1a2b45; }
.welcome-meta { margin-top: 5px; font-size: 12px; color: #7b8798; }
.assistant-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.assistant-chip { border: 1px solid #dbe7f8; background: #f5f9ff; color: #1a73e8; border-radius: 999px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.assistant-chip:hover { border-color: #1a73e8; background: #eaf2ff; }
.assistant-message { display: flex; margin-bottom: 12px; }
.assistant-message.user { justify-content: flex-end; }
.assistant-bubble { max-width: 94%; border-radius: 13px; padding: 10px 12px; background: #fff; border: 1px solid #e8edf4; box-shadow: 0 2px 8px rgba(31, 62, 102, 0.04); }
.assistant-message.user .assistant-bubble { background: #1a73e8; border-color: #1a73e8; color: #fff; }
.assistant-text { font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.assistant-meta { display: flex; gap: 12px; margin-top: 7px; color: #8a96a8; font-size: 11px; }
.assistant-loading { display: flex; align-items: center; gap: 7px; color: #66768c; font-size: 13px; }
.loading-dot { width: 7px; height: 7px; border-radius: 50%; background: #1a73e8; animation: assistant-pulse 1s infinite; }
@keyframes assistant-pulse { 50% { opacity: 0.3; transform: scale(0.8); } }
.assistant-table { margin-top: 10px; width: 100%; font-size: 12px; }
.assistant-notes { margin-top: 9px; padding: 8px 9px; border-radius: 8px; background: #f5f8fc; color: #6f7d90; font-size: 11px; line-height: 1.6; }
.assistant-answer-actions { margin-top: 10px; }
.assistant-followups { margin-top: 10px; }
.assistant-footer { flex-shrink: 0; padding: 12px 14px 14px; background: #fff; border-top: 1px solid #e8edf4; }
.assistant-footer .el-button { width: 100%; margin-top: 9px; }
.assistant-hint { margin-top: 7px; color: #93a0b1; font-size: 11px; line-height: 1.45; }
@media (max-width: 640px) {
  .assistant-launcher { top: auto; bottom: 76px; }
}
</style>

<style>
.assistant-drawer { width: min(460px, 94vw) !important; }
.assistant-drawer .el-drawer__body { padding: 0 !important; overflow: hidden; }
</style>
