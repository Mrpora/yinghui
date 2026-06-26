<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div ref="container" class="flex-1 overflow-y-scroll px-2 sm:px-4 py-4 sm:py-6">
    <div
      v-if="messages.length === 0 && !isTyping && !isThinking"
      class="flex items-center justify-center h-full text-smoke/30 text-sm"
    >
      开始对话吧
    </div>

    <template v-else>
      <template v-for="(msg, i) in messages" :key="i">
        <div
          v-if="formatTimeLabel(new Date(msg.timestamp), i > 0 ? new Date(messages[i - 1].timestamp) : undefined)"
          class="text-center text-smoke/70 text-xs my-3"
        >
          {{ formatTimeLabel(new Date(msg.timestamp), i > 0 ? new Date(messages[i - 1].timestamp) : undefined) }}
        </div>

        <div :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']">
          <ChatBubble
            :msg="msg"
            :accent-color="accentColor"
            :character-name="characterName"
            class="max-w-[88%] sm:max-w-2xl"
          />
        </div>
      </template>

      <!-- SSE 占位区域 -->
      <template v-if="isTyping || isThinking">
        <div
          v-if="streamingTimeLabel"
          class="text-center text-smoke/70 text-xs my-3"
        >
          {{ streamingTimeLabel }}
        </div>
        <div class="max-w-3xl w-full flex-col">
          <div class="flex gap-2 sm:gap-3 mb-1 max-w-[88%] sm:max-w-2xl">
            <div
              class="w-7 h-7 sm:w-9 sm:h-9 rounded-full flex-shrink-0 flex items-center justify-center text-xs sm:text-sm font-serif"
              :style="{ backgroundColor: accentColor + '18', color: accentColor }"
            >
              {{ characterName[0] }}
            </div>
            <div
              class="px-3 py-2 sm:px-5 sm:py-3 rounded-2xl rounded-tl-md text-xs sm:text-sm leading-relaxed min-w-[120px] break-words"
              :style="{ backgroundColor: accentColor + '10', color: streamingContent ? undefined : '#807F83' }"
            >
              <template v-if="streamingContent">
                <template v-for="(seg, i) in streamingSegments" :key="i">
                  <span :class="{ 'text-smoke': seg.isAction }">{{ seg.text }}</span>
                </template>
                <span class="animate-pulse text-smoke/60">|</span>
              </template>
              <template v-else>
                <span class="text-smoke/70">凝神欲语</span>
                <span v-for="i in 3" :key="i" class="typing-dot" :style="{ animationDelay: `${(i - 1) * 0.2}s` }" />
              </template>
            </div>
          </div>

          <!-- SSE 状态文案 -->
          <div
            v-show="isThinking || isRetrieving || isMemorizing"
            class="flex items-center gap-1.5 ml-9 sm:ml-12"
          >
            <span class="w-1.5 h-1.5 rounded-full"
              :class="{
                'bg-amber-500 thinking-dot': isThinking,
                'bg-moss animate-pulse': isRetrieving,
                'bg-cinnabar animate-pulse': isMemorizing,
              }"
            />
            <span class="text-xs text-smoke/70">
              {{ isThinking ? '思绪万千' : isRetrieving ? '追忆往昔' : '铭记于心' }}
            </span>
          </div>

          <!-- Token 输出状态 -->
          <div
            v-show="isTyping && streamingContent && !isThinking && !isRetrieving && !isMemorizing"
            class="flex items-center gap-1.5 ml-9 sm:ml-12"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
            <span class="text-xs text-smoke/70">娓娓道来</span>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import ChatBubble from './ChatBubble.vue'
import type { Message } from '@/types'

const props = defineProps<{
  messages: Message[]
  isTyping: boolean
  isThinking: boolean
  isRetrieving: boolean
  isMemorizing: boolean
  streamingContent: string
  characterName: string
  accentColor: string
}>()

const container = ref<HTMLElement>()

const streamingSegments = computed(() => {
  const result: { text: string; isAction: boolean }[] = []
  let current = ''
  let inAction = false

  for (const ch of props.streamingContent) {
    if (ch === '（') {
      if (current) result.push({ text: current, isAction: inAction })
      current = '（'
      inAction = true
    } else if (ch === '）') {
      current += '）'
      result.push({ text: current, isAction: true })
      current = ''
      inAction = false
    } else {
      current += ch
    }
  }
  if (current) result.push({ text: current, isAction: inAction })

  return result
})

const streamingTimeLabel = computed(() => {
  if (!props.isTyping && !props.isThinking) return null
  const now = new Date()
  const lastMsg = props.messages.length > 0
    ? new Date(props.messages[props.messages.length - 1].timestamp)
    : undefined
  return formatTimeLabel(now, lastMsg)
})

function scrollToBottom() {
  if (container.value) container.value.scrollTop = container.value.scrollHeight
}

watch(() => props.messages.length, async () => {
  await nextTick()
  scrollToBottom()
})

watch(() => props.streamingContent, async () => {
  await nextTick()
  scrollToBottom()
})

function formatTimeLabel(date: Date, prevDate?: Date): string | null {
  if (prevDate) {
    const diff = date.getTime() - prevDate.getTime()
    if (diff < 2 * 60 * 1000) return null
  }

  const now = new Date()
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const time = `${hours}:${minutes}`

  if (date.toDateString() === now.toDateString()) return time

  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return `昨天 ${time}`

  const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays < 7) return `${weekdays[date.getDay()]} ${time}`

  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${time}`
}
</script>

<style scoped>
.typing-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: #807F83;
  margin-left: 4px;
  vertical-align: middle;
  animation: dot-bounce 1.4s ease-in-out infinite;
}

@keyframes dot-bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-4px); }
}

.thinking-dot {
  animation: thinking-scale 1.2s ease-in-out infinite;
}

@keyframes thinking-scale {
  0%, 100% { transform: scale(1); opacity: 0.7; }
  50% { transform: scale(1.8); opacity: 1; }
}

div::-webkit-scrollbar {
  width: 5px;
}

div::-webkit-scrollbar-track {
  background: transparent;
}

div::-webkit-scrollbar-thumb {
  background: rgba(128, 127, 131, 0.4);
  border-radius: 4px;
}
</style>
