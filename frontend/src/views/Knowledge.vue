<template>
  <div>
    <div class="head-row">
      <div>
        <div class="page-title">知识库</div>
        <div class="page-sub">每个知识库是一组文档，成员按库授权</div>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建知识库</el-button>
    </div>

    <div v-if="!kbs.length" class="empty card">
      <el-icon :size="28"><Collection /></el-icon>
      <div class="empty-title">还没有知识库</div>
      <div class="page-sub">先建一个，然后上传 PDF / Word / Markdown</div>
      <el-button type="primary" style="margin-top: 14px" @click="openCreate">创建第一个知识库</el-button>
    </div>

    <div v-else class="grid kb-grid">
      <div v-for="kb in kbs" :key="kb.id" class="card kb-card">
        <div class="kb-top">
          <div class="kb-icon"><el-icon><Folder /></el-icon></div>
          <el-tag size="small" effect="plain" :type="roleType(kb.my_role)">{{ roleText(kb.my_role) }}</el-tag>
        </div>
        <div class="kb-name">{{ kb.name }}</div>
        <div class="kb-desc">{{ kb.description || '暂无描述' }}</div>
        <div class="kb-meta">
          <span><el-icon><Document /></el-icon> {{ kb.doc_count }} 篇文档</span>
        </div>
        <div class="kb-actions">
          <el-button size="small" @click="$router.push(`/kb/${kb.id}`)">打开</el-button>
          <el-button v-if="kb.my_role === 'owner'" size="small" text @click="openEdit(kb)">编辑</el-button>
          <el-button v-if="kb.my_role === 'owner'" size="small" text @click="openMembers(kb)">成员</el-button>
          <el-button v-if="kb.my_role === 'owner'" size="small" text type="danger" @click="remove(kb)">删除</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" :title="editing ? '编辑知识库' : '新建知识库'" width="440px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="64" show-word-limit placeholder="例如：人事制度" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="memberDialog" title="成员管理" width="520px">
      <div class="member-add">
        <el-select v-model="newMember.user_id" placeholder="选择用户" style="flex: 1">
          <el-option v-for="u in candidates" :key="u.id" :label="`${u.display_name || u.username}（${u.username}）`" :value="u.id" />
        </el-select>
        <el-select v-model="newMember.role" style="width: 120px">
          <el-option label="可管理" value="editor" />
          <el-option label="只读" value="viewer" />
        </el-select>
        <el-button type="primary" @click="addMember">添加</el-button>
      </div>
      <el-table :data="members" size="small" style="margin-top: 12px">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="display_name" label="姓名" />
        <el-table-column prop="role" label="角色" width="100" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button text type="danger" size="small" @click="removeMember(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorMessage } from '../api'

const props = defineProps({ kbs: { type: Array, default: () => [] } })
const emit = defineEmits(['refresh-kbs'])

const dialog = ref(false)
const editing = ref(null)
const form = ref({ name: '', description: '' })
const saving = ref(false)

const memberDialog = ref(false)
const members = ref([])
const candidates = ref([])
const newMember = ref({ user_id: null, role: 'viewer' })
const currentKb = ref(null)

function roleText(r) {
  return { owner: '所有者', editor: '可管理', viewer: '只读' }[r] || r
}
function roleType(r) {
  return { owner: 'warning', editor: 'primary', viewer: 'info' }[r] || 'info'
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '' }
  dialog.value = true
}

function openEdit(kb) {
  editing.value = kb
  form.value = { name: kb.name, description: kb.description }
  dialog.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('请输入名称')
  saving.value = true
  try {
    if (editing.value) {
      await api.patch(`/kbs/${editing.value.id}`, form.value)
      ElMessage.success('已保存')
    } else {
      await api.post('/kbs', form.value)
      ElMessage.success('已创建')
    }
    dialog.value = false
    emit('refresh-kbs')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    saving.value = false
  }
}

async function remove(kb) {
  try {
    await ElMessageBox.confirm(`删除「${kb.name}」会同时删除其所有文档与索引，确定吗？`, '确认删除', {
      type: 'warning'
    })
    await api.delete(`/kbs/${kb.id}`)
    ElMessage.success('已删除')
    emit('refresh-kbs')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(errorMessage(e))
  }
}

async function openMembers(kb) {
  currentKb.value = kb
  memberDialog.value = true
  try {
    const [m, c] = await Promise.all([api.get(`/kbs/${kb.id}/members`), api.get(`/kbs/${kb.id}/candidates`)])
    members.value = m.data
    candidates.value = c.data
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function addMember() {
  if (!newMember.value.user_id) return
  try {
    await api.post(`/kbs/${currentKb.value.id}/members`, newMember.value)
    const { data } = await api.get(`/kbs/${currentKb.value.id}/members`)
    members.value = data
    newMember.value = { user_id: null, role: 'viewer' }
    ElMessage.success('已添加')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function removeMember(row) {
  try {
    await api.delete(`/kbs/${currentKb.value.id}/members/${row.user_id}`)
    members.value = members.value.filter((m) => m.user_id !== row.user_id)
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}
</script>

<style scoped>
.head-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.kb-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.kb-card { padding: 18px; display: flex; flex-direction: column; gap: 8px; }
.kb-top { display: flex; align-items: center; justify-content: space-between; }
.kb-icon {
  width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: var(--primary-soft); color: var(--primary);
}
.kb-name { font-size: 15.5px; font-weight: 650; margin-top: 4px; }
.kb-desc { font-size: 12.5px; color: var(--muted); min-height: 34px; line-height: 1.5; }
.kb-meta { font-size: 12px; color: var(--muted); display: flex; gap: 12px; }
.kb-meta span { display: inline-flex; align-items: center; gap: 4px; }
.kb-actions { display: flex; gap: 2px; margin-top: 8px; border-top: 1px solid var(--border); padding-top: 10px; }
.empty { padding: 60px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.empty-title { font-size: 16px; font-weight: 600; }
.member-add { display: flex; gap: 8px; }
</style>
