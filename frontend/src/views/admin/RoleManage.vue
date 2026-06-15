<template>
  <div class="page-card">
    <div class="toolbar">
      <h3 style="margin:0;">角色管理</h3>
      <el-button type="primary" @click="openCreateDialog">新增角色</el-button>
    </div>

    <el-table :data="tableData" border stripe v-loading="loading">
      <el-table-column prop="role_name" label="角色名称" width="150" />
      <el-table-column prop="is_admin" label="管理员" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">
            {{ row.is_admin ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限" min-width="300">
        <template #default="{ row }">
          <el-tag v-for="p in row.permissions" :key="p" size="small" style="margin: 2px;">
            {{ p }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该角色吗？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="角色名称" prop="role_name">
          <el-input v-model="form.role_name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="管理员角色" prop="is_admin">
          <el-switch v-model="form.is_admin" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item label="权限">
          <div v-for="group in permissionGroups" :key="group.label" style="margin-bottom: 12px;">
            <div style="font-weight: 600; font-size: 12px; color: #666; margin-bottom: 6px;">{{ group.label }}</div>
            <el-checkbox-group v-model="form.permissions">
              <el-checkbox v-for="opt in group.options" :key="opt.value" :value="opt.value" :label="opt.value">
                {{ opt.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getRoles, createRole, updateRole, deleteRole } from '../../api/roles'

const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const dialogTitle = computed(() => isEdit.value ? '编辑角色' : '新增角色')

const form = reactive({
  role_name: '', is_admin: false, permissions: [],
})

const formRules = {
  role_name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
}

const permissionGroups = [
  {
    label: '管理类',
    options: [
      { value: 'dashboard', label: '首页看板' },
      { value: 'user_manage', label: '用户管理' },
      { value: 'role_manage', label: '角色管理' },
      { value: 'module_manage', label: '模块管理' },
      { value: 'upload_manage', label: '上传配置管理' },
    ],
  },
  {
    label: '看板类',
    options: [
      { value: 'dashboard_receivables', label: '报价统计分析看板' },
      { value: 'dashboard_performance', label: '业绩完成情况看板' },
      { value: 'dashboard_daily', label: '国际运营业绩日报看板' },
      { value: 'dashboard_ledger', label: '报价执行台账看板' },
      { value: 'dashboard_function', label: '职能工作看板' },
      { value: 'dashboard_spare_parts', label: '国贸备件报价' },
    ],
  },
  {
    label: '上传类',
    options: [
      { value: 'upload_performance', label: '业绩数据上传' },
      { value: 'upload_module_target', label: '模块业绩指标上传' },
      { value: 'upload_payment', label: '回款数据上传' },
      { value: 'upload_spare_parts', label: '商贸备件数据上传' },
      { value: 'upload_trade', label: '商贸数据上传' },
      { value: 'upload_delivery', label: '备件发货数据上传' },
      { value: 'upload_offline_quote', label: '2026线下报价上传' },
    ],
  },
]

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await getRoles()
    tableData.value = res.data || []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.role_name = ''
  form.is_admin = false
  form.permissions = []
}

function openCreateDialog() {
  isEdit.value = false
  editId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  editId.value = row.id
  form.role_name = row.role_name
  form.is_admin = row.is_admin
  form.permissions = [...(row.permissions || [])]
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateRole(editId.value, {
        role_name: form.role_name,
        is_admin: form.is_admin,
        permissions: form.permissions,
      })
      ElMessage.success('角色已更新')
    } else {
      await createRole({
        role_name: form.role_name,
        is_admin: form.is_admin,
        permissions: form.permissions,
      })
      ElMessage.success('角色创建成功')
    }
    dialogVisible.value = false
    await fetchData()
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteRole(id)
    ElMessage.success('角色已删除')
    await fetchData()
  } catch { /* error handled in interceptor */ }
}
</script>

<style scoped>
.page-card { background: #fff; border-radius: 12px; padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
