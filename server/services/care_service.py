# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
记忆回响服务——判断是否在对话开头注入回响记忆。

支持两种回响模式：
- 记忆回响（主动）（is_active=True）：用户刚打开新会话，注入 [待回响记忆]
- 记忆回响（被动）（is_active=False）：对话中途轮次，注入 [被动回响 - 事件记忆]
"""
import json
import random
import logging


from server.config import config
from server.storage.sqlite_client import get_db, now_ms

logger = logging.getLogger(__name__)


async def judge_and_prepare_care(
    user_id: str,
    novel_id: str,
    character_id: str,
    care_level: int,
    is_active: bool,
) -> dict | None:
    """判断是否需要注入回响记忆，并返回回响记忆 dict。

    流程：
    1. 以 care_level 为基础计算概率，随机决定是否触发。
    2. 从 memories 表中检索一条符合条件的 event 类型记忆（限定 novel）。
    3. 若找到，更新其 last_recalled_at 并返回回响记忆 dict。
    4. 若未找到或概率未命中，返回 None。

    Args:
        user_id: 用户 ID。
        novel_id: 小说 ID。
        character_id: 角色 ID（引用 novel_characters.character_id）。
        care_level: 记忆回响强度，取值范围 0–100，用于计算触发概率。
        is_active: True 表示记忆回响（主动）（新会话），False 表示记忆回响（被动）（对话中途）。

    Returns:
        dict | None: 回响记忆 dict，包含 role / content / timestamp / round 字段；
                     若无需回响则返回 None。
    """
    # 1. 概率判断
    p = (care_level / 100.0) * 0.8
    if random.random() > p:
        logger.debug("回响概率未命中 user=%s novel=%s care_level=%d p=%.2f",
                     user_id, novel_id, care_level, p)
        return None

    db = await get_db()
    now = now_ms()
    cooldown_threshold = now - config.CARE_COOLDOWN_HOURS * 3600 * 1000

    # 2. 事务内检索 + 更新时间戳，防止并发重复召回
    await db.execute("BEGIN IMMEDIATE")
    cursor = await db.execute(
        """SELECT m.memory_id, m.memory_type, m.content, m.created_at, m.updated_at,
                  json_extract(nc.character_snapshot, '$.name') AS character_name
           FROM memories m
           JOIN novel_characters nc ON m.character_id = nc.character_id
           WHERE m.user_id = ?
             AND m.novel_id = ?
             AND m.memory_type = 'event'
             AND (m.last_recalled_at IS NULL OR m.last_recalled_at < ?)
             AND (m.expires_at IS NULL OR m.expires_at >= ?)
           ORDER BY m.updated_at DESC
           LIMIT 1""",
        (user_id, novel_id, cooldown_threshold, now),
    )
    row = await cursor.fetchone()

    if row is None:
        await db.execute("ROLLBACK")
        logger.debug("回响无可用记忆 user=%s novel=%s",
                     user_id, novel_id)
        return None

    # 3. 立即更新时间戳（仍在事务内）防止并发选中同一条
    await db.execute(
        "UPDATE memories SET last_recalled_at = ? WHERE memory_id = ?",
        (now, row["memory_id"]),
    )
    await db.commit()

    # 4. 构建回响记忆 dict
    label = "[待回响记忆]" if is_active else "[被动回响 - 事件记忆]"
    memory_json = json.dumps(
        {
            "memory_id": row["memory_id"],
            "type": row["memory_type"],
            "content": row["content"],
            "character_name": row["character_name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
        ensure_ascii=False,
    )

    care_event = {
        "role": "care_event",
        "content": f"{label}\n{memory_json}",
        "timestamp": now,
        "round": 0,
    }

    logger.info(
        "📌 回响记忆触发 user_id=%s novel_id=%s character_id=%s is_active=%s memory_id=%s",
        user_id, novel_id, character_id, is_active, row["memory_id"],
    )
    return care_event
