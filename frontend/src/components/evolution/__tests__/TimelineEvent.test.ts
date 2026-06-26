// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TimelineEvent from '../TimelineEvent.vue'

const baseEvent = {
  id: 'ev1',
  type: 'action' as const,
  round: 3,
  content: '林清雪走进了茶室。',
  character: '林清雪',
  timestamp: 1767273600000,
}

describe('TimelineEvent', () => {
  it('renders action event with blue dot', () => {
    const wrapper = mount(TimelineEvent, { props: { event: baseEvent } })
    const dot = wrapper.find('.bg-blue-400')
    expect(dot.exists()).toBe(true)
    expect(wrapper.text()).toContain('行动')
    expect(wrapper.text()).toContain('林清雪走进了茶室。')
  })

  it('renders conflict event with cinnabar diamond marker', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'conflict' } },
    })
    expect(wrapper.find('.bg-cinnabar').exists()).toBe(true)
    expect(wrapper.text()).toContain('冲突')
  })

  it('renders scene_setting event with teal dot', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'scene_setting' } },
    })
    expect(wrapper.find('.bg-teal-400').exists()).toBe(true)
    expect(wrapper.text()).toContain('场景')
  })

  it('renders round 0 scene_setting as initial event with old-gold styling', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'scene_setting', round: 0, character: null as any } },
    })
    expect(wrapper.find('.bg-old-gold').exists()).toBe(true)
    expect(wrapper.text()).toContain('初始事件')
    expect(wrapper.text()).not.toContain('第 0 轮')
    expect(wrapper.text()).not.toContain('场景')
  })

  it('renders unknown event type with gray default fallback', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'unknown_type' as any } },
    })
    expect(wrapper.find('.bg-gray-400').exists()).toBe(true)
    expect(wrapper.text()).toContain('unknown_type')
  })

  it('does not crash when event.round is undefined for scene_setting', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'scene_setting', round: undefined as any } },
    })
    expect(wrapper.text()).toContain('场景')
    expect(wrapper.find('.bg-teal-400').exists()).toBe(true)
  })

  it('renders user_decision event with yellow dot', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'user_decision' } },
    })
    expect(wrapper.find('.bg-yellow-400').exists()).toBe(true)
  })

  it('renders round_summary event with green dot', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'round_summary' } },
    })
    expect(wrapper.find('.bg-green-400').exists()).toBe(true)
  })

  it('renders relationship event with purple dot', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: { ...baseEvent, type: 'relationship' } },
    })
    expect(wrapper.find('.bg-purple-400').exists()).toBe(true)
  })

  it('shows expand toggle when motive or inner_thoughts present', () => {
    const wrapper = mount(TimelineEvent, {
      props: {
        event: { ...baseEvent, motive: '想测试一下', inner_thoughts: '内心独白' },
      },
    })
    expect(wrapper.text()).toContain('查看动机与内心活动')
  })

  it('does not show toggle when no motive or inner_thoughts', () => {
    const wrapper = mount(TimelineEvent, {
      props: { event: baseEvent },
    })
    expect(wrapper.text()).not.toContain('查看动机与内心活动')
  })

  it('expands to show motive and inner_thoughts when clicked', async () => {
    const wrapper = mount(TimelineEvent, {
      props: {
        event: { ...baseEvent, motive: '想测试一下', inner_thoughts: '内心独白' },
      },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('想测试一下')
    expect(wrapper.text()).toContain('内心独白')
  })
})
