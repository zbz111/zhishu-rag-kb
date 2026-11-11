import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('./components/AppShell.vue'),
    children: [
      { path: '', redirect: '/chat' },
      { path: 'chat', component: () => import('./views/Chat.vue'), meta: { title: '智能问答' } },
      { path: 'knowledge', component: () => import('./views/Knowledge.vue'), meta: { title: '知识库' } },
      { path: 'kb/:id', component: () => import('./views/Documents.vue'), meta: { title: '文档管理' } },
      { path: 'admin', component: () => import('./views/Admin.vue'), meta: { title: '管理后台' } },
      { path: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '个人设置' } }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/chat' }
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
  if (to.path === '/login' && token) return '/chat'
  return true
})

export default router
