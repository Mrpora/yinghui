<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import type { MemoryItem } from '@/types'

defineProps<{
  memory: MemoryItem
}>()

const emit = defineEmits<{
  'update-expiry': [expiresAt: number | null]
  delete: []
}>()

function formatTime(ts: number | string) {
  const d = new Date(typeof ts === 'string' ? ts : ts)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
  const hm = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 0) return `今天 ${hm}`
  if (diffDays === 1) return `昨天 ${hm}`
  return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`
}

function onExpiryChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  if (v === '永久') {
    emit('update-expiry', null)
  } else {
    const days = v === '7d' ? 7 : 30
    emit('update-expiry', Date.now() + days * 86400000)
  }
}
</script>

<template>
  <div class="bg-frost/20 rounded-lg p-2.5 relative group">
    <!-- 右上角删除按钮 -->
    <button
      class="absolute right-2.5 top-1 p-1
             opacity-0 group-hover:opacity-100 transition-opacity duration-150
             hover:bg-cinnabar/10 rounded text-xs text-smoke/50 hover:text-cinnabar"
      @click="emit('delete')"
    >
      <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M18 6L6 18M6 6l12 12" />
      </svg>
    </button>

    <div class="flex items-center gap-1.5 mb-1">
      <span
        class="text-xs rounded-full px-1.5 py-0.5"
        :class="memory.memory_type === 'user_fact'
          ? 'bg-moss/15 text-moss'
          : 'bg-persimmon/15 text-persimmon'"
      >
        {{ memory.memory_type === 'user_fact' ? '事实' : '事件' }}
      </span>
      <span class="text-smoke text-xs">{{ memory.character_name }}</span>
    </div>

    <p class="text-ink text-sm leading-relaxed mb-2">{{ memory.content }}</p>

    <div class="flex items-center justify-between text-xs text-smoke/70">
      <span>{{ formatTime(memory.created_at) }}</span>
      <div class="flex items-center gap-2">
        <select
          class="text-xs bg-transparent border-none cursor-pointer"
          :value="memory.expires_at || '永久'"
          @change="onExpiryChange"
        >
          <option value="永久">永久</option>
          <option value="7d">7天</option>
          <option value="30d">30天</option>
        </select>
      </div>
    </div>
  </div>
</template>
