<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useWorldStore } from '@/stores/world'
import { useEvolutionStore } from '@/stores/evolution'
import { useUserStore } from '@/stores/user'
import type { CharacterConfig } from '@/types'
import BaseButton from '@/components/ui/BaseButton.vue'

const router = useRouter()
const route = useRoute()
const world = useWorldStore()
const evolution = useEvolutionStore()
const user = useUserStore()

const worldId = route.params.worldId as string

const isEditing = ref(false)
const errorMsg = ref('')
const isSubmitting = ref(false)
const starting = ref(false)

// ── 表单数据 ──
const name = ref('')
const description = ref('')
const worldHistory = ref('')
const rulesText = ref('')
const initialEventContent = ref('')
const initialEventTime = ref('')
const characters = ref<CharacterConfig[]>([])
const attitudesTexts = ref<string[]>([])

function emptyCharacter(): CharacterConfig {
  return {
    name: '', identity: '', personality: '', speech_style: '',
    goal: '', attitudes: {}, backstory: '', initial_location: '', initial_state: '',
  }
}

const MIN_CHARACTERS = 3
const MAX_CHARACTERS = 10

function addCharacter() {
  if (characters.value.length >= MAX_CHARACTERS) return
  characters.value.push(emptyCharacter())
  attitudesTexts.value.push('')
}

function removeCharacter(i: number) {
  if (characters.value.length <= MIN_CHARACTERS) return
  characters.value.splice(i, 1)
  attitudesTexts.value.splice(i, 1)
}

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

function loadFromDetail(detail: Record<string, unknown>) {
  name.value = detail.name as string || ''
  description.value = detail.description as string || ''
  worldHistory.value = detail.world_history as string || ''
  const rules = detail.rules as string[] || []
  rulesText.value = rules.join('\n')
  const ie = detail.initial_event as Record<string, string> || {}
  initialEventContent.value = ie.content || ''
  initialEventTime.value = ie.time || ''
  const chs = detail.characters as Record<string, unknown>[] || []
  characters.value = chs.map((ch) => ({
    ...emptyCharacter(),
    ...ch,
  }))
  attitudesTexts.value = chs.map((ch) => attitudesToText((ch.attitudes || {}) as Record<string, string>))
}

onMounted(async () => {
  if (!user.isLoggedIn) {
    router.push('/').catch(() => {})
    return
  }
  try {
    const detail = await world.fetchWorldDetail(worldId)
    loadFromDetail(detail as unknown as Record<string, unknown>)
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '加载世界详情失败'
  }
})

function goBack() {
  router.push('/worlds').catch(() => {})
}

function startEdit() {
  isEditing.value = true
}

function cancelEdit() {
  // 重新加载原始数据
  if (world.currentWorld) {
    loadFromDetail(world.currentWorld)
  }
  isEditing.value = false
  errorMsg.value = ''
}

async function handleSave() {
  errorMsg.value = ''
  if (!name.value.trim()) {
    errorMsg.value = '请输入世界名称'
    return
  }
  const unnamed = characters.value.findIndex((c) => !c.name.trim())
  if (unnamed !== -1) {
    errorMsg.value = `角色 ${unnamed + 1} 未填写名称`
    return
  }
  const validChars = characters.value.filter(c => c.name.trim())
  if (validChars.length < MIN_CHARACTERS) {
    errorMsg.value = `至少需要 ${MIN_CHARACTERS} 个角色（当前已填 ${validChars.length} 个）`
    return
  }
  isSubmitting.value = true
  try {
    await world.modifyWorld(worldId, {
      user_id: user.userId,
      name: name.value.trim(),
      description: description.value.trim(),
      world_history: worldHistory.value.trim(),
      rules: rulesText.value.split('\n').map(l => l.trim()).filter(Boolean),
      initial_event: {
        content: initialEventContent.value.trim(),
        time: initialEventTime.value.trim(),
      },
      characters: characters.value
        .map((ch, i) => ({ ch, i }))
        .filter(({ ch }) => ch.name.trim())
        .map(({ ch, i }) => ({
          ...ch,
          attitudes: textToAttitudes(attitudesTexts.value[i] || ''),
        })),
    })
    isEditing.value = false
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '保存失败，请重试'
  } finally {
    isSubmitting.value = false
  }
}

async function startEvolution() {
  if (starting.value) return
  errorMsg.value = ''
  starting.value = true
  try {
    await evolution.create(worldId)
    await router.push(`/evolution/${evolution.currentEvolutionId}`)
  } catch (e: unknown) {
    errorMsg.value = (e as Error)?.message || '进入世界失败，请重试'
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 animate-fade-up">
    <div class="flex items-center justify-between mb-6">
      <button
        class="inline-flex items-center gap-1.5 text-sm text-smoke hover:text-old-gold transition-colors border border-border-light hover:border-old-gold rounded-lg px-3 py-1.5"
        @click="goBack"
      >
        <span class="text-base leading-none">←</span>
        <span>返回</span>
      </button>
      <div class="flex items-center gap-3">
        <BaseButton
          v-if="!isEditing"
          variant="secondary"
          @click="startEdit"
        >
          编辑
        </BaseButton>
        <BaseButton
          variant="primary"
          :disabled="starting"
          @click="startEvolution"
        >
          {{ starting ? '进入中…' : '开始演化' }}
        </BaseButton>
      </div>
    </div>

    <div v-if="errorMsg" class="mb-4 p-3 bg-cinnabar/10 border border-cinnabar/30 rounded-lg text-sm text-cinnabar">
      {{ errorMsg }}
      <button class="ml-2 underline" @click="errorMsg = ''">关闭</button>
    </div>

    <!-- ═══ 只读模式 ═══ -->
    <template v-if="!isEditing">
      <h1 class="font-serif text-2xl font-bold text-ink mb-2">{{ name || '未命名世界' }}</h1>
      <p class="text-smoke mb-8">{{ description }}</p>

      <div class="space-y-6">
        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-2 border-b border-border-light pb-1">世界历史</h2>
          <p class="text-sm text-ink whitespace-pre-wrap">{{ worldHistory || '未填写' }}</p>
        </section>

        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-2 border-b border-border-light pb-1">世界规则</h2>
          <ul v-if="rulesText" class="list-disc list-inside text-sm text-ink space-y-1">
            <li v-for="(r, i) in rulesText.split('\n').filter(Boolean)" :key="i">{{ r }}</li>
          </ul>
          <p v-else class="text-sm text-smoke">未填写</p>
        </section>

        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-2 border-b border-border-light pb-1">初始事件</h2>
          <p class="text-sm text-ink">{{ initialEventContent || '未填写' }}</p>
          <p v-if="initialEventTime" class="text-xs text-smoke/70 mt-1">{{ initialEventTime }}</p>
        </section>

        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">角色</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div
              v-for="(ch, i) in characters"
              :key="i"
              class="bg-white rounded-xl border border-border-light p-4"
            >
              <h3 class="font-bold text-ink mb-1">{{ ch.name || '(未命名)' }}</h3>
              <p class="text-xs text-smoke/70">{{ ch.identity }}</p>
              <div class="mt-2 space-y-1 text-xs text-smoke">
                <p v-if="ch.personality"><span class="text-ink/60">性格：</span>{{ ch.personality }}</p>
                <p v-if="ch.speech_style"><span class="text-ink/60">说话风格：</span>{{ ch.speech_style }}</p>
                <p v-if="ch.goal"><span class="text-ink/60">目标：</span>{{ ch.goal }}</p>
                <p v-if="ch.backstory"><span class="text-ink/60">背景：</span>{{ ch.backstory }}</p>
                <p v-if="ch.initial_location"><span class="text-ink/60">位置：</span>{{ ch.initial_location }}</p>
                <p v-if="ch.initial_state"><span class="text-ink/60">状态：</span>{{ ch.initial_state }}</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>

    <!-- ═══ 编辑模式 ═══ -->
    <template v-else>
      <h1 class="font-serif text-2xl font-bold text-ink mb-8">编辑世界</h1>

      <div class="space-y-8">
        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">基本信息</h2>
          <div class="space-y-4">
            <div>
              <label for="world-name" class="text-sm text-ink block mb-1">世界名称</label>
              <input id="world-name" v-model="name" type="text" placeholder="输入世界名称"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
            </div>
            <div>
              <label for="world-desc" class="text-sm text-ink block mb-1">描述</label>
              <textarea id="world-desc" v-model="description" rows="3" placeholder="简要描述这个世界…"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
            </div>
          </div>
        </section>

        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">世界设定</h2>
          <div class="space-y-4">
            <div>
              <label for="world-history" class="text-sm text-ink block mb-1">世界历史</label>
              <textarea id="world-history" v-model="worldHistory" rows="4" placeholder="这个世界经历了什么…"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
            </div>
            <div>
              <label for="world-rules" class="text-sm text-ink block mb-1">世界规则</label>
              <textarea id="world-rules" v-model="rulesText" rows="3" placeholder="每行一条规则…"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
              <p class="text-xs text-smoke/60 mt-0.5">每行一条规则</p>
            </div>
          </div>
        </section>

        <section>
          <h2 class="text-sm text-smoke tracking-widest mb-3 border-b border-border-light pb-1">初始事件</h2>
          <div class="space-y-4">
            <div>
              <label for="event-content" class="text-sm text-ink block mb-1">事件内容</label>
              <textarea id="event-content" v-model="initialEventContent" rows="3" placeholder="这个世界发生的第一件事…"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
            </div>
            <div>
              <label for="event-time" class="text-sm text-ink block mb-1">事件时间</label>
              <input id="event-time" v-model="initialEventTime" type="text" placeholder="如：永和三年春、创世之初…"
                class="w-full border border-border-light rounded-lg px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30" />
            </div>
          </div>
        </section>

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
            <div v-for="(ch, i) in characters" :key="i" class="bg-white rounded-xl border border-border-light p-5 space-y-3">
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
                  <textarea v-model="attitudesTexts[i]" rows="2" placeholder="角色A: 信任&#10;角色B: 戒备"
                    class="w-full border border-border-light rounded px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-old-gold/30 resize-none" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <div class="flex items-center gap-3 pt-4 border-t border-border-light">
          <BaseButton variant="primary" :disabled="isSubmitting" @click="handleSave">
            {{ isSubmitting ? '保存中…' : '保存' }}
          </BaseButton>
          <BaseButton variant="secondary" :disabled="isSubmitting" @click="cancelEdit">
            取消
          </BaseButton>
        </div>
      </div>
    </template>
  </div>
</template>
