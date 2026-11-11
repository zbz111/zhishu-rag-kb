<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="logo">知</div>
        <div>
          <div class="brand-name">知源</div>
          <div class="brand-sub">企业知识库</div>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in menus"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="kb-block">
        <div class="kb-title">
          <span>知识库</span>
          <el-tooltip content="新建知识库" placement="top">
            <el-icon class="kb-add" @click="$router.push('/knowledge')"><Plus /></el-icon>
          </el-tooltip>
        </div>
        <div class="kb-list scroll-y">
          <div
            v-for="kb in kbs"
            :key="kb.id"
            class="kb-item"
            :class="{ active: route.params.id === String(kb.id) }"
            @click="$router.push(`/kb/${kb.id}`)"
          >
            <el-icon><Folder /></el-icon>
            <span class="kb-name">{{ kb.name }}</span>
            <span class="kb-count">{{ kb.doc_count }}</span>
          </div>
          <div v-if="!kbs.length" class="kb-empty">还没有知识库</div>
        </div>
      </div>

      <div class="user-box">
        <div class="avatar">{{ initials }}</div>
        <div class="user-meta">
          <div class="user-name">{{ user.display_name || user.username }}</div>
          <div class="user-role">{{ user.role === 'admin' ? '管理员' : '成员' }}</div>
        </div>
        <el-dropdown trigger="click" @command="onCommand">
          <el-icon class="user-more"><MoreFilled /></el-icon>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="settings">个人设置</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <h1 class="page-title">{{ route.meta.title || '工作台' }}</h1>
          <div class="page-sub">{{ subtitle }}</div>
        </div>
        <div class="topbar-actions">
          <el-tooltip :content="isDark ? '切换浅色' : '切换深色'" placement="bottom">
            <el-button circle text @click="toggleTheme">
              <el-icon><Moon v-if="!isDark" /><Sunny v-else /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tag size="small" effect="plain" round>v1.0</el-tag>
        </div>
      </header>

      <section class="content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" :kbs="kbs" @refresh-kbs="loadKbs" />
          </transition>
        </router-view>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

const user = ref(JSON.parse(localStorage.getItem('user') || '{}'))
const kbs = ref([])
const isDark = ref(document.documentElement.classList.contains('dark'))

const menus = computed(() => {
  const base = [
    { path: '/chat', label: '智能问答', icon: 'ChatDotRound' },
    { path: '/knowledge', label: '知识库', icon: 'Collection' }
  ]
  if (user.value.role === 'admin') base.push({ path: '/admin', label: '管理后台', icon: 'DataAnalysis' })
  return base
})

const initials = computed(() => (user.value.display_name || user.value.username || '?').slice(0, 1).toUpperCase())

const subtitle = computed(() => {
  if (route.path.startsWith('/kb/')) return '上传文档、查看索引状态'
  if (route.path === '/chat') return '基于你的知识库回答，答案可溯源'
  if (route.path === '/admin') return '用户、用量与审计日志'
  return '私有化部署的文档问答系统'
})

function isActive(path) {
  return route.path === path || route.path.startsWith(path + '/')
}

function toggleTheme() {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

async function loadKbs() {
  try {
    const { data } = await api.get('/kbs')
    kbs.value = data
  } catch {
    kbs.value = []
  }
}

function onCommand(cmd) {
  if (cmd === 'logout') {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    router.push('/login')
  } else if (cmd === 'settings') {
    router.push('/settings')
  }
}

watch(() => route.path, () => loadKbs())
onMounted(loadKbs)
</script>

<style scoped>
.shell { display: flex; height: 100vh; overflow: hidden; }

.sidebar {
  width: 252px;
  flex: 0 0 252px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 18px 14px 14px;
}

.brand { display: flex; align-items: center; gap: 10px; padding: 2px 8px 18px; }
.logo {
  width: 34px; height: 34px; border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff; display: grid; place-items: center;
  font-weight: 700; font-size: 17px;
  box-shadow: 0 6px 14px rgba(99, 102, 241, 0.35);
}
.brand-name { font-weight: 700; font-size: 15px; letter-spacing: 0.4px; }
.brand-sub { font-size: 11px; color: var(--muted); margin-top: 1px; }

.nav { display: flex; flex-direction: column; gap: 4px; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 10px;
  color: var(--muted); font-size: 13.5px; font-weight: 500;
  transition: all 0.15s ease;
}
.nav-item:hover { background: var(--surface-2); color: var(--text); }
.nav-item.active { background: var(--primary-soft); color: var(--primary); font-weight: 600; }

.kb-block { margin-top: 22px; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.kb-title {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; letter-spacing: 0.8px; text-transform: uppercase;
  color: var(--muted); padding: 0 10px 8px; font-weight: 600;
}
.kb-add { cursor: pointer; font-size: 14px; }
.kb-add:hover { color: var(--primary); }
.kb-list { flex: 1; overflow-y: auto; }
.kb-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: 9px; cursor: pointer;
  font-size: 13px; color: var(--text); transition: background 0.15s;
}
.kb-item:hover { background: var(--surface-2); }
.kb-item.active { background: var(--primary-soft); color: var(--primary); }
.kb-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-count { font-size: 11px; color: var(--muted); background: var(--surface-2); padding: 1px 6px; border-radius: 20px; }
.kb-empty { font-size: 12px; color: var(--muted); padding: 8px 10px; }

.user-box {
  display: flex; align-items: center; gap: 10px;
  border-top: 1px solid var(--border); padding: 12px 6px 2px; margin-top: 10px;
}
.avatar {
  width: 32px; height: 32px; border-radius: 9px;
  background: var(--primary-soft); color: var(--primary);
  display: grid; place-items: center; font-weight: 700; font-size: 13px;
}
.user-meta { flex: 1; min-width: 0; }
.user-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-role { font-size: 11px; color: var(--muted); }
.user-more { cursor: pointer; color: var(--muted); }

.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar {
  height: 68px; flex: 0 0 68px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 26px; border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter: blur(8px);
}
.topbar-actions { display: flex; align-items: center; gap: 10px; }
.content { flex: 1; min-height: 0; padding: 22px 26px; overflow: auto; }
</style>
