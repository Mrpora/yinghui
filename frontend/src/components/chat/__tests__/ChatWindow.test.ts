// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatWindow from '../ChatWindow.vue'

const baseProps = {
  isTyping: false,
  isThinking: false,
  isRetrieving: false,
  isMemorizing: false,
  streamingContent: '',
  characterName: '林黛玉',
  accentColor: '#7A9A7E',
}

describe('ChatWindow', () => {
  it('renders messages', () => {
    const wrapper = mount(ChatWindow, {
      props: {
        ...baseProps,
        messages: [{ role: 'user', content: '你好', timestamp: 1735689600000, round: 1 }],
      },
    })
    expect(wrapper.text()).toContain('你好')
  })

  it('shows empty state when no messages and not streaming', () => {
    const wrapper = mount(ChatWindow, {
      props: { ...baseProps, messages: [] },
    })
    expect(wrapper.text()).toContain('开始对话吧')
  })

  it('shows streaming placeholder when thinking', () => {
    const wrapper = mount(ChatWindow, {
      props: {
        ...baseProps,
        messages: [{ role: 'character', content: '...', timestamp: 1735689600000, round: 1 }],
        isTyping: true,
        isThinking: true,
      },
    })
    expect(wrapper.text()).toContain('凝神欲语')
  })

  it('shows 思绪万千 when thinking', () => {
    const wrapper = mount(ChatWindow, {
      props: {
        ...baseProps,
        messages: [],
        isTyping: true,
        isThinking: true,
      },
    })
    expect(wrapper.text()).toContain('思绪万千')
  })
})
