<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEvolutionStore } from '@/stores/evolution'
import { useUserStore } from '@/stores/user'
import { deleteEvolution } from '@/api/client'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const router = useRouter()
const evolution = useEvolutionStore()
const user = useUserStore()

const loading = ref(false)
const error = ref('')

// 删除确认
const deleteTarget = ref<string | null>(null)
const deleteName = ref('')
const deleting = ref(false)

function formatDate(ms: number | string): string {
  const d = new Date(typeof ms === 'string' ? ms : ms)
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}年${m}月${day}日 ${h}:${min}`
}

function promptDelete(evolutionId: string, name: string) {
  deleteTarget.value = evolutionId
  deleteName.value = name
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteEvolution(deleteTarget.value, user.userId)
    deleteTarget.value = null
    await evolution.fetchSessions()
  } catch (e: unknown) {
    error.value = (e as Error)?.message || '删除失败'
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch((err: unknown) => {
      if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
        console.error('[EvolutionListPage] 登录重定向失败:', err)
      }
    })
    return
  }
  loading.value = true
  try {
    await evolution.fetchSessions()
  } catch (e: unknown) {
    error.value = (e as Error)?.message || '加载演化记录失败'
  } finally {
    loading.value = false
  }
})

function enterEvolution(evolutionId: string) {
  router.push(`/evolution/${evolutionId}`).catch(() => {})
}

const statusLabels: Record<string, string> = {
  idle: '待开始',
  running: '运行中',
  paused: '已暂停',
  waiting_next_round: '等待下一轮',
  ended: '已结束',
}

const statusColors: Record<string, string> = {
  idle: 'text-smoke',
  running: 'text-celadon',
  paused: 'text-persimmon',
  waiting_next_round: 'text-old-gold',
  ended: 'text-smoke/60',
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <h1 class="font-serif text-2xl font-bold text-ink mb-6">演化记录</h1>

    <div v-if="loading" class="flex justify-center py-24">
      <span class="w-8 h-8 border-2 border-old-gold border-t-transparent rounded-full animate-spin" />
    </div>

    <div v-else-if="error" class="text-center py-16">
      <p class="text-cinnabar text-sm mb-3">{{ error }}</p>
      <button class="text-sm text-old-gold hover:underline" @click="router.go(0)">重试</button>
    </div>

    <div v-else-if="evolution.sessions.length === 0" class="text-center py-16">
      <p class="text-smoke text-sm">暂无演化记录。在"世界"页面中进入一个世界开始演化。</p>
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
      <div
        v-for="s in evolution.sessions"
        :key="s.evolution_id"
        role="button"
        tabindex="0"
        class="relative bg-white rounded-lg border border-border-light p-5 cursor-pointer hover:border-old-gold/40 transition-all duration-300 hover:shadow-md hover:-translate-y-1 group"
        @click="enterEvolution(s.evolution_id)"
        @keydown.enter.prevent="enterEvolution(s.evolution_id)"
        @keydown.space.prevent="enterEvolution(s.evolution_id)"
      >
        <!-- 删除按钮 -->
        <button
          class="absolute -top-2.5 -right-2.5 w-7 h-7 flex items-center justify-center rounded-full border border-cinnabar/30 text-cinnabar/60 bg-white hover:bg-cinnabar hover:text-white hover:border-cinnabar opacity-0 group-hover:opacity-100 transition-all text-base font-light"
          title="删除记录"
          @click.stop="promptDelete(s.evolution_id, s.world_name || s.evolution_id)"
        >
          ×
        </button>
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-lg font-bold text-ink">{{ s.world_name || s.world_id }}</h3>
          <span class="text-xs" :class="statusColors[s.status] || 'text-smoke'">
            {{ statusLabels[s.status] || s.status }}
          </span>
        </div>
        <div class="flex gap-4 text-xs text-smoke">
          <span>第 {{ s.current_round }}/{{ s.max_rounds }} 轮</span>
          <span v-if="s.character_names?.length">{{ s.character_names.length }} 个角色</span>
        </div>
        <p class="text-xs text-smoke/60 mt-2">{{ formatDate(s.created_at) }}</p>
      </div>
    </div>

    <!-- 删除确认 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除演化记录"
      :message="`确定删除「${deleteName}」的演化记录吗？`"
      confirm-text="删除"
      @confirm="confirmDelete"
      @cancel="deleteTarget = null"
    />
  </div>
</template>
