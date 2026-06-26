// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createApp } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

vi.mock('@/stores/chat')
vi.mock('@/stores/user')
vi.mock('@/api/client')

const mockRoute: { params: Record<string, string>; query: Record<string, string | undefined> } = { params: {}, query: { novelId: 'n1', characterId: 'c1' } }
const mockRouter = { push: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => mockRouter,
}))

function createTestPinia() {
  const app = createApp({})
  const pinia = createPinia()
  app.use(pinia)
  setActivePinia(pinia)
  return pinia
}

function mockDefaultStore() {
  return {
    messages: [],
    isTyping: false,
    isThinking: false,
    isRetrieving: false,
    isMemorizing: false,
    streamingContent: '',
    error: null,
    clearError: vi.fn(),
    activeChatId: null,
    activeCharacterId: 'c1',
    characters: [
      { id: 'c1', name: '林清雪', identity: '元婴修士', accent_color: '#7A9A7E' },
    ],
    chatHistory: [],
    fetchChatHistory: vi.fn(),
    fetchCharacters: vi.fn(),
    fetchMessages: vi.fn(),
    initSession: vi.fn(),
    sendMessage: vi.fn(),
    abort: vi.fn(),
    reset: vi.fn(),
    removeChat: vi.fn(),
    removeChar: vi.fn(),
  } as unknown as ReturnType<typeof useChatStore>
}

describe('ChatPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRoute.query = { novelId: 'n1', characterId: 'c1' }
  })

  it('渲染新对话就绪状态——显示"开始新对话"按钮', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)

    const store = mockDefaultStore()
    vi.mocked(useChatStore).mockReturnValue(store)

    const { default: ChatPage } = await import('../ChatPage.vue')
    const wrapper = mount(ChatPage, {
      global: {
        stubs: {
          CharacterHeader: true,
          ChatWindow: true,
          ChatInput: true,
          ChatHistory: true,
          MemoryPanel: true,
          Teleport: true,
        },
      },
    })
    expect(wrapper.text()).toContain('开始新对话')
  })

  it('渲染对话展示中状态——显示 ChatWindow', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)

    const store = mockDefaultStore()
    store.activeChatId = 'chat1'
    vi.mocked(useChatStore).mockReturnValue(store)

    const { default: ChatPage } = await import('../ChatPage.vue')
    const wrapper = mount(ChatPage, {
      global: {
        stubs: {
          CharacterHeader: true,
          ChatWindow: true,
          ChatInput: true,
          ChatHistory: true,
          MemoryPanel: true,
          Teleport: true,
        },
      },
    })
    expect(wrapper.findComponent({ name: 'ChatWindow' }).exists()).toBe(true)
  })

  it('点击"开始新对话"调用 initSession 并传入 onSessionCreated 回调', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)

    const store = mockDefaultStore()
    vi.mocked(useChatStore).mockReturnValue(store)

    const { default: ChatPage } = await import('../ChatPage.vue')
    const wrapper = mount(ChatPage, {
      global: {
        stubs: {
          CharacterHeader: true,
          ChatWindow: true,
          ChatInput: true,
          ChatHistory: true,
          MemoryPanel: true,
          Teleport: true,
        },
      },
    })

    const btns = wrapper.findAll('button')
    const btn = btns.find(b => b.text().includes('开始新对话'))
    await btn!.trigger('click')

    expect(store.initSession).toHaveBeenCalledWith('n1', 'c1', expect.any(Function), undefined, expect.any(Function))
  })

  it('sendMessage 传入 onDone 回调', async () => {
    createTestPinia()
    vi.mocked(useUserStore).mockReturnValue({
      userId: 'u1', isLoggedIn: true,
    } as unknown as ReturnType<typeof useUserStore>)

    const store = mockDefaultStore()
    store.activeChatId = 'chat1'
    store.activeCharacterId = 'c1'
    vi.mocked(useChatStore).mockReturnValue(store)

    mockRoute.query = { novelId: 'n1', characterId: 'c1', chatId: 'chat1' }

    const { default: ChatPage } = await import('../ChatPage.vue')
    const wrapper = mount(ChatPage, {
      global: {
        stubs: {
          CharacterHeader: true,
          ChatWindow: true,
          ChatInput: true,
          ChatHistory: true,
          MemoryPanel: true,
          Teleport: true,
        },
      },
    })

    const chatInput = wrapper.findComponent({ name: 'ChatInput' })
    await chatInput.vm.$emit('send', '你好')

    expect(store.sendMessage).toHaveBeenCalledWith('n1', 'c1', '你好', expect.any(Function))
  })
})
