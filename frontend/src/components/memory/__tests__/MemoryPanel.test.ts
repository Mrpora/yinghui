// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { listMemories, deleteMemory, updateMemoryExpiry } from '@/api/client'
import { useUserStore } from '@/stores/user'

vi.mock('@/api/client')
vi.mock('@/stores/user')

function createTestPinia() {
  const app = createApp({})
  const pinia = createPinia()
  app.use(pinia)
  setActivePinia(pinia)
  return pinia
}

describe('MemoryPanel', () => {
  it('renders loading state initially', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({ userId: 'u1', nickname: 'test' } as ReturnType<typeof useUserStore>)
    vi.mocked(listMemories).mockReturnValue(new Promise(() => {}))

    const { default: MemoryPanel } = await import('../MemoryPanel.vue')
    const wrapper = mount(MemoryPanel, { props: { novelId: 'n1', characterId: 'c1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('加载中…')
  })

  it('renders memory list after loading', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({ userId: 'u1', nickname: 'test' } as ReturnType<typeof useUserStore>)
    vi.mocked(listMemories).mockResolvedValue({
      memories: [
        {
          id: 'm1',
          character_name: '林清雪',
          memory_type: 'user_fact',
          content: '用户喜欢喝乌龙茶',
          created_at: 1767273600000,
          expires_at: null,
          recall_count: 3,
        },
        {
          id: 'm2',
          character_name: '墨渊',
          memory_type: 'event',
          content: '用户在山门前被拦住',
          created_at: 1767358800000,
          expires_at: 1772784000000,
          recall_count: 1,
        },
      ],
    })

    const { default: MemoryPanel } = await import('../MemoryPanel.vue')
    const wrapper = mount(MemoryPanel, { props: { novelId: 'n1', characterId: 'c1' } })
    await flushPromises()

    expect(wrapper.text()).toContain('用户喜欢喝乌龙茶')
    expect(wrapper.text()).toContain('用户在山门前被拦住')
  })

  it('shows empty state when no memories', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({ userId: 'u1', nickname: 'test' } as ReturnType<typeof useUserStore>)
    vi.mocked(listMemories).mockResolvedValue({ memories: [] })

    const { default: MemoryPanel } = await import('../MemoryPanel.vue')
    const wrapper = mount(MemoryPanel, { props: { novelId: 'n1', characterId: 'c1' } })
    await flushPromises()

    expect(wrapper.text()).toContain('暂无记忆')
  })

  it('shows forget button when memories exist', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({ userId: 'u1', nickname: 'test' } as ReturnType<typeof useUserStore>)
    vi.mocked(listMemories).mockResolvedValue({
      memories: [{
        id: 'm1',
        character_name: '林清雪',
        memory_type: 'user_fact',
        content: '用户喜欢喝乌龙茶',
        created_at: 1767273600000,
        expires_at: null,
        recall_count: 3,
      }],
    })

    const { default: MemoryPanel } = await import('../MemoryPanel.vue')
    const wrapper = mount(MemoryPanel, { props: { novelId: 'n1', characterId: 'c1' } })
    await flushPromises()

    expect(wrapper.text()).toContain('忘记我')
  })
})
