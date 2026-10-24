# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""会话管理器——世界演化会话生命周期管理。

完全基于 SQLite（world_evolutions 表）实现，替代原 Redis 版本。
上下文、时间线、关系等均存储为 world_evolutions 表的 JSON 列。

纯领域存储：不构建任何 LLM prompt（编排已外移至 yinghui-dsh-plug 桥接）。
director_context / character_contexts 列保留为持久化镜像——plug 播种
DSH 会话的数据源，也是 MCP 写入的落点；create() 不再预置内容。
"""
import json
import logging
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum

from fastapi import HTTPException

from server.config import config
from server.storage.sqlite_client import get_db, now_ms

logger = logging.getLogger(__name__)


# ── 简单数据类（Task 13-14 正式 Schema 合并后替换为 Pydantic models）──

class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_NEXT_ROUND = "waiting_next_round"
    ENDED = "ended"


@dataclass
class WorldInfo:
    name: str
    description: str
    world_history: str = ""
    rules: list[str] = field(default_factory=list)


@dataclass
class CharacterConfig:
    name: str
    identity: str
    personality: str
    speech_style: str
    goal: str
    attitudes: dict[str, str] = field(default_factory=dict)
    backstory: str = ""
    initial_location: str = ""
    initial_state: str = ""
    accent_color: str = ""


@dataclass
class InitialEvent:
    content: str
    time: str


@dataclass
class WorldConfig:
    world: WorldInfo
    characters: list[CharacterConfig]
    initial_event: InitialEvent

    @property
    def character_names(self) -> list[str]:
        return [c.name for c in self.characters]

    def get_character(self, name: str) -> CharacterConfig | None:
        for c in self.characters:
            if c.name == name:
                return c
        return None


@dataclass
class Session:
    id: str
    user_id: str
    world_id: str
    status: SessionStatus
    current_round: int
    max_rounds: int
    world_config: WorldConfig
    created_at: int
    director_context: list[dict] = field(default_factory=list)
    character_contexts: dict[str, list[dict]] = field(default_factory=dict)
    character_names: list[str] = field(default_factory=list)
    relationships: dict[str, dict[str, str]] = field(default_factory=dict)
    global_notify_count: int = 0


# ── 世界/角色查询（内联，后续统一到 storage 层）──

async def _get_world(world_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM worlds WHERE world_id = ? AND is_deleted = 0",
        (world_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def _get_world_characters(world_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM world_characters WHERE world_id = ? ORDER BY sort_order ASC",
        (world_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ── SessionManager ──

class SessionManager:
    """管理演化会话的完整生命周期——SQLite 持久化版本。"""

    # ── WorldConfig 构建 ──

    def _build_world_config(self, world_row: dict, char_rows: list[dict]) -> WorldConfig:
        return WorldConfig(
            world=WorldInfo(
                name=world_row["name"],
                description=world_row["description"],
                world_history=world_row.get("world_history", ""),
                rules=json.loads(world_row["rules"]),
            ),
            characters=[
                CharacterConfig(
                    name=cr["name"],
                    identity=cr.get("identity", ""),
                    personality=cr.get("personality", ""),
                    speech_style=cr.get("speech_style", ""),
                    goal=cr.get("goal", ""),
                    attitudes=json.loads(cr.get("attitudes", "{}")),
                    backstory=cr.get("backstory", ""),
                    initial_location=cr.get("initial_location", ""),
                    initial_state=cr.get("initial_state", ""),
                    accent_color=cr.get("accent_color", ""),
                ) for cr in char_rows
            ],
            initial_event=InitialEvent(**json.loads(world_row["initial_event"])),
        )

    # ── Session 生命周期 ──

    async def create(self, user_id: str, world_id: str) -> Session:
        """创建新的演化会话。

        从 worlds/world_characters 读取世界配置，写入 world_evolutions 表（SQLite）。
        director_context / character_contexts 置空（纯领域服务不再预置 prompt 上下文，
        由桥接进程播种 DSH 会话；MCP 经 get/set_context 读写该持久化镜像）。
        """
        world_row = await _get_world(world_id)
        if world_row is None:
            raise HTTPException(404, "世界不存在")
        char_rows = await _get_world_characters(world_id)
        wc = self._build_world_config(world_row, char_rows)

        sid = f"sess_{uuid4().hex[:8]}"
        now = now_ms()

        character_names = [cr["name"] for cr in char_rows]

        # 演化轮数与角色数正比：3 人 20 轮基准，封顶 EVOLUTION_MAX_ROUNDS
        max_rounds = min(
            config.EVOLUTION_MAX_ROUNDS,
            round(config.EVOLUTION_DEFAULT_ROUNDS * len(char_rows) / 3),
        )

        # 从 world_characters.attitudes 初始化角色关系
        initial_relationships: dict[str, dict[str, str]] = {}
        for char in wc.characters:
            for target, attitude in char.attitudes.items():
                initial_relationships.setdefault(char.name, {})[target] = attitude

        # 上下文列置空（持久化镜像，初始无内容）
        director_ctx: list[dict] = []
        char_ctxs: dict[str, list[dict]] = {}

        # 写入 world_evolutions 表
        db = await get_db()
        await db.execute(
            """INSERT INTO world_evolutions
               (evolution_id, user_id, world_id, status, current_round, max_rounds,
                global_notify_count,
                director_context, character_contexts, timeline, relationships,
                is_deleted, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid,
                user_id,
                world_id,
                SessionStatus.IDLE.value,
                0,
                max_rounds,
                0,
                json.dumps(director_ctx, ensure_ascii=False),
                json.dumps(char_ctxs, ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                json.dumps(initial_relationships, ensure_ascii=False),
                0,
                now,
            ),
        )
        await db.commit()

        logger.info(
            "📦 会话创建 session=%s user=%s world=%s chars=%d rounds=%d",
            sid, user_id, world_id, len(char_rows), max_rounds,
        )
        return Session(
            id=sid,
            user_id=user_id,
            world_id=world_id,
            status=SessionStatus.IDLE,
            current_round=0,
            max_rounds=max_rounds,
            world_config=wc,
            created_at=now,
            director_context=director_ctx,
            character_contexts=char_ctxs,
            character_names=character_names,
        )

    async def get(self, session_id: str, user_id: str | None = None) -> Session:
        """从 world_evolutions 表加载会话。"""
        db = await get_db()
        cursor = await db.execute(
            """SELECT * FROM world_evolutions
               WHERE evolution_id = ? AND is_deleted = 0""",
            (session_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(404, "会话不存在")
        meta = dict(row)
        if user_id and meta["user_id"] != user_id:
            raise HTTPException(403, "无权访问此会话")

        # 加载世界配置
        world_row = await _get_world(meta["world_id"])
        char_rows = await _get_world_characters(meta["world_id"])
        wc = self._build_world_config(world_row, char_rows)

        # 解析 JSON 列
        director_ctx = json.loads(meta.get("director_context", "[]"))
        char_ctxs = json.loads(meta.get("character_contexts", "{}"))

        # 角色名称来自世界配置（上下文列是持久化镜像，不承载角色清单）
        character_names = wc.character_names

        relationships = json.loads(meta.get("relationships", "{}"))

        return Session(
            id=session_id,
            user_id=meta["user_id"],
            world_id=meta["world_id"],
            status=SessionStatus(meta["status"]),
            current_round=int(meta["current_round"]),
            max_rounds=int(meta["max_rounds"]),
            world_config=wc,
            created_at=meta["created_at"],
            director_context=director_ctx,
            character_contexts=char_ctxs,
            character_names=character_names,
            relationships=relationships,
            global_notify_count=int(meta.get("global_notify_count", 0)),
        )

    async def delete(self, session_id: str, user_id: str):
        """软删除会话（设置 is_deleted=1）。"""
        db = await get_db()
        cursor = await db.execute(
            "SELECT user_id FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return
        if row["user_id"] != user_id:
            raise HTTPException(403, "无权删除此会话")

        await db.execute(
            "UPDATE world_evolutions SET is_deleted = 1 WHERE evolution_id = ?",
            (session_id,),
        )
        await db.commit()
        logger.info("🗑️ 会话删除 session=%s user=%s", session_id, user_id)

    async def update_meta(self, session_id: str, **kwargs):
        """更新会话元数据（status / current_round 等）。

        Args:
            session_id: 会话 ID
            **kwargs: 要更新的字段，如 status="running", current_round=3
        """
        db = await get_db()
        allowed = {"status", "current_round", "max_rounds", "global_notify_count"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(session_id)
        await db.execute(
            f"UPDATE world_evolutions SET {set_clause} WHERE evolution_id = ?",
            values,
        )
        await db.commit()

    async def compare_and_update(
        self, session_id: str, expected_statuses: list[str], **kwargs
    ) -> bool:
        """条件原子更新（状态机 CAS）：仅当当前 status ∈ expected_statuses 时更新。

        单条条件 UPDATE（WHERE status IN (...)），消除「读校验 → 异步 dispatch →
        写回」之间的 check-then-act 并发窗口：并发请求只有一个能占位成功。

        Args:
            session_id: 会话 ID
            expected_statuses: 允许占位的合法前置状态值列表
            **kwargs: 要更新的字段（同 update_meta 的白名单）

        Returns:
            是否占位成功（UPDATE rowcount > 0）。
        """
        db = await get_db()
        allowed = {"status", "current_round", "max_rounds", "global_notify_count"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        status_placeholders = ", ".join("?" for _ in expected_statuses)
        values = list(updates.values()) + [session_id, *expected_statuses]
        cursor = await db.execute(
            f"UPDATE world_evolutions SET {set_clause} "
            f"WHERE evolution_id = ? AND is_deleted = 0 "
            f"AND status IN ({status_placeholders})",
            values,
        )
        await db.commit()
        return cursor.rowcount > 0

    # ── 上下文操作 ──

    async def get_context(self, session_id: str, context_type: str) -> list[dict]:
        """获取导演或角色的对话上下文。

        Args:
            session_id: 会话 ID
            context_type: "director" 或角色名称
        """
        db = await get_db()
        cursor = await db.execute(
            "SELECT director_context, character_contexts FROM world_evolutions "
            "WHERE evolution_id = ? AND is_deleted = 0",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return []

        if context_type == "director":
            return json.loads(row["director_context"] or "[]")

        char_ctxs = json.loads(row["character_contexts"] or "{}")
        return char_ctxs.get(context_type, [])

    async def set_context(self, session_id: str, context_type: str, messages: list[dict]):
        """设置导演或角色的对话上下文。

        Args:
            session_id: 会话 ID
            context_type: "director" 或角色名称
            messages: 消息列表
        """
        db = await get_db()
        if context_type == "director":
            await db.execute(
                "UPDATE world_evolutions SET director_context = ? WHERE evolution_id = ?",
                (json.dumps(messages, ensure_ascii=False), session_id),
            )
        else:
            cursor = await db.execute(
                "SELECT character_contexts FROM world_evolutions "
                "WHERE evolution_id = ? AND is_deleted = 0",
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return
            char_ctxs = json.loads(row["character_contexts"] or "{}")
            char_ctxs[context_type] = messages
            await db.execute(
                "UPDATE world_evolutions SET character_contexts = ? WHERE evolution_id = ?",
                (json.dumps(char_ctxs, ensure_ascii=False), session_id),
            )
        await db.commit()

    # ── 时间线操作 ──

    async def get_timeline(self, session_id: str) -> list[dict]:
        """获取演化时间线。"""
        db = await get_db()
        cursor = await db.execute(
            "SELECT timeline FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return []
        return json.loads(row["timeline"] or "[]")

    _VALID_EVENT_TYPES = {
        "action", "conflict", "director_path", "scene_setting", "user_decision",
        "user_intervene", "round_summary", "relationship", "branch_options",
    }

    async def append_timeline_event(self, session_id: str, event: dict):
        """追加时间线事件。"""
        event_type = event.get("type", "")
        if event_type not in self._VALID_EVENT_TYPES:
            logger.warning(
                "时间线事件类型无效 session=%s type=%r，fallback 为 'action'",
                session_id, event_type,
            )
            event["type"] = "action"
        db = await get_db()
        cursor = await db.execute(
            "SELECT timeline FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return
        timeline = json.loads(row["timeline"] or "[]")
        timeline.append(event)
        await db.execute(
            "UPDATE world_evolutions SET timeline = ? WHERE evolution_id = ?",
            (json.dumps(timeline, ensure_ascii=False), session_id),
        )
        await db.commit()

    # ── 关系操作 ──

    async def get_relationships(self, session_id: str) -> dict[str, dict[str, str]]:
        """获取角色关系图。"""
        db = await get_db()
        cursor = await db.execute(
            "SELECT relationships FROM world_evolutions WHERE evolution_id = ? AND is_deleted = 0",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        return json.loads(row["relationships"] or "{}")

    async def set_relationships(self, session_id: str, relationships: dict[str, dict[str, str]]):
        """更新角色关系图。"""
        db = await get_db()
        await db.execute(
            "UPDATE world_evolutions SET relationships = ? WHERE evolution_id = ?",
            (json.dumps(relationships, ensure_ascii=False), session_id),
        )
        await db.commit()

    # ── 用户会话列表 ──

    async def list_user_sessions(self, user_id: str) -> list[dict]:
        """列出用户的所有未删除会话。"""
        db = await get_db()
        cursor = await db.execute(
            """SELECT e.evolution_id, e.world_id, e.status, e.current_round, e.max_rounds,
                      e.created_at, w.name as world_name
               FROM world_evolutions e
               LEFT JOIN worlds w ON e.world_id = w.world_id
               WHERE e.user_id = ? AND e.is_deleted = 0
               ORDER BY e.created_at DESC""",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [{"evolution_id": r["evolution_id"], "world_id": r["world_id"], "status": r["status"],
                 "current_round": r["current_round"], "max_rounds": r["max_rounds"],
                 "created_at": r["created_at"], "world_name": r["world_name"] or r["world_id"]}
                for r in rows]
