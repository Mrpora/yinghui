<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div class="hidden md:flex flex-col h-full bg-paper border-r border-frost shrink-0">
    <!-- 新对话 -->
    <div class="px-3 py-3 border-b border-frost">
      <button
        class="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg
               bg-old-gold text-white text-xs font-medium
               hover:bg-old-gold/90 active:scale-[0.98] transition-all duration-200"
        @click="$emit('new-chat')"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新对话
      </button>
    </div>

    <!-- 历史列表 -->
    <div class="flex-1 overflow-y-auto">
      <!-- 骨架屏 -->
      <div v-if="loading" class="px-3 py-2 space-y-2">
        <div v-for="i in 3" :key="i" class="flex items-center gap-2 animate-pulse">
          <div class="w-5 h-5 rounded-full bg-frost/60" />
          <div class="flex-1 h-3 rounded bg-frost/60" />
        </div>
      </div>

      <div v-else-if="historyError" class="px-4 py-6 text-center">
        <p class="text-xs text-cinnabar mb-2">{{ historyError }}</p>
        <button
          class="text-xs text-old-gold hover:text-old-gold/80 underline underline-offset-2"
          @click="$emit('retry')"
        >
          重试
        </button>
      </div>

      <div v-else-if="chats.length === 0 && !historyError" class="px-4 py-8 text-center text-smoke/50 text-xs">
        暂无对话记录
      </div>

      <div
        v-for="c in chats"
        :key="c.chat_id"
        class="w-full text-left px-3 py-3 border-b border-frost/50
               hover:bg-frost/30 transition-colors duration-200
               group cursor-pointer relative"
        :class="{ 'bg-frost/40': c.chat_id === activeChatId }"
        @click="$emit('select', c.chat_id)"
      >
        <div class="flex items-center gap-2 mb-1">
          <span
            class="w-5 h-5 rounded-full flex-shrink-0 flex items-center justify-center text-[10px] font-serif"
            :style="{ backgroundColor: (c.accent_color || '#7A9A7E') + '18', color: c.accent_color || '#7A9A7E' }"
          >
            {{ (c.character_name || '?')[0] }}
          </span>
          <span class="font-serif text-sm text-ink truncate group-hover:text-old-gold transition-colors">
            {{ formatBeijingTime(c.created_at) || '...' }}
          </span>
          <span class="ml-auto text-xs text-smoke/40 flex-shrink-0">
            {{ formatChatTime(c.modified_at) }}
          </span>
        </div>
        <button
          class="absolute right-1 top-1/2 -translate-y-1/2 p-1
                 opacity-0 group-hover:opacity-100 transition-opacity duration-150
                 hover:bg-cinnabar/10 rounded"
          @click.stop="$emit('delete-chat', c.chat_id)"
        >
          <svg class="w-3.5 h-3.5 text-smoke/50 hover:text-cinnabar transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChatHistoryItem } from '@/types'

const props = withDefaults(defineProps<{
  chats: ChatHistoryItem[]
  activeChatId: string | null
  loading?: boolean
  historyError?: string | null
}>(), {
  loading: false,
  historyError: null,
})

defineEmits<{
  'new-chat': []
  select: [chatId: string]
  retry: []
  'delete-chat': [chatId: string]
}>()

function formatChatTime(ms: number | string): string {
  if (!ms) return ''
  const d = new Date(typeof ms === 'string' ? ms : ms)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays === 1) return '昨天'
  if (diffDays < 7) return `${diffDays}天前`

  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getMonth() + 1}月${d.getDate()}日`
  }
  return `${d.getFullYear()}年`
}

function formatBeijingTime(ms: number | string): string {
  if (!ms) return ''
  const d = new Date(typeof ms === 'string' ? ms : ms)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${y}-${mo}-${day} ${h}:${mi}:${s}`
}
</script>
