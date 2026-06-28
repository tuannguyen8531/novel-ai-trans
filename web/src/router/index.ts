import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/novels', name: 'novels', component: () => import('@/views/NovelListView.vue') },
    {
      path: '/novels/:name',
      name: 'novel-detail',
      component: () => import('@/views/NovelDetailView.vue'),
      props: true
    },
    { path: '/crawl', name: 'crawl', component: () => import('@/views/CrawlView.vue') },
    { path: '/import', name: 'import', component: () => import('@/views/ImportView.vue') },
    { path: '/translate', name: 'translate', component: () => import('@/views/TranslateView.vue') },
    { path: '/jobs', name: 'jobs', component: () => import('@/views/JobListView.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})
