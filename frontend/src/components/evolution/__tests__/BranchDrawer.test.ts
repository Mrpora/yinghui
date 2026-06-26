// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BranchDrawer from '../BranchDrawer.vue'

const sampleBranches = [
  { index: 0, title: '帮助林清雪', description: '和她一起对抗敌人', reason: '她值得信任' },
  { index: 1, title: '独自行走', description: '离开这个地方', reason: '独行更安全' },
]

describe('BranchDrawer', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mountDrawer = (props: any) =>
    mount(BranchDrawer, {
      props,
      global: { stubs: { teleport: true } },
    })

  it('does not render when visible is false', () => {
    const wrapper = mountDrawer({ visible: false, branches: sampleBranches, reason: 'branches' })
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })

  it('shows unified title for any reason', () => {
    const wrapper = mountDrawer({ visible: true, branches: sampleBranches, reason: 'branches' })
    expect(wrapper.text()).toContain('剧情分歧点')
  })

  it('renders branch list', () => {
    const wrapper = mountDrawer({ visible: true, branches: sampleBranches, reason: 'branches' })
    expect(wrapper.text()).toContain('帮助林清雪')
    expect(wrapper.text()).toContain('独自行走')
  })

  it('emits select-branch when a branch card is clicked', async () => {
    const wrapper = mountDrawer({ visible: true, branches: sampleBranches, reason: 'branches' })
    const cards = wrapper.findAll('.bg-frost.border')
    await cards[0].trigger('click')
    expect(wrapper.emitted('select-branch')).toBeTruthy()
  })

  it('emits submit-custom with custom event text', async () => {
    const wrapper = mountDrawer({ visible: true, branches: sampleBranches, reason: 'branches' })
    const input = wrapper.find('input')
    await input.setValue('我的自定义决定')
    const buttons = wrapper.findAll('button')
    const submitBtn = buttons.find(b => b.text() === '提交')
    await submitBtn?.trigger('click')
    expect(wrapper.emitted('submit-custom')?.[0]).toEqual(['我的自定义决定'])
  })

  it('shows shuffle button when more than 3 branches', () => {
    const manyBranches = Array.from({ length: 5 }, (_, i) => ({
      index: i, title: `Branch ${i}`, description: '', reason: '',
    }))
    const wrapper = mountDrawer({ visible: true, branches: manyBranches, reason: 'branches' })
    expect(wrapper.text()).toContain('换一批')
  })

  it('hides shuffle button when 3 or fewer branches', () => {
    const wrapper = mountDrawer({ visible: true, branches: sampleBranches, reason: 'branches' })
    expect(wrapper.text()).not.toContain('换一批')
  })
})
