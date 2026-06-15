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
import { getModules } from '../../api/modules'
import { getUploadConfigs } from '../../api/upload-config'

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

const permissionGroups = ref([])

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const [rolesRes, modulesRes, uploadConfigsRes] = await Promise.all([
      getRoles(),
      getModules().catch(() => ({ data: [] })),
      getUploadConfigs().catch(() => ({ data: [] })),
    ])
    tableData.value = rolesRes.data || []

    // 动态构建权限分组
    const groups = [
      {
        label: '管理类（系统固定）',
        options: [
          { value: 'dashboard', label: '首页看板' },
          { value: 'user_manage', label: '用户管理' },
          { value: 'role_manage', label: '角色管理' },
          { value: 'module_manage', label: '模块管理' },
          { value: 'upload_manage', label: '上传配置管理' },
        ],
      },
    ]

    // 从模块表动态生成看板类权限
    const modulesList = modulesRes.data || []
    if (modulesList.length > 0) {
      groups.push({
        label: '看板类（模块管理 → 动态）',
        options: modulesList.map(m => ({
          value: m.permission,
          label: m.name,
        })),
      })
    }

    // 从上传配置表动态生成上传类权限
    const uploadList = uploadConfigsRes.data || []
    if (uploadList.length > 0) {
      groups.push({
        label: '上传类（上传配置管理 → 动态）',
        options: uploadList.map(c => ({
          value: c.permission,
          label: c.name,
        })),
      })
    }

    permissionGroups.value = groups
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
