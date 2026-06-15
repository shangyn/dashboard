<template>
  <div class="upload-console" v-loading="loading">
    <!-- 无上传权限时显示系统信息 -->
    <div v-if="uploadConfigs.length === 0 && !loading" class="no-permission">
      <div class="system-info-card">
        <el-icon :size="48" color="#1a73e8"><InfoFilled /></el-icon>
        <h3>企业管理系统</h3>
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
          <div class="sidebar-section-title">菜单导航</div>
          <div class="sidebar-item active">数据管理</div>
          <div class="sidebar-item" @click="showSystemInfo = !showSystemInfo">系统信息</div>

          <div class="sidebar-section-title" style="margin-top: 20px;">数据管理</div>
          <div
            v-for="config in uploadConfigs"
            :key="config.id"
            class="sidebar-sub-item"
            :class="{ active: activeConfig?.id === config.id }"
            @click="activeConfig = config"
          >
            {{ config.name }}
          </div>
        </div>

        <!-- 右侧内容 -->
        <div class="upload-content">
          <div class="content-topbar">
            <span>数据管理 / {{ activeConfig?.name || '' }}</span>
            <el-button text size="small" @click="$router.push('/home')">← 返回首页</el-button>
          </div>

          <div class="content-body" v-if="activeConfig">
            <UploadZone :config="activeConfig" @uploaded="onUploaded" />
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
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { getMyUploadConfigs } from '../api/upload-config'
import { getUploadStats } from '../api/upload'
import UploadZone from '../components/UploadZone.vue'

const uploadConfigs = ref([])
const activeConfig = ref(null)
const stats = ref(null)
const loading = ref(false)
const showSystemInfo = ref(false)

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
      activeConfig.value = uploadConfigs.value[0]
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

function onUploaded() {
  // Refresh stats after upload
  getUploadStats().then(res => {
    stats.value = res.data || { upload_count: 0, parsed_count: 0, db_size_mb: 0 }
  }).catch(() => {})
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
.info-list { text-align: left; font-size: 12px; color: #666; line-height: 2; }
</style>
