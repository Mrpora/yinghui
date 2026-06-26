<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref } from 'vue'
import { useEvolutionStore } from '@/stores/evolution'
import RoundCounter from '@/components/evolution/RoundCounter.vue'
import RelationshipGraph from './RelationshipGraph.vue'

defineProps<{
  worldName?: string
  worldHistory?: string
  rules?: string[]
}>()

const evolution = useEvolutionStore()
const collapsed = ref(false)
</script>

<template>
  <!-- 折叠态 -->
  <div
    v-if="collapsed"
    class="w-8 shrink-0 flex items-center justify-center cursor-pointer border-r border-border-light bg-frost/50 group"
    title="展开面板"
    @click="collapsed = false"
  >
    <span class="text-xs text-smoke group-hover:text-ink transition-colors font-serif" style="writing-mode: vertical-rl;">
      世界设定
    </span>
  </div>

  <!-- 展开态 -->
  <div v-else class="w-1/5 shrink-0 border-r border-border-light bg-frost/30 flex flex-col overflow-hidden">
    <!-- 标题行 + 折叠按钮 -->
    <div class="flex items-center justify-between px-3 py-2.5 border-b border-border-light">
      <h2 class="text-base font-bold text-ink font-serif tracking-wider">
        {{ worldName || '世界' }}
      </h2>
      <button class="text-smoke hover:text-ink transition-colors text-sm" title="收起面板" @click="collapsed = true">
        ◀
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-3 py-2 space-y-3">
      <!-- 世界历史 -->
      <div>
        <h3 class="text-sm font-medium text-ink/70 tracking-wider mb-1.5">世界历史</h3>
        <div class="bg-white/70 rounded p-2 text-xs text-ink/80 leading-relaxed max-h-32 overflow-y-auto">
          {{ worldHistory || '暂无历史记载' }}
        </div>
      </div>

      <!-- 世界规则 -->
      <div>
        <h3 class="text-sm font-medium text-ink/70 tracking-wider mb-1.5">世界规则</h3>
        <ul v-if="rules && rules.length > 0" class="text-xs text-ink/70 space-y-0.5 list-disc list-inside">
          <li v-for="(r, i) in rules" :key="i">{{ r }}</li>
        </ul>
        <p v-else class="text-xs text-smoke/50">暂无规则</p>
      </div>

      <!-- 分割线 -->
      <div class="border-t border-border-light" />

      <!-- 轮次 -->
      <RoundCounter :current="evolution.currentRound" :max="evolution.maxRounds" />

      <!-- 分割线 -->
      <div class="border-t border-border-light" />

      <!-- 关系图 -->
      <RelationshipGraph :relationships="evolution.relationships" />
    </div>
  </div>
</template>
