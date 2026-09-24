import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'
import { t } from '@/i18n'

const APP_NAME = 'Novel AI Translation'

const PAGE_TITLES: Record<string, string> = {
  dashboard: 'dashboard',
  novels: 'novels',
  'novel-detail': 'novel',
  'chapter-reader': 'chapter',
  sources: 'sources',
  translate: 'translate',
  jobs: 'jobs',
  settings: 'settings'
}

export function pageTitle(route: RouteLocationNormalized): string {
  return t(PAGE_TITLES[String(route.name ?? '')] ?? 'page')
}

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 }
  },
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
    { path: '/novels', name: 'novels', component: () => import('@/views/NovelListView.vue') },
    {
      path: '/novels/:name',
      name: 'novel-detail',
      component: () => import('@/views/NovelDetailView.vue'),
      props: true
    },
    {
      path: '/novels/:name/chapters/:chapter(\\d+)',
      name: 'chapter-reader',
      component: () => import('@/views/ChapterView.vue'),
      props: (route) => ({
        name: route.params.name,
        chapter: Number(route.params.chapter)
      })
    },
    { path: '/sources', name: 'sources', component: () => import('@/views/SourcesView.vue') },
    { path: '/translate', name: 'translate', component: () => import('@/views/TranslateView.vue') },
    { path: '/jobs', name: 'jobs', component: () => import('@/views/JobListView.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})


router.afterEach((to) => {
  document.title = `${pageTitle(to)} — ${APP_NAME}`
})
