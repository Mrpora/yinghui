# ═══ 后端 Dockerfile ═══
# 多阶段构建：pip install + 模型下载 → 精简运行时

FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── 下载 BGE 嵌入模型 ──
# DOWNLOAD_MODEL=false 跳过下载（回退到 BM25 检索）
# HF_ENDPOINT 默认走国内镜像，直连可设为 https://huggingface.co
ARG DOWNLOAD_MODEL=true
ARG HF_ENDPOINT=https://hf-mirror.com
RUN mkdir -p /build/models \
    && if [ "$DOWNLOAD_MODEL" = "true" ]; then \
    python -c "
import os
os.environ['HF_ENDPOINT'] = '$HF_ENDPOINT'
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-large-zh-v1.5', local_dir='/build/models/bge-large-zh-v1.5')
" \
    ; else \
    touch /build/models/.gitkeep ; \
    fi

# ═══ 运行时 ═══
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r yinghui && useradd -r -g yinghui -d /app yinghui

WORKDIR /app

COPY --from=builder /root/.local /home/yinghui/.local
ENV PATH="/home/yinghui/.local/bin:$PATH"

# 复制嵌入模型（如已下载）
COPY --from=builder /build/models/ ./models/
RUN chown -R yinghui:yinghui /app/models 2>/dev/null || true

COPY server/ ./server/
COPY requirements.txt ./

RUN chown -R yinghui:yinghui /app
USER yinghui

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

CMD ["python", "-m", "server.main"]
