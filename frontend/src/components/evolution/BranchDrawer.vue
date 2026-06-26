<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Branch } from '@/types'
import BranchCard from './BranchCard.vue'
import CustomEventInput from './CustomEventInput.vue'

const props = defineProps<{
  visible: boolean
  branches: Branch[]
  reason: 'conflict' | 'branches'
}>()

const emit = defineEmits<{
  'select-branch': [index: number]
  'submit-custom': [text: string]
  close: []
}>()

// 每次最多展示 3 条
const pageSize = 3
const pageStart = ref(0)
const displayed = computed(() =>
  props.branches.slice(pageStart.value, pageStart.value + pageSize),
)
const canRotate = computed(() => props.branches.length > pageSize)

function rotate() {
  const total = props.branches.length
  // 跳过当前展示的 3 条，避免重复
  pageStart.value = (pageStart.value + pageSize) % Math.max(total, 1)
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed bottom-0 left-0 right-0 z-40 animate-slide-up"
    >
      <div class="bg-frost border-t border-cinnabar/30 shadow-[0_-8px_32px_rgba(0,0,0,0.5)]">
        <div class="px-[15%] py-5">
          <!-- 标题 -->
          <div class="flex items-center gap-2 mb-4">
            <span class="text-cinnabar text-sm">⚡</span>
            <h3 class="font-serif text-lg text-ink tracking-wider">
              剧情分歧点 — 请选择演化方向
            </h3>
          </div>

          <!-- 分支卡片：桌面端横向排列 -->
          <div class="flex flex-col sm:flex-row gap-3 sm:gap-4">
            <BranchCard
              v-for="branch in displayed"
              :key="branch.index"
              :branch="branch"
              @select="emit('select-branch', $event)"
            />
          </div>

          <!-- 换一批 / 分支计数 -->
          <div class="mt-3 flex justify-between items-center">
            <button
              v-if="canRotate"
              class="text-xs text-old-gold hover:text-ink transition-colors tracking-wider"
              @click="rotate"
            >
              换一批 →
            </button>
            <span v-else class="text-xs text-smoke">
              {{ props.branches.length > 3 ? `共 ${props.branches.length} 条分支` : '' }}
            </span>
          </div>

          <!-- 自定义事件 -->
          <CustomEventInput @submit="emit('submit-custom', $event)" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
