// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Timeline from '../Timeline.vue'

describe('Timeline', () => {
  it('shows empty state when no events and not running', () => {
    const wrapper = mount(Timeline, {
      props: { events: [], isRunning: false },
    })
    expect(wrapper.text()).toContain('等待演化开始…')
  })

  it('hides empty state when running (events arrive via SSE)', () => {
    const wrapper = mount(Timeline, {
      props: { events: [], isRunning: true },
    })
    expect(wrapper.text()).not.toContain('等待演化开始…')
  })

  it('hides scroll button initially', () => {
    const wrapper = mount(Timeline, {
      props: {
        events: [{ id: 'e1', type: 'action', round: 1, content: 'test', timestamp: 1767225600000 }],
        isRunning: false,
      },
    })
    expect(wrapper.text()).not.toContain('新事件')
  })
})
