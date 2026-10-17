# SPDX-FileCopyrightText: 2025-2026  mrpora@163.com
# SPDX-License-Identifier: AGPL-3.0-or-later

"""会话管理器——世界演化会话生命周期管理。

完全基于 SQLite（world_evolutions 表）实现，替代原 Redis 版本。
上下文、时间线、关系等均存储为 world_evolutions 表的 JSON 列。
"""
import json
import logging
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum

from fastapi import HTTPException

from server.config import config
from server.storage.sqlite_client import get_db, now_ms
from server.prompt_loader import get_prompt

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

    def __init__(self):
        self.director_template = get_prompt("evolution_agent/director_system")
        if not self.director_template:
            self.director_template = get_prompt("evolution_agent_v2/director_system")
        self.world_injection_template = get_prompt("evolution_agent_v2/world_injection")
        self.character_template = get_prompt("evolution_agent/character_system")
        if not self.character_template:
            self.character_template = get_prompt("evolution_agent_v2/character_system")
        if not self.director_template or not self.world_injection_template or not self.character_template:
            logger.warning(
                "⚠️ 演化 Agent 提示词未找到: director=%s world_injection=%s character=%s",
                bool(self.director_template), bool(self.world_injection_template), bool(self.character_template),
            )

    # ── Prompt 构建 ──

    def _build_director_context(self, wc: WorldConfig) -> list[dict]:
        world_config_json = json.dumps({
            "world": {
                "name": wc.world.name,
                "description": wc.world.description,
                "world_history": wc.world.world_history,
                "rules": wc.world.rules,
            },
            "characters": [
                {
                    "name": c.name,
                    "identity": c.identity,
                    "personality": c.personality,
                    "speech_style": c.speech_style,
                    "goal": c.goal,
                    "attitudes": c.attitudes,
                    "backstory": c.backstory,
                    "initial_location": c.initial_location,
                    "initial_state": c.initial_state,
                }
                for c in wc.characters
            ],
            "initial_event": {
                "content": wc.initial_event.content,
                "time": wc.initial_event.time,
            },
        }, ensure_ascii=False, indent=2)
        prompt = (self.director_template
                  .replace("{world_name}", wc.world.name)
                  .replace("{world_config}", world_config_json))
        return [{"role": "system", "content": prompt}]

    def _build_character_context(self, char: CharacterConfig, wc: WorldConfig) -> list[dict]:
        knowledge_lines = []
        for other in wc.characters:
            if other.name == char.name:
                continue
            knowledge_lines.append(f"- {other.name}：{other.identity}，{other.personality}")
        rules_lines = [f"- {r}" for r in wc.world.rules]
        attitude_lines = []
        for target, attitude in char.attitudes.items():
            attitude_lines.append(f"- 对{target}：{attitude}")
        prompt = (self.character_template
                  .replace("{character_name}", char.name)
                  .replace("{identity}", char.identity)
                  .replace("{personality}", char.personality)
                  .replace("{speech_style}", char.speech_style)
                  .replace("{world_name}", wc.world.name)
                  .replace("{world_description}", wc.world.description)
                  .replace("{world_history}", wc.world.world_history)
                  .replace("{world_rules}", "\n".join(rules_lines))
                  .replace("{world_knowledge}", "\n".join(knowledge_lines))
                  .replace("{attitude_block}", "\n".join(attitude_lines))
                  .replace("{core_goal}", char.goal)
                  .replace("{backstory}", char.backstory))
        return [{"role": "system", "content": prompt}]

    def _build_world_config_json(self, wc: WorldConfig) -> str:
        """将 WorldConfig 序列化为 JSON 字符串（供 world_injection 模板使用）。"""
        world_config = {
            "world": {
                "name": wc.world.name,
                "description": wc.world.description,
                "world_history": wc.world.world_history,
                "rules": wc.world.rules,
            },
            "characters": [
                {
                    "name": c.name,
                    "identity": c.identity,
                    "personality": c.personality,
                    "speech_style": c.speech_style,
                    "goal": c.goal,
                    "attitudes": c.attitudes,
                    "backstory": c.backstory,
                    "initial_location": c.initial_location,
                    "initial_state": c.initial_state,
                }
                for c in wc.characters
            ],
            "initial_event": {
                "content": wc.initial_event.content,
                "time": wc.initial_event.time,
            },
        }
        return json.dumps(world_config, ensure_ascii=False, indent=2)

    def _build_director_system_message(self) -> list[dict]:
        """构建导演 system message（无占位符，纯行为规范）。"""
        return [{"role": "system", "content": self.director_template}]

    def _build_world_injection_message(self, wc: WorldConfig) -> str:
        """构建首条 user message（世界配置注入）。"""
        template = self.world_injection_template or "{world_config_json}"
        world_json = self._build_world_config_json(wc)
        return template.replace("{world_config_json}", world_json)

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

        从 worlds/world_characters 读取世界配置，构建导演和角色上下文，
        写入 world_evolutions 表（SQLite）。
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

        # 构建上下文
        director_ctx = self._build_director_context(wc)
        char_ctxs = {}
        for i, cr in enumerate(char_rows):
            char_config = wc.characters[i]
            char_name = cr["name"]
            char_ctx = self._build_character_context(char_config, wc)
            char_ctxs[char_name] = char_ctx

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

        # 从 character_contexts 的 key 推导角色名称列表
        character_names = list(char_ctxs.keys())

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
