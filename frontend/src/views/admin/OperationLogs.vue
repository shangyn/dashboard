<template>
  <div class="page-card">
    <div class="toolbar">
      <h3 style="margin:0;">操作日志</h3>
      <div style="display:flex;gap:10px;">
        <el-select v-model="filters.action_type" clearable placeholder="操作类型" style="width:150px;" @change="fetchData">
          <el-option label="上传文件" value="upload" />
          <el-option label="生成看板" value="generate_dashboard" />
        </el-select>
        <el-input v-model="filters.username" clearable placeholder="用户名" style="width:150px;" @clear="fetchData" @keyup.enter="fetchData" />
        <el-button type="primary" @click="fetchData">查询</el-button>
      </div>
    </div>

    <el-table :data="tableData" border stripe v-loading="loading">
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="username" label="用户" width="100" />
      <el-table-column prop="ip_address" label="IP地址" width="140" />
      <el-table-column prop="action_type" label="操作类型" width="120">
        <template #default="{ row }">
          <el-tag :type="row.action_type === 'generate_dashboard' ? 'warning' : 'primary'" size="small">
            {{ row.action_type === 'generate_dashboard' ? '生成看板' : row.action_type === 'upload' ? '上传文件' : row.action_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="target_name" label="目标" width="200" />
      <el-table-column prop="result" label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
            {{ row.result === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="详情" min-width="200" show-overflow-tooltip />
    </el-table>

    <el-pagination
      v-if="total > 0"
      style="margin-top:16px;justify-content:flex-end;"
      background layout="total, prev, pager, next"
      :total="total" :page-size="pageSize" v-model:current-page="page"
      @current-change="fetchData"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getOperationLogs } from '../../api/operations'

const loading = ref(false)
const tableData = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const filters = reactive({
  action_type: '',
  username: '',
})

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await getOperationLogs({
      page: page.value, page_size: pageSize.value,
      action_type: filters.action_type,
      username: filters.username,
    })
    tableData.value = res.data?.items || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page-card { background: #fff; border-radius: 12px; padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
