<!--
  SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
  SPDX-License-Identifier: AGPL-3.0-or-later
-->

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

const nickname = ref('')
const error = ref('')
const isSubmitting = ref(false)

const trimmed = () => nickname.value.trim()

async function handleLogin() {
  if (isSubmitting.value) return
  error.value = ''
  if (!trimmed()) {
    error.value = '昵称不能为空'
    return
  }
  isSubmitting.value = true
  try {
    await user.login(trimmed())
    router.push('/worlds')
  } catch (e: unknown) {
    error.value = (e as Error).message || '登录失败，请重试'
  } finally {
    isSubmitting.value = false
  }
}

function onEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') handleLogin()
}
</script>

<template>
  <div class="login-root">
    <!-- 氛围光晕 -->
    <div class="glow" />

    <!-- 品牌标签 -->
    <p class="brand-tag">AI 互动叙事平台</p>

    <!-- 主标题：逐字浮现 -->
    <h1 class="main-title">
      <span
        v-for="(char, i) in '萦回'"
        :key="i"
        class="title-char"
        :style="{ animationDelay: `${i * 300}ms` }"
      >{{ char }}</span>
    </h1>

    <!-- 品牌宣传语 -->
    <p class="tagline">
      <span
        v-for="(char, i) in '故事萦回，余音不去。'"
        :key="i"
        class="tagline-char"
        :style="{
          animationDelay: `${0.9 + i * 0.08}s, ${3 + i * 0.15}s`,
        }"
      >{{ char }}</span>
    </p>

    <!-- 金色分隔线 -->
    <div class="divider" />

    <!-- 输入区 -->
    <div class="input-area">
      <div class="input-wrapper">
        <input
          v-model="nickname"
          type="text"
          maxlength="20"
          placeholder="输入你的昵称"
          :disabled="isSubmitting"
          class="nickname-input"
          @keydown="onEnter"
          @input="error = ''"
        />
      </div>

      <button
        :disabled="!trimmed() || isSubmitting"
        class="submit-btn"
        @click="handleLogin"
      >
        <span v-if="isSubmitting" class="btn-loading">
          <span class="spinner-sm" />
          进入中…
        </span>
        <span v-else>登录</span>
      </button>
    </div>

    <!-- 错误提示 -->
    <p v-if="error && !isSubmitting" class="error-msg">{{ error }}</p>

    <!-- 底部标注 -->
    <p class="footer-text">体验版</p>
  </div>
</template>

<style scoped>
/* ═══ 根容器 ═══ */
.login-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  padding: 2rem;
}

/* ═══ 氛围光晕 ═══ */
.glow {
  position: absolute;
  top: 30%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 480px;
  height: 480px;
  border-radius: 50%;
  background: radial-gradient(
    circle,
    rgba(184, 131, 90, 0.08) 0%,
    rgba(184, 131, 90, 0.03) 40%,
    transparent 70%
  );
  pointer-events: none;
}

/* ═══ 品牌标签 ═══ */
.brand-tag {
  font-size: 0.7rem;
  color: var(--smoke);
  letter-spacing: 0.35em;
  text-transform: uppercase;
  margin-bottom: 1.5rem;
  position: relative;
  z-index: 1;
  animation: login-fade-in 0.8s ease both;
}

/* ═══ 主标题 ═══ */
.main-title {
  font-size: clamp(3rem, 8vw, 4.5rem);
  font-weight: 800;
  letter-spacing: 0.3em;
  color: var(--ink);
  margin: 0 0 1.25rem;
  position: relative;
  z-index: 1;
  line-height: 1.2;
}

.title-char {
  display: inline-block;
  opacity: 0;
  animation: login-fade-up 0.6s cubic-bezier(0.22, 0.61, 0.36, 1) both;
  text-shadow: 0 1px 2px rgba(61, 50, 38, 0.06);
}

/* ═══ 品牌宣传语 ═══ */
.tagline {
  font-size: 1.05rem;
  color: var(--old-gold);
  letter-spacing: 0.15em;
  margin: 0.25rem 0 1.5rem;
  position: relative;
  z-index: 1;
  opacity: 0.8;
}

.tagline-char {
  display: inline-block;
  opacity: 0;
  animation:
    tagline-reveal 1.2s cubic-bezier(0.22, 0.61, 0.36, 1) both,
    tagline-wave 3s ease-in-out infinite;
}

@keyframes tagline-reveal {
  0% {
    opacity: 0;
    transform: translateY(6px);
    letter-spacing: 0.5em;
  }
  100% {
    opacity: 1;
    transform: translateY(0);
    letter-spacing: 0.15em;
  }
}

@keyframes tagline-wave {
  0%, 100% {
    opacity: 0.7;
    text-shadow: 0 0 0 rgba(184, 131, 90, 0);
  }
  50% {
    opacity: 1;
    text-shadow: 0 0 8px rgba(184, 131, 90, 0.25);
  }
}

/* ═══ 分隔线 ═══ */
.divider {
  width: 130px;
  height: 2px;
  background: rgba(184, 131, 90, 0.12);
  border-radius: 1px;
  margin-bottom: 2.5rem;
  position: relative;
  z-index: 1;
  animation: login-divider-expand 0.7s 0.9s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}

/* 滑动的金色光珠 */
.divider::after {
  content: '';
  position: absolute;
  top: -1px;
  left: 0;
  height: 4px;
  width: 28px;
  background: radial-gradient(
    ellipse at center,
    var(--old-gold) 0%,
    rgba(184, 131, 90, 0.5) 35%,
    transparent 70%
  );
  border-radius: 2px;
  animation: divider-glide 3s linear infinite;
  animation-delay: 1.6s;
}

@keyframes divider-glide {
  /* 左端：收缩、隐藏 */
  0% {
    transform: translateX(0px) scaleX(0.35);
    opacity: 0;
  }
  /* 淡入（原地） */
  8% {
    transform: translateX(0px) scaleX(0.35);
    opacity: 1;
  }
  /* 左→中：展开 */
  25% {
    transform: translateX(51px) scaleX(1);
    opacity: 1;
  }
  /* 中→右：收缩 */
  42% {
    transform: translateX(102px) scaleX(0.35);
    opacity: 1;
  }
  /* 淡出（原地） */
  50% {
    transform: translateX(102px) scaleX(0.35);
    opacity: 0;
  }
  /* 淡入（原地） */
  58% {
    transform: translateX(102px) scaleX(0.35);
    opacity: 1;
  }
  /* 右→中：展开 */
  75% {
    transform: translateX(51px) scaleX(1);
    opacity: 1;
  }
  /* 中→左：收缩 */
  92% {
    transform: translateX(0px) scaleX(0.35);
    opacity: 1;
  }
  /* 淡出（原地） */
  100% {
    transform: translateX(0px) scaleX(0.35);
    opacity: 0;
  }
}

/* ═══ 输入区 ═══ */
.input-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
  opacity: 0;
  animation: login-fade-up 0.6s 1.1s cubic-bezier(0.22, 0.61, 0.36, 1) both;
  position: relative;
  z-index: 1;
}

.input-wrapper {
  position: relative;
}

.nickname-input {
  width: 260px;
  padding: 0.7rem 0.5rem;
  text-align: center;
  font-size: 1.05rem;
  font-family: inherit;
  color: var(--ink);
  background: transparent;
  border: none;
  border-bottom: 2px solid var(--border-light);
  outline: none;
  transition: border-color 0.35s ease;
  letter-spacing: 0.08em;
}

.nickname-input::placeholder {
  color: var(--smoke);
  letter-spacing: 0.08em;
}

.nickname-input:focus {
  border-bottom-color: var(--old-gold);
}

.nickname-input:disabled {
  opacity: 0.4;
}

/* ═══ 提交按钮 ═══ */
.submit-btn {
  padding: 0.55rem 2.25rem;
  font-size: 0.95rem;
  font-family: inherit;
  color: var(--old-gold);
  background: transparent;
  border: 1px solid var(--old-gold);
  border-radius: 2px;
  cursor: pointer;
  letter-spacing: 0.25em;
  transition: all 0.3s ease;
  position: relative;
}

.submit-btn:hover:not(:disabled) {
  background: var(--old-gold);
  color: #fff;
}

.submit-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.submit-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.btn-loading {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

/* ═══ 微型旋转器 ═══ */
.spinner-sm {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--old-gold);
  border-top-color: transparent;
  border-radius: 50%;
  animation: login-spin 0.6s linear infinite;
}

/* ═══ 错误提示 ═══ */
.error-msg {
  margin-top: 1rem;
  font-size: 0.85rem;
  color: var(--cinnabar);
  opacity: 0.9;
  animation: login-fade-in 0.3s ease both;
  position: relative;
  z-index: 1;
}

/* ═══ 底部标注 ═══ */
.footer-text {
  position: absolute;
  bottom: 1.75rem;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 0.7rem;
  color: var(--smoke);
  letter-spacing: 0.25em;
  opacity: 0.7;
}

/* ═══ 关键帧 ═══ */
@keyframes login-fade-up {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes login-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes login-divider-expand {
  from {
    width: 0;
    opacity: 0;
  }
  to {
    width: 130px;
    opacity: 1;
  }
}

@keyframes login-spin {
  to { transform: rotate(360deg); }
}
</style>
