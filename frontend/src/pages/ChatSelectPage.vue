<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useChatStore } from '@/stores/chat'
import CharacterCard from '@/components/chat/CharacterCard.vue'

const router = useRouter()
const route = useRoute()
const novel = useNovelStore()
const chat = useChatStore()

const selectedNovelId = ref('')

onMounted(async () => {
  await novel.fetchNovels()
  const routeNovelId = (route.query.novelId as string) || ''
  if (routeNovelId && novel.novels.some(n => n.novel_id === routeNovelId)) {
    selectedNovelId.value = routeNovelId
  } else if (novel.novels.length > 0) {
    selectedNovelId.value = novel.novels[0].novel_id
  }
  if (selectedNovelId.value) {
    await chat.fetchCharacters(selectedNovelId.value)
  }
})

async function onNovelChange() {
  if (selectedNovelId.value) {
    await chat.fetchCharacters(selectedNovelId.value)
  }
}

function startChat(characterId: string) {
  chat.activeCharacterId = characterId
  router.push({
    name: 'chat',
    query: { novelId: selectedNovelId.value, characterId },
  }).catch((err: any) => {
    if (err?.name !== 'NavigationDuplicated') throw err
  })
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <h1 class="font-serif text-2xl font-bold text-ink mb-6">选择对话角色</h1>

    <!-- 小说选择 -->
    <div class="mb-6">
      <select
        v-model="selectedNovelId"
        @change="onNovelChange"
        class="border border-border-light rounded-lg px-4 py-2 text-sm text-ink bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30"
      >
        <option value="" disabled>请选择一部小说…</option>
        <option v-for="n in novel.novels" :key="n.novel_id" :value="n.novel_id">
          {{ n.title }}
        </option>
      </select>
    </div>

    <!-- 未选小说 -->
    <div v-if="!selectedNovelId" class="text-center py-12">
      <p class="text-smoke text-sm">选择一部小说后查看可对话的角色</p>
    </div>

    <!-- 角色网格 -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div v-if="chat.characters.length === 0" class="col-span-full text-center py-12">
        <p class="text-smoke text-sm">该小说暂无可对话角色</p>
      </div>

      <CharacterCard
        v-for="ch in chat.characters"
        :key="ch.id"
        :character="ch"
        @start-chat="startChat(ch.id)"
      />
    </div>
  </div>
</template>
