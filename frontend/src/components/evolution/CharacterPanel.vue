<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  characters?: {
    name: string
    identity: string
    personality?: string
    speech_style?: string
    goal?: string
    backstory?: string
    inner_thoughts?: string
    accent_color?: string
  }[]
}>()

const collapsed = ref(false)

function personalityTags(p: string): string[] {
  if (!p) return []
  return p.split(/[、,，]/).map(s => s.trim()).filter(Boolean)
}
</script>

<template>
  <!-- 折叠态 -->
  <div
    v-if="collapsed"
    class="w-8 shrink-0 flex items-center justify-center cursor-pointer border-l border-border-light bg-frost/50 group"
    title="展开面板"
    @click="collapsed = false"
  >
    <span class="text-xs text-smoke group-hover:text-ink transition-colors font-serif" style="writing-mode: vertical-rl;">
      角色名录
    </span>
  </div>

  <!-- 展开态 -->
  <div v-else class="w-1/4 shrink-0 border-l border-border-light bg-frost/20 flex flex-col overflow-hidden">
    <div class="flex items-center justify-between px-3 py-2.5 border-b border-border-light">
      <h2 class="text-sm font-medium text-ink/70 tracking-wider">角色名录</h2>
      <button class="text-smoke hover:text-ink transition-colors text-sm" title="收起面板" @click="collapsed = true">
        ▶
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-3 py-2 space-y-2">
      <div v-if="!characters || characters.length === 0" class="text-smoke/50 text-xs text-center py-4">
        暂无角色
      </div>

      <div
        v-for="(ch, i) in characters"
        :key="i"
        class="bg-white rounded-lg border border-border-light p-2.5"
      >
        <p :style="{ color: ch.accent_color }" class="text-sm font-medium text-old-gold">{{ ch.name }}</p>
        <p class="text-smoke text-xs">{{ ch.identity }}</p>

        <!-- 性格标签 -->
        <div v-if="ch.personality" class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="tag in personalityTags(ch.personality)"
            :key="tag"
            class="px-1.5 py-0.5 text-xs bg-celadon/15 text-celadon rounded"
          >
            {{ tag }}
          </span>
        </div>

        <!-- 说话风格 -->
        <p v-if="ch.speech_style" class="mt-1.5 text-xs text-ink/70 leading-relaxed">
          <span class="text-smoke">说话风格：</span>{{ ch.speech_style }}
        </p>

        <div class="mt-2 pt-2 border-t border-border-light space-y-1.5">
          <p v-if="ch.goal" class="text-xs text-ink/70 leading-relaxed">
            <span class="text-smoke">目标：</span>{{ ch.goal }}
          </p>
          <div v-if="ch.goal && ch.backstory" class="border-t border-border-light" />
          <p v-if="ch.backstory" class="text-xs text-ink/70 leading-relaxed">
            <span class="text-smoke">背景：</span>{{ ch.backstory }}
          </p>
          <p v-if="ch.inner_thoughts" class="text-xs text-ink/60 italic leading-relaxed">
            {{ ch.inner_thoughts }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
