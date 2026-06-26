"""会话数据模型（Pydantic 版——供 API 路由使用）。"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from server.models.timeline import TimelineEvent
from server.models.world import WorldConfig


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_NEXT_ROUND = "waiting_next_round"
    ENDED = "ended"


class SessionResponse(BaseModel):
    """会话详情响应——返回给前端的序列化版本。"""
    model_config = ConfigDict(extra="forbid")
    evolution_id: str
    user_id: str
    world_id: str
    status: str
    current_round: int
    max_rounds: int
    created_at: int
    character_names: list[str]


class SessionListItem(BaseModel):
    """会话列表项——精简字段用于列表展示。"""
    model_config = ConfigDict(extra="forbid")
    evolution_id: str
    world_id: str
    status: str
    current_round: int
    max_rounds: int
    created_at: int
