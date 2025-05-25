from dataclasses import dataclass


@dataclass
class Roll:
    id: str
    character: str
    series: str
    kakera: int

class MudaeRollMixin:
    rolls: list[Roll] = []

    def roll(self):
        pass
