<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div class="px-3 sm:px-6 py-3 sm:py-4">
    <div class="max-w-3xl mx-auto flex gap-2 sm:gap-3 items-end bg-white/80 backdrop-blur rounded-2xl shadow-sm border border-frost px-3 sm:px-4 py-2">
      <textarea
        ref="inputRef"
        v-model="text"
        :disabled="disabled"
        rows="1"
        class="flex-1 resize-none bg-transparent text-ink text-sm sm:text-base placeholder:text-smoke/60
               outline-none py-2 leading-relaxed"
        placeholder="输入你的消息..."
        @keyup.enter.exact="handleSend"
        @input="autoResize"
      />
      <button
        :disabled="disabled || !text.trim()"
        class="flex-shrink-0 w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center
               transition-colors duration-200"
        :class="disabled || !text.trim() ? 'bg-frost text-smoke/50 cursor-not-allowed' : 'bg-cinnabar text-white hover:opacity-90'"
        @click="handleSend"
      >
        <svg class="w-4 h-4 sm:w-5 sm:h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'

defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ send: [content: string] }>()

const text = ref('')
const inputRef = ref<HTMLTextAreaElement>()

function handleSend() {
  const content = text.value.trim()
  if (!content) return
  emit('send', content)
  text.value = ''
  nextTick(() => autoResize())
}

function autoResize() {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = inputRef.value.scrollHeight + 'px'
  }
}
</script>
