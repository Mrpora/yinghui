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
        # ── LLM 通用 ──
        self.LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
        if not self.LLM_API_KEY:
            raise ValueError("LLM_API_KEY 环境变量未设置或为空，请在 .env 中配置")
        self.LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")

        _project_root = Path(__file__).resolve().parent.parent

        # ── 演化 Agent ──
        self.EVOLUTION_DIRECTOR_MODEL: str = os.getenv("EVOLUTION_DIRECTOR_MODEL", "deepseek-v4-flash")
        self.EVOLUTION_DIRECTOR_REASONING_EFFORT: str = os.getenv("EVOLUTION_DIRECTOR_REASONING_EFFORT", "max")
        self.EVOLUTION_DIRECTOR_MAX_TOKENS: int = _int_env("EVOLUTION_DIRECTOR_MAX_TOKENS", 32768)
        self.EVOLUTION_DIRECTOR_TEMPERATURE: float = _float_env("EVOLUTION_DIRECTOR_TEMPERATURE", 0.8)
        self.EVOLUTION_CHARACTER_MAX_TOKENS: int = _int_env("EVOLUTION_CHARACTER_MAX_TOKENS", 16384)
        self.EVOLUTION_CHARACTER_MODEL: str = os.getenv("EVOLUTION_CHARACTER_MODEL", "deepseek-v4-flash")
        self.EVOLUTION_CHARACTER_REASONING_EFFORT: str = os.getenv("EVOLUTION_CHARACTER_REASONING_EFFORT", "low")
        self.EVOLUTION_CHARACTER_ACTION_TEMPERATURE: float = _float_env("EVOLUTION_CHARACTER_ACTION_TEMPERATURE", 0.8)
        self.EVOLUTION_CHARACTER_ACTION_TOP_P: float = _float_env("EVOLUTION_CHARACTER_ACTION_TOP_P", 0.95)
        self.EVOLUTION_CHARACTER_ACTION_FREQUENCY_PENALTY: float = _float_env("EVOLUTION_CHARACTER_ACTION_FREQUENCY_PENALTY", 0.1)
        self.EVOLUTION_CHARACTER_ACTION_PRESENCE_PENALTY: float = _float_env("EVOLUTION_CHARACTER_ACTION_PRESENCE_PENALTY", 0.1)
        self.EVOLUTION_CHARACTER_STANCE_TEMPERATURE: float = _float_env("EVOLUTION_CHARACTER_STANCE_TEMPERATURE", 0.3)
        self.EVOLUTION_DEFAULT_ROUNDS: int = _int_env("EVOLUTION_DEFAULT_ROUNDS", 20)
        self.EVOLUTION_MAX_ROUNDS: int = _int_env("EVOLUTION_MAX_ROUNDS", 100)
        self.EVOLUTION_MAX_INTERACTION_ACTIONS: int = _int_env("EVOLUTION_MAX_INTERACTION_ACTIONS", 30)
        self.EVOLUTION_MAX_LOOPS: int = _int_env("EVOLUTION_MAX_LOOPS", 30)
        self.EVOLUTION_USER_DECISION_TIMEOUT: int = _int_env("EVOLUTION_USER_DECISION_TIMEOUT", 300)

        # ── 对话 Agent ──
        self.CHAT_MODEL: str = os.getenv("CHAT_MODEL", "deepseek-v4-pro")
        self.CHAT_REASONING_EFFORT: str = os.getenv("CHAT_REASONING_EFFORT", "high")
        self.CHAT_TEMPERATURE: float = _float_env("CHAT_TEMPERATURE", 0.5)
        self.CHAT_TOP_P: float = _float_env("CHAT_TOP_P", 1.0)
        self.CHAT_FREQUENCY_PENALTY: float = _float_env("CHAT_FREQUENCY_PENALTY", 0.4)
        self.CHAT_PRESENCE_PENALTY: float = _float_env("CHAT_PRESENCE_PENALTY", 0.5)
        self.CHAT_SEED: int = _int_env("CHAT_SEED", 42)
        self.CHAT_MAX_TOKENS: int = _int_env("CHAT_MAX_TOKENS", 2048)
        self.CHAT_STOP: list[str] = _list_env("CHAT_STOP", ["用户：", "User:", "用户说："])
        self.CHAT_MAX_AGENT_LOOP: int = _int_env("CHAT_MAX_AGENT_LOOP", 15)

        # ── 小说 Agent ──
        self.NOVEL_AGENT_MODEL: str = os.getenv("NOVEL_AGENT_MODEL", "deepseek-v4-flash")
        self.NOVEL_AGENT_REASONING_EFFORT: str = os.getenv("NOVEL_AGENT_REASONING_EFFORT", "max")
        self.NOVEL_AGENT_MAX_TOKENS: int = _int_env("NOVEL_AGENT_MAX_TOKENS", 327680)
        self.NOVEL_REVIEWER_MODEL: str = os.getenv("NOVEL_REVIEWER_MODEL", "deepseek-v4-flash")
        self.NOVEL_REVIEWER_REASONING_EFFORT: str = os.getenv("NOVEL_REVIEWER_REASONING_EFFORT", "high")
        self.NOVEL_REVIEWER_MAX_TOKENS: int = _int_env("NOVEL_REVIEWER_MAX_TOKENS", 327680)
        self.NOVEL_MAX_TURNS: int = _int_env("NOVEL_MAX_TURNS", 100)
        self.NOVEL_REVIEW_MAX: int = _int_env("NOVEL_REVIEW_MAX", 2)
        self.NOVEL_CYCLE_MAX: int = _int_env("NOVEL_CYCLE_MAX", 10)
        self.NOVEL_ROLLBACK_MAX: int = _int_env("NOVEL_ROLLBACK_MAX", 2)
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

        # ── 分词 ──
        self.TOKENIZER: str = os.getenv("TOKENIZER", "jieba")
        self.LLM_TOKENIZER_MODEL: str = os.getenv("LLM_TOKENIZER_MODEL", "deepseek-v4-flash")

        # ── 安全 ──
        self.ALERT_EMAIL: str = os.getenv("ALERT_EMAIL", "")

        # ── SQLite ──
        _sqlite_raw = os.getenv("SQLITE_PATH", "data/app.db")
        self.SQLITE_PATH: str = str(_project_root / _sqlite_raw)

        # ── LLM 重试 ──
        self.LLM_RETRY_MAX: int = _int_env("LLM_RETRY_MAX", 3)


config = Config()
