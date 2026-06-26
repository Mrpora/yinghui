<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div
    :class="[
      'flex gap-2 sm:gap-3 mb-4 sm:mb-6',
      msg.role === 'user' ? 'flex-row-reverse' : '',
    ]"
  >
    <div
      class="w-7 h-7 sm:w-9 sm:h-9 rounded-full flex-shrink-0 flex items-center justify-center text-xs sm:text-sm font-serif"
      :style="{
        backgroundColor: msg.role === 'user' ? '#F3EDE3' : accentColor + '18',
        color: msg.role === 'user' ? '#9B8E7E' : accentColor,
      }"
    >
      {{ msg.role === 'user' ? '你' : (characterName?.[0] ?? '?') }}
    </div>

    <div
      :class="[
        'px-3 py-2 sm:px-5 sm:py-3 rounded-2xl text-xs sm:text-sm leading-relaxed',
        msg.role === 'user' ? 'bg-frost text-ink rounded-tr-md' : 'text-ink rounded-tl-md',
      ]"
      :style="msg.role === 'character' ? { backgroundColor: accentColor + '10' } : {}"
    >
      <template v-for="(seg, i) in segments" :key="i">
        <span :class="{ 'text-smoke': seg.isAction }">{{ seg.text }}</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/types'

const props = defineProps<{
  msg: Message
  accentColor: string
  characterName?: string
}>()

const segments = computed(() => {
  const result: { text: string; isAction: boolean }[] = []
  let current = ''
  let inAction = false

  for (const ch of props.msg.content) {
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
</script>
