from __future__ import annotations

import random

from Tanks.TankBase import Tank


class TigerI(Tank):
    def __init__(self) -> None:
        super().__init__(
            name="Tiger I",
            faction="Axis",
            max_health=130,
            armor=8,
            min_damage=24,
            max_damage=38,
            accuracy=0.72,
            repair_amount=14,
            special_name="88mm Fury",
            special_description="A brutal heavy-shell attack with huge damage.",
        )

    def _special_attack(self, target: Tank) -> str:
        if random.random() > 0.85:
            return f"{self.name} unleashes {self.special_name}, but misses."

        raw_damage = random.randint(34, 50)
        damage = target.take_damage(raw_damage, armor_piercing=2)
        return f"{self.name} unleashes {self.special_name} on {target.name} for {damage} damage."
