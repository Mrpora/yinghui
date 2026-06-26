// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { config } from '@/config'
import type {
  LoginResponse, CreateWorldForm, UpdateWorldForm, WorldItem,
  CompleteConfigResponse, WorldDetailResponse,
  CreateSessionResponse, SessionState, StartRoundResponse,
  SelectBranchResponse, TimelineResponse, Branch,
  GenerateNovelResponse, TaskStatus, NovelItem, NovelDetail,
  ChatCharacter, ChatMessage, ChatHistoryItem, MemoryItem, CareLevelSettings,
} from '@/types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ═══ Auth ═══

export function login(nickname: string): Promise<LoginResponse> {
  return request('/auth/login', { method: 'POST', body: JSON.stringify({ nickname }) })
}

// ═══ Worlds ═══

export function listWorlds(userId: string): Promise<{ worlds: WorldItem[] }> {
  return request(`/worlds/list?user_id=${encodeURIComponent(userId)}`)
}

export function getWorldDetail(worldId: string): Promise<WorldDetailResponse> {
  return request(`/worlds/detail?world_id=${encodeURIComponent(worldId)}`)
}

export function createWorld(data: CreateWorldForm & { user_id: string }): Promise<{ world_id: string }> {
  return request('/worlds/create', { method: 'POST', body: JSON.stringify(data) })
}

export function deleteWorld(worldId: string, userId: string): Promise<{ status: string }> {
  return request(`/worlds/delete?world_id=${worldId}&user_id=${userId}`, { method: 'POST' })
}

export function updateWorld(data: UpdateWorldForm & { user_id: string }): Promise<{ status: string; world_id: string }> {
  return request('/worlds/update', { method: 'POST', body: JSON.stringify(data) })
}

export function completeWorldConfig(data: Record<string, unknown>): Promise<CompleteConfigResponse> {
  return request('/worlds/complete-config', { method: 'POST', body: JSON.stringify(data) })
}

// ═══ Evolutions ═══

export function listEvolutions(userId: string): Promise<{ sessions: SessionState[] }> {
  return request(`/evolutions/list?user_id=${encodeURIComponent(userId)}`)
}

export function createEvolution(userId: string, worldId: string): Promise<CreateSessionResponse> {
  return request('/evolutions/create', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, world_id: worldId }),
  })
}

export function getEvolutionDetail(evolutionId: string, userId: string): Promise<SessionState> {
  return request(`/evolutions/detail?evolution_id=${evolutionId}&user_id=${userId}`)
}

export function deleteEvolution(evolutionId: string, userId: string): Promise<{ status: string }> {
  return request(`/evolutions/delete?evolution_id=${evolutionId}&user_id=${userId}`, { method: 'POST' })
}

export function startRound(evolutionId: string, userId: string): Promise<StartRoundResponse> {
  return request(`/evolutions/start-round?evolution_id=${evolutionId}&user_id=${userId}`, { method: 'POST' })
}

export function selectBranch(evolutionId: string, userId: string, branchIndex: number): Promise<SelectBranchResponse> {
  return request(`/evolutions/select-branch?evolution_id=${evolutionId}&user_id=${userId}&branch_index=${branchIndex}`, { method: 'POST' })
}

export function submitCustomEvent(evolutionId: string, userId: string, eventText: string): Promise<{ accepted: boolean }> {
  return request(`/evolutions/custom-event?evolution_id=${evolutionId}&user_id=${userId}&event_text=${encodeURIComponent(eventText)}`, { method: 'POST' })
}

export function intervene(evolutionId: string, userId: string, eventText: string): Promise<{ accepted: boolean }> {
  return request(`/evolutions/intervene?evolution_id=${evolutionId}&user_id=${userId}&event_text=${encodeURIComponent(eventText)}`, { method: 'POST' })
}

export function getTimeline(evolutionId: string, userId: string): Promise<TimelineResponse> {
  return request(`/evolutions/timeline?evolution_id=${evolutionId}&user_id=${userId}`)
}

// ═══ Novels ═══

export function generateNovel(userId: string, worldId: string, evolutionId: string): Promise<GenerateNovelResponse> {
  return request(`/novels/generate?user_id=${userId}&world_id=${worldId}&evolution_id=${evolutionId}`, { method: 'POST' })
}

export function getNovelTaskStatus(taskId: string): Promise<TaskStatus> {
  return request(`/novels/task-status?task_id=${taskId}`)
}

export function listNovels(userId: string): Promise<{ novels: NovelItem[] }> {
  return request(`/novels/list?user_id=${encodeURIComponent(userId)}`)
}

export function getNovelDetail(novelId: string): Promise<NovelDetail> {
  return request(`/novels/detail?novel_id=${novelId}`)
}

export function deleteNovel(novelId: string, userId: string): Promise<{ status: string }> {
  return request(`/novels/delete?novel_id=${novelId}&user_id=${userId}`, { method: 'POST' })
}

export function checkNovelTask(evolutionId: string): Promise<{ has_task: boolean; task: Record<string, unknown> | null }> {
  return request(`/novels/check-task?evolution_id=${encodeURIComponent(evolutionId)}`)
}

export function importNovelCharacters(novelId: string, userId: string): Promise<{ status: string; characters: Record<string, unknown>[] }> {
  return request(`/novels/import-characters?novel_id=${novelId}&user_id=${userId}`, { method: 'POST' })
}

// ═══ Chats ═══

export function listChatCharacters(userId: string, novelId: string): Promise<{ characters: ChatCharacter[] }> {
  return request(`/chats/characters?user_id=${userId}&novel_id=${novelId}`)
}

export function getChatMessages(chatId: string): Promise<{ chat_id: string; messages: ChatMessage[] }> {
  return request(`/chats/messages?chat_id=${chatId}`)
}

export function listChatHistory(userId: string, novelId: string, characterId?: string): Promise<{ chats: ChatHistoryItem[] }> {
  let url = `/chats/list?user_id=${userId}&novel_id=${encodeURIComponent(novelId)}`
  if (characterId) url += `&character_id=${encodeURIComponent(characterId)}`
  return request(url)
}

export function deleteChat(chatId: string, userId: string): Promise<{ status: string }> {
  return request(`/chats/delete?chat_id=${chatId}&user_id=${userId}`, { method: 'POST' })
}

export function removeCharacter(novelId: string, userId: string, characterId: string): Promise<{ status: string }> {
  return request(`/chats/remove-characters?novel_id=${novelId}&user_id=${userId}&character_id=${characterId}`, { method: 'POST' })
}

export function getLatestChatNovel(userId: string): Promise<{ novel_id: string | null }> {
  return request(`/chats/latest-novel?user_id=${encodeURIComponent(userId)}`)
}

// ═══ Memories ═══

export function listMemories(userId: string, novelId: string, characterId?: string): Promise<{ memories: MemoryItem[] }> {
  let url = `/memories/list?user_id=${encodeURIComponent(userId)}&novel_id=${encodeURIComponent(novelId)}`
  if (characterId) url += `&character_id=${encodeURIComponent(characterId)}`
  return request(url)
}

export function deleteMemory(memoryId: string): Promise<{ status: string; memory_id: string }> {
  return request(`/memories/delete?memory_id=${memoryId}`, { method: 'POST' })
}

export function updateMemoryExpiry(memoryId: string, expiresAt: number | null): Promise<{ status: string; memory_id: string; expires_at: number | null }> {
  return request(`/memories/update-expiry?memory_id=${encodeURIComponent(memoryId)}`, {
    method: 'POST',
    body: JSON.stringify({ expires_at: expiresAt }),
  })
}

export function clearMemories(userId: string, novelId: string, characterId: string): Promise<{ status: string; deleted_count: number }> {
  return request(`/memories/clear?user_id=${userId}&novel_id=${novelId}&character_id=${characterId}`, { method: 'POST' })
}

// ═══ Settings ═══

export function getCareLevel(userId: string, novelId: string, characterId: string): Promise<CareLevelSettings> {
  return request(`/settings/care-level?user_id=${userId}&novel_id=${novelId}&character_id=${characterId}`)
}

export function setCareLevel(userId: string, novelId: string, characterId: string, level: number): Promise<{ status: string; level: number }> {
  return request('/settings/update-care-level', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, novel_id: novelId, character_id: characterId, level }),
  })
}

// ═══ SSE 流式对话 ═══

export function chatSSE(
  params: { user_id: string; novel_id: string; character_id: string; chat_id?: string; content?: string },
  callbacks: {
    onSessionCreated?: (chatId: string) => void
    onThinking?: () => void
    onRetrieving?: () => void
    onMemorizing?: () => void
    onToken?: (text: string) => void
    onDone?: (data: Record<string, unknown>) => void
    onError?: (msg: string) => void
  },
): AbortController {
  const controller = new AbortController()
  const qs = new URLSearchParams(params as Record<string, string>)
  if (!params.chat_id) qs.delete('chat_id')
  if (!params.content) qs.delete('content')

  fetch(`${BASE}/chats/start?${qs}`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) { callbacks.onError?.(`HTTP ${res.status}`); return }
      if (!res.body) { callbacks.onError?.('No body'); return }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = '', currentEvent = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim() }
          else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6).trim())
              switch (currentEvent) {
                case 'session_created': callbacks.onSessionCreated?.(data.chat_id); break
                case 'thinking': callbacks.onThinking?.(); break
                case 'retrieving': callbacks.onRetrieving?.(); break
                case 'memorizing': callbacks.onMemorizing?.(); break
                case 'token': if (data.content) callbacks.onToken?.(data.content); break
                case 'done': callbacks.onDone?.(data); break
                case 'error': callbacks.onError?.(data.message || 'Unknown'); break
                default: if (data.content) callbacks.onToken?.(data.content); break
              }
            } catch { /* skip */ }
          }
        }
      }
    })
    .catch((err) => { if (err.name !== 'AbortError') callbacks.onError?.(err.message) })
  return controller
}
