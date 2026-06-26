// SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
// SPDX-License-Identifier: AGPL-3.0-or-later

export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  appName:    import.meta.env.VITE_APP_NAME || '萦回',
  appVersion: import.meta.env.VITE_APP_VERSION || '1.0.0',
  appAuthor:  import.meta.env.VITE_APP_AUTHOR || '这就是AI',
}
