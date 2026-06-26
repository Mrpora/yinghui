// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { useUserStore } from '@/stores/user'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'

vi.mock('@/stores/user')
vi.mock('@/stores/novel')
vi.mock('@/stores/chat')
vi.mock('@/api/client')

function createTestPinia() {
  const app = createApp({})
  const pinia = createPinia()
  app.use(pinia)
  setActivePinia(pinia)
  return pinia
}

async function createTestRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', component: { template: '<div>login</div>' } },
      { path: '/settings', component: { template: '<div>settings</div>' } },
    ],
  })
  router.push('/settings')
  await router.isReady()
  return router
}

describe('SettingsPage', () => {
  it('renders page title', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)
    vi.mocked(useNovelStore).mockReturnValue({
      novels: [], fetchNovels: vi.fn(),
    } as unknown as ReturnType<typeof useNovelStore>)
    vi.mocked(useChatStore).mockReturnValue({
      characters: [], fetchCharacters: vi.fn(),
    } as unknown as ReturnType<typeof useChatStore>)

    const router = await createTestRouter()
    const { default: SettingsPage } = await import('../SettingsPage.vue')
    const wrapper = mount(SettingsPage, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('关怀设置')
  })
})
