<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import type { WorldItem } from '@/types'

const props = withDefaults(defineProps<{
  world?: WorldItem
  isCreateCard?: boolean
}>(), {
  isCreateCard: false,
})

defineEmits<{
  click: []
  delete: []
}>()

</script>

<template>
  <!-- 创建卡片 -->
  <div
    v-if="isCreateCard"
    role="button"
    tabindex="0"
    class="p-6 rounded-lg border-2 border-dashed border-smoke bg-transparent cursor-pointer transition-all duration-300 hover:border-old-gold hover:bg-frost flex flex-col items-center justify-center min-h-[160px]"
    @click="$emit('click')"
    @keydown.enter.prevent="$emit('click')"
    @keydown.space.prevent="$emit('click')"
  >
    <span class="text-3xl text-smoke mb-2">+</span>
    <span class="text-sm text-smoke">创建新世界</span>
  </div>

  <!-- 世界卡片 -->
  <div
    v-else-if="world"
    role="button"
    tabindex="0"
    class="relative p-6 rounded-lg border cursor-pointer transition-all duration-300 hover:shadow-lg hover:-translate-y-1 group"
    :class="world.is_preset
      ? 'border-old-gold bg-frost'
      : 'border-border-light bg-white'"
    @click="$emit('click')"
    @keydown.enter.prevent="$emit('click')"
    @keydown.space.prevent="$emit('click')"
  >
    <!-- 删除按钮：预设世界不显示 -->
    <button
      v-if="!world.is_preset"
      class="absolute -top-2.5 -right-2.5 w-7 h-7 flex items-center justify-center rounded-full border border-cinnabar/30 text-cinnabar/60 bg-white hover:bg-cinnabar hover:text-white hover:border-cinnabar opacity-0 group-hover:opacity-100 transition-all text-base font-light"
      title="删除世界"
      @click.stop="$emit('delete')"
    >
      ×
    </button>
    <div class="flex items-center gap-2 mb-3">
      <h3 class="text-lg font-bold text-ink">{{ world.name }}</h3>
      <span
        v-if="world.is_preset"
        class="text-xs px-2 py-0.5 bg-old-gold text-white rounded-sm"
      >预设</span>
    </div>
    <p class="text-sm text-smoke mb-4 line-clamp-2">{{ world.description || '暂无描述' }}</p>
    <div class="flex gap-4 text-xs text-smoke">
      <span>规则 {{ world.rules?.length ?? 0 }} 条</span>
      <span>{{ world.character_count ?? 0 }} 个角色</span>
    </div>
  </div>

  <!-- world 数据缺失降级 -->
  <div
    v-else
    class="p-6 rounded-lg border border-border-light bg-white"
  >
    <p class="text-smoke text-sm">世界数据不可用</p>
  </div>
</template>
