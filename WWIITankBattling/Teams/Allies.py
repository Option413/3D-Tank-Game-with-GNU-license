from __future__ import annotations

from Tanks.M3Grant import M3Grant
from Tanks.M4Sherman import M4Sherman
from Teams.TeamBase import Team


class Allies(Team):
    def __init__(self) -> None:
        super().__init__(
            name="Allies",
            tanks=[
                M4Sherman(),
                M4Sherman(),
                M3Grant(),
            ],
        )
