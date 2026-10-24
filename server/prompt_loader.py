# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""启动预加载——嵌入模型（原系统提示词预载随内置 agent 编排移除，prompts 资产迁往 yinghui-dsh-plug）。"""
import logging

logger = logging.getLogger(__name__)

# 全局缓存
_embedding_model = None


def preload_embedding_model():
    """预加载 BGE-large-zh-v1.5 嵌入模型。

    库未安装或模型文件缺失时降级为 BM25-only（与 README 的降级语义一致），
    不阻断启动——本地开发环境通常不装 sentence-transformers（Docker 构建才安装）。
    """
    global _embedding_model
    try:
        from server.services.embedding_service import load_model
        _embedding_model = load_model()
        logger.info("✅ 嵌入模型预加载完成")
    except Exception as exc:  # noqa: BLE001——任何加载失败都降级，不阻断启动
        _embedding_model = None
        logger.warning("⚠️ 嵌入模型预加载失败，向量检索降级为 BM25-only：%s: %s",
                       type(exc).__name__, exc)
    return _embedding_model


def get_embedding_model():
    """获取已缓存的嵌入模型实例。"""
    return _embedding_model


def preload_all():
    """启动时调用——预加载嵌入模型（jieba 预载在 main.py lifespan 中单独调用）。"""
    preload_embedding_model()
    logger.info("✅ 启动预加载完成 embedding=ready")
