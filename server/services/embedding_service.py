# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""嵌入模型服务——加载 BGE-large-zh-v1.5，提供文本向量化接口。

供 prompt_loader 预加载调用（load_model），以及 memory/retrieval 服务
在运行时编码文本（encode / encode_single）。
"""
import os
import logging

from server.config import config

os.environ.setdefault("HF_HUB_OFFLINE", "1")

logger = logging.getLogger(__name__)

_model = None


def load_model():
    """加载嵌入模型（供 prompt_loader 在启动时预加载调用）。"""
    global _model
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(config.EMBEDDING_MODEL, local_files_only=True)
    logger.info("⏳ 嵌入模型就绪: %s", config.EMBEDDING_MODEL)
    return _model


def get_model():
    """获取已加载的嵌入模型（懒加载，首次请求时自动加载）。"""
    global _model
    if _model is None:
        logger.info("⏳ 首次请求，加载嵌入模型 %s ...", config.EMBEDDING_MODEL)
        load_model()
    return _model


def encode(texts: list[str]) -> list[list[float]]:
    """批量文本编码，返回归一化向量列表。"""
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def encode_single(text: str) -> list[float]:
    """单条文本编码，返回归一化向量。"""
    return encode([text])[0]
