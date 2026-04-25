from __future__ import annotations

import random

from Tanks.TankBase import Tank


class M4Sherman(Tank):
    def __init__(self) -> None:
        super().__init__(
            name="M4 Sherman",
            faction="Allies",
            max_health=110,
            armor=6,
            min_damage=20,
            max_damage=32,
            accuracy=0.8,
            repair_amount=18,
            special_name="Stabilized Shot",
            special_description="A high-accuracy blast that ignores some armor.",
        )

    def _special_attack(self, target: Tank) -> str:
        if random.random() > 0.95:
            return f"{self.name} uses {self.special_name}, but the shot goes wide."

        raw_damage = random.randint(28, 40)
        damage = target.take_damage(raw_damage, armor_piercing=3)
        return f"{self.name} uses {self.special_name} on {target.name} for {damage} damage."
