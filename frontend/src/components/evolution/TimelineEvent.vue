<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref } from 'vue'
import { marked } from 'marked'
import type { TimelineEvent } from '@/types'

const props = withDefaults(defineProps<{
  event: TimelineEvent
  characterColors?: Record<string, string>
}>(), {
  characterColors: () => ({}),
})

function charColor(name: string | null | undefined): string | undefined {
  if (!name) return undefined
  return props.characterColors[name]
}

const expanded = ref(false)

function renderMarkdown(content: string): string {
  return marked.parse(content, { async: false }) as string
}

const dotColorMap: Record<string, string> = {
  action: 'bg-blue-400',
  conflict: 'bg-red-400',
  scene_setting: 'bg-teal-400',
  user_decision: 'bg-yellow-400',
  user_intervene: 'bg-persimmon',
  round_summary: 'bg-green-400',
  relationship: 'bg-purple-400',
}

const lineColorMap: Record<string, string> = {
  action: 'bg-blue-400/25',
  scene_setting: 'bg-teal-400/25',
  user_decision: 'bg-yellow-400/25',
  user_intervene: 'bg-persimmon/25',
  round_summary: 'bg-green-400/25',
}

const typeLabelMap: Record<string, string> = {
  action: '行动',
  conflict: '冲突',
  scene_setting: '场景',
  user_decision: '决策',
  user_intervene: '干预',
  round_summary: '总结',
  relationship: '关系',
}

function dotColor(type: string) {
  return dotColorMap[type] || 'bg-gray-400'
}

function lineColor(type: string) {
  return lineColorMap[type] || 'bg-gray-400/25'
}

function typeLabel(type: string) {
  return typeLabelMap[type] || type
}

const typeTextColorMap: Record<string, string> = {
  action: 'text-blue-500',
  conflict: 'text-cinnabar',
  scene_setting: 'text-teal-500',
  user_decision: 'text-yellow-600',
  user_intervene: 'text-persimmon',
  round_summary: 'text-moss',
  relationship: 'text-purple-500',
}

function typeTextColor(type: string) {
  return typeTextColorMap[type] || 'text-ink'
}
</script>

<template>
  <!-- 冲突事件 -->
  <div v-if="event.type === 'conflict'" class="flex items-start gap-4 ml-4">
    <div class="self-stretch relative shrink-0 pt-1.5" style="width: 10px">
      <div class="absolute left-1/2 -translate-x-1/2 -top-2 -bottom-2 w-[2px] rounded bg-cinnabar/40" />
      <div class="w-2 h-2 bg-cinnabar rotate-45 animate-cinnabar-pulse relative z-10" />
    </div>
    <div class="flex-1 bg-white rounded-lg border border-cinnabar/30 bg-cinnabar/[0.03] p-3 min-w-0">
      <div class="flex items-center gap-2 text-base mb-1.5">
        <span class="font-bold text-cinnabar">第 {{ event.round }} 轮</span>
        <span class="text-cinnabar/30">·</span>
        <span class="text-cinnabar font-medium">冲突</span>
        <span v-if="event.timestamp" class="ml-auto text-xs text-smoke">{{ event.timestamp }}</span>
      </div>
      <p class="text-sm text-ink/85 leading-relaxed whitespace-pre-wrap">{{ event.content }}</p>
      <p v-if="event.involved_characters?.length" class="text-xs text-smoke mt-2">
        涉及：{{ event.involved_characters.join('、') }}
      </p>
      <div v-if="event.motive || event.inner_thoughts" class="mt-2 space-y-1.5">
        <p v-if="event.motive" class="text-xs text-ink/60 leading-relaxed">
          <span class="text-smoke">动机：</span>{{ event.motive }}
        </p>
        <p v-if="event.inner_thoughts" class="text-xs text-ink/50 italic leading-relaxed">
          <span class="text-smoke">内心：</span>{{ event.inner_thoughts }}
        </p>
      </div>
    </div>
  </div>

  <!-- 互动事件 -->
  <div
    v-else-if="event.type === 'action' && event.source === 'interaction'"
    class="flex items-start gap-4 ml-4"
  >
    <div class="self-stretch relative shrink-0 pt-1.5" style="width: 10px">
      <div class="absolute left-1/2 -translate-x-1/2 -top-2 -bottom-2 w-[2px] rounded bg-c-line-cyan/30" />
      <div class="w-2.5 h-2.5 rounded-full bg-c-line-cyan ring-2 ring-c-line-cyan/20 relative z-10" />
    </div>
    <div class="flex-1 bg-white rounded-lg border border-border-light p-3 min-w-0">
      <div class="flex items-center gap-2 text-base text-ink mb-1.5">
        <span class="font-bold">第 {{ event.round }} 轮</span>
        <span class="text-smoke/40">·</span>
        <span class="text-c-line-cyan font-medium">互动</span>
        <template v-if="event.character">
          <span class="text-smoke/40">·</span>
          <span :style="{ color: charColor(event.character) }">{{ event.character }}</span>
        </template>
        <span v-if="event.timestamp" class="ml-auto text-xs text-smoke">{{ event.timestamp }}</span>
      </div>

      <p class="text-sm text-ink/85 leading-relaxed">{{ event.content }}</p>

      <div v-if="event.motive || event.inner_thoughts" class="mt-2">
        <button
          class="text-xs text-smoke/70 hover:text-smoke transition-colors"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起细节 ▲' : '查看动机与内心活动 ▼' }}
        </button>
        <div v-if="expanded" class="mt-2 space-y-1.5 animate-fade-in">
          <p v-if="event.motive" class="text-xs text-ink/60 leading-relaxed">
            <span class="text-smoke">动机：</span>{{ event.motive }}
          </p>
          <p v-if="event.inner_thoughts" class="text-xs text-ink/50 italic leading-relaxed">
            <span class="text-smoke">内心：</span>{{ event.inner_thoughts }}
          </p>
        </div>
      </div>
    </div>
  </div>

  <!-- 普通事件 -->
  <div v-else class="flex items-start gap-4 ml-4">
    <div class="self-stretch relative shrink-0 pt-1.5" style="width: 10px">
      <div class="absolute left-1/2 -translate-x-1/2 -top-2 -bottom-2 w-[2px] rounded" :class="event.type === 'scene_setting' && event.round === 0 ? 'bg-old-gold/25' : lineColor(event.type)" />
      <div class="w-2.5 h-2.5 rounded-full relative z-10" :class="event.type === 'scene_setting' && event.round === 0 ? 'bg-old-gold' : dotColor(event.type)" />
    </div>

    <div class="flex-1 bg-white rounded-lg border border-border-light p-3 min-w-0">
      <div class="flex items-center gap-2 text-base text-ink mb-1.5">
        <span v-if="event.type === 'scene_setting' && event.round === 0" class="font-bold text-old-gold">初始事件</span>
        <span v-else class="font-bold">第 {{ event.round }} 轮</span>
        <template v-if="!(event.type === 'scene_setting' && event.round === 0)">
          <span class="text-smoke/40">·</span>
          <span class="font-medium" :class="typeTextColor(event.type)">{{ typeLabel(event.type) }}</span>
        </template>
        <template v-if="event.character">
          <span class="text-smoke/40">·</span>
          <span :style="{ color: charColor(event.character) }">{{ event.character }}</span>
        </template>
        <span v-if="event.timestamp" class="ml-auto text-xs text-smoke">{{ event.timestamp }}</span>
      </div>

      <div v-if="event.type === 'round_summary'" class="mt-1 text-sm text-ink/85 leading-relaxed prose prose-sm max-w-none" v-html="renderMarkdown(event.content)" />
      <p v-else class="text-sm text-ink/85 leading-relaxed">{{ event.content }}</p>

      <div v-if="event.motive || event.inner_thoughts" class="mt-2">
        <button
          class="text-xs text-smoke/70 hover:text-smoke transition-colors"
          @click="expanded = !expanded"
        >
          {{ expanded ? '收起细节 ▲' : '查看动机与内心活动 ▼' }}
        </button>
        <div v-if="expanded" class="mt-2 space-y-1.5 animate-fade-in">
          <p v-if="event.motive" class="text-xs text-ink/60 leading-relaxed">
            <span class="text-smoke">动机：</span>{{ event.motive }}
          </p>
          <p v-if="event.inner_thoughts" class="text-xs text-ink/50 italic leading-relaxed">
            <span class="text-smoke">内心：</span>{{ event.inner_thoughts }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
