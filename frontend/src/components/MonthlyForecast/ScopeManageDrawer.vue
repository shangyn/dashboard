<template>
  <el-drawer v-model="innerVisible" size="860px">
    <template #header>
      <div class="scope-header">
        <span class="scope-title">模块名单管理</span>
        <el-button type="primary" size="small" @click="startAdd">新增</el-button>
      </div>
    </template>
    <div class="scope-drawer" v-loading="loading">
      <div class="scope-toolbar">
        <el-select
          v-model="filterModule"
          size="small"
          clearable
          filterable
          placeholder="全部模块"
          style="width:180px"
        >
          <el-option v-for="m in options.modules" :key="m" :label="m" :value="m" />
        </el-select>
        <el-input
          v-model="keyword"
          size="small"
          clearable
          placeholder="DT号 / 姓名"
          style="width:170px"
        />
        <el-checkbox v-model="onlyAbnormal">只看异常</el-checkbox>
        <el-button size="small" @click="loadAll">刷新</el-button>
        <span class="scope-count">{{ filteredRows.length }} / {{ rows.length }} 条</span>
      </div>

      <div v-if="adding" class="scope-addbar">
        <el-select
          v-model="addForm.user_id"
          size="small"
          filterable
          placeholder="选择账号"
          style="width:250px"
        >
          <el-option v-for="u in userOptions" :key="u.id" :label="u.label" :value="u.id" />
        </el-select>
        <el-select
          v-model="addForm.module_name"
          size="small"
          filterable
          placeholder="选择模块"
          style="width:230px"
        >
          <el-option v-for="m in options.modules" :key="m" :label="m" :value="m" />
        </el-select>
        <el-button size="small" type="primary" :loading="saving" @click="submitAdd">确定</el-button>
        <el-button size="small" @click="adding = false">取消</el-button>
      </div>

      <el-table
        :data="filteredRows"
        size="small"
        border
        height="calc(100vh - 260px)"
        class="scope-table"
      >
        <el-table-column prop="username" label="账号" width="120" />
        <el-table-column prop="real_name" label="姓名" width="90" />
        <el-table-column prop="module_name" label="模块" min-width="150" show-overflow-tooltip />
        <el-table-column label="来源" width="130">
          <template #default="{ row }">{{ row.match_key || '—' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="150" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row.user_status).type" size="small" disable-transitions>
              {{ statusMeta(row.user_status).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeRow(row)">移除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <span>没有符合条件的名单记录</span>
        </template>
      </el-table>

      <div class="scope-footer">
        <span class="scope-tip">「导入名单」为全量替换：会覆盖这里手工增删的结果，请以完整名单导入。</span>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="orphanCount === 0"
          :loading="cleaning"
          @click="runCleanup"
        >
          清理无效归属（{{ orphanCount }}）
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getScope,
  getScopeOptions,
  addScopeItem,
  removeScopeItem,
  cleanupScope,
} from '../../api/monthly-forecast'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const innerVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const saving = ref(false)
const cleaning = ref(false)
const rows = ref([])
const options = ref({ modules: [], users: [] })
const filterModule = ref('')
const keyword = ref('')
const onlyAbnormal = ref(false)
const adding = ref(false)
const addForm = ref({ user_id: null, module_name: '' })

const userOptions = computed(() =>
  (options.value.users || []).map((u) => ({
    id: u.id,
    label:
      `${u.username || '(无账号)'} ${u.real_name || ''}`.trim() +
      (u.is_active ? '' : '（已停用）'),
  }))
)

const orphanCount = computed(() => rows.value.filter((r) => r.user_status === 'missing').length)

const filteredRows = computed(() => {
  const text = (keyword.value || '').trim().toLowerCase()
  const module = filterModule.value || ''
  return rows.value.filter((row) => {
    if (module && row.module_name !== module) return false
    if (onlyAbnormal.value && row.user_status === 'active') return false
    if (!text) return true
    const haystack = `${row.username || ''} ${row.real_name || ''} ${row.match_key || ''}`.toLowerCase()
    return haystack.includes(text)
  })
})

function statusMeta(status) {
  if (status === 'missing') return { text: '账号不存在', type: 'danger' }
  if (status === 'inactive') return { text: '账号已停用', type: 'warning' }
  return { text: '正常', type: 'success' }
}

async function loadScope() {
  const res = await getScope()
  rows.value = res.data || []
}

async function loadOptions() {
  const res = await getScopeOptions()
  options.value = res.data || { modules: [], users: [] }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadScope(), loadOptions()])
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (!val) return
    adding.value = false
    addForm.value = { user_id: null, module_name: filterModule.value || '' }
    loadAll()
  }
)

function startAdd() {
  adding.value = true
  addForm.value = { user_id: null, module_name: filterModule.value || '' }
}

async function submitAdd() {
  if (!addForm.value.user_id) {
    ElMessage.warning('请选择账号')
    return
  }
  if (!addForm.value.module_name) {
    ElMessage.warning('请选择模块')
    return
  }
  saving.value = true
  try {
    await addScopeItem({
      user_id: addForm.value.user_id,
      module_name: addForm.value.module_name,
    })
    ElMessage.success('已添加')
    adding.value = false
    addForm.value = { user_id: null, module_name: '' }
    await loadScope()
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    saving.value = false
  }
}

async function removeRow(row) {
  try {
    await ElMessageBox.confirm(
      '移除后，该账号将变成「可看全部模块汇总」的只读账号，无法再填报本模块。建议同时到「用户管理」停用账号或更换角色。确认移除？',
      '移除归属',
      { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' }
    )
  } catch (error) {
    return
  }
  try {
    await removeScopeItem(row.id)
    ElMessage.success('已移除')
    await loadScope()
  } catch (error) {
    // 响应拦截器已统一提示
  }
}

async function runCleanup() {
  const count = orphanCount.value
  try {
    await ElMessageBox.confirm(
      `检测到 ${count} 条「账号已不存在」的无效归属，清理后不可恢复。确认清理？`,
      '清理无效归属',
      { type: 'warning', confirmButtonText: '确认清理', cancelButtonText: '取消' }
    )
  } catch (error) {
    return
  }
  cleaning.value = true
  try {
    const res = await cleanupScope()
    ElMessage.success(`已清理 ${(res.data && res.data.removed) || 0} 条`)
    await loadScope()
  } catch (error) {
    // 响应拦截器已统一提示
  } finally {
    cleaning.value = false
  }
}
</script>

<style scoped>
.scope-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 1;
}

.scope-title {
  font-size: 16px;
  font-weight: 600;
}

.scope-drawer {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scope-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.scope-count {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}

.scope-addbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.scope-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.scope-tip {
  color: #909399;
  font-size: 12px;
}
</style>
