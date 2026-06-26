// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WorldItem } from '@/types'
import { listWorlds, getWorldDetail, createWorld, updateWorld, deleteWorld } from '@/api/client'
import { useUserStore } from './user'

export const useWorldStore = defineStore('world', () => {
  const worlds = ref<WorldItem[]>([])
  const currentWorld = ref<Record<string, unknown> | null>(null)
  const loading = ref(false)

  async function fetchWorlds() {
    const user = useUserStore()
    if (!user.userId) return
    loading.value = true
    try {
      const res = await listWorlds(user.userId)
      worlds.value = res.worlds
    } finally { loading.value = false }
  }

  async function fetchWorldDetail(worldId: string) {
    const detail = await getWorldDetail(worldId)
    currentWorld.value = detail as unknown as Record<string, unknown>
    return detail
  }

  async function addWorld(data: Parameters<typeof createWorld>[0]) {
    const res = await createWorld(data)
    await fetchWorlds()
    return res
  }

  async function modifyWorld(worldId: string, data: Parameters<typeof createWorld>[0]) {
    const user = useUserStore()
    const res = await updateWorld({ ...data, world_id: worldId, user_id: user.userId } as Parameters<typeof updateWorld>[0])
    await fetchWorlds()
    return res
  }

  async function removeWorld(worldId: string) {
    const user = useUserStore()
    await deleteWorld(worldId, user.userId)
    await fetchWorlds()
  }

  return { worlds, currentWorld, loading, fetchWorlds, fetchWorldDetail, addWorld, modifyWorld, removeWorld }
})
