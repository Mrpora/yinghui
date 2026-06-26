// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin } from '@/api/client'

export const useUserStore = defineStore('user', () => {
  const userId = ref(localStorage.getItem('userId') || '')
  const nickname = ref(localStorage.getItem('nickname') || '')

  const isLoggedIn = computed(() => !!userId.value)

  async function login(nick: string) {
    const res = await apiLogin(nick)
    userId.value = res.user_id
    nickname.value = res.nickname
    localStorage.setItem('userId', res.user_id)
    localStorage.setItem('nickname', res.nickname)
  }

  function logout() {
    userId.value = ''
    nickname.value = ''
    localStorage.removeItem('userId')
    localStorage.removeItem('nickname')
  }

  return { userId, nickname, isLoggedIn, login, logout }
})
