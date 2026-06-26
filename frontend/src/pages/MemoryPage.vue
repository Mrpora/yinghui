<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'
import { listMemories, deleteMemory, updateMemoryExpiry, getLatestChatNovel, getCareLevel, setCareLevel } from '@/api/client'
import type { MemoryItem } from '@/types'
import MemoryItemCard from '@/components/memory/MemoryItem.vue'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const novel = useNovelStore()
const chat = useChatStore()

const novelId = ref((route.query.novelId as string) || '')
const memories = ref<MemoryItem[]>([])
const careLevels = ref<Record<string, number>>({})

const loading = ref(false)
const memoriesLoading = ref(false)
const errorMsg = ref('')

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch((err: unknown) => {
      if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
        console.error('[MemoryPage] 登录重定向失败:', err)
      }
    })
    return
  }

  loading.value = true
  try {
    await novel.fetchNovels()
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '加载小说列表失败'
    loading.value = false
    return
  }

  if (!novelId.value) {
    try {
      const res = await getLatestChatNovel(user.userId)
      novelId.value = res.novel_id || novel.novels[0]?.novel_id || ''
    } catch {
      novelId.value = novel.novels[0]?.novel_id || ''
    }
  }

  if (novelId.value) {
    await loadCharacters()
    await Promise.all([loadCareLevels(), loadMemories()])
    updateUrl()
  }
  loading.value = false
})

async function loadCareLevels() {
  if (!novelId.value || chat.characters.length === 0) return
  const levels: Record<string, number> = {}
  await Promise.all(chat.characters.map(async (ch) => {
    try {
      const res = await getCareLevel(user.userId, novelId.value, ch.id)
      levels[ch.id] = res.level
    } catch {
      levels[ch.id] = 80
    }
  }))
  careLevels.value = levels
}

async function loadCharacters() {
  if (!novelId.value) return
  try {
    await chat.fetchCharacters(novelId.value)
  } catch (e: unknown) {
    console.error('[MemoryPage] 加载角色失败:', e)
  }
}

async function loadMemories() {
  if (!novelId.value) return
  memoriesLoading.value = true
  errorMsg.value = ''
  try {
    const res = await listMemories(user.userId, novelId.value)
    memories.value = res.memories
  } catch (e: unknown) {
    memories.value = []
    errorMsg.value = (e as Error)?.message || '加载记忆失败'
  } finally {
    memoriesLoading.value = false
  }
}

function updateUrl() {
  router.replace({ name: 'memories', query: { novelId: novelId.value } }).catch((err: unknown) => {
    if ((err as { name?: string })?.name !== 'NavigationDuplicated') throw err
  })
}

async function selectNovel(id: string) {
  if (id === novelId.value) return
  novelId.value = id
  memories.value = []
  careLevels.value = {}
  await loadCharacters()
  await Promise.all([loadCareLevels(), loadMemories()])
  updateUrl()
}

async function handleDelete(memoryId: string) {
  try {
    await deleteMemory(memoryId)
    memories.value = memories.value.filter(m => m.id !== memoryId)
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '删除记忆失败'
  }
}

async function handleUpdateExpiry(memoryId: string, expiresAt: number | null) {
  try {
    await updateMemoryExpiry(memoryId, expiresAt)
    const m = memories.value.find(m => m.id === memoryId)
    if (m) m.expires_at = expiresAt
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '更新过期时间失败'
  }
}

async function handleCareLevelChange(characterId: string, value: number) {
  if (!novelId.value) return
  try {
    await setCareLevel(user.userId, novelId.value, characterId, value)
    careLevels.value[characterId] = value
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '更新关怀等级失败'
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 py-8 animate-fade-up">
    <h1 class="font-serif text-2xl font-bold text-ink mb-6">角色记忆</h1>

    <!-- 错误消息 -->
    <div
      v-if="errorMsg"
      role="alert"
      class="mb-4 p-3 bg-cinnabar/10 border border-cinnabar/30 rounded-lg text-sm text-cinnabar flex items-center"
    >
      <span class="flex-1">{{ errorMsg }}</span>
      <button class="ml-2 underline" @click="errorMsg = ''">关闭</button>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="text-center py-12">
      <span class="text-smoke text-sm animate-celadon-pulse">加载中…</span>
    </div>

    <template v-else>
      <!-- 小说下拉选择 -->
      <div v-if="novel.novels.length > 0" class="mb-6">
        <select
          :value="novelId"
          @change="selectNovel(($event.target as HTMLSelectElement).value)"
          class="w-full max-w-xs px-4 py-2 rounded-lg border border-frost bg-white text-ink text-sm focus:outline-none focus:border-old-gold transition-colors appearance-none bg-no-repeat"
          style="background-image: url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22%3E%3Cpath d=%22M7 10l5 5 5-5z%22/%3E%3C/svg%3E'); background-position: right 12px center;"
        >
          <option v-for="n in novel.novels" :key="n.novel_id" :value="n.novel_id">
            {{ n.title }}
          </option>
        </select>
      </div>

      <!-- 记忆回响设置 -->
      <div v-if="chat.characters.length > 0" class="bg-frost/30 rounded-xl p-4 sm:p-6 mb-4 space-y-4">
        <div v-for="ch in chat.characters" :key="ch.id">
          <p class="text-sm text-smoke mb-2">{{ ch.name }} 记忆回响</p>
          <div class="flex items-center gap-3">
            <input
              type="range"
              min="0"
              max="100"
              :value="careLevels[ch.id] ?? 80"
              @input="careLevels[ch.id] = Number(($event.target as HTMLInputElement).value)"
              @change="handleCareLevelChange(ch.id, careLevels[ch.id])"
              class="flex-1 accent-cinnabar"
            />
            <span class="text-sm text-smoke w-8 text-right">{{ careLevels[ch.id] ?? 80 }}</span>
          </div>
        </div>
      </div>

      <!-- 记忆加载 -->
      <div v-if="memoriesLoading" class="text-center py-12">
        <span class="text-smoke text-sm animate-celadon-pulse">加载记忆…</span>
      </div>

      <!-- 记忆列表 -->
      <div v-else class="space-y-2">
        <div v-if="memories.length === 0" class="text-center py-12">
          <p class="text-smoke text-sm">暂无记忆</p>
        </div>
        <MemoryItemCard
          v-for="m in memories"
          :key="m.id"
          :memory="m"
          @update-expiry="(exp: number | null) => handleUpdateExpiry(m.id, exp)"
          @delete="handleDelete(m.id)"
        />
      </div>
    </template>
  </div>
</template>
