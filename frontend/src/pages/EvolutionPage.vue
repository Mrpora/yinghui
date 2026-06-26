<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRoute, useRouter, onBeforeRouteUpdate } from 'vue-router'
import { useEvolutionStore } from '@/stores/evolution'
import { useUserStore } from '@/stores/user'
import { useSSE } from '@/composables/useSSE'
import type { WorldConfig } from '@/types'

import WorldPanel from '@/components/world/WorldPanel.vue'
import CharacterPanel from '@/components/evolution/CharacterPanel.vue'
import Timeline from '@/components/evolution/Timeline.vue'
import EvolutionControl from '@/components/evolution/EvolutionControl.vue'
import BranchDrawer from '@/components/evolution/BranchDrawer.vue'

// ═══ Props ═══
const props = defineProps<{
  evolutionId?: string
}>()

// ═══ Router / Stores ═══
const route = useRoute()
const router = useRouter()
const evolution = useEvolutionStore()
const user = useUserStore()

// ═══ Evolution ID ═══
const eid = computed(() => props.evolutionId || (route.params.evolutionId as string | undefined))

// ═══ SSE ═══
const { connectionStatus, connect: sseConnect, disconnect: sseDisconnect, on: sseOn } = useSSE()

// ═══ World Detail ═══
const worldDetail = ref<WorldConfig | null>(null)

// ═══ Branch Drawer ═══
const showBranchDrawer = ref(false)
const branchTrigger = ref(0)

// ═══ Character Color Map ═══
const characterColorMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const c of worldDetail.value?.characters ?? []) {
    if (c.name && c.accent_color) map[c.name] = c.accent_color
  }
  return map
})

// ═══ Connection Warning ═══
const connectionWarning = computed(() =>
  connectionStatus.value === 'disconnected' && evolution.currentEvolutionId ? 'SSE 连接已断开，演化数据可能不是最新' : ''
)

// ═══ SSE Handler ═══
onMounted(() => {
  sseOn('*', (msg: unknown) => {
    const m = msg as Record<string, unknown>
    if (m && m.type) {
      try {
        evolution.handleSSEEvent(m.type as string, m)
        // 替代原 watch(isPaused)：SSE 事件处理后检查是否需要弹出分支抽屉
        if (evolution.isPaused) {
          branchTrigger.value++
          showBranchDrawer.value = true
        }
      } catch (_err) {
        // SSE 事件处理失败，静默忽略
      }
    }
  })
  // 替代原 watch(channel) + immediate：显式连接 SSE
  if (eid.value && eid.value !== 'undefined' && eid.value !== 'null' && user.userId) {
    sseConnect(eid.value, user.userId)
  }
})

// ═══ Initial Load ═══
const isLoading = ref(true)
const loadError = ref('')

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch((_err: unknown) => {
      // 登录重定向失败，静默忽略
    })
    return
  }
  if (!eid.value || eid.value === 'undefined' || eid.value === 'null') return

  try {
    const detail = await evolution.fetchDetail(eid.value)
    worldDetail.value = detail.world_config ?? null
    await evolution.fetchTimeline(eid.value)
    // 恢复暂停状态：如果会话上次停在暂停态，弹出分支抽屉
    if (evolution.isPaused) {
      showBranchDrawer.value = true
    }
  } catch (e: unknown) {
    loadError.value = (e as Error)?.message || '加载演化数据失败'
  } finally {
    isLoading.value = false
  }
})

// 离开页面时断开 SSE
onUnmounted(() => {
  sseDisconnect()
})

// 演化切换时重连并加载数据（路由参数变化，组件不重新挂载）
onBeforeRouteUpdate(async (to) => {
  sseDisconnect()
  const newEid = to.params.evolutionId as string | undefined
  if (newEid && user.userId) {
    isLoading.value = true
    try {
      const detail = await evolution.fetchDetail(newEid)
      worldDetail.value = detail.world_config ?? null
      await evolution.fetchTimeline(newEid)
      sseConnect(newEid, user.userId)
      // 恢复暂停状态
      if (evolution.isPaused) {
        showBranchDrawer.value = true
      }
    } catch (e: unknown) {
      loadError.value = (e as Error)?.message || '加载演化数据失败'
    } finally {
      isLoading.value = false
    }
  }
})

// ═══ Actions ═══
const roundError = ref('')
const branchError = ref('')

async function startRound() {
  roundError.value = ''
  try {
    await evolution.runRound()
  } catch (e: unknown) {
    roundError.value = (e as Error)?.message || '启动演化失败，请重试'
  }
}

async function selectBranch(index: number) {
  branchError.value = ''
  try {
    await evolution.pickBranch(index)
    showBranchDrawer.value = false
  } catch (e: unknown) {
    branchError.value = (e as Error)?.message || '选择分支失败，请重试'
  }
}

async function submitCustomEvent(text: string) {
  branchError.value = ''
  try {
    await evolution.sendCustomEvent(text)
    showBranchDrawer.value = false
  } catch (e: unknown) {
    branchError.value = (e as Error)?.message || '提交事件失败，请重试'
  }
}

function reset() {
  evolution.reset()
  router.push('/worlds').catch((_err: unknown) => {
    // 导航失败，静默忽略
  })
}
</script>

<template>
  <!-- ═══ 三层布局 (桌面端) ═══ -->
  <div class="h-[calc(100vh-48px)] flex flex-col overflow-hidden">
    <!-- 页面标题栏 -->
    <div class="h-10 shrink-0 flex items-center px-4 border-b border-border-light bg-white/50">
      <button
        class="text-sm text-smoke hover:text-ink transition-colors flex items-center gap-1"
        @click="router.push('/evolution')"
      >
        ← 返回
      </button>
    </div>

    <div class="flex-1 flex overflow-hidden">
    <!-- 加载/错误状态 -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center">
      <span class="text-smoke text-sm animate-celadon-pulse">加载中…</span>
    </div>
    <div v-else-if="loadError" class="flex-1 flex flex-col items-center justify-center gap-3">
      <p class="text-cinnabar text-sm">{{ loadError }}</p>
      <button class="text-sm text-old-gold hover:underline" @click="router.go(0)">重试</button>
    </div>
    <template v-else>
    <!-- 左：世界面板（桌面端内联，移动端隐藏） -->
    <div class="hidden md:contents">
      <WorldPanel
        :world-name="worldDetail?.world.name"
        :world-history="worldDetail?.world.world_history"
        :rules="worldDetail?.world.rules"
      />
    </div>

    <!-- 中：时间线 + 控制栏 -->
    <div class="flex-1 flex flex-col overflow-hidden min-w-0">
      <Timeline
        :events="evolution.timeline"
        :is-running="evolution.isRunning"
        :character-colors="characterColorMap"
      />
      <p v-if="connectionWarning" class="px-4 py-1 text-xs text-old-gold/80">{{ connectionWarning }}</p>
      <p v-if="roundError" class="px-4 py-1 text-xs text-cinnabar/80">{{ roundError }}</p>
      <EvolutionControl
        :connection-status="connectionStatus"
        @start-round="startRound"
        @reset="reset"
      />
    </div>

    <!-- 右：角色面板（桌面端内联，移动端隐藏） -->
    <div class="hidden md:contents">
      <CharacterPanel
        :characters="(worldDetail?.characters ?? []).map(c => ({
          name: c?.name ?? '未知',
          identity: c?.identity ?? '',
          personality: c?.personality ?? '',
          speech_style: c?.speech_style ?? '',
          goal: c?.goal ?? '',
          backstory: c?.backstory ?? '',
          inner_thoughts: undefined,
          accent_color: c?.accent_color ?? '',
        }))"
      />
    </div>
    </template>
  </div>

  <!-- ═══ 分支抽屉（已自带 Teleport to body） ═══ -->
  <BranchDrawer
    :visible="showBranchDrawer"
    :branches="evolution.branches"
    :reason="evolution.pauseReason || 'branches'"
    @select-branch="selectBranch"
    @submit-custom="submitCustomEvent"
    @close="showBranchDrawer = false"
  />
  <p v-if="branchError" class="fixed bottom-4 left-1/2 -translate-x-1/2 bg-cinnabar/10 text-cinnabar text-sm px-4 py-2 rounded-lg z-50">{{ branchError }}</p>
  </div>
</template>
