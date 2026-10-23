# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""启动预加载——嵌入模型（原系统提示词预载随内置 agent 编排移除，prompts 资产迁往 yinghui-dsh-plug）。"""
import logging

logger = logging.getLogger(__name__)

# 全局缓存
_embedding_model = None


def preload_embedding_model():
    """预加载 BGE-large-zh-v1.5 嵌入模型。"""
    global _embedding_model
    from server.services.embedding_service import load_model
    _embedding_model = load_model()
    logger.info("✅ 嵌入模型预加载完成")
    return _embedding_model


def get_embedding_model():
    """获取已缓存的嵌入模型实例。"""
    return _embedding_model


def preload_all():
    """启动时调用——预加载嵌入模型（jieba 预载在 main.py lifespan 中单独调用）。"""
    preload_embedding_model()
    logger.info("✅ 启动预加载完成 embedding=ready")
