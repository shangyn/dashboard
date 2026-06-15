<template>
  <div class="page-card">
    <!-- 搜索栏和操作栏 -->
    <div class="toolbar">
      <el-form :inline="true" :model="searchForm" size="default">
        <el-form-item label="工号">
          <el-input v-model="searchForm.username" placeholder="请输入工号" clearable />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="searchForm.real_name" placeholder="请输入姓名" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
      <el-button type="primary" @click="openCreateDialog">新增用户</el-button>
    </div>

    <!-- 表格 -->
    <el-table :data="tableData" border stripe v-loading="loading" style="width: 100%">
      <el-table-column prop="username" label="工号" width="120" />
      <el-table-column prop="real_name" label="姓名" width="120" />
      <el-table-column prop="role_name" label="角色" width="150" />
      <el-table-column prop="is_active" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" min-width="220">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="warning" link @click="openResetPwdDialog(row)">重置密码</el-button>
          <el-popconfirm title="确认删除该用户吗？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="fetchData"
        @current-change="fetchData"
      />
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="工号" prop="username">
          <el-input v-model="form.username" :disabled="isEdit" placeholder="请输入工号" />
        </el-form-item>
        <el-form-item label="密码" prop="password" v-if="!isEdit">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="form.real_name" placeholder="请输入真实姓名" />
        </el-form-item>
        <el-form-item label="角色" prop="role_id">
          <el-select v-model="form.role_id" placeholder="请选择角色" style="width: 100%">
            <el-option v-for="r in roles" :key="r.id" :label="r.role_name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确认</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码确认 -->
    <el-dialog v-model="resetPwdVisible" title="重置密码" width="400px">
      <p>确认将用户 <b>{{ resetTarget?.username }}</b> 的密码重置为 <b>123456</b> 吗？</p>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getUsers, createUser, updateUser, deleteUser, resetPassword } from '../../api/users'
import { getRoles } from '../../api/roles'

const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref([])
const roles = ref([])

const searchForm = reactive({ username: '', real_name: '' })
const pagination = reactive({ page: 1, page_size: 10, total: 0 })

const dialogVisible = ref(false)
const resetPwdVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const resetTarget = ref(null)
const formRef = ref(null)

const dialogTitle = computed(() => isEdit.value ? '编辑用户' : '新增用户')

const form = reactive({
  username: '', password: '', real_name: '',
  role_id: null, is_active: true,
})

const formRules = {
  username: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码不少于6位', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  role_id: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

onMounted(async () => {
  await fetchRoles()
  await fetchData()
})

async function fetchRoles() {
  try {
    const res = await getRoles()
    roles.value = res.data || []
  } catch { /* ignore */ }
}

async function fetchData() {
  loading.value = true
  try {
    const res = await getUsers({
      page: pagination.page,
      page_size: pagination.page_size,
      username: searchForm.username,
      real_name: searchForm.real_name,
    })
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchData()
}

function handleReset() {
  searchForm.username = ''
  searchForm.real_name = ''
  pagination.page = 1
  fetchData()
}

function resetForm() {
  form.username = ''
  form.password = ''
  form.real_name = ''
  form.role_id = null
  form.is_active = true
}

function openCreateDialog() {
  isEdit.value = false
  editId.value = null
  resetForm()
  // 新增时需要密码
  formRules.password[0].required = true
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  editId.value = row.id
  // 编辑时不需要密码
  formRules.password[0].required = false
  form.username = row.username
  form.password = ''
  form.real_name = row.real_name
  form.role_id = row.role_id
  form.is_active = row.is_active
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateUser(editId.value, {
        real_name: form.real_name,
        role_id: form.role_id,
        is_active: form.is_active,
      })
      ElMessage.success('用户信息已更新')
    } else {
      await createUser({
        username: form.username,
        password: form.password,
        real_name: form.real_name,
        role_id: form.role_id,
        is_active: form.is_active,
      })
      ElMessage.success('用户创建成功')
    }
    dialogVisible.value = false
    await fetchData()
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteUser(id)
    ElMessage.success('用户已删除')
    await fetchData()
  } catch { /* ignore */ }
}

function openResetPwdDialog(row) {
  resetTarget.value = row
  resetPwdVisible.value = true
}

async function handleResetPassword() {
  try {
    await resetPassword(resetTarget.value.id)
    ElMessage.success('密码已重置为 123456')
    resetPwdVisible.value = false
  } catch { /* ignore */ }
}
</script>

<style scoped>
.page-card { background: #fff; border-radius: 12px; padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; gap: 8px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
