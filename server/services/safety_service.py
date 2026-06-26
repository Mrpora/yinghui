# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""安全服务——极端情绪报警，写入独立日志文件 logs/safety.log。"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from server.config import config
from server.storage.sqlite_client import now_ms

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

_alert_logger: logging.Logger | None = None


def _get_alert_logger() -> logging.Logger:
    """懒加载独立报警日志器，写入 logs/safety.log，与主日志隔离。"""
    global _alert_logger
    if _alert_logger is None:
        _alert_logger = logging.getLogger("safety")
        _alert_logger.setLevel(logging.WARNING)
        _alert_logger.propagate = False  # 不向根日志器重复输出

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_DIR / "safety.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-7s | %(message)s",
            datefmt="%m-%d %H:%M:%S",
        ))
        _alert_logger.addHandler(handler)

    return _alert_logger


def send_alert(nickname: str, user_quote: str, reason: str) -> dict:
    """记录极端情绪安全报警，写入独立日志文件 logs/safety.log。"""
    timestamp = now_ms()
    subject = f"[萦回安全报警] 用户 {nickname} 触发极端情绪"

    alert_logger = _get_alert_logger()
    alert_logger.warning(
        "=" * 60 + "\n"
        "主题: %s\n"
        "用户昵称: %s\n"
        "报警原因: %s\n"
        "用户原话: %s\n"
        "时间戳: %s\n"
        "报警邮箱: %s",
        subject, nickname, reason, user_quote, timestamp, config.ALERT_EMAIL,
    )

    return {"status": "success"}
