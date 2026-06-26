// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#FDF9F3',
        ink: '#3D3226',
        smoke: '#9B8E7E',
        frost: '#F3EDE3',
        cinnabar: '#C44B3A',
        moss: '#7A9A7E',
        persimmon: '#E2805C',
        'old-gold': '#B8835A',
        celadon: '#7B9A8E',
        'c-line-cyan': '#4ECDC4',
        'border-light': '#EBE5DA',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', '"Source Han Serif SC"', 'STSong', 'SimSun', 'serif'],
        sans: ['"Noto Sans SC"', '"Source Han Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
      },
      keyframes: {
        'cinnabar-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'celadon-pulse': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
      },
      animation: {
        'cinnabar-pulse': 'cinnabar-pulse 1.5s ease-in-out infinite',
        'fade-up': 'fade-up 0.5s ease-out',
        'celadon-pulse': 'celadon-pulse 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [typography],
} satisfies Config
