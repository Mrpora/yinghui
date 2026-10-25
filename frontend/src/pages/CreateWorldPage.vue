<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWorldStore } from '@/stores/world'
import { useUserStore } from '@/stores/user'
import { completeWorldConfig } from '@/api/client'
import type { CharacterConfig } from '@/types'
import BaseButton from '@/components/ui/BaseButton.vue'

const router = useRouter()
const world = useWorldStore()
const user = useUserStore()

// ── 基本信息 ──
const name = ref('')
const description = ref('')

// ── 世界设定 ──
const worldHistory = ref('')
const rulesText = ref('')
const initialEventContent = ref('')
const initialEventTime = ref('')

// ── 角色 ──
const MIN_CHARACTERS = 3
const MAX_CHARACTERS = 10

function emptyCharacter(): CharacterConfig {
  return {
    name: '', identity: '', personality: '', speech_style: '',
    goal: '', attitudes: {}, backstory: '', initial_location: '', initial_state: '',
  }
}

// 卡片级稳定 id：创建时生成、存于本地数组元素上，供 v-for :key 使用；
// 删除中间卡片时其余卡片不因索引错位而错误复用 DOM/组件状态（W4a F5）。
// _key 仅用于前端 diff，出站载荷（AI 补全/创建）经 toConfig 剥离。
type CharacterCard = CharacterConfig & { _key: number }
let _keySeq = 0
function withKey(c: CharacterConfig): CharacterCard {
  return { ...c, _key: ++_keySeq }
}
function toConfig({ _key, ...cfg }: CharacterCard): CharacterConfig {
  return cfg
}

const characters = ref<CharacterCard[]>(
  Array.from({ length: MIN_CHARACTERS }, () => withKey(emptyCharacter())),
)

// ── 态度文本 ↔ Record 互转 ──
function attitudesToText(a: Record<string, string>): string {
  return Object.entries(a).map(([k, v]) => `${k}: ${v}`).join('\n')
}

function textToAttitudes(text: string): Record<string, string> {
  const result: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const idx = line.indexOf(':')
    if (idx > 0) {
      const key = line.slice(0, idx).trim()
      const val = line.slice(idx + 1).trim()
      if (key && val) result[key] = val
    }
  }
  return result
}

// 角色态度文本（独立于 CharacterConfig.attitudes，方便编辑）
const attitudesTexts = ref<string[]>(Array.from({ length: MIN_CHARACTERS }, () => ''))

onMounted(() => {
  if (!user.isLoggedIn) {
    router.push('/').catch((err: unknown) => {
      if ((err as { name?: string })?.name !== 'NavigationDuplicated') {
        console.error('[CreateWorldPage] 登录重定向失败:', err)
      }
    })
  }
})

function goBack() {
  router.push('/worlds').catch(() => {})
}

// ── AI 补全（可选辅助） ──
const isCompleting = ref(false)
const completeError = ref('')

function addCharacter() {
  if (characters.value.length >= MAX_CHARACTERS) return
  characters.value.push(withKey(emptyCharacter()))
  attitudesTexts.value.push('')
}

function removeCharacter(i: number) {
  if (characters.value.length <= MIN_CHARACTERS) return
  characters.value.splice(i, 1)
  attitudesTexts.value.splice(i, 1)
}

async function aiComplete() {
  completeError.value = ''
  isCompleting.value = true
  try {
    const res = await completeWorldConfig({
      world_name: name.value,
      world_description: description.value,
      characters: characters.value.filter(c => c.name.trim()).map(toConfig),
    })
    if (!res.world_history && !res.rules?.length && !res.characters?.length) throw new Error('AI 返回数据为空，请重试')

    worldHistory.value = res.world_history || ''
    rulesText.value = (res.rules || []).join('\n')
    initialEventContent.value = res.initial_event?.content || ''
    initialEventTime.value = res.initial_event?.time || ''

    const chs = res.characters || []
    const incoming = chs.slice(0, MAX_CHARACTERS)
    characters.value = incoming.map((ch) => withKey({ ...emptyCharacter(), ...ch }))
    attitudesTexts.value = incoming.map((ch) => attitudesToText(ch.attitudes || {}))
    while (characters.value.length < MIN_CHARACTERS) {
      characters.value.push(withKey(emptyCharacter()))
      attitudesTexts.value.push('')
    }
  } catch (e: unknown) {
    completeError.value = (e as Error).message || 'AI 补全失败，请重试'
  } finally {
    isCompleting.value = false
  }
}

// ── 表单校验 ──
const canSubmit = computed(() => {
  if (!name.value.trim() || !description.value.trim()) return false
  if (!worldHistory.value.trim()) return false
  const validChars = characters.value.filter(c => c.name.trim())
  if (validChars.length < MIN_CHARACTERS || validChars.length > MAX_CHARACTERS) return false
  if (validChars.some(c => !c.backstory?.trim())) return false
  return true
})

// ── 创建世界 ──
const isSubmitting = ref(false)
const submitError = ref('')

async function handleCreate() {
  submitError.value = ''
  if (!name.value.trim()) {
    submitError.value = '请输入世界名称'
    return
  }
  if (!worldHistory.value.trim()) {
    submitError.value = '请填写世界历史'
    return
  }
  const unnamed = characters.value.findIndex((c) => !c.name.trim())
  if (unnamed !== -1) {
    submitError.value = `角色 ${unnamed + 1} 未填写名称`
    return
  }
  const validChars = characters.value.filter(c => c.name.trim())
  if (validChars.length < MIN_CHARACTERS) {
    submitError.value = `至少需要 ${MIN_CHARACTERS} 个角色（当前已填 ${validChars.length} 个）`
    return
  }
  const emptyBackstories = validChars.filter(c => !c.backstory?.trim())
  if (emptyBackstories.length) {
    submitError.value = `以下角色缺少背景故事：${emptyBackstories.map(c => c.name || '(未命名)').join('、')}`
    return
  }
  isSubmitting.value = true
  try {
    await world.addWorld({
      user_id: user.userId,
      name: name.value.trim(),
      description: description.value.trim(),
      world_history: worldHistory.value.trim(),
      rules: rulesText.value
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean),
      initial_event: {
        content: initialEventContent.value.trim(),
        time: initialEventTime.value.trim(),
      },
      characters: characters.value
        .map((ch, i) => ({ ch, i }))
        .filter(({ ch }) => ch.name.trim())
        .map(({ ch, i }) => ({
          ...toConfig(ch),
          attitudes: textToAttitudes(attitudesTexts.value[i] || ''),
        })),
    })
    await router.push('/worlds')
  } catch (e: unknown) {
    submitError.value = (e as Error).message || '创建失败，请重试'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <div class="mb-6">
      <button
        class="inline-flex items-center gap-1.5 text-sm text-smoke hover:text-old-gold transition-colors border border-border-light hover:border-old-gold rounded-lg px-3 py-1.5"
        @click="goBack"
      >
        <span class="text-base leading-none">←</span>
        <span>返回世界模板</span>
      </button>
    </div>

    <h1 class="font-serif text-2xl font-bold text-ink mb-8">创建新世界</h1>

    <div class="space-y-8">
      <!-- ═══ 基本信息 ═══ -->
      <section>
        <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">基本信息</h2>
        <div class="space-y-4">
          <div>
            <label for="world-name" class="text-sm text-ink block mb-1">世界名称</label>
            <input
              id="world-name"
              v-model="name"
              type="text"
              placeholder="输入世界名称"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30"
            />
          </div>
          <div>
            <label for="world-desc" class="text-sm text-ink block mb-1">描述</label>
            <textarea
              id="world-desc"
              v-model="description"
              rows="3"
              placeholder="简要描述这个世界…"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none"
            />
          </div>
          <div class="flex items-center gap-3">
            <BaseButton
              variant="primary"
              :disabled="isCompleting || !name.trim() || !description.trim()"
              title="根据世界名称和描述，由 AI 自动补全世界历史、规则、初始事件和角色设定"
              @click="aiComplete"
            >
              AI 智能补全
            </BaseButton>
            <span v-if="isCompleting" class="text-smoke text-xs animate-celadon-pulse">正在生成…</span>
            <span v-else class="text-xs text-smoke/50">输入名称和描述后可使用</span>
          </div>
          <p v-if="completeError" class="text-cinnabar/80 text-xs">{{ completeError }}</p>
        </div>
      </section>

      <!-- ═══ 世界设定 ═══ -->
      <section>
        <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">世界设定</h2>
        <div class="space-y-4">
          <div>
            <label for="world-history" class="text-sm text-ink block mb-1">世界历史</label>
            <textarea
              id="world-history"
              v-model="worldHistory"
              rows="4"
              placeholder="这个世界经历了什么…"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none"
            />
          </div>
          <div>
            <label for="world-rules" class="text-sm text-ink block mb-1">世界规则</label>
            <textarea
              id="world-rules"
              v-model="rulesText"
              rows="3"
              placeholder="每行一条规则…"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none"
            />
            <p class="text-xs text-smoke/60 mt-0.5">每行一条规则</p>
          </div>
        </div>
      </section>

      <!-- ═══ 初始事件 ═══ -->
      <section>
        <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">初始事件</h2>
        <div class="space-y-4">
          <div>
            <label for="event-content" class="text-sm text-ink block mb-1">事件内容</label>
            <textarea
              id="event-content"
              v-model="initialEventContent"
              rows="3"
              placeholder="这个世界发生的第一件事…"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none"
            />
          </div>
          <div>
            <label for="event-time" class="text-sm text-ink block mb-1">事件时间</label>
            <input
              id="event-time"
              v-model="initialEventTime"
              type="text"
              placeholder="如：永和三年春、创世之初…"
              class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30"
            />
          </div>
        </div>
      </section>

      <!-- ═══ 角色设定 ═══ -->
      <section>
        <div class="flex items-center justify-between mb-3 border-b border-border-light pb-1">
          <h2 class="text-sm text-smoke tracking-widest">角色设定</h2>
          <div class="flex items-center gap-2">
            <span class="text-xs text-smoke">{{ characters.length }} / {{ MAX_CHARACTERS }}</span>
            <button
              class="text-xs text-old-gold border border-old-gold/30 rounded px-2 py-0.5 hover:bg-old-gold hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="characters.length >= MAX_CHARACTERS"
              title="最多 10 个角色"
              @click="addCharacter"
            >
              ＋ 添加角色
            </button>
          </div>
        </div>

        <div class="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="(ch, i) in characters"
            :key="ch._key"
            class="bg-white rounded-xl border border-border-light p-5 space-y-3"
          >
            <p class="text-xs text-old-gold tracking-widest flex items-center justify-between">
              <span>角色 {{ i + 1 }}</span>
              <button
                v-if="characters.length > MIN_CHARACTERS"
                class="text-cinnabar/60 hover:text-cinnabar text-xs"
                title="删除该角色"
                @click="removeCharacter(i)"
              >
                删除
              </button>
            </p>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="text-xs text-smoke block mb-0.5">名称</label>
                <input v-model="ch.name" type="text" placeholder="角色名"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div>
                <label class="text-xs text-smoke block mb-0.5">身份</label>
                <input v-model="ch.identity" type="text" placeholder="如：女、江湖剑客"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div>
                <label class="text-xs text-smoke block mb-0.5">性格</label>
                <input v-model="ch.personality" type="text" placeholder="如：沉默寡言、内心炽热"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div>
                <label class="text-xs text-smoke block mb-0.5">说话风格</label>
                <input v-model="ch.speech_style" type="text" placeholder="如：简洁有力、自带江湖气"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div class="col-span-2">
                <label class="text-xs text-smoke block mb-0.5">目标</label>
                <input v-model="ch.goal" type="text" placeholder="角色想要达成什么…"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div>
                <label class="text-xs text-smoke block mb-0.5">初始位置</label>
                <input v-model="ch.initial_location" type="text" placeholder="如：洛阳城外破庙"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div>
                <label class="text-xs text-smoke block mb-0.5">初始状态</label>
                <input v-model="ch.initial_state" type="text" placeholder="如：刚刚经历了一场恶战"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
              </div>
              <div class="col-span-2">
                <label class="text-xs text-smoke block mb-0.5">背景故事</label>
                <textarea v-model="ch.backstory" rows="2" placeholder="角色的过往…"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
              </div>
              <div class="col-span-2">
                <label class="text-xs text-smoke block mb-0.5">
                  对其他角色的态度
                  <span class="text-smoke/50">（每行一条，"角色名: 态度"）</span>
                </label>
                <textarea
                  v-model="attitudesTexts[i]"
                  rows="2"
                  placeholder="角色A: 信任&#10;角色B: 戒备"
                  class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ═══ 提交 ═══ -->
      <p v-if="submitError" class="text-cinnabar/80 text-sm">{{ submitError }}</p>

      <div class="pt-4 border-t border-border-light">
        <BaseButton
          variant="primary"
          class="w-full py-3 text-base tracking-wider"
          :disabled="!canSubmit || isSubmitting"
          @click="handleCreate"
        >
          {{ isSubmitting ? '创建中…' : '创建世界' }}
        </BaseButton>
      </div>
    </div>
  </div>
</template>
