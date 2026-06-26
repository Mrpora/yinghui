# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""启动预加载——系统提示词 + 嵌入模型。"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 全局缓存
PROMPTS: dict[str, str] = {}
_embedding_model = None


def preload_prompts(prompt_dir: str) -> dict[str, str]:
    """遍历 prompt_dir 下所有 .md 文件，加载到 dict。
    key 为子目录名/文件名（不含 .md），如 `evolution_agent/director_system`。
    """
    base = Path(prompt_dir)
    for md_file in base.rglob("*.md"):
        rel = md_file.relative_to(base).with_suffix("")
        key = str(rel).replace("\\", "/")
        # 剥离 prompts/ 中间目录，使 key 为 `evolution_agent/director_system`
        key = key.replace("/prompts/", "/")
        PROMPTS[key] = md_file.read_text(encoding="utf-8")
        logger.info("📄 prompt 已加载: %s (%d 字符)", key, len(PROMPTS[key]))
    logger.info("✅ 全部 prompt 加载完成，共 %d 个", len(PROMPTS))
    return PROMPTS


def preload_embedding_model():
    """预加载 BGE-large-zh-v1.5 嵌入模型。"""
    global _embedding_model
    from server.services.embedding_service import load_model
    _embedding_model = load_model()
    logger.info("✅ 嵌入模型预加载完成")
    return _embedding_model


def get_prompt(key: str) -> str:
    """按 key 获取已缓存的系统提示词。"""
    return PROMPTS.get(key, "")


def get_embedding_model():
    """获取已缓存的嵌入模型实例。"""
    return _embedding_model


def preload_all():
    """启动时调用——预加载所有提示词和嵌入模型。"""
    preload_embedding_model()
    preload_prompts(Path(__file__).resolve().parent / "ai")
    logger.info("✅ 启动预加载全部完成 embedding=ready prompt=%d", len(PROMPTS))
