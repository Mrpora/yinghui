<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'
import { getCareLevel, setCareLevel } from '@/api/client'

const router = useRouter()
const user = useUserStore()
const novel = useNovelStore()
const chat = useChatStore()

const selectedNovelId = ref('')
const selectedCharacterId = ref('')
const careLevel = ref(80)
const loading = ref(false)
const errorMsg = ref('')

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch((err: unknown) => {
      if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
        console.error('[SettingsPage] 登录重定向失败:', err)
      }
    })
    return
  }
  try {
    await novel.fetchNovels()
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '加载小说列表失败'
    console.error('[SettingsPage] 加载小说列表失败:', e)
  }
})

async function onNovelChange() {
  if (selectedNovelId.value) {
    try {
      await chat.fetchCharacters(selectedNovelId.value)
    } catch (e: unknown) {
      errorMsg.value = (e as Error)?.message || '加载角色列表失败'
      console.error('[SettingsPage] 加载角色列表失败:', e)
    }
  }
  selectedCharacterId.value = ''
  careLevel.value = 80
}

async function onCharacterChange() {
  if (selectedCharacterId.value && selectedNovelId.value) {
    loading.value = true
    errorMsg.value = ''
    try {
      const res = await getCareLevel(user.userId, selectedNovelId.value, selectedCharacterId.value)
      careLevel.value = res.level
    } catch (e: unknown) {
      careLevel.value = 80
      errorMsg.value = (e as Error)?.message || '加载关怀等级失败'
      console.error('[SettingsPage] 加载关怀等级失败:', e)
    } finally {
      loading.value = false
    }
  } else {
    careLevel.value = 80
  }
}

async function handleChange() {
  if (selectedCharacterId.value && selectedNovelId.value) {
    errorMsg.value = ''
    try {
      await setCareLevel(user.userId, selectedNovelId.value, selectedCharacterId.value, careLevel.value)
    } catch (e: unknown) {
      errorMsg.value = (e as Error)?.message || '保存关怀等级失败'
      console.error('[SettingsPage] 保存关怀等级失败:', e)
    }
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 py-8 animate-fade-up">
    <h1 class="font-serif text-2xl font-bold text-ink mb-6">关怀设置</h1>

    <!-- 错误消息 -->
    <div
      v-if="errorMsg"
      role="alert"
      class="mb-4 p-3 bg-cinnabar/10 border border-cinnabar/30 rounded-lg text-sm text-cinnabar"
    >
      {{ errorMsg }}
      <button class="ml-2 underline" @click="errorMsg = ''">关闭</button>
    </div>

    <!-- 级联选择器 -->
    <div class="flex items-center gap-3 mb-8">
      <select
        v-model="selectedNovelId"
        @change="onNovelChange"
        class="border border-border-light rounded-lg px-3 py-1.5 text-sm text-smoke bg-white"
        aria-label="选择小说"
      >
        <option value="" disabled>选择小说</option>
        <option v-for="n in novel.novels" :key="n.novel_id" :value="n.novel_id">
          {{ n.title }}
        </option>
      </select>

      <select
        v-model="selectedCharacterId"
        @change="onCharacterChange"
        class="border border-border-light rounded-lg px-3 py-1.5 text-sm text-smoke bg-white"
        :disabled="!selectedNovelId"
        aria-label="选择角色"
      >
        <option value="" disabled>选择角色</option>
        <option v-for="ch in chat.characters" :key="ch.id" :value="ch.id">
          {{ ch.name }}
        </option>
      </select>
    </div>

    <!-- 关怀滑块 -->
    <div v-if="selectedCharacterId" class="bg-white rounded-xl border border-border-light p-6">
      <div v-if="loading" class="text-center">
        <span class="text-smoke text-sm animate-celadon-pulse">加载中…</span>
      </div>

      <div v-else>
        <div class="flex items-center justify-between mb-4">
          <span class="font-serif text-sm text-smoke">关怀等级</span>
          <span class="text-ink text-lg font-bold">{{ careLevel }}</span>
        </div>

        <input
          :value="careLevel"
          type="range"
          min="0"
          max="100"
          step="5"
          class="w-full accent-old-gold"
          aria-label="关怀等级滑块"
          @input="careLevel = Number(($event.target as HTMLInputElement).value)"
          @change="handleChange"
        />

        <div class="flex justify-between text-xs text-smoke/60 mt-2">
          <span>低 (0)</span>
          <span>默认 (80)</span>
          <span>高 (100)</span>
        </div>
      </div>
    </div>
  </div>
</template>
