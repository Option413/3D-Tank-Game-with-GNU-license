from __future__ import annotations

import random

from Tanks.TankBase import Tank


class M3Grant(Tank):
    def __init__(self) -> None:
        super().__init__(
            name="M3 Grant",
            faction="Allies",
            max_health=100,
            armor=5,
            min_damage=18,
            max_damage=30,
            accuracy=0.7,
            repair_amount=16,
            special_name="Dual Gun Barrage",
            special_description="Two quick attacks that can chip through armor.",
        )

    def _special_attack(self, target: Tank) -> str:
        total_damage = 0
        hits = []
        for shot_number in range(1, 3):
            if random.random() <= 0.8:
                raw_damage = random.randint(14, 22)
                damage = target.take_damage(raw_damage, armor_piercing=1)
                total_damage += damage
                hits.append(f"shot {shot_number} hits for {damage}")
            else:
                hits.append(f"shot {shot_number} misses")

        return (
            f"{self.name} uses {self.special_name} on {target.name}: "
            + ", ".join(hits)
            + f". Total damage: {total_damage}."
        )
