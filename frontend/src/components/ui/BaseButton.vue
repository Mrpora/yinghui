<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
defineProps<{
  variant?: 'primary' | 'secondary' | 'danger'
  disabled?: boolean
}>()

defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    :class="[
      'rounded-lg px-5 py-2.5 text-sm font-semibold transition-all duration-200 select-none shadow-sm',
      disabled
        ? 'opacity-40 cursor-not-allowed'
        : [
            'cursor-pointer active:scale-[0.98]',
            variant === 'danger'
              ? 'bg-cinnabar text-white hover:bg-cinnabar/85 shadow-cinnabar/20'
              : variant === 'secondary'
                ? 'border-2 border-old-gold text-old-gold hover:bg-old-gold hover:text-white'
                : 'bg-old-gold text-white hover:bg-old-gold/85 shadow-old-gold/25',
          ],
    ]"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>
