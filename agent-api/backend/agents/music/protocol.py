from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(StrictModel):
    lights: list[str] = Field(default_factory=list, max_length=50)
    player: str = ""
    profile: Literal["ambient", "dynamic", "party"] = "ambient"
    intensity: float = Field(default=0.5, ge=0, le=1)


class Frame(StrictModel):
    version: Literal[1] = 1
    session: str = Field(min_length=16, max_length=80)
    seq: int = Field(ge=0)
    bass: float = Field(ge=0, le=1)
    mid: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)
    level: float = Field(ge=0, le=1)
    beat: bool = False
