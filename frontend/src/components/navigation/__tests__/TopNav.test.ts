// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import TopNav from '../TopNav.vue'
import { useUserStore } from '@/stores/user'
import { useEvolutionStore } from '@/stores/evolution'

vi.mock('@/stores/user')
vi.mock('@/stores/evolution')

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
      { path: '/worlds', component: { template: '<div>worlds</div>' } },
      { path: '/evolution', component: { template: '<div>evolution</div>' } },
      { path: '/novels', component: { template: '<div>novels</div>' } },
      { path: '/chat', component: { template: '<div>chat</div>' } },
      { path: '/memories', component: { template: '<div>memories</div>' } },
    ],
  })
  router.push('/worlds')
  await router.isReady()
  return router
}

describe('TopNav', () => {
  it('renders all 5 navigation labels', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', nickname: 'tester', logout: vi.fn(),
    } as unknown as ReturnType<typeof useUserStore>)
    vi.mocked(useEvolutionStore).mockReturnValue({
      currentEvolutionId: null,
    } as unknown as ReturnType<typeof useEvolutionStore>)

    const router = await createTestRouter()
    const wrapper = mount(TopNav, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('世界')
    expect(wrapper.text()).toContain('演化')
    expect(wrapper.text()).toContain('小说')
    expect(wrapper.text()).toContain('对话')
    expect(wrapper.text()).toContain('记忆')
  })

  it('shows user nickname', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', nickname: 'tester', logout: vi.fn(),
    } as unknown as ReturnType<typeof useUserStore>)
    vi.mocked(useEvolutionStore).mockReturnValue({
      currentEvolutionId: null,
    } as unknown as ReturnType<typeof useEvolutionStore>)

    const router = await createTestRouter()
    const wrapper = mount(TopNav, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('tester')
  })

  it('hides responsive panel buttons on wide screens (class lg:hidden)', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', nickname: 'tester', logout: vi.fn(),
    } as unknown as ReturnType<typeof useUserStore>)
    vi.mocked(useEvolutionStore).mockReturnValue({
      currentEvolutionId: null,
    } as unknown as ReturnType<typeof useEvolutionStore>)

    const router = await createTestRouter()
    const wrapper = mount(TopNav, {
      global: { plugins: [router] },
    })
    const panelButtons = wrapper.findAll('button').filter(b => b.text() === '世界' || b.text() === '角色')
    for (const btn of panelButtons) {
      expect(btn.classes()).toContain('lg:hidden')
    }
  })
})
