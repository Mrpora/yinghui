<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWorldStore } from '@/stores/world'
import { useUserStore } from '@/stores/user'
import { deleteWorld } from '@/api/client'
import WorldCard from '@/components/world/WorldCard.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const router = useRouter()
const user = useUserStore()
const world = useWorldStore()

const errorMsg = ref('')

// 删除确认
const deleteTarget = ref<string | null>(null)
const deleteName = ref('')
const deleting = ref(false)

function promptDelete(worldId: string, name: string) {
  deleteTarget.value = worldId
  deleteName.value = name
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteWorld(deleteTarget.value, user.userId)
    deleteTarget.value = null
    await world.fetchWorlds()
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '删除失败'
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch((err: unknown) => {
      if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
        console.error('[WorldListPage] 登录重定向失败:', err)
      }
    })
    return
  }
  try {
    await world.fetchWorlds()
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '加载世界列表失败'
  }
})

function goCreateWorld() {
  router.push('/worlds/create').catch((err: unknown) => {
    if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
      console.error('[WorldListPage] 导航到创建页面失败:', err)
    }
  })
}

function goWorldDetail(worldId: string) {
  router.push(`/worlds/${worldId}`).catch((err: unknown) => {
    if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
      console.error('[WorldListPage] 导航到世界详情失败:', err)
    }
  })
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <div class="flex items-center justify-between mb-6">
      <h1 class="font-serif text-2xl font-bold text-ink">世界</h1>
      <button
        class="px-4 py-2 text-sm text-old-gold border border-old-gold rounded-lg hover:bg-old-gold hover:text-white transition-colors"
        @click="goCreateWorld"
      >
        + 创建
      </button>
    </div>

    <div
      v-if="errorMsg"
      class="mb-4 p-3 bg-cinnabar/10 border border-cinnabar/30 rounded-lg text-sm text-cinnabar"
    >
      {{ errorMsg }}
      <button class="ml-2 underline" @click="errorMsg = ''">关闭</button>
    </div>

    <div v-if="world.loading" class="flex justify-center py-24">
      <span class="w-8 h-8 border-2 border-old-gold border-t-transparent rounded-full animate-spin" />
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
      <WorldCard
        v-for="w in world.worlds"
        :key="w.world_id"
        :world="w"
        @click="goWorldDetail(w.world_id)"
        @delete="promptDelete(w.world_id, w.name)"
      />
    </div>

    <!-- 删除确认 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除世界"
      :message="`确定删除「${deleteName}」吗？该世界下的演化记录和小说也会随之失效。`"
      confirm-text="删除"
      @confirm="confirmDelete"
      @cancel="deleteTarget = null"
    />
  </div>
</template>
