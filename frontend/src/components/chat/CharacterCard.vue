<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import type { ChatCharacter } from '@/types'
import BaseButton from '@/components/ui/BaseButton.vue'

defineProps<{
  character: ChatCharacter
}>()

defineEmits<{
  'start-chat': []
}>()
</script>

<template>
  <div
    class="bg-white rounded-xl border border-border-light hover:border-old-gold/40 transition-colors p-4 flex flex-col"
  >
    <h3 class="font-serif text-lg" :style="{ color: character.accent_color || '#7A9A7E' }">{{ character.name }}</h3>
    <p class="text-smoke text-xs mt-0.5">{{ character.identity }}</p>
    <div class="flex flex-wrap gap-1 mt-2">
      <span
        v-for="trait in character.personality_traits"
        :key="trait"
        class="bg-frost text-smoke text-xs rounded-full px-2 py-0.5"
      >
        {{ trait }}
      </span>
    </div>
    <div class="flex-1" />
    <BaseButton variant="secondary" class="mt-3 w-full" @click="$emit('start-chat')">
      开始对话
    </BaseButton>
  </div>
</template>
