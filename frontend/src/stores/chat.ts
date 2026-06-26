// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatCharacter, ChatHistoryItem, Message } from '@/types'
import { listChatCharacters, getChatMessages, listChatHistory, deleteChat, removeCharacter, chatSSE } from '@/api/client'
import { useUserStore } from './user'

export const useChatStore = defineStore('chat', () => {
  const characters = ref<ChatCharacter[]>([])
  const messages = ref<Message[]>([])
  const activeChatId = ref<string | null>(null)
  const activeCharacterId = ref<string | null>(null)
  const isTyping = ref(false)
  const isThinking = ref(false)
  const isRetrieving = ref(false)
  const isMemorizing = ref(false)
  const error = ref<string | null>(null)
  const streamingContent = ref('')
  const chatHistory = ref<ChatHistoryItem[]>([])

  let abortController: AbortController | null = null

  // ── 对话历史 ──

  async function fetchChatHistory(novelId: string, characterId?: string) {
    const user = useUserStore()
    if (!user.userId) return
    const res = await listChatHistory(user.userId, novelId, characterId)
    chatHistory.value = res.chats
  }

  // ── 角色 ──

  async function fetchCharacters(novelId: string) {
    const user = useUserStore()
    const res = await listChatCharacters(user.userId, novelId)
    characters.value = res.characters
  }

  async function fetchMessages(chatId: string) {
    messages.value = []
    const res = await getChatMessages(chatId)
    messages.value = res.messages.map((m, i) => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp ?? Date.now(),
      round: i + 1,
    }))
    activeChatId.value = chatId
  }

  // ── 对话 SSE ──

  function initSession(
    novelId: string,
    characterId: string,
    onSessionCreated?: (chatId: string) => void,
    chatId?: string,
    onDone?: () => void,
  ) {
    const user = useUserStore()
    if (!user.userId) {
      error.value = '未找到用户 ID，请返回首页重新进入'
      return
    }

    activeCharacterId.value = characterId
    isTyping.value = true
    isThinking.value = true
    streamingContent.value = ''
    error.value = null

    abortController?.abort()
    abortController = chatSSE(
      {
        user_id: user.userId,
        novel_id: novelId,
        character_id: characterId,
        chat_id: chatId ?? undefined,
      },
      {
        onSessionCreated(id) {
          activeChatId.value = id
          onSessionCreated?.(id)
        },
        onThinking() {
          isThinking.value = true
          isRetrieving.value = false
          isMemorizing.value = false
        },
        onRetrieving() {
          isThinking.value = false
          isRetrieving.value = true
        },
        onMemorizing() {
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = true
        },
        onToken(content) {
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          streamingContent.value += content
        },
        onDone(data) {
          const d = data as Record<string, any>
          activeChatId.value = d.chat_id
          if (d.message?.content) {
            messages.value.push(d.message)
          }
          streamingContent.value = ''
          isTyping.value = false
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          onDone?.()
        },
        onError(msg) {
          error.value = msg
          isTyping.value = false
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          streamingContent.value = ''
        },
      },
    )
  }

  function sendMessage(
    novelId: string,
    characterId: string,
    content: string,
    onDone?: () => void,
  ) {
    const user = useUserStore()
    if (!user.userId) return

    messages.value.push({
      role: 'user',
      content,
      timestamp: Date.now(),
      round: messages.value.length + 1,
    })

    isTyping.value = true
    isThinking.value = true
    streamingContent.value = ''
    error.value = null

    abortController?.abort()
    abortController = chatSSE(
      {
        user_id: user.userId,
        novel_id: novelId,
        character_id: characterId,
        chat_id: activeChatId.value ?? undefined,
        content,
      },
      {
        onSessionCreated(id) {
          activeChatId.value = id
        },
        onThinking() {
          isThinking.value = true
          isRetrieving.value = false
          isMemorizing.value = false
        },
        onRetrieving() {
          isThinking.value = false
          isRetrieving.value = true
        },
        onMemorizing() {
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = true
        },
        onToken(content) {
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          streamingContent.value += content
        },
        onDone(data) {
          const d = data as Record<string, any>
          activeChatId.value = d.chat_id
          if (d.message?.content) {
            messages.value.push(d.message)
          }
          streamingContent.value = ''
          isTyping.value = false
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          onDone?.()
        },
        onError(msg) {
          error.value = msg
          // 回滚乐观添加的用户消息
          const lastMsg = messages.value[messages.value.length - 1]
          if (lastMsg && lastMsg.role === 'user') {
            messages.value.pop()
          }
          isTyping.value = false
          isThinking.value = false
          isRetrieving.value = false
          isMemorizing.value = false
          streamingContent.value = ''
        },
      },
    )
  }

  function abort() {
    // 保存已流式输出的内容，标记中断
    if (streamingContent.value && activeChatId.value) {
      messages.value.push({
        role: 'character',
        content: streamingContent.value + '\n\n[输出中断]',
        timestamp: Date.now(),
        round: messages.value.length + 1,
      })
    }
    abortController?.abort()
    abortController = null
    isTyping.value = false
    isThinking.value = false
    isRetrieving.value = false
    isMemorizing.value = false
    streamingContent.value = ''
  }

  function reset() {
    abort()
    messages.value = []
    activeChatId.value = null
    activeCharacterId.value = null
    error.value = null
  }

  function clearError() {
    error.value = null
  }

  async function removeChat(chatId: string) {
    const user = useUserStore()
    const removed = chatHistory.value.filter(c => c.chat_id !== chatId)
    await deleteChat(chatId, user.userId)
    chatHistory.value = removed
    if (activeChatId.value === chatId) {
      activeChatId.value = null
      messages.value = []
    }
  }

  async function removeChar(novelId: string, characterId: string) {
    const user = useUserStore()
    await removeCharacter(novelId, user.userId, characterId)
    characters.value = characters.value.filter(c => c.id !== characterId)
  }

  return {
    characters, messages, activeChatId, activeCharacterId,
    isTyping, isThinking, isRetrieving, isMemorizing,
    error, streamingContent, chatHistory,
    fetchChatHistory, fetchCharacters, fetchMessages, initSession, sendMessage, abort, reset, clearError,
    removeChat, removeChar,
  }
})
