"""Pydantic 世界配置模型。"""
from pydantic import BaseModel, ConfigDict, Field


class WorldInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    description: str
    world_history: str = ""
    rules: list[str]


class CharacterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    identity: str
    personality: str
    speech_style: str
    goal: str
    attitudes: dict[str, str]
    accent_color: str = ""
    backstory: str = ""
    initial_location: str
    initial_state: str


class InitialEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str
    time: str


class WorldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world: WorldInfo
    characters: list[CharacterConfig] = Field(min_length=1)
    initial_event: InitialEvent

    @property
    def character_names(self) -> list[str]:
        return [c.name for c in self.characters]

    def get_character(self, name: str) -> CharacterConfig | None:
        for c in self.characters:
            if c.name == name:
                return c
        return None
