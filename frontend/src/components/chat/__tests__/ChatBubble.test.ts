// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatBubble from '../ChatBubble.vue'

const baseMsg = {
  role: 'character' as const,
  content: '你好',
  timestamp: 1735689600000,
  round: 1,
}

const accent = '#7A9A7E'
const name = '林黛玉'

describe('ChatBubble', () => {
  it('renders user message with right alignment', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        msg: { ...baseMsg, role: 'user', content: '你好' },
        accentColor: accent,
        characterName: name,
      },
    })
    expect(wrapper.text()).toContain('你好')
    // 现实现：用户消息右对齐由外层容器 flex-row-reverse 实现（头像翻转到右侧）
    expect(wrapper.find('.flex-row-reverse').exists()).toBe(true)
  })

  it('renders character message with left alignment', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        msg: { ...baseMsg, role: 'character', content: '你好呀（微笑）' },
        accentColor: accent,
        characterName: name,
      },
    })
    expect(wrapper.text()).toContain('你好呀')
    expect(wrapper.text()).toContain('（微笑）')
  })

  it('shows first character of characterName in avatar', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        msg: { ...baseMsg, role: 'character', content: '你好' },
        accentColor: accent,
        characterName: '林黛玉',
      },
    })
    expect(wrapper.text()).toContain('林')
  })

  it('shows 你 for user avatar', () => {
    const wrapper = mount(ChatBubble, {
      props: {
        msg: { ...baseMsg, role: 'user', content: '你好' },
        accentColor: accent,
        characterName: name,
      },
    })
    expect(wrapper.text()).toContain('你')
  })
})
