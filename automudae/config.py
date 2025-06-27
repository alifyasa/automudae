# pylint: disable=R0903
import logging
import sys
from typing import Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Criteria(BaseModel):

    wish: bool = False
    character: list[str] = Field(default_factory=list[str])
    series: list[str] = Field(default_factory=list[str])
    minKakera: int = sys.maxsize


class ClaimCriteria(Criteria):
    exception: Criteria = Field(default_factory=Criteria)


class ClaimConfig(BaseModel):

    snipe: ClaimCriteria = Field(default_factory=ClaimCriteria)
    earlyClaim: ClaimCriteria = Field(default_factory=ClaimCriteria)
    lateClaim: ClaimCriteria = Field(default_factory=ClaimCriteria)


class RollConfig(BaseModel):

    command: Literal["$wg", "$wa", "$w"]
    doNotRollWhenCannotClaim: bool
    doNotRollWhenCannotKakeraReact: bool
    rollResetMinuteOffset: int


class KakeraReactConfig(BaseModel):

    doNotReactToKakeraTypes: list[str] = Field(default_factory=list[str])
    doNotReactToKakeraTypeIfKakeraPowerLessThan: dict[str, int] = Field(
        default_factory=dict[str, int]
    )


class MudaeConfig(BaseModel):

    roll: RollConfig
    claim: ClaimConfig = Field(default_factory=ClaimConfig)
    kakeraReact: KakeraReactConfig = Field(default_factory=KakeraReactConfig)


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
