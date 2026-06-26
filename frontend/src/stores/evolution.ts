// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SessionState, TimelineEvent, Branch } from '@/types'
import {
  listEvolutions, createEvolution, getEvolutionDetail, deleteEvolution,
  startRound, selectBranch, submitCustomEvent, intervene,
  getTimeline,
} from '@/api/client'
import { useUserStore } from './user'

export const useEvolutionStore = defineStore('evolution', () => {
  // 列表
  const sessions = ref<SessionState[]>([])
  // 当前演化
  const currentEvolutionId = ref<string | null>(null)
  const currentSession = ref<SessionState | null>(null)
  // 时间线
  const timeline = ref<TimelineEvent[]>([])
  const relationships = ref<{ from: string; to: string; relationship: string }[]>([])
  // 分支
  const branches = ref<Branch[]>([])
  const isPaused = ref(false)
  const pauseReason = ref<'conflict' | 'branches' | null>(null)
  const isRunning = ref(false)

  const currentRound = computed(() => currentSession.value?.current_round ?? 0)
  const maxRounds = computed(() => currentSession.value?.max_rounds ?? 0)

  async function fetchSessions() {
    const user = useUserStore()
    if (!user.userId) return
    const res = await listEvolutions(user.userId)
    sessions.value = res.sessions
  }

  async function create(worldId: string) {
    const user = useUserStore()
    const res = await createEvolution(user.userId, worldId)
    currentEvolutionId.value = res.evolution_id
    await fetchSessions()
    return res
  }

  async function fetchDetail(evolutionId: string) {
    const user = useUserStore()
    const res = await getEvolutionDetail(evolutionId, user.userId)
    currentSession.value = res
    currentEvolutionId.value = evolutionId
    // 从 API 响应恢复运行/暂停状态（SSE 不会回放历史事件）
    isRunning.value = res.status === 'running'
    isPaused.value = res.status === 'paused'
    if (res.status !== 'paused') {
      pauseReason.value = null
      branches.value = []
    }
    return res
  }

  async function remove(evolutionId: string) {
    const user = useUserStore()
    await deleteEvolution(evolutionId, user.userId)
    if (currentEvolutionId.value === evolutionId) {
      currentEvolutionId.value = null
      currentSession.value = null
    }
    await fetchSessions()
  }

  async function runRound() {
    if (!currentEvolutionId.value) return
    const user = useUserStore()
    isRunning.value = true
    const res = await startRound(currentEvolutionId.value, user.userId)
    if (currentSession.value) {
      currentSession.value = { ...currentSession.value, current_round: res.round, status: 'running' }
    }
    isPaused.value = false
    branches.value = []
    return res
  }

  async function pickBranch(branchIndex: number) {
    if (!currentEvolutionId.value) return
    const user = useUserStore()
    const res = await selectBranch(currentEvolutionId.value, user.userId, branchIndex)
    if (res.accepted) { isPaused.value = false; branches.value = [] }
    return res
  }

  async function sendCustomEvent(eventText: string) {
    if (!currentEvolutionId.value) return
    const user = useUserStore()
    const res = await submitCustomEvent(currentEvolutionId.value, user.userId, eventText)
    if (res.accepted) { isPaused.value = false }
    return res
  }

  async function sendIntervene(eventText: string) {
    if (!currentEvolutionId.value) return
    const user = useUserStore()
    return intervene(currentEvolutionId.value, user.userId, eventText)
  }

  async function fetchTimeline(evolutionId: string) {
    const user = useUserStore()
    const res = await getTimeline(evolutionId, user.userId)
    timeline.value = res.events.filter(e => e.type !== 'director_path')
    relationships.value = res.relationships || []

    // 历史加载时从 timeline 恢复暂停状态和分支选项（SSE 不会回放历史事件）
    if (isPaused.value) {
      const lastBranchEvent = [...timeline.value].reverse().find(e => e.type === 'branch_options')
      if (lastBranchEvent) {
        pauseReason.value = 'branches'
        try {
          const parsed = JSON.parse(lastBranchEvent.content)
          branches.value = Array.isArray(parsed) ? parsed as Branch[] : []
        } catch { /* branch_options content 可能不是有效 JSON */ }
      }
      // 无 branch_options 则保持 isPaused 但不设置 branches，EvolutionPage 检查 branches 长度决定是否展示抽屉
    }
    return res
  }

  function handleSSEEvent(type: string, data: Record<string, unknown>) {
    switch (type) {
      case 'round_start':
        isRunning.value = true
        break
      case 'timeline_event':
        if (data.event) {
          const ev = data.event as Record<string, unknown>
          if (ev.type !== 'director_path') timeline.value.push(ev as unknown as TimelineEvent)
        }
        break
      case 'branches':
        branches.value = (data.branches || []) as unknown as Branch[]
        isPaused.value = true
        pauseReason.value = 'branches'
        break
      case 'session_paused':
        isPaused.value = true
        pauseReason.value = (data.reason as 'conflict' | 'branches') || 'conflict'
        break
      case 'round_end':
        isRunning.value = false
        if (currentSession.value) currentSession.value.current_round = (data.round as number) || currentSession.value.current_round
        break
      case 'session_ended':
        isRunning.value = false
        if (currentSession.value) currentSession.value.status = 'ended'
        break
      case 'relationships':
        if (data.edges) relationships.value = data.edges as { from: string; to: string; relationship: string }[]
        break
      default:
        // 未知 SSE 事件类型，静默忽略
    }
  }

  function reset() {
    timeline.value = []
    relationships.value = []
    branches.value = []
    isPaused.value = false
    pauseReason.value = null
    isRunning.value = false
    currentEvolutionId.value = null
    currentSession.value = null
  }

  return {
    sessions, currentEvolutionId, currentSession, timeline, relationships,
    branches, isPaused, pauseReason, isRunning, currentRound, maxRounds,
    fetchSessions, create, fetchDetail, remove, runRound, pickBranch,
    sendCustomEvent, sendIntervene, fetchTimeline, handleSSEEvent, reset,
  }
})
