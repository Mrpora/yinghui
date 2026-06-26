<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  relationships: { from: string; to: string; relationship: string }[]
}>()

// 按 from 分组
const groupedEdges = computed(() => {
  const map = new Map<string, typeof props.relationships>()
  for (const e of props.relationships) {
    if (!map.has(e.from)) map.set(e.from, [])
    map.get(e.from)!.push(e)
  }
  return map
})

// 颜色编码：正面=celadon，负面=cinnabar，中性=old-gold
function badgeClass(rel: string): string {
  const positive = ['信任', '友好', '爱慕', '关心', '忠诚', '敬仰', '依赖', '钦佩', '喜爱', '亲密', '友善']
  const negative = ['警惕', '敌意', '仇恨', '恐惧', '厌恶', '嫉妒', '怀疑', '轻视', '戒备', '敌视', '怨恨']
  if (positive.some(k => rel.includes(k))) return 'bg-celadon/10 text-celadon border-celadon/30'
  if (negative.some(k => rel.includes(k))) return 'bg-cinnabar/10 text-cinnabar border-cinnabar/30'
  return 'bg-old-gold/10 text-old-gold border-old-gold/30'
}
</script>

<template>
  <div class="space-y-2">
    <h3 class="text-sm font-medium text-ink/70 tracking-wider mb-1.5">角色关系</h3>

    <div v-if="groupedEdges.size === 0" class="text-xs text-smoke/50 italic">
      演化后将展示关系
    </div>
    <div v-else class="space-y-3">
      <div v-for="[char, rels] in groupedEdges" :key="char" class="space-y-1">
        <p class="text-xs text-ink font-serif">{{ char }}</p>
        <div
          v-for="e in rels"
          :key="`${e.from}-${e.to}`"
          class="flex items-center gap-2 pl-3 text-xs"
        >
          <span class="text-smoke shrink-0">→ {{ e.to }}</span>
          <span
            class="inline-block px-1.5 py-0.5 rounded border text-[10px] leading-tight"
            :class="badgeClass(e.relationship)"
          >
            {{ e.relationship }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
