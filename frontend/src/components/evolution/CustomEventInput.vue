<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref } from 'vue'
import BaseButton from '@/components/ui/BaseButton.vue'

const emit = defineEmits<{ submit: [text: string] }>()

const text = ref('')
const isSubmitting = ref(false)

function handleSubmit() {
  const trimmed = text.value.trim()
  if (!trimmed || isSubmitting.value) return
  isSubmitting.value = true
  emit('submit', trimmed)
  text.value = ''
  setTimeout(() => { isSubmitting.value = false }, 1000)
}
</script>

<template>
  <div class="mt-4 flex gap-2">
    <input
      v-model="text"
      type="text"
      maxlength="500"
      placeholder="输入自定义事件干预剧情走向…"
      class="flex-1 border border-border-light rounded-lg px-3 py-2 text-sm
             focus:outline-none focus:ring-2 focus:ring-old-gold/30
             transition-colors duration-200"
      @keydown.enter="handleSubmit"
    />
    <BaseButton variant="primary" :disabled="!text.trim() || isSubmitting" @click="handleSubmit">
      {{ isSubmitting ? '提交中' : '提交' }}
    </BaseButton>
  </div>
</template>
