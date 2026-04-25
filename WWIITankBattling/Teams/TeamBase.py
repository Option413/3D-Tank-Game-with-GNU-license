from __future__ import annotations

import random

from Tanks.TankBase import Tank


class Team:
    def __init__(self, name: str, tanks: list[Tank]) -> None:
        self.name = name
        self.tanks = tanks

    def living_tanks(self) -> list[Tank]:
        return [tank for tank in self.tanks if not tank.is_destroyed]

    def defeated(self) -> bool:
        return not self.living_tanks()

    def random_living_tank(self) -> Tank:
        return random.choice(self.living_tanks())

    def roster_text(self) -> str:
        lines = [f"{index}. {tank.status_line()}" for index, tank in enumerate(self.living_tanks(), start=1)]
        return "\n".join(lines) if lines else "No tanks remaining."
