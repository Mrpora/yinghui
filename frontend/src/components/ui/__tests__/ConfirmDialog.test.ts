// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmDialog from '../ConfirmDialog.vue'

describe('ConfirmDialog', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mountDialog = (props: any) =>
    mount(ConfirmDialog, {
      props,
      global: { stubs: { teleport: true } },
    })

  it('does not render when visible is false', () => {
    const wrapper = mountDialog({ visible: false, title: 'T', message: 'M' })
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })

  it('renders title and message when visible', () => {
    const wrapper = mountDialog({ visible: true, title: 'Delete?', message: 'Are you sure?' })
    expect(wrapper.text()).toContain('Delete?')
    expect(wrapper.text()).toContain('Are you sure?')
  })

  it('emits cancel when backdrop is clicked', async () => {
    const wrapper = mountDialog({ visible: true, title: 'T', message: 'M' })
    await wrapper.find('.fixed').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('emits confirm when confirm button is clicked', async () => {
    const wrapper = mountDialog({ visible: true, title: 'T', message: 'M' })
    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons[buttons.length - 1]
    await confirmBtn.trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })
})
