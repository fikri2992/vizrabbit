import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue') },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/pages/DashboardPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/projects/:projectId',
    name: 'project',
    component: () => import('@/pages/ProjectPage.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/projects/:projectId/images/:imageId',
    name: 'review',
    component: () => import('@/pages/ReviewPage.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    // Run-finished notifications link here. There is no per-run screen — the
    // project's Activity tab is what the reader actually wants — but the link is
    // already stored on notifications in the wild, so it has to land somewhere.
    path: '/projects/:projectId/runs/:runId',
    redirect: (to) => ({
      name: 'project',
      params: { projectId: to.params.projectId },
      query: { tab: 'activity' },
    }),
  },
  {
    // PROTOTYPE — throwaway, delete with PrototypeSlotFlowPage.vue.
    path: '/prototype/slot-flow',
    name: 'prototype-slot-flow',
    component: () => import('@/pages/PrototypeSlotFlowPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: { name: 'dashboard' },
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.resolved) await auth.fetchMe()
  if (to.meta.requiresAuth && !auth.isAuthenticated) return { name: 'login' }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'dashboard' }
  return true
})

export default router
