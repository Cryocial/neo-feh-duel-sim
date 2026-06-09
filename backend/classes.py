from dataclasses import dataclass, field
from typing import Callable, Any, Self
from .constants import MovementType, WeaponType, Color


@dataclass(frozen=True)
class StatBlock:
    """
    An immutable container for a unit's five primary stats.
    Supports basic arithmetic operations like addition and subtraction.
    """

    hp: int = 0
    atk: int = 0
    spd: int = 0
    defense: int = 0
    res: int = 0

    def __add__(self, other: "StatBlock") -> "StatBlock":
        return StatBlock(
            self.hp + other.hp,
            self.atk + other.atk,
            self.spd + other.spd,
            self.defense + other.defense,
            self.res + other.res,
        )

    def __sub__(self, other: "StatBlock") -> "StatBlock":
        return StatBlock(
            self.hp - other.hp,
            self.atk - other.atk,
            self.spd - other.spd,
            self.defense - other.defense,
            self.res - other.res,
        )

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "StatBlock":
        """Helper to create a StatBlock from a raw dictionary."""
        return cls(
            hp=data.get("hp", 0),
            atk=data.get("atk", 0),
            spd=data.get("spd", 0),
            defense=data.get("defense", 0) or data.get("def", 0),
            res=data.get("res", 0),
        )


@dataclass
class UtilityBlock:
    """
    Container for non-stat skill effects like damage reduction,
    true damage logic, and cooldown modifiers.
    """

    truedr: int = 0
    truedr_logic: Callable | None = None
    truedmg: int = 0
    truedmg_logic: Callable | None = None
    heal_precombat_logic: Callable | None = None
    heal_on_hit_logic: Callable | None = None
    heal_after_logic: Callable | None = None
    predmg_logic: Callable | None = None
    dynamic_stats_logic: Callable | None = None
    cooldown_modifiers: dict[str, Any] = field(default_factory=dict)
    percentdr: float = 0.0
    potent_logic: Callable | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """Represents an equipped skill (Weapon, A/B/C slot, etc.)."""

    name: str
    slot: str
    visible_stats: StatBlock = field(default_factory=StatBlock)
    combat_stats: StatBlock = field(default_factory=StatBlock)
    utilities: UtilityBlock = field(default_factory=UtilityBlock)
    enemy_combat_stats: StatBlock = field(default_factory=StatBlock)


class Unit:
    """
    The primary Unit class representing a hero in the game.
    Handles stat initialization (merges/IVs) and dynamic stat retrieval during combat.
    """

    def __init__(
        self,
        name: str,
        movement_type: MovementType,
        weapon_type: WeaponType,
        color: Color,
        hp: int,
        atk: int,
        spd: int,
        defense: int,
        res: int,
        dragonflower: int = 0,
        merges: int = 0,
        superboon: list[str] | None = None,
        superbane: list[str] | None = None,
        boon: str | None = None,
        bane: str | None = None,
        floret: str | None = None,
        weapon: Skill | None = None,
        special: Skill | None = None,
        a_slot: Skill | None = None,
        b_slot: Skill | None = None,
        c_slot: Skill | None = None,
        s_slot: Skill | None = None,
        x_slot: Skill | None = None,
    ):

        self.name, self.movement_type, self.weapon_type, self.color = (
            name,
            movement_type,
            weapon_type,
            color,
        )
        self.base_stats = StatBlock(hp, atk, spd, defense, res)
        self.dragonflower, self.merges = dragonflower, merges
        self.boon, self.bane, self.floret = boon, bane, floret
        self.superboon, self.superbane = (superboon or []), (superbane or [])

        self.weapon, self.special = weapon, special
        self.a_slot, self.b_slot, self.c_slot = a_slot, b_slot, c_slot
        self.s_slot, self.x_slot = s_slot, x_slot

        self.visible_buffs = StatBlock()
        self.visible_debuffs = StatBlock()
        self.active_statuses: list[str] = []
        self.current_cooldown = 0
        self.damage_mitigated_bucket = 0  # Used for specific reflex-style skills
        self.bonus_count = 0
        self.penalty_count = 0

        self._initialize_stats()
        self.current_hp = self.base_stats.hp
        self.first_combat_of_turn = True

    def _initialize_stats(self):
        """
        Applies IVs, merges, and dragonflowers to base stats.
        Follows FEH's internal priority system for stat distribution.
        """
        d = {
            "hp": self.base_stats.hp,
            "atk": self.base_stats.atk,
            "spd": self.base_stats.spd,
            "defense": self.base_stats.defense,
            "res": self.base_stats.res,
        }

        if self.bane:
            d[self.bane] -= 4 if self.bane in self.superbane else 3
        if self.boon:
            d[self.boon] += 4 if self.boon in self.superboon else 3
        if self.floret and self.floret != self.boon:
            d[self.floret] += 4 if self.floret in self.superboon else 3

        priority_map = {"hp": 1, "atk": 2, "spd": 3, "defense": 4, "res": 5}

        if self.merges > 0:
            if self.merges >= 1 and self.bane:
                d[self.bane] += 4 if self.bane in self.superbane else 3
                self.bane = None

            priority = sorted(d.keys(), key=lambda k: (-d[k], priority_map[k]))

            if not self.boon and not self.bane:
                for k in priority[:3]:
                    d[k] += 1

            for i in range(self.merges * 2):
                d[priority[i % 5]] += 1

        if self.dragonflower > 0:
            priority = sorted(d.keys(), key=lambda k: (-d[k], priority_map[k]))
            for i in range(self.dragonflower):
                d[priority[i % 5]] += 1

        self.base_stats = StatBlock(**d)

    @property
    def equipped_items(self) -> list[Skill]:
        """Convenience property to get all non-empty skill slots."""
        return [
            s
            for s in [
                self.weapon,
                self.special,
                self.a_slot,
                self.b_slot,
                self.c_slot,
                self.s_slot,
                self.x_slot,
            ]
            if s
        ]

    def get_visible_stat(self, name: str) -> int:
        """Calculates the 'stat-screen' value including buffs, debuffs, and visible skill stats."""
        val = (
            getattr(self.base_stats, name)
            + getattr(self.visible_buffs, name)
            - getattr(self.visible_debuffs, name)
        )
        for item in self.equipped_items:
            val += getattr(item.visible_stats, name)
        return val

    def get_combat_stat(self, name: str, target: Self | None = None) -> int:
        """
        Calculates the final combat value, including in-combat buffs, status effects,
        and enemy-inflicted penalties.
        """
        from .jsonbootupstuff import STATUS_EFFECT_DATABASE

        total = self.get_visible_stat(name)

        for item in self.equipped_items:
            total += getattr(item.combat_stats, name)

        for s in self.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                total += getattr(info["combat_stats"], name)

        if target:
            for item in target.equipped_items:
                total += getattr(item.enemy_combat_stats, name)
            for s in target.active_statuses:
                if info := STATUS_EFFECT_DATABASE.get(s):
                    total += getattr(info["enemy_combat_stats"], name)
        return total

    def has_keyword(self, keyword: str) -> bool:
        """Checks if the unit has a specific keyword (e.g. 'null_follow_up') from skills or statuses."""
        from .jsonbootupstuff import STATUS_EFFECT_DATABASE

        if any(keyword in item.utilities.keywords for item in self.equipped_items):
            return True
        return any(
            keyword in STATUS_EFFECT_DATABASE[s]["utilities"].keywords
            for s in self.active_statuses
            if s in STATUS_EFFECT_DATABASE
        )

    def get_pulse_amount(self, phase: str, target: Self | None = None) -> int:
        """Scans all sources for cooldown modifiers during a specific combat phase."""
        from .jsonbootupstuff import STATUS_EFFECT_DATABASE

        total = 0
        for item in self.equipped_items:
            mod = item.utilities.cooldown_modifiers.get(phase, 0)
            total += mod(self, target) if callable(mod) else mod
        for s in self.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                mod = info["utilities"].cooldown_modifiers.get(phase, 0)
                total += mod(self, target) if callable(mod) else mod
        return total
