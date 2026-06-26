<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div class="h-[calc(100vh-48px)] flex flex-col overflow-hidden">
    <!-- 页面标题栏 -->
    <div class="h-10 shrink-0 flex items-center px-4 border-b border-border-light bg-white/50">
      <button
        class="text-sm text-smoke hover:text-ink transition-colors flex items-center gap-1"
        @click="$router.push({ name: 'chat-select', query: { novelId } })"
      >
        ← 返回
      </button>
    </div>

    <div class="flex-1 flex overflow-hidden">
    <!-- 左侧历史对话 -->
    <ChatHistory
      :chats="chat.chatHistory"
      :active-chat-id="chat.activeChatId"
      :loading="historyLoading"
      :history-error="historyError"
      class="hidden md:flex w-1/5"
      @new-chat="handleStartNewChat"
      @select="handleSelectChat"
      @retry="handleRetryHistory"
      @delete-chat="handleDeleteChat"
    />

    <!-- 中间对话区 -->
    <div class="flex min-w-0 flex-1 flex-col relative">
      <!-- Error banner -->
      <div
        v-if="chat.error"
        class="flex items-center gap-2 px-4 py-1.5 text-xs text-white bg-cinnabar/80"
      >
        <span>{{ chat.error }}</span>
        <button class="ml-auto text-white/80 hover:text-white text-xs" @click="chat.clearError()">✕</button>
      </div>

      <!-- 窄屏汉堡菜单 -->
      <button
        class="md:hidden absolute left-3 top-3 z-10 p-1.5 rounded-lg hover:bg-frost/50 transition-colors"
        @click="showHistoryDrawer = !showHistoryDrawer"
      >
        <svg class="w-5 h-5 text-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 12h18M3 6h18M3 18h18" />
        </svg>
      </button>

      <CharacterHeader
        :name="charName"
        :identity="charIdentity"
        :accent-color="charAccentColor"
      />
      <!-- 状态一：新对话就绪 -->
      <div v-if="!chat.activeChatId" class="flex-1 flex flex-col items-center justify-center gap-4">
        <button
          class="px-8 py-4 rounded-2xl bg-old-gold text-white text-lg font-medium
                 hover:bg-old-gold/90 active:scale-[0.98] transition-all duration-200
                 font-serif shadow-lg shadow-old-gold/20
                 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="chat.isTyping"
          @click="handleStartNewChat"
        >
          <span v-if="chat.isTyping" class="flex items-center gap-2">
            <div class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            连接中...
          </span>
          <span v-else>开始新对话</span>
        </button>
        <button
          v-if="chat.error"
          class="text-sm text-cinnabar hover:text-cinnabar/80 underline underline-offset-2"
          @click="chat.clearError(); handleStartNewChat()"
        >
          重试
        </button>
      </div>

      <!-- 状态二：对话展示中 -->
      <template v-else>
        <div v-if="messagesLoading" class="flex items-center justify-center py-8">
          <div class="w-5 h-5 border-2 border-old-gold/30 border-t-old-gold rounded-full animate-spin" />
          <span class="ml-2 text-sm text-smoke">加载中...</span>
        </div>
        <template v-else>
          <ChatWindow
          :messages="chat.messages"
          :is-typing="chat.isTyping"
          :is-thinking="chat.isThinking"
          :is-retrieving="chat.isRetrieving"
          :is-memorizing="chat.isMemorizing"
          :streaming-content="chat.streamingContent"
          :character-name="charName"
          :accent-color="charAccentColor"
        />
        <div class="flex-shrink-0">
          <ChatInput
            :disabled="chat.isTyping"
            @send="handleSend"
          />
        </div>
        </template>
      </template>
    </div>

    <!-- 记忆面板（宽屏常驻） -->
    <MemoryPanel
      ref="memoryPanelRef"
      v-show="!showMemoryDrawer"
      :novel-id="novelId"
      :class="['hidden', 'md:flex', 'w-1/4', 'min-w-[240px]', 'shrink-0']"
      @forget="showMemoryDrawer = false"
    />
    </div>

    <!-- 历史面板（窄屏抽屉） -->
    <Teleport to="body">
      <div v-if="showHistoryDrawer" class="fixed inset-0 z-50 md:hidden">
        <div class="absolute inset-0 bg-ink/30" @click="showHistoryDrawer = false" />
        <div class="absolute bottom-0 left-0 top-12 w-72 bg-white shadow-xl animate-slide-right">
          <ChatHistory
            :chats="chat.chatHistory"
            :active-chat-id="chat.activeChatId"
            :loading="historyLoading"
            :history-error="historyError"
            @new-chat="handleStartNewChat(); showHistoryDrawer = false"
            @select="(id: string) => { handleSelectChat(id); showHistoryDrawer = false }"
            @retry="handleRetryHistory"
            @delete-chat="(id: string) => { handleDeleteChat(id); showHistoryDrawer = false }"
          />
        </div>
      </div>
    </Teleport>

    <!-- 记忆面板（窄屏抽屉） -->
    <Teleport to="body">
      <div v-if="showMemoryDrawer" class="fixed inset-0 z-50 md:hidden">
        <div class="absolute inset-0 bg-ink/30" @click="showMemoryDrawer = false" />
        <div class="absolute bottom-0 right-0 top-12 w-80 bg-white shadow-xl animate-slide-right">
          <button
            class="absolute left-2 top-2 z-10 text-smoke hover:text-ink"
            @click="showMemoryDrawer = false"
          >
            × 关闭
          </button>
          <MemoryPanel
            :novel-id="novelId"
            @forget="showMemoryDrawer = false"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import CharacterHeader from '@/components/chat/CharacterHeader.vue'
import ChatWindow from '@/components/chat/ChatWindow.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatHistory from '@/components/chat/ChatHistory.vue'
import MemoryPanel from '@/components/memory/MemoryPanel.vue'

const route = useRoute()
const router = useRouter()
const chat = useChatStore()

const novelId = computed(() => (route.query.novelId as string) || '')
const chatId = computed(() => (route.query.chatId as string) || null)

const showMemoryDrawer = ref(false)
const showHistoryDrawer = ref(false)
const historyLoading = ref(false)
const messagesLoading = ref(false)
const historyError = ref<string | null>(null)
const memoryPanelRef = ref<InstanceType<typeof MemoryPanel> | null>(null)

const charName = computed(() => {
  const c = chat.characters.find(c => c.id === chat.activeCharacterId)
  return c?.name || '...'
})

const charIdentity = computed(() => {
  const c = chat.characters.find(c => c.id === chat.activeCharacterId)
  return c?.identity || ''
})

const charAccentColor = computed(() => {
  const c = chat.characters.find(c => c.id === chat.activeCharacterId)
  return c?.accent_color || '#7A9A7E'
})

onMounted(async () => {
  if (!novelId.value) {
    router.replace({ name: 'chat-select' }).catch((err: any) => {
      if (err?.name !== 'NavigationDuplicated') throw err
    })
    return
  }

  historyLoading.value = true
  const initialCharId = (route.query.characterId as string) || undefined
  try {
    await chat.fetchChatHistory(novelId.value, initialCharId)
  } catch (err) {
    console.error('[ChatPage] fetchChatHistory failed:', err)
    historyError.value = '加载失败，请重试'
    // 继续加载角色（非致命错误）
  }
  try {
    await chat.fetchCharacters(novelId.value)
  } catch (err) {
    console.error('[ChatPage] fetchCharacters failed:', err)
  }
  historyLoading.value = false

  if (chatId.value) {
    const item = chat.chatHistory.find(h => h.chat_id === chatId.value)
    if (item) {
      chat.activeCharacterId = item.character_id
    }
    try {
      messagesLoading.value = true
      await chat.fetchMessages(chatId.value)
    } catch (err) {
      console.error('[ChatPage] fetchMessages failed:', err)
      chat.error = '加载对话消息失败，请重试'
    } finally {
      messagesLoading.value = false
    }
    return
  }

  const charId = route.query.characterId as string
  if (charId) {
    chat.activeCharacterId = charId
  }
})

onBeforeUnmount(() => {
  chat.reset()
})

// 错误 banner 3 秒自动消失
watch(() => chat.error, (newErr) => {
  if (newErr) {
    setTimeout(() => {
      if (chat.error === newErr) {
        chat.clearError()
      }
    }, 3000)
  }
})

watch(chatId, async (newId, oldId) => {
  if (newId && newId !== oldId && newId !== chat.activeChatId) {
    chat.abort()
    const item = chat.chatHistory.find(h => h.chat_id === newId)
    if (item) {
      chat.activeCharacterId = item.character_id
    }
    messagesLoading.value = true
    try {
      await chat.fetchMessages(newId)
    } catch (err) {
      console.error('[ChatPage] fetchMessages failed:', err)
      chat.error = '切换对话失败，请重试'
    } finally {
      messagesLoading.value = false
    }
  }
})

async function handleRetryHistory() {
  historyError.value = null
  historyLoading.value = true
  try {
    await chat.fetchChatHistory(novelId.value, chat.activeCharacterId ?? undefined)
  } catch (err) {
    console.error('[ChatPage] retry history failed:', err)
    historyError.value = '加载失败，请重试'
  } finally {
    historyLoading.value = false
  }
}

function handleSend(content: string) {
  if (!chat.activeCharacterId) return
  chat.sendMessage(novelId.value, chat.activeCharacterId, content, () => {
    chat.fetchChatHistory(novelId.value, chat.activeCharacterId ?? undefined)
    memoryPanelRef.value?.refresh()
  })
}

function handleStartNewChat() {
  const charId = route.query.characterId as string
  if (!charId) {
    chat.error = '缺少角色信息，请返回重新选择角色'
    return
  }

  chat.reset()
  chat.initSession(novelId.value, charId, (newChatId) => {
    chat.fetchChatHistory(novelId.value, charId)
    memoryPanelRef.value?.refresh()
    router.replace({
      name: 'chat',
      query: { novelId: novelId.value, characterId: charId, chatId: newChatId },
    }).catch((err: any) => {
      if (err?.name !== 'NavigationDuplicated') throw err
    })
  }, undefined, () => {
    chat.fetchChatHistory(novelId.value, chat.activeCharacterId ?? undefined)
    memoryPanelRef.value?.refresh()
  })
}

function handleNewChat() {
  chat.reset()
  router.push({
    name: 'chat-select',
    query: { novelId: novelId.value },
  }).catch((err: any) => {
    if (err?.name !== 'NavigationDuplicated') throw err
  })
}

function handleSelectChat(selectedChatId: string) {
  chat.abort()
  const item = chat.chatHistory.find(h => h.chat_id === selectedChatId)
  const charId = item?.character_id || (route.query.characterId as string)
  router.push({
    name: 'chat',
    query: { novelId: novelId.value, characterId: charId, chatId: selectedChatId },
  }).catch((err: any) => {
    if (err?.name !== 'NavigationDuplicated') throw err
  })
}

async function handleDeleteChat(chatIdToDelete: string) {
  const wasActive = chat.activeChatId === chatIdToDelete
  const currentCharId = chat.activeCharacterId ?? (route.query.characterId as string)
  try {
    await chat.removeChat(chatIdToDelete)
  } catch {
    // 可能已被删除（重复点击等），直接刷新列表
  }
  await chat.fetchChatHistory(novelId.value, currentCharId)
  if (wasActive) {
    chat.abort()
    chat.activeChatId = null
    chat.messages = []
    chat.error = null
    router.push({
      name: 'chat',
      query: { novelId: novelId.value, characterId: currentCharId },
    }).catch((err: any) => {
      if (err?.name !== 'NavigationDuplicated') throw err
    })
  }
}
</script>
