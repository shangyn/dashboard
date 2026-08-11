<template>
  <div class="upload-zone-card">
    <div class="upload-zone-title">{{ config?.name }}</div>
    <p class="upload-zone-desc" v-if="config?.description">{{ config.description }}</p>
    <p v-if="config?.required_columns" class="upload-zone-required">
      必需列：{{ config.required_columns }}
    </p>
    <el-upload
      class="upload-zone"
      drag
      :action="`/api/upload/${config?.code}`"
      :headers="uploadHeaders"
      :accept="acceptTypes"
      :on-success="onSuccess"
      :on-error="onError"
    >
      <el-icon :size="32" class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">拖放文件到此处或点击选择</div>
      <div class="upload-hint">{{ fileTypeHint }}</div>
    </el-upload>
    <div class="upload-time" v-if="lastUploadTime">上次上传：{{ lastUploadTime }}</div>
    <div class="upload-time" v-else>尚未上传</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

const props = defineProps({
  config: { type: Object, required: true },
  lastUploadTime: { type: String, default: '' },
})

const emit = defineEmits(['uploaded'])

const uploadHeaders = computed(() => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
}))

const acceptTypes = computed(() => {
  const types = props.config?.file_types || '.xlsx,.xls'
  return types.split(',').map(t => t.trim()).join(',')
})

const fileTypeHint = computed(() => {
  const types = props.config?.file_types || '.xlsx,.xls'
  return `支持文件：${types}`
})

function onSuccess(response) {
  if (response.code === 200) {
    ElMessage.success('上传成功')
    emit('uploaded', response.data)
  }
}

function onError(error) {
  const msg = error?.response?.data?.msg || error?.message || '上传失败'
  ElMessage.error(msg)
}
</script>

<style scoped>
.upload-zone-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  margin-bottom: 12px; border: 1px solid #eef0f2;
}
.upload-zone-title { font-weight: 600; font-size: 13px; color: #1a1a2e; margin-bottom: 4px; }
.upload-zone-desc { font-size: 11px; color: #999; margin: 0 0 4px; }
.upload-zone-required { font-size: 10px; color: #e6a23c; margin: 0 0 12px; }
.upload-icon { color: #c0c4cc; }
.upload-text { font-size: 12px; color: #999; margin-top: 8px; }
.upload-hint { font-size: 10px; color: #bbb; margin-top: 4px; }
.upload-time { font-size: 11px; color: #999; margin-top: 8px; text-align: right; }
</style>
