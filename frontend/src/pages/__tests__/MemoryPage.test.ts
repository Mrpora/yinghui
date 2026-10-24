// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { useUserStore } from '@/stores/user'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'
import { getLatestChatNovel, listMemories } from '@/api/client'

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
      { path: '/memories', name: 'memories', component: { template: '<div>memories</div>' } },
    ],
  })
  router.push('/memories')
  await router.isReady()
  return router
}

describe('MemoryPage', () => {
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
    vi.mocked(getLatestChatNovel).mockResolvedValue({ novel_id: null })

    const router = await createTestRouter()
    const { default: MemoryPage } = await import('../MemoryPage.vue')
    const wrapper = mount(MemoryPage, {
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('角色记忆')
  })

  it('shows empty state when no character selected', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)
    vi.mocked(useNovelStore).mockReturnValue({
      novels: [{ novel_id: 'n1', title: '测试小说' }], fetchNovels: vi.fn(),
    } as unknown as ReturnType<typeof useNovelStore>)
    vi.mocked(useChatStore).mockReturnValue({
      characters: [], fetchCharacters: vi.fn(),
    } as unknown as ReturnType<typeof useChatStore>)
    vi.mocked(getLatestChatNovel).mockResolvedValue({ novel_id: 'n1' })
    vi.mocked(listMemories).mockResolvedValue({ memories: [] })

    const router = await createTestRouter()
    const { default: MemoryPage } = await import('../MemoryPage.vue')
    const wrapper = mount(MemoryPage, {
      global: { plugins: [router] },
    })
    await flushPromises()
    // 现行页面：无角色时显示小说下拉 + 空记忆占位，不出现错误横幅
    expect(wrapper.text()).toContain('测试小说')
    expect(wrapper.text()).toContain('暂无记忆')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
