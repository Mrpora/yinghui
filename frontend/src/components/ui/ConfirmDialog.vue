<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import BaseButton from './BaseButton.vue'

const props = defineProps<{
  visible: boolean
  title: string
  message: string
  confirmVariant?: 'primary' | 'danger'
  confirmText?: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.visible) {
    emit('cancel')
  }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-50 flex items-center justify-center bg-ink/30"
      @click.self="$emit('cancel')"
    >
      <div class="bg-white rounded-xl p-6 max-w-xs mx-4 shadow-xl text-center animate-fade-in">
        <h3 class="font-serif text-lg text-ink mb-3">{{ title }}</h3>
        <p class="text-smoke text-sm mb-6">{{ message }}</p>
        <div class="flex gap-3 justify-center">
          <BaseButton variant="secondary" @click="$emit('cancel')">取消</BaseButton>
          <BaseButton :variant="confirmVariant || 'danger'" @click="$emit('confirm')">
            {{ confirmText || '确认' }}
          </BaseButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>
