"""
AutoMudae Config

All classes related to the bot's configuration
"""

from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ClaimCriteria(BaseModel):
    """
    Criterias used in measuring whether a Claimable Roll should be claimed or not
    """

    wish: bool = False
    character: list[str] = Field(default_factory=list[str])
    series: list[str] = Field(default_factory=list[str])
    minKakera: int = 10_000


class ClaimConfig(BaseModel):
    """
    Configures how and when should a roll be judged
    """

    snipe: ClaimCriteria = ClaimCriteria()
    earlyClaim: ClaimCriteria = ClaimCriteria()
    lateClaim: ClaimCriteria = ClaimCriteria()


class RollConfig(BaseModel):
    """
    Configures when and what to roll
    """

    command: Literal["$wg", "$wa", "$w"]
    doNotRollWhenCanotClaim: bool = True
    doNotRollWhenCannotKakeraReact: bool = False


class MudaeConfig(BaseModel):
    """
    AutoMudae Mudae Configuration
    """

    roll: RollConfig
    claim: ClaimConfig


class DiscordConfig(BaseModel):
    """
    AutoMudae Discord Configuration
    """

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
    """
    AutoMudae Config
    """

    name: str
    version: Literal[1]
    discord: DiscordConfig
    mudae: MudaeConfig

    @classmethod
    def from_file(cls, path: str = "config/config.yaml"):
        """
        Load config from file
        """

        with open(path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
            return Config(**yaml_data)
