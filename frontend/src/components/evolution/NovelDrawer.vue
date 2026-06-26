<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { useNovelStore } from '@/stores/novel'
import BaseButton from '@/components/ui/BaseButton.vue'

defineProps<{
  visible: boolean
}>()

defineEmits<{
  close: []
  retry: []
}>()

const novel = useNovelStore()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-50 flex items-end"
      @click.self="$emit('close')"
    >
      <div class="bg-frost w-full rounded-t-2xl animate-slide-up">
        <!-- 拖拽手柄 -->
        <div class="flex justify-center pt-2 pb-1">
          <div class="w-10 h-1 rounded-full bg-border-light" />
        </div>

        <!-- 标题行 -->
        <div class="flex items-center justify-between px-4 mb-3">
          <h3 class="font-serif text-lg text-ink flex-1 text-center">导出小说</h3>
          <button class="text-smoke hover:text-ink transition-colors text-lg" @click="$emit('close')">✕</button>
        </div>

        <!-- 错误状态 -->
        <div v-if="novel.taskStatus === 'failed'" class="px-4 pb-6 text-center">
          <p class="text-cinnabar text-sm mb-3">{{ novel.progressMessage || '生成失败，请稍后重试' }}</p>
          <BaseButton variant="primary" @click="$emit('retry')">重试</BaseButton>
        </div>

        <!-- 已有任务进行中 -->
        <div v-else-if="novel.existingTask" class="px-4 pb-6 text-center">
          <p class="text-smoke text-sm">该演化记录已有小说生成任务进行中</p>
          <p class="text-smoke text-xs mt-1 mb-3">可在「小说」页面查看进度</p>
          <BaseButton variant="secondary" @click="$emit('close')">关闭</BaseButton>
        </div>

        <!-- 新任务已提交 -->
        <div v-else class="px-4 pb-6 text-center">
          <p class="text-smoke text-sm">小说生成任务已提交</p>
          <p class="text-smoke text-xs mt-1 mb-3">可在「小说」页面查看进度</p>
          <BaseButton variant="secondary" @click="$emit('close')">关闭</BaseButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>
