<template>
  <div>
    <div class="head-row">
      <div>
        <div class="page-title">{{ kb?.name || '文档管理' }}</div>
        <div class="page-sub">{{ kb?.description || '上传后自动解析、切分、建立向量索引' }}</div>
      </div>
      <el-button :icon="Back" @click="$router.push('/knowledge')">返回知识库</el-button>
    </div>

    <div class="card upload-card">
      <el-upload
        drag
        :show-file-list="false"
        :http-request="upload"
        :disabled="uploading"
        accept=".pdf,.docx,.xlsx,.xlsm,.md,.markdown,.txt"
        multiple
      >
        <div class="drop">
          <el-icon :size="30" class="drop-icon"><UploadFilled /></el-icon>
          <div class="drop-title">{{ uploading ? '上传中…' : '把 PDF / Word / Excel / Markdown 拖到这里，或点击选择' }}</div>
          <div class="drop-sub">支持 PDF、DOCX、XLSX、MD、TXT；单文件不超过 30MB，相同内容自动去重</div>
        </div>
      </el-upload>
    </div>

    <div class="card table-card">
      <div class="table-head">
        <div class="table-title">文档（{{ docs.length }}）</div>
        <el-button text :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-table :data="docs" size="default" style="width: 100%">
        <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ (row.size / 1024).toFixed(0) }} KB</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" effect="light" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块" width="80" />
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-tooltip v-if="row.error" :content="row.error" placement="top">
              <el-icon class="err-icon"><WarningFilled /></el-icon>
            </el-tooltip>
            <el-button text size="small" @click="reindex(row)">重建</el-button>
            <el-button text size="small" @click="download(row)">下载</el-button>
            <el-button text size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorMessage } from '../api'

const route = useRoute()
const kbId = route.params.id
const kb = ref(null)
const docs = ref([])
const uploading = ref(false)
let timer = null

function statusText(s) {
  return { pending: '排队中', parsing: '解析中', indexing: '建索引', ready: '已就绪', failed: '失败' }[s] || s
}
function statusType(s) {
  return { pending: 'info', parsing: 'warning', indexing: 'warning', ready: 'success', failed: 'danger' }[s] || 'info'
}
function formatTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-'
}

async function load() {
  try {
    const [k, d] = await Promise.all([api.get('/kbs'), api.get(`/kbs/${kbId}/documents`)])
    kb.value = k.data.find((x) => String(x.id) === String(kbId))
    docs.value = d.data
    const busy = docs.value.some((x) => ['pending', 'parsing', 'indexing'].includes(x.status))
    if (busy && !timer) timer = setInterval(load, 2500)
    if (!busy && timer) {
      clearInterval(timer)
      timer = null
    }
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function upload({ file }) {
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    await api.post(`/kbs/${kbId}/documents`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success(`${file.name} 已上传，正在建索引`)
    load()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    uploading.value = false
  }
}

async function reindex(row) {
  try {
    await api.post(`/documents/${row.id}/reindex`)
    ElMessage.success('已加入重建队列')
    load()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除「${row.filename}」及其索引？`, '确认删除', { type: 'warning' })
    await api.delete(`/documents/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(errorMessage(e))
  }
}

async function download(row) {
  const token = localStorage.getItem('token')
  const resp = await fetch(`/api/v1/documents/${row.id}/download`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!resp.ok) return ElMessage.error('下载失败')
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = row.filename
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<style scoped>
.head-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.upload-card { padding: 16px; margin-bottom: 16px; }
.upload-card :deep(.el-upload), .upload-card :deep(.el-upload-dragger) { width: 100%; }
.upload-card :deep(.el-upload-dragger) {
  background: var(--surface-2); border: 1.5px dashed var(--border); border-radius: 12px; padding: 26px;
}
.upload-card :deep(.el-upload-dragger:hover) { border-color: var(--primary); }
.drop { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.drop-icon { color: var(--primary); }
.drop-title { font-size: 14px; font-weight: 550; }
.drop-sub { font-size: 12px; color: var(--muted); }
.table-card { padding: 6px 8px 8px; }
.table-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; }
.table-title { font-weight: 600; font-size: 14px; }
.err-icon { color: var(--danger); margin-right: 6px; vertical-align: middle; }
</style>

