// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'

vi.mock('@/stores/novel')
vi.mock('@/stores/chat')

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
    routes: [{ path: '/chat', component: { template: '<div>chat</div>' } }],
  })
  router.push('/chat')
  await router.isReady()
  return router
}

describe('ChatSelectPage', () => {
  it('shows prompt when no novel selected', async () => {
    createTestPinia()
    vi.mocked(useNovelStore).mockReturnValue({
      novels: [], fetchNovels: vi.fn(),
    } as unknown as ReturnType<typeof useNovelStore>)
    vi.mocked(useChatStore).mockReturnValue({
      characters: [], fetchCharacters: vi.fn(), startChat: vi.fn(), activeChatId: null,
    } as unknown as ReturnType<typeof useChatStore>)

    const router = await createTestRouter()
    const { default: ChatSelectPage } = await import('../ChatSelectPage.vue')
    const wrapper = mount(ChatSelectPage, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('选择一部小说后查看可对话的角色')
  })
})
