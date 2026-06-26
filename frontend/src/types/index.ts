// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

// ═══ 通用 ═══

export interface LoginResponse {
  user_id: string
  nickname: string
  created_at: number
}

// ═══ World ═══

export interface CharacterConfig {
  name: string
  identity: string
  personality: string
  speech_style: string
  goal: string
  attitudes: Record<string, string>
  backstory?: string
  initial_location: string
  initial_state: string
  accent_color?: string
}

export interface WorldConfig {
  world: { name: string; description: string; world_history?: string; rules: string[] }
  characters: CharacterConfig[]
  initial_event: { content: string; time: string }
}

export interface WorldItem {
  world_id: string
  name: string
  description: string
  rules: string[]
  is_preset: boolean
  character_count: number
  created_at: number
}

export interface CreateWorldForm {
  name: string
  description: string
  world_history: string
  rules: string[]
  initial_event: { content: string; time: string }
  characters: CharacterConfig[]
}

export interface UpdateWorldForm extends CreateWorldForm {
  world_id: string
}

export interface CompleteConfigResponse {
  world_history: string | null
  rules: string[]
  initial_event: { content: string; time: string } | null
  characters: CharacterConfig[]
}

export interface WorldDetailResponse {
  world_id: string
  name: string
  description: string
  world_history: string
  rules: string[]
  initial_event: { content: string; time: string }
  is_preset: boolean
  created_at: number
  characters: Record<string, unknown>[]
}

// ═══ Session / Evolution ═══

export type SessionStatus = 'idle' | 'running' | 'paused' | 'waiting_next_round' | 'ended'

export interface SessionState {
  evolution_id: string
  user_id: string
  world_id: string
  world_name?: string
  status: SessionStatus
  current_round: number
  max_rounds: number
  created_at: number
  character_names: string[]
  world_config?: WorldConfig | null
}

export interface CreateSessionResponse {
  evolution_id: string
  user_id: string
  world_id: string
  status: SessionStatus
  max_rounds: number
  created_at: number
  world_config: WorldConfig | null
}

export interface StartRoundResponse {
  round: number
  status: string
}

// ═══ Timeline ═══

export type TimelineEventType =
  | 'action' | 'conflict' | 'scene_setting' | 'user_decision' | 'user_intervene'
  | 'round_summary' | 'relationship' | 'branch_options' | 'director_path'

export interface ConflictSelfAssessment {
  potential_conflict_with: string
  reason: string
}

export interface TimelineEvent {
  id: string
  type: TimelineEventType
  round: number
  content: string
  character?: string
  character_color?: string
  motive?: string
  inner_thoughts?: string
  conflict_self_assessment?: ConflictSelfAssessment | null
  involved_characters?: string[]
  source?: string
  timestamp: number
}

export interface RelationshipEdge {
  from: string
  to: string
  relationship: string
}

export interface TimelineResponse {
  evolution_id: string
  current_round: number
  events: TimelineEvent[]
  relationships: RelationshipEdge[]
}

// ═══ Branch ═══

export interface Branch {
  index: number
  title: string
  description: string
  reason: string
}

export interface SelectBranchResponse {
  accepted: boolean
  selected_branch: { index: number; title: string }
}

// ═══ Novel ═══

export interface NovelItem {
  novel_id: string
  title: string
  user_id: string
  world_id: string
  evolution_id: string
  created_at: number
  task_status?: string | null
}

export interface NovelDetail {
  novel_id: string
  title: string
  content: string
  world_snapshot: Record<string, unknown>
  created_at: number
  characters: Record<string, unknown>[]
  task_status?: string | null
}

export interface GenerateNovelResponse {
  task_id: string
  novel_id: string
  status: string
}

export interface TaskStatus {
  task_id: string
  status: string
  result: Record<string, unknown> | null
  error: string | null
  created_at: number
  completed_at: number | null
}

export interface ChatHistoryItem {
  chat_id: string
  character_id: string
  character_name: string
  accent_color: string
  created_at: number
  modified_at: number
}

// ═══ Chat ═══

export interface ChatCharacter {
  id: string
  name: string
  identity: string
  personality_traits: string[]
  speaking_style: string
  accent_color: string
  relationships: Record<string, string>
  story_context: string
}

export interface ChatMessage {
  role: 'user' | 'character'
  content: string
  timestamp?: number
  round?: number
}

export interface Message {
  role: 'user' | 'character'
  content: string
  timestamp: number
  round: number
}

// ═══ Memory ═══

export interface MemoryItem {
  id: string
  character_name: string
  memory_type: 'user_fact' | 'event'
  content: string
  created_at: number
  expires_at: number | null
  recall_count: number
}

export interface CareLevelSettings {
  level: number
}

// ═══ SSE ═══

export interface SSECallbacks {
  onEvent?: (type: string, data: unknown) => void
  onError?: (message: string) => void
  onComplete?: () => void
}
