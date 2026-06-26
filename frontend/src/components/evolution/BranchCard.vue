<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import type { Branch } from '@/types'

defineProps<{ branch: Branch }>()
const emit = defineEmits<{ select: [index: number] }>()
</script>

<template>
  <div
    class="flex-1 min-w-0 bg-frost border border-border-light rounded-lg p-4
           cursor-pointer transition-all duration-300 flex flex-col
           hover:border-old-gold hover:bg-white hover:translate-y-[-2px] hover:shadow-md
           h-[22rem]"
    role="button"
    tabindex="0"
    @click="emit('select', branch.index)"
    @keydown.enter.prevent="emit('select', branch.index)"
    @keydown.space.prevent="emit('select', branch.index)"
  >
    <h4 class="font-serif text-base text-ink tracking-wider">
      {{ branch.title }}
    </h4>
    <div class="max-h-28 overflow-y-auto rounded border border-border-light/50 bg-white/50 p-2 mt-2 flex-1">
      <p class="text-sm text-ink/80 leading-relaxed whitespace-pre-wrap">
        {{ branch.description }}
      </p>
    </div>
    <div class="mt-3 pt-2 border-t border-border-light">
      <span class="text-[10px] text-old-gold tracking-wider">推荐理由</span>
      <p class="text-xs text-smoke mt-1 leading-relaxed">
        {{ branch.reason }}
      </p>
    </div>
  </div>
</template>
