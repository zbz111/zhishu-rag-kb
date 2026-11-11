<template>
  <div>
    <div class="grid stats">
      <div class="card stat-card">
        <div class="label">今日提问</div>
        <div class="value">{{ stats.questions_today }}</div>
        <div class="hint">累计 {{ stats.messages }} 条消息</div>
      </div>
      <div class="card stat-card">
        <div class="label">今日 Token</div>
        <div class="value">{{ stats.tokens_today }}</div>
        <div class="hint">平均延迟 {{ (stats.avg_latency_ms / 1000).toFixed(1) }}s</div>
      </div>
      <div class="card stat-card">
        <div class="label">文档 / 分块</div>
        <div class="value">{{ stats.documents }} / {{ stats.chunks }}</div>
        <div class="hint">{{ stats.kbs }} 个知识库</div>
      </div>
      <div class="card stat-card">
        <div class="label">用户</div>
        <div class="value">{{ stats.users }}</div>
        <div class="hint">{{ stats.conversations }} 个会话</div>
      </div>
    </div>

    <div class="card panel">
      <el-tabs v-model="tab">
        <el-tab-pane label="用户管理" name="users">
          <div class="toolbar">
            <el-button type="primary" :icon="Plus" @click="userDialog = true">新建用户</el-button>
          </div>
          <el-table :data="users" size="default">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="用户名" min-width="140" />
            <el-table-column prop="display_name" label="姓名" min-width="140" />
            <el-table-column label="角色" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.role === 'admin' ? 'warning' : 'info'" effect="plain">
                  {{ row.role === 'admin' ? '管理员' : '成员' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_active ? 'success' : 'danger'" effect="light">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button text size="small" @click="toggle(row)">{{ row.is_active ? '禁用' : '启用' }}</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="审计日志" name="logs">
          <el-table :data="logs" size="small" max-height="520">
            <el-table-column prop="id" label="#" width="70" />
            <el-table-column prop="action" label="动作" width="150" />
            <el-table-column prop="target" label="对象" width="180" show-overflow-tooltip />
            <el-table-column prop="detail" label="详情" min-width="240" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="130" />
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN', { hour12: false }) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="系统状态" name="system">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="模型提供方">{{ system.llm?.provider }}</el-descriptions-item>
            <el-descriptions-item label="对话模型">{{ system.llm?.chat_model }}</el-descriptions-item>
            <el-descriptions-item label="向量模型">{{ system.embedding_model }}</el-descriptions-item>
            <el-descriptions-item label="模型服务">
              <el-tag :type="system.llm?.ok ? 'success' : 'danger'" size="small">
                {{ system.llm?.ok ? '正常' : '不可用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="分块大小">{{ system.chunk_size }}</el-descriptions-item>
            <el-descriptions-item label="Top-K">{{ system.top_k }}</el-descriptions-item>
            <el-descriptions-item label="混合检索">{{ system.hybrid ? '开启' : '关闭' }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ system.version }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="userDialog" title="新建用户" width="420px">
      <el-form label-position="top">
        <el-form-item label="用户名（登录用，英文）">
          <el-input v-model="newUser.username" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="newUser.display_name" />
        </el-form-item>
        <el-form-item label="初始密码">
          <el-input v-model="newUser.password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUser.role" style="width: 100%">
            <el-option label="普通成员" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" @click="createUser">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { errorMessage } from '../api'

const tab = ref('users')
const stats = ref({ questions_today: 0, tokens_today: 0, avg_latency_ms: 0, documents: 0, chunks: 0, kbs: 0, users: 0, conversations: 0, messages: 0 })
const users = ref([])
const logs = ref([])
const system = ref({})
const userDialog = ref(false)
const newUser = ref({ username: '', display_name: '', password: '', role: 'user' })

async function load() {
  try {
    const [s, u, l, sys] = await Promise.all([
      api.get('/admin/stats'),
      api.get('/admin/users'),
      api.get('/admin/logs', { params: { limit: 100 } }),
      api.get('/admin/system')
    ])
    stats.value = s.data
    users.value = u.data
    logs.value = l.data
    system.value = sys.data
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function createUser() {
  if (!newUser.value.username || !newUser.value.password) return ElMessage.warning('请填写用户名和密码')
  try {
    await api.post('/admin/users', newUser.value)
    ElMessage.success('已创建')
    userDialog.value = false
    newUser.value = { username: '', display_name: '', password: '', role: 'user' }
    load()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function toggle(row) {
  try {
    await api.patch(`/admin/users/${row.id}?is_active=${!row.is_active}`)
    row.is_active = !row.is_active
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

onMounted(load)
</script>

<style scoped>
.stats { grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-bottom: 18px; }
.panel { padding: 8px 18px 18px; }
.toolbar { margin-bottom: 10px; }
</style>
