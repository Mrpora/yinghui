# ═══ 前端 Dockerfile ═══
# 多阶段构建：Vite 编译 → Nginx 服务

# ── 阶段 1：构建 ──
FROM node:20-alpine AS builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── 阶段 2：Nginx 服务 ──
FROM nginx:alpine-slim

# 删除默认配置
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=builder /build/dist /usr/share/nginx/html

# Nginx 配置：SPA 路由 + API 代理 + 安全头 + gzip
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
