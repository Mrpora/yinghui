// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import EvolutionControl from '../EvolutionControl.vue'
import { useEvolutionStore } from '@/stores/evolution'
import { useNovelStore } from '@/stores/novel'

vi.mock('@/stores/evolution')
vi.mock('@/stores/novel')

function createTestPinia() {
  const app = createApp({})
  const pinia = createPinia()
  app.use(pinia)
  setActivePinia(pinia)
  return pinia
}

describe('EvolutionControl', () => {
  beforeEach(() => {
    createTestPinia()
    vi.mocked(useNovelStore).mockReturnValue({
      startGeneration: vi.fn(),
    } as unknown as ReturnType<typeof useNovelStore>)
  })

  function mountControl(storeOverrides: Record<string, unknown> = {}) {
    vi.mocked(useEvolutionStore).mockReturnValue({
      currentEvolutionId: null,
      currentSession: null,
      isRunning: false,
      isPaused: false,
      pauseReason: null,
      currentRound: 0,
      maxRounds: 10,
      sendIntervene: vi.fn(),
      ...storeOverrides,
    } as unknown as ReturnType<typeof useEvolutionStore>)
    return mount(EvolutionControl, { props: { connectionStatus: 'connected' } })
  }

  it('shows "开始演化" when idle', () => {
    const wrapper = mountControl({ currentEvolutionId: null })
    expect(wrapper.text()).toContain('开始演化')
  })

  it('shows "演化中…" when running and button is disabled', () => {
    const wrapper = mountControl({ currentEvolutionId: 's1', isRunning: true })
    expect(wrapper.text()).toContain('演化中…')
    const btn = wrapper.findAll('button').find(b => b.text() === '演化中…')
    expect(btn?.attributes('disabled')).toBeDefined()
  })

  it('shows "等待决策" when paused with conflict reason', () => {
    const wrapper = mountControl({
      currentEvolutionId: 's1',
      isPaused: true,
      pauseReason: 'conflict',
      currentRound: 1,
    })
    expect(wrapper.text()).toContain('等待决策')
  })

  it('shows "选择分支" when paused with branches reason', () => {
    const wrapper = mountControl({
      currentEvolutionId: 's1',
      isPaused: true,
      pauseReason: 'branches',
      currentRound: 1,
    })
    expect(wrapper.text()).toContain('选择分支')
  })

  it('shows "继续演化" in waiting_next_round state', () => {
    const wrapper = mountControl({
      currentEvolutionId: 's1',
      currentSession: { status: 'running' },
      currentRound: 3,
      isRunning: false,
      isPaused: false,
    })
    expect(wrapper.text()).toContain('继续演化')
  })

  it('shows "重新开始" when ended', () => {
    const wrapper = mountControl({
      currentEvolutionId: 's1',
      currentSession: { status: 'ended' },
      currentRound: 5,
      isRunning: false,
      isPaused: false,
    })
    expect(wrapper.text()).toContain('重新开始')
  })

  it('shows intervene button only in waiting_next_round state', () => {
    const idleWrapper = mountControl({ currentEvolutionId: null })
    expect(idleWrapper.text()).not.toContain('干预剧情')

    const waitingWrapper = mountControl({
      currentEvolutionId: 's1',
      currentSession: { status: 'running' },
      currentRound: 2,
      isRunning: false,
      isPaused: false,
    })
    expect(waitingWrapper.text()).toContain('干预剧情')
  })

  it('shows export button when conditions met', () => {
    const wrapper = mountControl({
      currentEvolutionId: 's1',
      currentSession: { status: 'ended' },
      currentRound: 5,
      isRunning: false,
      isPaused: false,
    })
    expect(wrapper.text()).toContain('导出小说')
  })
})
