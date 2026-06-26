"""合并 API 请求/响应 Schema——来自 demoA 与 demoC-re，适配 11 表模型。"""
from pydantic import BaseModel, ConfigDict, Field

# ═══════════════════════════════════════════════════════════
# Auth（合并 demoA UserRegister + demoC-re Login）
# ═══════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(min_length=1, max_length=50)


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    nickname: str
    created_at: int


# ═══════════════════════════════════════════════════════════
# Character（demoA 原有）
# ═══════════════════════════════════════════════════════════

class CharacterResponse(BaseModel):
    """角色公开信息。world_knowledge 为内部字段，不返回前端。"""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    identity: str
    personality_traits: list[str]
    speaking_style: str
    accent_color: str
    relationships: dict[str, str]


class CharacterListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    characters: list[CharacterResponse]


# ═══════════════════════════════════════════════════════════
# World（demoC-re 原有，增量适配）
# ═══════════════════════════════════════════════════════════

class CharacterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    identity: str = ""
    personality: str = ""
    speech_style: str = ""
    goal: str = ""
    attitudes: dict[str, str] = Field(default_factory=dict)
    backstory: str = ""
    initial_location: str = ""
    initial_state: str = ""
    accent_color: str = ""


class CreateWorldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    world_history: str = ""
    rules: list[str] = Field(default_factory=list)
    initial_event: dict = Field(default_factory=dict)
    characters: list[CharacterCreate] = Field(min_length=1, max_length=3)


class CreateWorldResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str


class UpdateWorldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    world_history: str = ""
    rules: list[str] = Field(default_factory=list)
    initial_event: dict = Field(default_factory=dict)
    characters: list[CharacterCreate] = Field(min_length=1, max_length=3)


class WorldItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str
    name: str
    description: str
    rules: list[str]
    is_preset: bool
    character_count: int
    created_at: int


class WorldListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worlds: list[WorldItem]


# ═══════════════════════════════════════════════════════════
# Session（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1)
    world_id: str = Field(min_length=1)


# ═══════════════════════════════════════════════════════════
# Round（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class StartRoundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1)


class StartRoundResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    round: int
    status: str


# ═══════════════════════════════════════════════════════════
# Branch（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class SelectBranchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1)
    branch_index: int = Field(ge=0, le=5)


class SelectBranchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    selected_branch: dict


# ═══════════════════════════════════════════════════════════
# Custom Event（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class CustomEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1)
    event_text: str = Field(min_length=1, max_length=500)


class CustomEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool


# ═══════════════════════════════════════════════════════════
# Timeline（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class TimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evolution_id: str
    current_round: int
    events: list[dict]
    relationships: list[dict]


# ═══════════════════════════════════════════════════════════
# Novel（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class NovelGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    novel_id: str


class NovelGetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    novel_id: str
    title: str
    content: str
    generated_at: int


# ═══════════════════════════════════════════════════════════
# World Completion（demoC-re 原有）
# ═══════════════════════════════════════════════════════════

class CompleteConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_name: str = Field(min_length=1)
    world_description: str = Field(min_length=1)
    world_history: str = ""
    rules: list[str] = Field(default_factory=list)
    initial_event: dict | None = None
    characters: list[CharacterCreate] = Field(default_factory=list)


class CompleteConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_history: str | None = None
    rules: list[str] = Field(default_factory=list)
    initial_event: dict | None = None
    characters: list[CharacterCreate] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Chat（demoA 原有）
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    character_id: str
    novel_id: str | None = None
    content: str | None = None


# ═══════════════════════════════════════════════════════════
# Memory（demoA 原有）
# ═══════════════════════════════════════════════════════════

class MemoryItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    character_name: str
    memory_type: str
    content: str
    created_at: int
    expires_at: int | None
    recall_count: int


class MemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memories: list[MemoryItemResponse]


class DeleteMemoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    memory_id: str


class SetExpiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: int | None


class SetExpiryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    memory_id: str
    expires_at: int | None


class ClearMemoriesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    deleted_count: int


# ═══════════════════════════════════════════════════════════
# Care（demoA 原有）
# ═══════════════════════════════════════════════════════════

class CareLevelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int


class CareLevelUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    novel_id: str
    character_id: str
    level: int


class CareLevelUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    level: int
