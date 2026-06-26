<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useEvolutionStore } from '@/stores/evolution'
import { useNovelStore } from '@/stores/novel'

import BaseButton from '@/components/ui/BaseButton.vue'
import NovelDrawer from './NovelDrawer.vue'

defineProps<{
  connectionStatus: 'connected' | 'connecting' | 'disconnected'
}>()

const emit = defineEmits<{
  'start-round': []
  reset: []
}>()

const evolution = useEvolutionStore()
const novel = useNovelStore()

// 派生状态
const derivedStatus = computed(() => {
  if (!evolution.currentEvolutionId) return 'idle'
  if (evolution.isRunning) return 'running'
  if (evolution.currentSession?.status === 'ended') return 'ended'
  if (evolution.isPaused && evolution.pauseReason === 'conflict') return 'paused-conflict'
  if (evolution.isPaused && evolution.pauseReason === 'branches') return 'paused-branches'
  if (evolution.isPaused) return 'paused-conflict'
  if (evolution.currentRound > 0 && !evolution.isPaused) return 'waiting_next_round'
  return 'idle'
})

const buttonConfig = computed(() => {
  switch (derivedStatus.value) {
    case 'idle':
      return { text: '开始演化', cls: 'bg-old-gold text-white hover:bg-old-gold/85 shadow-lg shadow-old-gold/25', disabled: false, action: 'start' }
    case 'running':
      return { text: '演化中…', cls: 'bg-old-gold text-white animate-celadon-pulse shadow-[0_0_12px_rgba(201,169,110,0.3)]', disabled: true, action: null }
    case 'paused-conflict':
      return { text: '等待决策', cls: 'border-2 border-cinnabar text-cinnabar opacity-60 cursor-not-allowed', disabled: true, action: null }
    case 'paused-branches':
      return { text: '选择分支', cls: 'border-2 border-cinnabar text-cinnabar opacity-60 cursor-not-allowed', disabled: true, action: null }
    case 'waiting_next_round':
      return { text: '继续演化', cls: 'bg-old-gold text-white hover:bg-old-gold/85 shadow-lg shadow-old-gold/25', disabled: false, action: 'start' }
    case 'ended':
      return { text: '重新开始', cls: 'border-2 border-cinnabar text-cinnabar hover:bg-cinnabar hover:text-white hover:animate-cinnabar-pulse', disabled: false, action: 'reset' }
    default:
      return { text: '开始演化', cls: 'bg-old-gold text-white hover:bg-old-gold/85 shadow-lg shadow-old-gold/25', disabled: false, action: 'start' }
  }
})

function onMainClick() {
  const act = buttonConfig.value.action
  if (act === 'start') {
    showIntervene.value = false
    emit('start-round')
  }
  if (act === 'reset') emit('reset')
}

// 干预输入
const showIntervene = ref(false)
const interveneText = ref('')
const interveneError = ref('')
async function submitIntervene() {
  const text = interveneText.value.trim()
  if (!text) return
  try {
    await evolution.sendIntervene(text)
    interveneText.value = ''
    showIntervene.value = false
    interveneError.value = ''
  } catch (e: unknown) {
    interveneError.value = (e as Error)?.message || '干预提交失败，请重试'
  }
}

// 导出小说
const showExport = computed(() =>
  evolution.currentRound >= 1 &&
  (derivedStatus.value === 'waiting_next_round' || derivedStatus.value === 'ended'),
)
const showNovelDrawer = ref(false)
async function exportNovel() {
  showNovelDrawer.value = true
  const hasExisting = await novel.checkExistingTask(evolution.currentEvolutionId || '')
  if (!hasExisting) {
    novel.startGeneration(
      evolution.currentSession?.world_id || '',
      evolution.currentEvolutionId || '',
    )
  }
}
</script>

<template>
  <div class="border-t border-border-light bg-frost">
    <!-- 干预输入行 -->
    <div v-if="showIntervene" class="px-6 py-2 flex gap-2 animate-fade-in">
      <input
        v-model="interveneText"
        type="text"
        maxlength="500"
        placeholder="输入自定义事件干预剧情走向…"
        class="flex-1 border border-border-light rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-old-gold/30"
        @keydown.enter="submitIntervene"
      />
      <BaseButton variant="primary" :disabled="!interveneText.trim()" @click="submitIntervene">
        提交
      </BaseButton>
    </div>
    <p v-if="interveneError" class="px-6 pb-1 text-xs text-cinnabar/80">{{ interveneError }}</p>

    <!-- 控制栏主体 -->
    <div class="h-14 flex items-center px-4 relative">
      <!-- 左侧：干预按钮 -->
      <div class="w-24 shrink-0">
        <button
          v-if="derivedStatus === 'waiting_next_round'"
          class="text-xs text-old-gold border border-old-gold/30 rounded px-2 py-0.5 hover:bg-old-gold hover:text-white transition-colors"
          @click="showIntervene = !showIntervene"
        >
          {{ showIntervene ? '取消干预' : '干预剧情' }}
        </button>
      </div>

      <!-- 中央：主按钮 -->
      <button
        :class="[buttonConfig.cls, 'absolute left-1/2 -translate-x-1/2 font-semibold tracking-wider rounded-lg px-6 py-2.5 transition-all duration-200 text-sm font-sans min-w-[140px] select-none', buttonConfig.disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer active:scale-[0.98]']"
        :disabled="buttonConfig.disabled"
        @click="onMainClick"
      >
        {{ buttonConfig.text }}
      </button>

      <!-- 右侧：导出 + SSE 指示 -->
      <div class="flex items-center gap-3 ml-auto">
        <!-- 导出小说（固定占位，避免 SSE 指示位移） -->
        <div class="w-[72px] shrink-0">
          <button
            v-if="showExport"
            class="text-xs text-old-gold border border-old-gold/30 rounded px-2 py-0.5 hover:bg-old-gold hover:text-white transition-colors"
            @click="exportNovel"
          >
            导出小说
          </button>
        </div>

        <!-- SSE 指示灯 -->
        <div class="flex items-center gap-1 shrink-0">
          <span
            class="w-2 h-2 rounded-full"
            :class="{
              'bg-celadon animate-celadon-pulse': connectionStatus === 'connected',
              'bg-persimmon animate-cinnabar-pulse': connectionStatus === 'connecting',
              'bg-cinnabar': connectionStatus === 'disconnected',
            }"
          />
          <span class="text-xs text-smoke/60">{{
            connectionStatus === 'connected' ? '已连接' :
            connectionStatus === 'connecting' ? '连接中…' :
            '断开'
          }}</span>
        </div>
      </div>
    </div>

    <!-- NovelDrawer -->
    <NovelDrawer
      :visible="showNovelDrawer"
      @close="showNovelDrawer = false; novel.resetNovelState()"
      @retry="exportNovel"
    />
  </div>
</template>
