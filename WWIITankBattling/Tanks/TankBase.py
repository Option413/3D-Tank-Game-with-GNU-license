from __future__ import annotations

from dataclasses import dataclass, field
import random


@dataclass
class Tank:
    name: str
    faction: str
    max_health: int
    armor: int
    min_damage: int
    max_damage: int
    accuracy: float
    repair_amount: int
    special_name: str
    special_description: str
    health: int = field(init=False)
    special_ready: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        self.health = self.max_health

    @property
    def is_destroyed(self) -> bool:
        return self.health <= 0

    def status_line(self) -> str:
        special_state = "READY" if self.special_ready else "USED"
        return (
            f"{self.name} | HP {self.health}/{self.max_health} | Armor {self.armor} "
            f"| Special {special_state}"
        )

    def attack(self, target: "Tank") -> tuple[bool, int, str]:
        if random.random() > self.accuracy:
            return False, 0, f"{self.name} fires at {target.name}, but misses."

        raw_damage = random.randint(self.min_damage, self.max_damage)
        damage = target.take_damage(raw_damage)
        return True, damage, f"{self.name} hits {target.name} for {damage} damage."

    def take_damage(self, raw_damage: int, armor_piercing: int = 0) -> int:
        effective_armor = max(0, self.armor - armor_piercing)
        damage = max(1, raw_damage - effective_armor)
        self.health = max(0, self.health - damage)
        return damage

    def repair(self) -> str:
        if self.is_destroyed:
            return f"{self.name} is destroyed and cannot be repaired."

        healed = min(self.repair_amount, self.max_health - self.health)
        if healed == 0:
            return f"{self.name} is already at full health."

        self.health += healed
        return f"{self.name} repairs {healed} health."

    def use_special(self, target: "Tank") -> str:
        if not self.special_ready:
            return f"{self.name}'s special move has already been used."

        self.special_ready = False
        return self._special_attack(target)

    def _special_attack(self, target: "Tank") -> str:
        raw_damage = random.randint(self.max_damage, self.max_damage + 8)
        damage = target.take_damage(raw_damage, armor_piercing=2)
        return f"{self.name} uses {self.special_name} on {target.name} for {damage} damage."
