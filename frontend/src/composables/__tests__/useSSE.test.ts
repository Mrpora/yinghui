// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { useSSE } from '@/composables/useSSE'

describe('useSSE', () => {
  it('returns connect/disconnect/on/off without watch', () => {
    const sse = useSSE()
    expect(sse.connectionStatus.value).toBe('disconnected')
    expect(typeof sse.connect).toBe('function')
    expect(typeof sse.disconnect).toBe('function')
    expect(typeof sse.on).toBe('function')
    expect(typeof sse.off).toBe('function')
  })

  it('connect accepts channel and userId parameters', () => {
    const sse = useSSE('/api/test')
    expect(sse.connect.length).toBe(2)
  })
})
