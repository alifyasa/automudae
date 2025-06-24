# pylint: disable=R0903
from typing import Literal

import yaml
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class ClaimCriteria(BaseModel):

    wish: bool = False
    character: list[str] = Field(default_factory=list[str])
    series: list[str] = Field(default_factory=list[str])
    minKakera: int = 10_000


class ClaimConfig(BaseModel):

    snipe: ClaimCriteria = ClaimCriteria()
    earlyClaim: ClaimCriteria = ClaimCriteria()
    lateClaim: ClaimCriteria = ClaimCriteria()


class RollConfig(BaseModel):

    command: Literal["$wg", "$wa", "$w"] = "$w"
    doNotRollWhenCanotClaim: bool = True
    doNotRollWhenCannotKakeraReact: bool = False
    rollResetMinuteOffset: int = 0


class KakeraReactConfig(BaseModel):

    doNotReactToKakeraTypes: list[str] = Field(default_factory=list[str])
    doNotReactToKakeraTypeIfKakeraPowerLessThan: dict[str, int] = Field(
        default_factory=dict[str, int]
    )


class MudaeConfig(BaseModel):

    roll: RollConfig = RollConfig()
    claim: ClaimConfig = ClaimConfig()
    kakeraReact: KakeraReactConfig = KakeraReactConfig()


class DiscordConfig(BaseModel):

    token: str
    channelId: int
    mudaeBotId: int

    def __repr__(self) -> str:
        return (
            f"DiscordConfig(token='****', channelId=****, mudaeBotId={self.mudaeBotId})"
        )

    def __str__(self) -> str:
        return self.__repr__()


class Config(BaseModel):

    name: str
    version: Literal[1]
    discord: DiscordConfig
    mudae: MudaeConfig

    class Config:
        extra = "forbid"

    @classmethod
    def from_file(cls, path: str = "config/config.yaml"):
        logger.info("Loading Config from %s", path)
        with open(path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
            return Config(**yaml_data)
