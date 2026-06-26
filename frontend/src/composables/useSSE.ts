// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { ref } from 'vue'

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected'

export function useSSE(path = '/api/evolutions/events') {
  const eventSource = ref<EventSource | null>(null)
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const handlers = new Map<string, Set<(data: unknown) => void>>()
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let intentionalClose = false

  function on(event: string, handler: (data: unknown) => void) {
    if (!handlers.has(event)) handlers.set(event, new Set())
    handlers.get(event)!.add(handler)
  }

  function off(event: string, handler: (data: unknown) => void) {
    handlers.get(event)?.delete(handler)
  }

  function dispatch(event: string, data: unknown) {
    handlers.get(event)?.forEach(h => h(data))
    handlers.get('*')?.forEach(h => h(data))
  }

  function connect(channel: string, userId: string) {
    if (!channel) return
    disconnect()
    intentionalClose = false
    connectionStatus.value = 'connecting'
    const url = `${path}?evolution_id=${encodeURIComponent(channel)}&user_id=${encodeURIComponent(userId)}`
    const es = new EventSource(url)
    eventSource.value = es
    es.onopen = () => { connectionStatus.value = 'connected' }
    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        dispatch(msg.type || 'message', msg)
      } catch { /* 非 JSON 消息静默忽略 */ }
    }
    // 监听命名事件（如 event: connected）
    es.addEventListener('connected', () => {
      connectionStatus.value = 'connected'
    })
    es.onerror = () => {
      if (intentionalClose) return
      connectionStatus.value = 'disconnected'
      es.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(() => {
        if (channel && !intentionalClose) connect(channel, userId)
      }, 2000)
    }
  }

  function disconnect() {
    intentionalClose = true
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    eventSource.value?.close()
    eventSource.value = null
    connectionStatus.value = 'disconnected'
  }

  return { connectionStatus, connect, disconnect, on, off }
}

/** POST-based SSE for novel generation */
export function usePostSSE() {
  function stream(url: string, callbacks: {
    onEvent?: (type: string, data: unknown) => void
    onError?: (msg: string) => void
    onComplete?: () => void
  }): AbortController {
    const controller = new AbortController()
    fetch(url, {
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) { callbacks.onError?.(`HTTP ${res.status}`); return }
        if (!res.body) { callbacks.onError?.('No body'); return }
        const reader = res.body.getReader()
        controller.signal.addEventListener('abort', () => {
          reader.cancel().catch(() => {})
        })
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) { callbacks.onComplete?.(); break }
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const msg = JSON.parse(line.slice(6).trim())
                callbacks.onEvent?.(msg.type || 'message', msg)
              } catch { /* JSON 解析失败，静默忽略 */ }
            }
          }
        }
      })
      .catch((err) => { if (err.name !== 'AbortError') callbacks.onError?.(err.message) })
    return controller
  }

  return { stream }
}
