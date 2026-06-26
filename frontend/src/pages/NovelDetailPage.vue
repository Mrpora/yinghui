<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { marked } from 'marked'
import { useRoute, useRouter } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import { useUserStore } from '@/stores/user'
import BaseButton from '@/components/ui/BaseButton.vue'

const route = useRoute()
const router = useRouter()
const novel = useNovelStore()
const user = useUserStore()

const novelId = route.params.novelId as string | undefined

const loading = ref(true)
const error = ref('')

const importLoading = ref(false)
const importError = ref('')
const importSuccess = ref(false)
let importMsgTimer: ReturnType<typeof setTimeout> | null = null

let pollTimer: ReturnType<typeof setInterval> | null = null

const contentRef = ref<HTMLElement | null>(null)

function blockCopy(e: ClipboardEvent) { e.preventDefault() }
function blockContext(e: MouseEvent) { e.preventDefault() }
function blockDrag(e: DragEvent) { e.preventDefault() }

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/')
    return
  }
  if (!novelId) {
    router.replace('/novels')
    return
  }
  try {
    await novel.fetchNovelDetail(novelId)
  } catch (e: unknown) {
    error.value = (e as Error)?.message || '加载小说详情失败'
  } finally {
    loading.value = false
  }

  // 防盗保护：等 DOM 渲染后绑定事件
  await nextTick()
  const el = contentRef.value
  if (el) {
    el.addEventListener('copy', blockCopy)
    el.addEventListener('cut', blockCopy)
    el.addEventListener('contextmenu', blockContext)
    el.addEventListener('dragstart', blockDrag)
  }
})

watch(() => novel.currentNovel?.task_status, (status) => {
  if (status === 'processing' && novelId) {
    if (!pollTimer) {
      pollTimer = setInterval(async () => {
        try {
          await novel.fetchNovelDetail(novelId!)
          if (novel.currentNovel?.task_status !== 'processing') {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
          }
        } catch { /* 轮询失败静默忽略 */ }
      }, 3000)
    }
  } else {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }
})

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (importMsgTimer) { clearTimeout(importMsgTimer); importMsgTimer = null }
  const el = contentRef.value
  if (el) {
    el.removeEventListener('copy', blockCopy)
    el.removeEventListener('cut', blockCopy)
    el.removeEventListener('contextmenu', blockContext)
    el.removeEventListener('dragstart', blockDrag)
  }
})

async function importCharacters() {
  importLoading.value = true
  importError.value = ''
  importSuccess.value = false
  if (importMsgTimer) { clearTimeout(importMsgTimer); importMsgTimer = null }
  try {
    await novel.importCharacters(novelId!)
    importSuccess.value = true
    importMsgTimer = setTimeout(() => { importSuccess.value = false }, 5000)
  } catch (e: unknown) {
    importError.value = (e as Error)?.message || '角色导入失败，请重试'
    importMsgTimer = setTimeout(() => { importError.value = '' }, 5000)
  } finally {
    importLoading.value = false
  }
}

function formatDate(ms: number | string): string {
  const d = new Date(typeof ms === 'string' ? ms : ms)
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}年${m}月${day}日 ${h}:${min}`
}

const renderedContent = computed(() => {
  const raw = novel.currentNovel?.content
  if (!raw) return ''
  return marked(raw, { breaks: true }) as string
})

function goBack() {
  router.push('/novels').catch((err: unknown) => {
    if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
      error.value = '页面跳转失败，请重试'
    }
  })
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <button class="text-smoke hover:text-ink transition-colors text-sm mb-4" @click="goBack">
      ← 返回小说列表
    </button>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center py-16">
      <span class="text-smoke text-sm animate-celadon-pulse">加载中…</span>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="error" class="text-center py-16">
      <p class="text-cinnabar text-sm mb-3">{{ error }}</p>
      <button class="text-sm text-old-gold hover:underline" @click="router.go(0)">重试</button>
    </div>

    <!-- 小说内容 -->
    <template v-else-if="novel.currentNovel">
      <div class="flex items-start justify-between mb-4">
        <div>
          <h1 class="font-serif text-2xl font-bold text-ink">{{ novel.currentNovel.title || '(未命名小说)' }}</h1>
          <p class="text-smoke text-xs mt-1">{{ formatDate(novel.currentNovel.created_at) }}</p>
        </div>
        <div class="flex flex-col items-end">
          <BaseButton variant="secondary" :disabled="importLoading" @click="importCharacters">
            {{ importLoading ? '导入中…' : '导入角色到对话系统' }}
          </BaseButton>
          <p v-if="importSuccess" class="text-moss text-xs mt-1">角色已成功导入到对话系统</p>
          <p v-if="importError" class="text-cinnabar text-xs mt-1">{{ importError }}</p>
        </div>
      </div>

      <div ref="contentRef" class="bg-paper rounded-xl border border-border-light p-8 select-none" style="-webkit-touch-callout: none;">
        <div v-if="novel.currentNovel.content" class="prose prose-stone max-w-none" v-html="renderedContent" style="font-family: 'NovelObfuscated', 'Noto Serif SC', serif;" />
        <template v-else-if="novel.currentNovel.task_status === 'processing'">
          <div class="flex flex-col items-center justify-center py-16 gap-3">
            <span class="w-10 h-10 border-2 border-old-gold border-t-transparent rounded-full animate-spin" />
            <p class="text-old-gold text-sm animate-celadon-pulse">生成中…</p>
          </div>
        </template>
        <p v-else class="text-smoke text-sm">暂无内容</p>
      </div>
    </template>
  </div>
</template>
