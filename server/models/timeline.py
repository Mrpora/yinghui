"""时间线事件模型。"""
from server.storage.sqlite_client import now_ms
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["action", "conflict", "director_path", "scene_setting", "user_decision",
                    "user_intervene", "round_summary", "relationship", "branch_options"]


class ConflictSelfAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    potential_conflict_with: str | None = None
    reason: str | None = None


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    type: EventType
    round: int = Field(ge=0)  # round=0 为初始事件（scene_setting）
    character: str | None = None
    content: str = Field(min_length=1)
    motive: str | None = None
    inner_thoughts: str | None = None
    conflict_self_assessment: ConflictSelfAssessment | None = None
    involved_characters: list[str] | None = None
    source: str | None = None
    timestamp: int | None = None

    def assign_id(self, counter: int):
        self.id = f"evt_{counter:04d}"
        self.timestamp = now_ms()

    def to_sse_dict(self) -> dict:
        return self.model_dump(exclude_none=True)
