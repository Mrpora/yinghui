<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import type { TimelineEvent } from '@/types'
import TimelineEventCard from './TimelineEvent.vue'

const props = withDefaults(defineProps<{
  events: TimelineEvent[]
  isRunning: boolean
  characterColors?: Record<string, string>
}>(), {
  characterColors: () => ({}),
})

const visibleEvents = computed(() =>
  props.events.filter(e => e.type !== 'relationship' && e.type !== 'branch_options'),
)

interface EventGroup {
  round: number
  events: TimelineEvent[]
}

const roundGroups = computed<EventGroup[]>(() => {
  const groups: EventGroup[] = []
  for (const e of visibleEvents.value) {
    const last = groups[groups.length - 1]
    if (last && last.round === e.round) {
      last.events.push(e)
    } else {
      groups.push({ round: e.round, events: [e] })
    }
  }
  return groups
})

const container = ref<HTMLDivElement>()

function scrollToBottom() {
  if (!container.value || typeof container.value.scrollTo !== 'function') return
  container.value.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' })
}

// 实时演化时，新事件到达自动滚动到底部
watch(
  () => visibleEvents.value.length,
  () => nextTick(scrollToBottom),
  { flush: 'post' },
)

// 历史记录首次加载时，组件挂载后滚动到底部
onMounted(() => {
  if (visibleEvents.value.length > 0) {
    nextTick(scrollToBottom)
  }
})
</script>

<template>
  <div class="flex-1 relative">
    <div ref="container" class="absolute inset-0 overflow-y-auto py-4 pr-4">
      <!-- 空状态 -->
      <div v-if="visibleEvents.length === 0 && !isRunning" class="flex items-center justify-center h-full">
        <p class="text-smoke animate-celadon-pulse text-sm">等待演化开始…</p>
      </div>

      <!-- 时间线竖线 + 事件列表 -->
      <div v-else class="space-y-4">

        <template v-for="(group, gIdx) in roundGroups" :key="group.round">
          <!-- 轮次分割线（非第一组） -->
          <div v-if="gIdx > 0" class="flex items-center gap-4 ml-4">
            <div class="relative shrink-0" style="width: 10px; height: 16px">
              <div class="absolute left-1/2 -translate-x-1/2 -top-2 -bottom-2 w-[2px] rounded bg-smoke/15" />
            </div>
            <div class="flex-1 border-t border-border-light" />
          </div>

          <TimelineEventCard
            v-for="event in group.events"
            :key="event.id"
            :event="event"
            :character-colors="characterColors"
          />
        </template>
      </div>
    </div>

  </div>
</template>
