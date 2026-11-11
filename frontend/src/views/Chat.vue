<template>
  <div class="chat-page">
    <div class="toolbar card">
      <el-select v-model="kbId" placeholder="选择知识库" style="width: 220px" @change="onKbChange">
        <el-option v-for="kb in kbs" :key="kb.id" :label="`${kb.name}（${kb.doc_count} 篇）`" :value="kb.id" />
      </el-select>

      <el-select
        v-model="conversationId"
        placeholder="历史对话"
        clearable
        style="width: 220px"
        @change="loadConversation"
      >
        <el-option v-for="c in conversations" :key="c.id" :label="c.title" :value="c.id" />
      </el-select>

      <div class="spacer"></div>
      <el-tooltip content="打开后显示答案出处（默认隐藏，保持界面清爽）" placement="top">
        <span class="switch-wrap">
          <el-switch v-model="showSources" size="small" @change="toggleSources" />
          <span class="switch-label">引用来源</span>
        </span>
      </el-tooltip>
      <el-button :icon="Plus" @click="newChat">新对话</el-button>
      <el-tag v-if="kbReady" type="success" effect="light" round size="small">知识库就绪</el-tag>
    </div>

    <div ref="listRef" class="messages scroll-y">
      <div v-if="!messages.length" class="empty">
        <div class="empty-icon"><el-icon :size="30"><ChatDotRound /></el-icon></div>
        <div class="empty-title">问点什么，答案只来自你的文档</div>
        <div class="empty-sub">{{ showSources ? '每个回答都会标注出自哪份文件、第几页' : '需要核对出处时，打开右上角「引用来源」' }}</div>
        <div class="samples">
          <div v-for="q in samples" :key="q" class="sample" @click="ask(q)">{{ q }}</div>
        </div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div v-if="m.role === 'user'" class="row right">
          <div class="bubble-user">{{ m.content }}</div>
          <div class="avatar user">{{ userInitial }}</div>
        </div>

        <div v-else class="row">
          <div class="avatar ai">知</div>
          <div class="ai-wrap">
            <div class="bubble-ai" v-html="render(m.content, showSources) || (m.pending ? '<span class=&quot;typing&quot;>思考中…</span>' : '')"></div>

            <div v-if="showSources && m.sources?.length" class="sources">
              <div class="sources-head" @click="toggleExpand(m)">
                <el-icon><Document /></el-icon>
                <span>引用来源 · {{ m.sources.length }} 条</span>
                <span class="src-toggle">{{ m.expanded ? '收起' : '展开' }}</span>
              </div>
              <div v-if="m.expanded" class="source-list">
                <div v-for="s in m.sources.slice(0, m.showAll ? m.sources.length : 3)" :key="s.index" class="source-card">
                  <div class="src-title">[{{ s.index }}] {{ s.filename }} · {{ s.sheet ? `工作表 ${s.sheet}` : `第 ${s.page} 页` }}</div>
                  <div class="src-body">{{ s.snippet }}</div>
                </div>
                <el-button
                  v-if="!m.showAll && m.sources.length > 3"
                  text
                  size="small"
                  class="more"
                  @click="m.showAll = true"
                >
                  展开全部 {{ m.sources.length }} 条
                </el-button>
              </div>
            </div>

            <div v-if="!m.pending && m.content" class="msg-actions">
              <el-tooltip content="有帮助" placement="top">
                <el-button text size="small" @click="feedback(m, 1)"><el-icon><Select /></el-icon></el-button>
              </el-tooltip>
              <el-tooltip content="没帮助" placement="top">
                <el-button text size="small" @click="feedback(m, -1)"><el-icon><CloseBold /></el-icon></el-button>
              </el-tooltip>
              <el-button text size="small" @click="copy(m.content)"><el-icon><CopyDocument /></el-icon></el-button>
              <span v-if="m.latency_ms" class="meta">{{ (m.latency_ms / 1000).toFixed(1) }}s</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="composer card">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        resize="none"
        :disabled="!kbId"
        :placeholder="kbId ? '输入问题，Enter 发送，Shift+Enter 换行' : '请先选择或创建一个知识库'"
        @keydown.enter.exact.prevent="send"
      />
      <div class="composer-actions">
        <span class="hint">答案仅基于所选知识库 · 温度 0.1</span>
        <el-button type="primary" :loading="loading" :disabled="!canSend" @click="send">
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import api, { errorMessage, streamChat } from '../api'

const props = defineProps({ kbs: { type: Array, default: () => [] } })

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const kbId = ref(null)
const conversationId = ref(null)
const conversations = ref([])
const messages = ref([])
const input = ref('')
const loading = ref(false)
const listRef = ref(null)
const user = JSON.parse(localStorage.getItem('user') || '{}')
const userInitial = (user.display_name || user.username || '?').slice(0, 1)

const samples = ['年假有几天？', '报销流程是什么？', '加班怎么算？', '试用期多久？']
const kbReady = computed(() => !!kbId.value)
const canSend = computed(() => !loading.value && input.value.trim() && kbId.value)

// 引用来源默认隐藏：答案区保持干净；需要核对出处时再打开
const showSources = ref(localStorage.getItem('showSources') === '1')

function toggleSources(val) {
  localStorage.setItem('showSources', val ? '1' : '0')
}

function toggleExpand(m) {
  m.expanded = !m.expanded
}

function render(text, withCite = false) {
  if (!text) return ''
  let html = md.render(text)
  if (withCite) {
    html = html.replace(/\[(\d+)\]/g, '<span class="cite">$1</span>')
  } else {
    // 不显示引用时把 [1] 这类角标去掉，否则句子像被切断
    html = html.replace(/\s*\[\d+\]/g, '')
  }
  return html
}

function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

async function loadConversations() {
  if (!kbId.value) return
  try {
    const { data } = await api.get('/conversations', { params: { kb_id: kbId.value } })
    conversations.value = data
  } catch {
    conversations.value = []
  }
}

async function loadConversation(id) {
  if (!id) {
    messages.value = []
    return
  }
  try {
    const { data } = await api.get(`/conversations/${id}/messages`)
    messages.value = data.map((m) => ({ ...m, pending: false, expanded: false, showAll: false }))
    scrollToBottom()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

function onKbChange() {
  conversationId.value = null
  messages.value = []
  loadConversations()
}

function newChat() {
  conversationId.value = null
  messages.value = []
  input.value = ''
}

function ask(q) {
  input.value = q
  send()
}

async function send() {
  if (!canSend.value) return
  const question = input.value.trim()
  input.value = ''
  messages.value.push({ role: 'user', content: question })
  const assistant = { role: 'assistant', content: '', sources: [], pending: true, expanded: false, showAll: false }
  messages.value.push(assistant)
  loading.value = true
  scrollToBottom()

  try {
    const stream = await streamChat({
      kb_id: kbId.value,
      question,
      conversation_id: conversationId.value
    })
    for await (const { event, data } of stream) {
      if (event === 'sources') {
        assistant.sources = data || []
      } else if (event === 'token') {
        assistant.content += data.t || ''
        scrollToBottom()
      } else if (event === 'done') {
        assistant.message_id = data.message_id
        assistant.latency_ms = data.latency_ms
        if (!conversationId.value) conversationId.value = data.conversation_id
      } else if (event === 'error') {
        assistant.content += `\n\n> 出错了：${data.message}`
      }
    }
  } catch (e) {
    assistant.content += `\n\n> 出错了：${errorMessage(e)}`
  } finally {
    assistant.pending = false
    loading.value = false
    scrollToBottom()
    loadConversations()
  }
}

async function feedback(m, rating) {
  if (!m.message_id) return
  try {
    await api.post('/chat/feedback', { message_id: m.message_id, rating, reason: '' })
    ElMessage.success(rating > 0 ? '已记录：有帮助' : '已记录：待改进')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('浏览器不支持复制')
  }
}

onMounted(() => {
  if (props.kbs.length) {
    kbId.value = props.kbs[0].id
    loadConversations()
  }
})
</script>

<style scoped>
.chat-page { height: 100%; display: flex; flex-direction: column; gap: 14px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
.spacer { flex: 1; }

.messages { flex: 1; min-height: 0; padding: 6px 2px 10px; }
.empty { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; }
.empty-icon {
  width: 62px; height: 62px; border-radius: 18px; display: grid; place-items: center;
  background: var(--primary-soft); color: var(--primary); margin-bottom: 6px;
}
.empty-title { font-size: 17px; font-weight: 650; }
.empty-sub { color: var(--muted); font-size: 13px; }
.samples { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; justify-content: center; max-width: 560px; }
.sample {
  border: 1px solid var(--border); background: var(--surface); border-radius: 999px;
  padding: 7px 14px; font-size: 12.5px; cursor: pointer; color: var(--muted);
  transition: all 0.15s;
}
.sample:hover { border-color: var(--primary); color: var(--primary); }

.msg { margin: 14px 0; }
.row { display: flex; gap: 10px; align-items: flex-start; }
.row.right { justify-content: flex-end; }
.avatar {
  width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
  font-size: 12px; font-weight: 700; flex: 0 0 30px;
}
.avatar.user { background: var(--primary-soft); color: var(--primary); }
.avatar.ai { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }

.ai-wrap { max-width: 800px; }
.sources { margin-top: 10px; }
.switch-wrap { display: inline-flex; align-items: center; gap: 6px; }
.switch-label { font-size: 12.5px; color: var(--muted); user-select: none; }
.sources-head {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--muted); margin-bottom: 6px;
  cursor: pointer; user-select: none;
}
.sources-head:hover { color: var(--primary); }
.src-toggle { margin-left: auto; font-size: 11.5px; color: var(--primary); }
.more { margin-top: 6px; }
.source-list { display: grid; gap: 6px; }
.msg-actions { display: flex; align-items: center; gap: 2px; margin-top: 4px; opacity: 0.75; }
.meta { font-size: 11px; color: var(--muted); margin-left: 6px; }

.composer { padding: 12px 14px; }
.composer :deep(.el-textarea__inner) { background: transparent; box-shadow: none; padding: 4px 6px; font-size: 14px; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
.hint { font-size: 11.5px; color: var(--muted); }
.typing { color: var(--muted); }
</style>


