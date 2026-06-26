<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useEvolutionStore } from '@/stores/evolution'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const evolution = useEvolutionStore()

const tabs = [
  { label: '世界', prefix: '/worlds', line: 'C' },
  { label: '演化', prefix: '/evolution', line: 'C' },
  { label: '小说', prefix: '/novels', line: 'C' },
  { label: '对话', prefix: '/chat', line: 'A' },
  { label: '记忆', prefix: '/memories', line: 'A' },
]

function isActive(tab: (typeof tabs)[0]) {
  if (tab.prefix === '/worlds') return route.path.startsWith('/worlds')
  if (tab.prefix === '/evolution') return route.path === '/evolution' || route.path.startsWith('/evolution/')
  if (tab.prefix === '/novels') return route.path.startsWith('/novels')
  if (tab.prefix === '/chat') return route.path.startsWith('/chat')
  if (tab.prefix === '/memories') return route.path.startsWith('/memories')
  return route.path === tab.prefix
}

function goEvolution() {
  router.push('/evolution')
}

function handleLogout() {
  user.logout()
  evolution.reset()
  router.push('/')
}

const cTabs = tabs.filter(t => t.line === 'C')
const aTabs = tabs.filter(t => t.line === 'A')
</script>

<template>
  <nav class="sticky top-0 z-40 h-12 bg-white/90 backdrop-blur border-b border-border-light flex items-center px-4 shrink-0">
    <!-- 品牌 Logo -->
    <img src="/assets/images/logo-icon.png" alt="萦回" class="h-7 w-auto mr-6 shrink-0" />

    <!-- C 线标签 -->
    <template v-for="tab in cTabs" :key="tab.label">
      <button
        v-if="tab.label === '演化'"
        class="text-sm px-3 py-1 transition-colors relative"
        :class="{
          'text-smoke hover:text-ink': !isActive(tab),
          'text-c-line-cyan': isActive(tab) && tab.line === 'C',
          'text-old-gold': isActive(tab) && tab.line === 'A',
        }"
        :aria-current="isActive(tab) ? 'page' : undefined"
        @click="goEvolution"
      >
        {{ tab.label }}
        <span
          v-if="isActive(tab)"
          class="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded"
          :class="{
            'bg-c-line-cyan': tab.line === 'C',
            'bg-old-gold': tab.line === 'A',
          }"
        />
      </button>
      <router-link
        v-else
        :to="tab.prefix"
        :aria-current="isActive(tab) ? 'page' : undefined"
        class="text-sm px-3 py-1 transition-colors relative"
        :class="{
          'text-smoke hover:text-ink': !isActive(tab),
          'text-c-line-cyan': isActive(tab) && tab.line === 'C',
          'text-old-gold': isActive(tab) && tab.line === 'A',
        }"
      >
        {{ tab.label }}
        <span
          v-if="isActive(tab)"
          class="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded"
          :class="{
            'bg-c-line-cyan': tab.line === 'C',
            'bg-old-gold': tab.line === 'A',
          }"
        />
      </router-link>
    </template>

    <!-- 分隔线 -->
    <span class="w-px h-5 bg-border-light mx-2" />

    <!-- A 线标签 -->
    <router-link
      v-for="tab in aTabs"
      :key="tab.label"
      :to="tab.prefix"
      :aria-current="isActive(tab) ? 'page' : undefined"
      class="text-sm px-3 py-1 transition-colors relative"
      :class="{
        'text-smoke hover:text-ink': !isActive(tab),
        'text-c-line-cyan': isActive(tab) && tab.line === 'C',
        'text-old-gold': isActive(tab) && tab.line === 'A',
      }"
    >
      {{ tab.label }}
      <span
        v-if="isActive(tab)"
        class="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded"
        :class="{
          'bg-c-line-cyan': tab.line === 'C',
          'bg-old-gold': tab.line === 'A',
        }"
      />
    </router-link>

    <div class="flex-1" />

    <!-- 用户区 -->
    <span class="text-smoke text-sm mr-4">{{ user.nickname }}</span>
    <button class="text-sm text-cinnabar hover:text-cinnabar/80 transition-colors" @click="handleLogout">
      退出
    </button>
  </nav>
</template>
