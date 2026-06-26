// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseButton from '../BaseButton.vue'

describe('BaseButton', () => {
  it('renders default primary variant', () => {
    const wrapper = mount(BaseButton, { slots: { default: 'Click' } })
    expect(wrapper.text()).toBe('Click')
    expect(wrapper.classes()).toContain('bg-old-gold')
  })

  it('renders secondary variant', () => {
    const wrapper = mount(BaseButton, { props: { variant: 'secondary' }, slots: { default: 'Cancel' } })
    expect(wrapper.classes()).toContain('border-2')
    expect(wrapper.classes()).toContain('text-old-gold')
  })

  it('renders danger variant', () => {
    const wrapper = mount(BaseButton, { props: { variant: 'danger' }, slots: { default: 'Delete' } })
    expect(wrapper.classes()).toContain('bg-cinnabar')
  })

  it('is disabled when disabled prop is true', () => {
    const wrapper = mount(BaseButton, { props: { disabled: true }, slots: { default: 'Nope' } })
    expect(wrapper.attributes('disabled')).toBeDefined()
    expect(wrapper.classes()).toContain('opacity-40')
  })

  it('emits click event', async () => {
    const wrapper = mount(BaseButton, { slots: { default: 'Click' } })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
  })
})
