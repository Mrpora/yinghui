<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listMemories, deleteMemory, updateMemoryExpiry } from '@/api/client'
import { useUserStore } from '@/stores/user'
import type { MemoryItem } from '@/types'
import MemoryItemCard from './MemoryItem.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const props = defineProps<{
  novelId: string | null
  characterId?: string | null
  compact?: boolean
}>()

const emit = defineEmits<{
  forget: []
}>()

const user = useUserStore()

const memories = ref<MemoryItem[]>([])
const loading = ref(false)

async function fetchMemories() {
  if (!props.novelId || !user.userId) return
  loading.value = true
  try {
    const res = await listMemories(user.userId, props.novelId, props.characterId || undefined)
    memories.value = res.memories
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh: fetchMemories })

onMounted(() => {
  fetchMemories()
})

async function handleDelete(memoryId: string) {
  await deleteMemory(memoryId)
  memories.value = memories.value.filter(m => m.id !== memoryId)
}

async function handleUpdateExpiry(memoryId: string, expiresAt: number | null) {
  await updateMemoryExpiry(memoryId, expiresAt)
  const m = memories.value.find(m => m.id === memoryId)
  if (m) m.expires_at = expiresAt
}

const showForgetConfirm = ref(false)
</script>

<template>
  <div class="w-80 shrink-0 border-l border-border-light flex flex-col h-full">
    <!-- 标题 -->
    <div class="px-3 py-2.5 border-b border-border-light flex items-center justify-between">
      <h3 class="font-serif text-ink text-sm">记忆（{{ memories.length }}条）</h3>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <span class="text-smoke text-xs animate-celadon-pulse">加载中…</span>
    </div>

    <!-- 记忆列表 -->
    <div v-else class="flex-1 overflow-y-auto px-3 py-2 space-y-2">
      <div v-if="memories.length === 0" class="flex items-center justify-center h-full">
        <p class="text-smoke/50 text-sm">暂无记忆</p>
      </div>

      <MemoryItemCard
        v-for="m in memories"
        :key="m.id"
        :memory="m"
        @update-expiry="(exp: number | null) => handleUpdateExpiry(m.id, exp)"
        @delete="handleDelete(m.id)"
      />
    </div>

    <!-- 忘记我 -->
    <div v-if="memories.length > 0" class="px-3 py-2 border-t border-border-light">
      <button
        class="text-xs text-cinnabar/60 hover:text-cinnabar transition-colors"
        @click="showForgetConfirm = true"
      >
        忘记我
      </button>
    </div>
  </div>

  <ConfirmDialog
    :visible="showForgetConfirm"
    title="确认清除"
    message="确定要清除该角色对你的所有记忆吗？此操作不可撤销。"
    confirm-variant="danger"
    confirm-text="确认清除"
    @confirm="emit('forget'); showForgetConfirm = false"
    @cancel="showForgetConfirm = false"
  />
</template>
