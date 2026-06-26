<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<template>
  <div class="flex items-center px-3 sm:px-6 py-2.5 sm:py-3 border-b border-frost bg-paper shrink-0">
    <div>
      <h2 class="font-serif text-base sm:text-lg" :style="{ color: accentColor || undefined }">{{ name }}</h2>
      <p class="text-smoke/80 text-xs">{{ identity }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  name: string
  identity: string
  memoryCount?: number
  accentColor?: string
}>()

defineEmits<{}>()
</script>
