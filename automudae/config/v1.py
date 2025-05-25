from typing import Literal

import yaml
from pydantic import BaseModel


class WishConfig(BaseModel):
    character: list[str]
    series: list[str]


class ClaimConfig(BaseModel):
    claimBeforeResetIfKakeraMoreThan: int
    claimRegardlessResetIfKakeraMoreThan: int


class SnipeConfig(BaseModel):
    kakera: bool
    character: bool
    series: bool


class RollConfig(BaseModel):
    command: Literal["$wg"]


class MudaeConfig(BaseModel):
    roll: RollConfig
    snipe: SnipeConfig
    claim: ClaimConfig
    wish: WishConfig


class DiscordConfig(BaseModel):
    token: str
    channelId: int
    mudaeBotId: int


class Config(BaseModel):
    name: str
    version: Literal[1]
    discord: DiscordConfig
    mudae: MudaeConfig


def get_config(path: str = "configs/main.yaml"):
    with open(path, "r") as f:
        yaml_data = yaml.safe_load(f)
        return Config(**yaml_data)
