from typing import Literal

import yaml
from pydantic import BaseModel


class ClaimCriteria(BaseModel):
    character: list[str] = []
    series: list[str] = []
    minKakera: int = 10_000


class ClaimConfig(BaseModel):
    snipe: ClaimCriteria = ClaimCriteria()
    earlyClaim: ClaimCriteria = ClaimCriteria()
    lateClaim: ClaimCriteria = ClaimCriteria()


class RollConfig(BaseModel):
    command: Literal["$wg"]

class ClaimRule:
    criteria: ClaimCriteria


class MudaeConfig(BaseModel):
    roll: RollConfig
    claim: ClaimConfig


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


def get_config(path: str = "configs/main.yaml"):
    with open(path, "r") as f:
        yaml_data = yaml.safe_load(f)
        return Config(**yaml_data)
