import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'

const APP_NAME = 'Novel AI Translation'

const PAGE_TITLES: Record<string, string> = {
  dashboard: 'Dashboard',
  novels: 'Novels',
  'novel-detail': 'Novel',
  crawl: 'Crawl',
  import: 'Import',
  translate: 'Translate',
  jobs: 'Jobs',
  settings: 'Settings'
}

function pageTitle(route: RouteLocationNormalized): string {
  const base = PAGE_TITLES[String(route.name ?? '')] ?? 'Page'
  if (route.name === 'novel-detail') {
    return base
  }
  return base
}

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

router.afterEach((to) => {
  document.title = `${pageTitle(to)} — ${APP_NAME}`
})
