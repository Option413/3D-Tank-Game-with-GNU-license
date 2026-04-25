from __future__ import annotations

from Tanks.PanzerIV import PanzerIV
from Tanks.TigerI import TigerI
from Teams.TeamBase import Team


class Axis(Team):
    def __init__(self) -> None:
        super().__init__(
            name="Axis",
            tanks=[
                TigerI(),
                PanzerIV(),
                PanzerIV(),
            ],
        )
