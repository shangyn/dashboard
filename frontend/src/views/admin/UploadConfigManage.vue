<template>
  <div class="page-card">
    <div class="toolbar">
      <h3 style="margin:0;">上传配置管理</h3>
      <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
    </div>

    <el-table :data="tableData" border stripe v-loading="loading">
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="code" label="Code" width="140" />
      <el-table-column prop="permission" label="权限标识" width="160" />
      <el-table-column prop="file_types" label="文件类型" width="140" />
      <el-table-column prop="sort_order" label="排序" width="70" />
      <el-table-column prop="is_active" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该配置吗？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="550px">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="上传项名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述说明" />
        </el-form-item>
        <el-form-item label="Code" prop="code">
          <el-input v-model="form.code" placeholder="唯一标识符，如 performance_data" />
        </el-form-item>
        <el-form-item label="权限标识" prop="permission">
          <el-input v-model="form.permission" placeholder="如 upload_performance" />
        </el-form-item>
        <el-form-item label="文件类型" prop="file_types">
          <el-input v-model="form.file_types" placeholder="如 .xlsx,.xls,.csv" />
        </el-form-item>
        <el-form-item label="必需列" prop="required_columns">
          <el-input v-model="form.required_columns" placeholder="必需的列名说明（可选）" />
        </el-form-item>
        <el-form-item label="排序" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="状态" prop="is_active">
          <el-switch v-model="form.is_active" />
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
import { getUploadConfigs, createUploadConfig, updateUploadConfig, deleteUploadConfig } from '../../api/upload-config'

const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const dialogTitle = computed(() => isEdit.value ? '编辑上传配置' : '新增上传配置')

const form = reactive({
  name: '', description: '', code: '', permission: '',
  file_types: '.xlsx,.xls', required_columns: '', sort_order: 0, is_active: true,
})

const formRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入code', trigger: 'blur' }],
  permission: [{ required: true, message: '请输入权限标识', trigger: 'blur' }],
}

onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    const res = await getUploadConfigs()
    tableData.value = res.data || []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''; form.description = ''; form.code = ''; form.permission = ''
  form.file_types = '.xlsx,.xls'; form.required_columns = ''
  form.sort_order = 0; form.is_active = true
}

function openCreateDialog() {
  isEdit.value = false; editId.value = null; resetForm(); dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true; editId.value = row.id
  form.name = row.name; form.description = row.description || ''
  form.code = row.code; form.permission = row.permission
  form.file_types = row.file_types || '.xlsx,.xls'
  form.required_columns = row.required_columns || ''
  form.sort_order = row.sort_order || 0; form.is_active = row.is_active
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const data = { ...form }
    if (isEdit.value) {
      await updateUploadConfig(editId.value, data)
      ElMessage.success('配置已更新')
    } else {
      await createUploadConfig(data)
      ElMessage.success('配置创建成功')
    }
    dialogVisible.value = false
    await fetchData()
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteUploadConfig(id)
    ElMessage.success('配置已删除')
    await fetchData()
  } catch { /* ignore */ }
}
</script>

<style scoped>
.page-card { background: #fff; border-radius: 12px; padding: 20px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
