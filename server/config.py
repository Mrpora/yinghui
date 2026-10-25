# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""统一配置——从项目根目录 .env 加载全部环境变量。"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# .env 位于项目根目录（server/ 的上一级）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"配置项 {key} 的值 '{raw}' 不是有效整数") from None


def _float_env(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"配置项 {key} 的值 '{raw}' 不是有效浮点数") from None


def _list_env(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


class Config:
    def __init__(self) -> None:
        _project_root = Path(__file__).resolve().parent.parent

        # ── 演化（额度计算为领域逻辑） ──
        self.EVOLUTION_DEFAULT_ROUNDS: int = _int_env("EVOLUTION_DEFAULT_ROUNDS", 20)
        self.EVOLUTION_MAX_ROUNDS: int = _int_env("EVOLUTION_MAX_ROUNDS", 100)

        # ── 桥接（yinghui-dsh-plug bridge） ──
        self.BRIDGE_URL: str = os.getenv("BRIDGE_URL", "http://127.0.0.1:8100")
        # /api/agent/* 共享 token（横切鉴权）：空=开放（零配置启动/selftest 不变）；
        # 非空时全部 /api/agent/* 端点要求请求头 X-Agent-Token 匹配（失配 401）
        self.AGENT_TOKEN: str = os.getenv("AGENT_TOKEN", "")

        # ── 小说（precheck 硬门用） ──
        self.NOVEL_CHAPTER_MIN_CHARS: int = _int_env("NOVEL_CHAPTER_MIN_CHARS", 3000)
        self.NOVEL_CHAPTER_MAX_CHARS: int = _int_env("NOVEL_CHAPTER_MAX_CHARS", 5000)
        self.NOVEL_WORK_DIR_BASE: str = os.getenv("NOVEL_WORK_DIR_BASE", "data/work")

        # ── 记忆 ──
        self.MEMORY_LIMIT: int = _int_env("MEMORY_LIMIT", 10)
        self.INSTANT_MEMORY_SIZE: int = _int_env("INSTANT_MEMORY_SIZE", 200)
        self.CARE_COOLDOWN_HOURS: int = _int_env("CARE_COOLDOWN_HOURS", 24)
        self.RETRIEVAL_TOP_K: int = _int_env("RETRIEVAL_TOP_K", 5)
        self.DECAY_HALF_LIFE_DAYS: float = _float_env("DECAY_HALF_LIFE_DAYS", 15.0)

        # ── 嵌入 ──
        _embed_raw = os.getenv("EMBEDDING_MODEL", "models/bge-large-zh-v1.5")
        self.EMBEDDING_MODEL: str = str(_project_root / _embed_raw)
        self.EMBEDDING_DIM: int = _int_env("EMBEDDING_DIM", 1024)

        # ── 安全 ──
        self.ALERT_EMAIL: str = os.getenv("ALERT_EMAIL", "")

        # ── CORS ──
        # 允许跨域的来源（逗号分隔）；默认空=后端回落 "*"（开放所有来源，维持
        # 本地开发与 docker nginx 同源代理的现状兼容）。公网/跨域部署应显式
        # 收窄，如 CORS_ORIGINS=https://yinghui.example.com（debt-wave4a F2）
        self.CORS_ORIGINS: list[str] = _list_env("CORS_ORIGINS", [])

        # ── SQLite ──
        _sqlite_raw = os.getenv("SQLITE_PATH", "data/app.db")
        self.SQLITE_PATH: str = str(_project_root / _sqlite_raw)


config = Config()
