<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
defineProps<{
  current: number
  max: number
}>()
</script>

<template>
  <div class="text-center py-3">
    <h3 class="text-sm font-medium text-ink/70 tracking-wider mb-1.5">演化</h3>
    <span class="text-5xl text-old-gold font-serif font-bold">
      {{ current }}
    </span>
    <span class="text-smoke text-base"> / {{ max }}</span>
  </div>
</template>
