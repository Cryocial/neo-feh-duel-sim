from dataclasses import dataclass
from typing import Literal
from .constants import MovementType, WeaponType, Color, SpecialType


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


@dataclass(frozen=True)
class Skill:
    """Represents an equipped skill (Weapon, A/B/C slot, etc.)."""

    name: str
    slot: str
    might: int
    slaying: int
    cooldown: int
    visible_stats: StatBlock
    effects: list[dict]
    allowed_movement_types: list[MovementType]
    allowed_weapon_types: list[WeaponType]
    is_arcane: bool = False
    is_prf: bool = False
    grants_style: bool = False
    special_type: SpecialType = SpecialType.NONE


@dataclass(frozen=True)
class Status:
    name: str
    type: Literal["bonus", "penalty"]
    effects: list[dict]  # raw effect definitions from the JSON
    grants_style: bool = False

@dataclass(frozen=True)
class DivineVein:
    name: str
    effects: list[dict]

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
        engage_ring_level: int = 0,
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
        self.active_statuses: list[Status] = []

        self.max_cooldown = 0
        self.pre_charge = 0

        self._initialize_stats()
        self.first_combat_of_turn = True
        self.is_engaged = False
        self.style_enabled = False
        self.chosen_range: int | None = None
        self.allies_within_2_spaces = 0
        self.allies_within_3_spaces = 0
        self.allies_within_3_rows_cols = 0
        # APPLY PROGRESSION STATS

        temp_max_flower_cap = 30
        applied_flowers = min(self.dragonflower, temp_max_flower_cap)
        self._distribute_sequential_stats(applied_flowers)

        if self.is_engaged:
            applied_engage_stats = min(self.engage_ring_level, 10)
            self._distribute_sequential_stats(applied_engage_stats)

        self.current_hp = self.base_stats.hp
        self.start_of_combat_hp = self.base_stats.hp

    def _distribute_sequential_stats(self, total_points: int):
        """
        Universally handles FEH stat distribution.
        Sorts by highest Level 40 stat (Descending).
        Ties are broken by FEH order: HP -> Atk -> Spd -> Def -> Res.
        """
        if total_points <= 0:
            return

        tie_breaker_order = ["hp", "atk", "spd", "defense", "res"]

        # Sort directly using the unit's actual base_stats!
        sorted_stats = sorted(
            tie_breaker_order,
            key=lambda stat: (
                -getattr(self.base_stats, stat, 0),
                tie_breaker_order.index(stat),
            ),
        )

        for i in range(total_points):
            stat_to_buff = sorted_stats[i % 5]
            current_val = getattr(self.base_stats, stat_to_buff)
            setattr(self.base_stats, stat_to_buff, current_val + 1)

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

    def get_visible_stat(
        self, name: str, ignore_buffs: bool = False, ignore_debuffs: bool = False
    ) -> int:
        """Calculates the 'stat-screen' value including buffs, debuffs, and visible skill stats."""
        val = getattr(self.base_stats, name)
        if not ignore_buffs:
            val += getattr(self.visible_buffs, name)
        if not ignore_debuffs:
            val -= getattr(self.visible_debuffs, name)

        for item in self.equipped_items:
            val += getattr(item.visible_stats, name)
        return val

    def is_physical(self) -> bool:
        """Returns True if the unit's weapon type is physical (not magic/staff/beast)."""
        return self.weapon_type not in {
            WeaponType.TOME,
            WeaponType.STAFF,
            WeaponType.DRAGON,
            WeaponType.BEAST,
        }

