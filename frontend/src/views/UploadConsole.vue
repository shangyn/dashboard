<template>
  <div class="upload-console" v-loading="loading">
    <!-- 无上传权限时显示系统信息 -->
    <div v-if="uploadConfigs.length === 0 && !loading" class="no-permission">
      <div class="system-info-card">
        <el-icon :size="48" color="#1a73e8"><InfoFilled /></el-icon>
        <h3>数据看板</h3>
        <p>版本 v1.0.0 | 内部管理系统</p>
        <el-divider />
        <div class="info-list">
          <div>系统名称：国际运营数据管理系统</div>
          <div>版本号：v1.0.0</div>
          <div>技术栈：Vue 3 + Element Plus + Flask + SQLite</div>
          <div>部署环境：局域网内部部署</div>
          <div>&copy; 2026 企业内部管理系统</div>
        </div>
      </div>
    </div>

    <!-- 有上传权限时显示上传区 -->
    <template v-else>
      <div class="upload-layout">
        <!-- 左侧菜单 -->
        <div class="upload-sidebar">
          <div class="sidebar-section-title">数据管理</div>
          <div
            v-for="config in uploadConfigs"
            :key="config.id"
            class="sidebar-sub-item"
            :class="{ active: currentMenu === 'data' && selectedConfig?.id === config.id }"
            @click="selectConfig(config); currentMenu = 'data'"
          >
            {{ config.name }}
          </div>
          <div
            class="sidebar-item"
            :class="{ active: currentMenu === 'system' }"
            @click="currentMenu = 'system'"
          >系统信息</div>
        </div>

        <!-- 右侧内容 -->
        <div class="upload-content">
          <div class="content-topbar">
            <span>{{ topbarTitle }}</span>
            <el-button text size="small" @click="goHome">← 返回首页</el-button>
          </div>

          <!-- 数据管理模式 -->
          <template v-if="currentMenu === 'data' && dataZoneConfigs.length">
            <div class="content-body">
              <UploadZone
                v-for="config in dataZoneConfigs"
                :key="config.id"
                :config="config"
                :last-upload-time="fileTimes[config.id] || ''"
                @uploaded="onUploaded(config)"
              />
            </div>
            <!-- 生成看板按钮（仅父级有 handler_script 时显示） -->
            <div class="generate-bar" v-if="showGenerateBtn">
              <el-date-picker
                v-if="selectedConfig?.code === 'generate_data'"
                v-model="genMonth"
                type="month"
                placeholder="选择月份"
                format="YYYY-MM"
                value-format="YYYY-MM"
                size="default"
                style="width:160px;margin-right:10px;"
              />
              <el-button type="primary" :loading="generating" @click="handleGenerate">
                生成看板
              </el-button>
              <span v-if="generating" class="generate-hint">请耐心等待</span>
            </div>
            <!-- 统计 -->
            <div class="stats-row" v-if="stats">
              <div class="stat-item">
                <div class="stat-num">{{ stats.upload_count }}</div>
                <div class="stat-lbl">上传次数</div>
              </div>
              <div class="stat-item">
                <div class="stat-num">{{ stats.parsed_count }}</div>
                <div class="stat-lbl">更新次数</div>
              </div>
              <div class="stat-item">
                <div class="stat-num">{{ stats.db_size_mb }} MB</div>
                <div class="stat-lbl">数据库大小</div>
              </div>
            </div>
          </template>

          <!-- 系统信息模式 -->
          <div class="content-body system-info-page" v-if="currentMenu === 'system'">
            <div class="system-info-card">
              <el-icon :size="48" color="#1a73e8"><InfoFilled /></el-icon>
              <h3>数据看板</h3>
              <p>版本 v1.0.0 | 内部管理系统</p>
              <el-divider />
              <div class="info-list">
                <div>版本号：v1.0.0</div>
                <div>技术栈：Vue 3 + Element Plus + Flask + SQLite</div>
                <div>部署环境：局域网内部部署</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 生成看板成功弹窗 -->
    <el-dialog v-model="genDialogVisible" title="看板生成" width="400px" center>
      <div style="text-align:center;padding:20px 0;">
        <el-icon :size="48" color="#67c23a"><SuccessFilled /></el-icon>
        <p style="font-size:16px;margin:16px 0 8px;color:#333;">看板生成成功！</p>
        <p style="font-size:12px;color:#999;">{{ genMessage }}</p>
      </div>
      <template #footer>
        <el-button @click="genDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="openDashboard">打开看板</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { InfoFilled, SuccessFilled } from '@element-plus/icons-vue'
import { getMyUploadConfigs } from '../api/upload-config'
import { getUploadStats, getFileTimes, generateDashboard } from '../api/upload'
import { useAuthStore } from '../stores/auth'
import UploadZone from '../components/UploadZone.vue'

const router = useRouter()
const authStore = useAuthStore()

const uploadConfigs = ref([])
const stats = ref(null)
const loading = ref(false)
const currentMenu = ref('data')
const selectedConfig = ref(null)
const fileTimes = reactive({})
const generating = ref(false)
const genDialogVisible = ref(false)
const genDashboardUrl = ref('')
const genModuleId = ref(null)
const genMonth = ref('')
const genMessage = ref('')

// 当前右侧需要显示的 UploadZone 配置列表
const dataZoneConfigs = computed(() => {
  if (!selectedConfig.value) return []
  if (selectedConfig.value.children && selectedConfig.value.children.length) {
    return selectedConfig.value.children
  }
  return [selectedConfig.value]
})

// 是否显示"生成看板"按钮
const showGenerateBtn = computed(() => {
  const sel = selectedConfig.value
  return sel && sel.handler_script && sel.children && sel.children.length
})

const topbarTitle = computed(() => {
  if (currentMenu.value === 'system') return '系统信息'
  if (!selectedConfig.value) return '数据管理'
  const sel = selectedConfig.value
  const roots = uploadConfigs.value
  for (const r of roots) {
    if (r.children && r.children.find(c => c.id === sel.id)) {
      return `数据管理 / ${r.name} / ${sel.name}`
    }
  }
  return `数据管理 / ${sel.name}`
})

onMounted(async () => {
  loading.value = true
  try {
    const [configsRes, statsRes] = await Promise.all([
      getMyUploadConfigs(),
      getUploadStats(),
    ])
    uploadConfigs.value = configsRes.data || []
    stats.value = statsRes.data || { upload_count: 0, parsed_count: 0, db_size_mb: 0 }
    if (uploadConfigs.value.length > 0) {
      selectedConfig.value = uploadConfigs.value[0]
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

// 选中项变化 → 加载文件上传时间
watch(selectedConfig, (val) => {
  if (val && val.id) {
    loadFileTimes(val.id)
  }
})

async function loadFileTimes(parentId) {
  try {
    const res = await getFileTimes(parentId)
    const children = res.data?.children || []
    children.forEach(c => {
      fileTimes[c.id] = c.last_upload
    })
  } catch { /* ignore */ }
}

function selectConfig(config) {
  selectedConfig.value = config
}

async function onUploaded(config) {
  // 刷新上传时间
  if (config && config.id) {
    fileTimes[config.id] = (await getFileTimes(selectedConfig.value.id).then(r =>
      (r.data?.children || []).find(c => c.id === config.id)?.last_upload
    ).catch(() => '')) || ''
  }
  // 刷新统计
  getUploadStats().then(res => {
    stats.value = res.data || { upload_count: 0, parsed_count: 0, db_size_mb: 0 }
  }).catch(() => {})
}

async function handleGenerate() {
  if (!selectedConfig.value) return
  if (selectedConfig.value.code === 'generate_data' && !genMonth.value) {
    ElMessage.warning('请先选择月份')
    return
  }
  generating.value = true
  try {
    const data = selectedConfig.value.code === 'generate_data'
      ? { month: genMonth.value }
      : null
    const res = await generateDashboard(selectedConfig.value.code, data)
    genDashboardUrl.value = res.data?.dashboard_url || ''
    genModuleId.value = res.data?.module_id || null
    genMessage.value = res.msg || '看板生成成功'
    genDialogVisible.value = true
  } catch (e) {
    const msg = e?.response?.data?.msg || e?.message || '看板生成失败'
    ElMessage.error(msg)
  } finally {
    generating.value = false
  }
}

function openDashboard() {
  genDialogVisible.value = false
  if (genModuleId.value) {
    router.push(`/dashboard/${genModuleId.value}`)
  } else if (genDashboardUrl.value) {
    router.push(genDashboardUrl.value)
  }
}

function goHome() {
  router.push(authStore.isAdmin ? '/admin/dashboard' : '/home')
}
</script>

<style scoped>
.upload-console { background: #f0f2f5; min-height: calc(100vh - 50px - 56px); }
.upload-layout { display: flex; min-height: calc(100vh - 50px - 56px); }
.upload-sidebar {
  width: 200px; background: #fff; padding: 16px 0;
  border-right: 1px solid #eef0f2; flex-shrink: 0;
}
.sidebar-section-title {
  padding: 8px 16px; font-size: 10px; color: #999;
  text-transform: uppercase; letter-spacing: 1px;
}
.sidebar-item {
  padding: 9px 16px; margin: 0 8px; font-size: 12px; color: #555;
  cursor: pointer; border-radius: 6px;
}
.sidebar-item.active, .sidebar-item:hover { background: #e8f0fe; color: #1a73e8; }
.sidebar-sub-item {
  padding: 7px 16px; margin: 2px 8px; font-size: 11px; color: #555;
  cursor: pointer; border-radius: 6px;
}
.sidebar-sub-item.active, .sidebar-sub-item:hover {
  background: #e8f0fe; color: #1a73e8; font-weight: 500;
}
.upload-content { flex: 1; display: flex; flex-direction: column; }
.content-topbar {
  background: #fff; height: 44px; display: flex; align-items: center;
  justify-content: space-between; padding: 0 20px; font-size: 12px;
  color: #555; border-bottom: 1px solid #eef0f2;
}
.content-body { flex: 1; padding: 16px 20px; overflow-y: auto; }

.generate-bar { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 0 20px 16px; }
.generate-hint { font-size: 13px; color: #909399; }
.stats-row { display: flex; gap: 12px; padding: 0 20px 16px; }
.stat-item {
  flex: 1; background: #fff; border-radius: 10px; padding: 14px;
  text-align: center; border: 1px solid #eef0f2;
}
.stat-num { font-size: 18px; font-weight: 700; color: #1a73e8; }
.stat-lbl { font-size: 10px; color: #999; margin-top: 2px; }

.no-permission {
  display: flex; align-items: center; justify-content: center;
  min-height: calc(100vh - 50px - 56px);
}
.system-info-card {
  background: #fff; border-radius: 16px; padding: 48px; text-align: center;
  border: 1px solid #eef0f2; max-width: 480px;
}
.system-info-card h3 { margin: 16px 0 8px; color: #1a1a2e; }
.system-info-card p { color: #999; font-size: 13px; margin: 0; }
.system-info-page { display: flex; justify-content: center; flex: none; }
.system-info-page .system-info-card { max-width: none; width: 100%; }
.system-info-page .info-list { text-align: center; }
.info-list { text-align: left; font-size: 12px; color: #666; line-height: 2; }
</style>
