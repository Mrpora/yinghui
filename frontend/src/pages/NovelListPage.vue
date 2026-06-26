<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useUserStore } from '@/stores/user'
import { deleteNovel } from '@/api/client'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const router = useRouter()
const novel = useNovelStore()
const user = useUserStore()

const loading = ref(false)
const error = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// 列表中存在生成中的小说时轮询刷新
watch(() => novel.novels, (list) => {
  const hasProcessing = list.some(n => n.task_status === 'processing')
  if (hasProcessing && !pollTimer) {
    pollTimer = setInterval(() => {
      novel.fetchNovels().catch(() => { /* 轮询失败静默忽略 */ })
    }, 3000)
  } else if (!hasProcessing && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}, { immediate: true })

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

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

function promptDelete(novelId: string, name: string) {
  deleteTarget.value = novelId
  deleteName.value = name
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await deleteNovel(deleteTarget.value, user.userId)
    deleteTarget.value = null
    await novel.fetchNovels()
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
        console.error('[NovelListPage] 登录重定向失败:', err)
      }
    })
    return
  }
  loading.value = true
  try {
    await novel.fetchNovels()
  } catch (e: unknown) {
    error.value = (e as Error)?.message || '加载小说列表失败'
  } finally {
    loading.value = false
  }
})

function goToNovel(novelId: string) {
  router.push(`/novels/${novelId}`).catch((err: unknown) => {
    if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
      error.value = '页面跳转失败，请重试'
    }
  })
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <h1 class="font-serif text-2xl font-bold text-ink mb-6">小说</h1>

    <!-- 加载中 -->
    <div v-if="loading" class="flex justify-center py-24">
      <span class="w-8 h-8 border-2 border-old-gold border-t-transparent rounded-full animate-spin" />
    </div>

    <!-- 加载失败 -->
    <div v-else-if="error" class="text-center py-16">
      <p class="text-cinnabar text-sm mb-3">{{ error }}</p>
      <button class="text-sm text-old-gold hover:underline" @click="router.go(0)">重试</button>
    </div>

    <!-- 空状态 -->
    <div v-else-if="novel.novels.length === 0" class="text-center py-16">
      <p class="text-smoke text-sm">暂无生成的小说。在演化页面中使用"导出小说"功能。</p>
    </div>

    <!-- 列表 -->
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
      <div
        v-for="n in novel.novels"
        :key="n.novel_id"
        role="button"
        tabindex="0"
        class="relative bg-white rounded-lg border border-border-light p-5 cursor-pointer hover:border-old-gold/40 transition-all duration-300 hover:shadow-md hover:-translate-y-1 group"
        @click="goToNovel(n.novel_id)"
        @keydown.enter.prevent="goToNovel(n.novel_id)"
        @keydown.space.prevent="goToNovel(n.novel_id)"
      >
        <!-- 删除按钮 -->
        <button
          class="absolute -top-2.5 -right-2.5 w-7 h-7 flex items-center justify-center rounded-full border border-cinnabar/30 text-cinnabar/60 bg-white hover:bg-cinnabar hover:text-white hover:border-cinnabar opacity-0 group-hover:opacity-100 transition-all text-base font-light"
          title="删除小说"
          @click.stop="promptDelete(n.novel_id, n.title || '(未命名小说)')"
        >
          ×
        </button>
        <div class="flex items-center gap-2">
          <h3 class="font-serif text-lg text-ink font-bold">{{ n.title || '(未命名小说)' }}</h3>
          <span
            v-if="n.task_status === 'processing'"
            class="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-old-gold/10 text-old-gold"
          >
            <span class="w-2 h-2 border border-old-gold border-t-transparent rounded-full animate-spin" />
            生成中
          </span>
        </div>
        <p class="text-xs text-smoke/60 mt-2">{{ formatDate(n.created_at) }}</p>
      </div>
    </div>

    <!-- 删除确认 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除小说"
      :message="`确定删除「${deleteName}」吗？`"
      confirm-text="删除"
      @confirm="confirmDelete"
      @cancel="deleteTarget = null"
    />
  </div>
</template>
