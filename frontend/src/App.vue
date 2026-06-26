<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import TopNav from '@/components/navigation/TopNav.vue'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/')
</script>

<template>
  <div class="min-h-screen bg-paper text-ink font-sans">
    <template v-if="isLoginPage">
      <router-view />
    </template>
    <template v-else>
      <TopNav />
      <router-view />
    </template>
  </div>
</template>
