from __future__ import annotations

import random

from Tanks.TankBase import Tank


class PanzerIV(Tank):
    def __init__(self) -> None:
        super().__init__(
            name="Panzer IV",
            faction="Axis",
            max_health=105,
            armor=6,
            min_damage=19,
            max_damage=31,
            accuracy=0.78,
            repair_amount=16,
            special_name="Armor-Piercing Round",
            special_description="A focused strike that cuts through armor.",
        )

    def _special_attack(self, target: Tank) -> str:
        raw_damage = random.randint(26, 36)
        damage = target.take_damage(raw_damage, armor_piercing=4)
        return f"{self.name} uses {self.special_name} on {target.name} for {damage} damage."
