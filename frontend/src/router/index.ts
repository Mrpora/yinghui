// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
    },
    {
      path: '/worlds',
      name: 'worlds',
      component: () => import('@/pages/WorldListPage.vue'),
    },
    {
      path: '/worlds/create',
      name: 'world-create',
      component: () => import('@/pages/CreateWorldPage.vue'),
    },
    {
      path: '/worlds/:worldId',
      name: 'world-detail',
      component: () => import('@/pages/WorldDetailPage.vue'),
      props: true,
    },
    {
      path: '/evolution',
      name: 'evolution-list',
      component: () => import('@/pages/EvolutionListPage.vue'),
    },
    {
      path: '/evolution/:evolutionId',
      name: 'evolution',
      component: () => import('@/pages/EvolutionPage.vue'),
      props: true,
    },
    {
      path: '/novels',
      name: 'novels',
      component: () => import('@/pages/NovelListPage.vue'),
    },
    {
      path: '/novels/:novelId',
      name: 'novel-detail',
      component: () => import('@/pages/NovelDetailPage.vue'),
      props: true,
    },
    {
      path: '/chat',
      name: 'chat-select',
      component: () => import('@/pages/ChatSelectPage.vue'),
    },
    {
      path: '/chat/dialogue',
      name: 'chat',
      component: () => import('@/pages/ChatPage.vue'),
    },
    {
      path: '/memories',
      name: 'memories',
      component: () => import('@/pages/MemoryPage.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/pages/SettingsPage.vue'),
    },
  ],
})

export default router
