// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { NovelItem, NovelDetail, TaskStatus } from '@/types'
import {
  generateNovel, getNovelTaskStatus, listNovels, getNovelDetail,
  deleteNovel, importNovelCharacters, checkNovelTask,
} from '@/api/client'
import { useUserStore } from './user'

export const useNovelStore = defineStore('novel', () => {
  const novels = ref<NovelItem[]>([])
  const currentNovel = ref<NovelDetail | null>(null)
  const isGenerating = ref(false)
  const taskId = ref<string | null>(null)
  const taskStatus = ref<string | null>(null)
  const progressMessage = ref('')
  const existingTask = ref(false)

  async function fetchNovels() {
    const user = useUserStore()
    if (!user.userId) return
    const res = await listNovels(user.userId)
    novels.value = res.novels
  }

  async function startGeneration(worldId: string, evolutionId: string) {
    const user = useUserStore()
    isGenerating.value = true
    taskStatus.value = 'processing'
    progressMessage.value = '正在启动生成...'
    const res = await generateNovel(user.userId, worldId, evolutionId)
    taskId.value = res.task_id
    return res
  }

  async function checkExistingTask(evolutionId: string): Promise<boolean> {
    if (!evolutionId) return false
    const res = await checkNovelTask(evolutionId)
    existingTask.value = res.has_task
    return res.has_task
  }

  function resetNovelState() {
    isGenerating.value = false
    taskId.value = null
    taskStatus.value = null
    progressMessage.value = ''
    existingTask.value = false
    currentNovel.value = null
  }

  async function pollTaskStatus(id: string) {
    const res = await getNovelTaskStatus(id)
    taskStatus.value = res.status
    if (res.error) progressMessage.value = res.error
    return res
  }

  async function fetchNovelDetail(novelId: string) {
    const res = await getNovelDetail(novelId)
    currentNovel.value = res
    return res
  }

  async function removeNovel(novelId: string) {
    const user = useUserStore()
    await deleteNovel(novelId, user.userId)
    await fetchNovels()
  }

  async function importCharacters(novelId: string) {
    const user = useUserStore()
    return importNovelCharacters(novelId, user.userId)
  }

  function handleNovelSSE(type: string, data: Record<string, unknown>) {
    switch (type) {
      case 'chapter_start':
      case 'progress':
        progressMessage.value = (data.message as string) || ''
        break
      case 'round':
        progressMessage.value = `写作中...`
        break
      case 'completed':
        isGenerating.value = false
        taskStatus.value = 'completed'
        if (data.novel_id) currentNovel.value = { novel_id: data.novel_id as string } as NovelDetail
        break
    }
  }

  return {
    novels, currentNovel, isGenerating, taskId, taskStatus, progressMessage,
    existingTask,
    fetchNovels, startGeneration, checkExistingTask, resetNovelState,
    pollTaskStatus, fetchNovelDetail, removeNovel,
    importCharacters, handleNovelSSE,
  }
})
