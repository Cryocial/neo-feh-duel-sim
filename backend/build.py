from dataclasses import dataclass, replace
from typing import Literal
from .constants import (
    COMBAT_STATS,
    VISIBLE_STAT_CAP,
    Color,
    MovementType,
    SpecialType,
    WeaponType,
)


def cap_visible_stat(name: str, value: int) -> int:
    """Visible Atk/Spd/Def/Res never display above VISIBLE_STAT_CAP."""
    return min(VISIBLE_STAT_CAP, value) if name in COMBAT_STATS else value


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


@dataclass(frozen=True)
class AllySupport:
    """A skill an ally has equipped whose in-combat effects reach this unit
    (Drive) or its foe (Crux), tagged with the ally's colour for Feud."""
    skill: Skill
    color: Color

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
        great_talent: dict[str, int] | None = None,
        engage_ring_level: int = 0,
        superboon: list[str] | None = None,
        superbane: list[str] | None = None,
        boon: str | None = None,
        bane: str | None = None,
        floret: str | None = None,
        is_engaged: bool = False,
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
        # Accumulated over the game, entered per stat like dragonflowers. A
        # permanent stat layer, not a bonus: nothing that neutralizes bonuses
        # can see it.
        self.great_talent = StatBlock.from_dict(great_talent or {})
        self.engage_ring_level = engage_ring_level
        self.is_engaged = is_engaged
        self.boon, self.bane, self.floret = boon, bane, floret
        self.superboon, self.superbane = (superboon or []), (superbane or [])

        self.weapon, self.special = weapon, special
        self.a_slot, self.b_slot, self.c_slot = a_slot, b_slot, c_slot
        self.s_slot, self.x_slot = s_slot, x_slot

        self.visible_buffs = StatBlock()
        self.visible_debuffs = StatBlock()
        self.active_statuses: list[Status] = []
        self.ally_supports: list[AllySupport] = []

        self._max_cooldown_override: int | None = None
        self.pre_charge = 0

        self._initialize_stats()
        self.first_combat_of_turn = True
        # Scenario facts the user sets; the engine never counts turns or
        # tracks transformation itself, it just reads these.
        self.is_transformed = False
        self.is_savior = False
        self.turn_window_active = False
        self.style_enabled = False
        self.chosen_range: int | None = None
        self.allies_within_1_space = 0
        self.allies_within_2_spaces = 0
        self.allies_within_3_spaces = 0
        self.allies_within_3_rows_cols = 0
        # Highest visible bonus / penalty per stat among allies within 2 spaces,
        # entered by the user for Fringe Bonus / Sabotage. Only read while
        # allies_within_2_spaces > 0.
        self.ally_bonuses_within_2_spaces = StatBlock()
        self.ally_penalties_within_2_spaces = StatBlock()
        # APPLY PROGRESSION STATS

        temp_max_flower_cap = 30
        applied_flowers = min(self.dragonflower, temp_max_flower_cap)
        self._distribute_sequential_stats(applied_flowers)

        if self.is_engaged:
            applied_engage_stats = min(self.engage_ring_level, 10)
            self._distribute_sequential_stats(applied_engage_stats)

        self._current_hp: int | None = None

    @property
    def max_hp(self) -> int:
        """Full HP including visible +HP from equipped skills (HP+5 etc.)."""
        return self.get_visible_stat("hp")

    @property
    def current_hp(self) -> int:
        """Full HP unless explicitly set. Resolved lazily so skills equipped
        after construction count toward the default."""
        return self.max_hp if self._current_hp is None else self._current_hp

    @current_hp.setter
    def current_hp(self, value: int) -> None:
        self._current_hp = value

    @property
    def max_cooldown(self) -> int:
        """Special cooldown after every equipped item's slaying (Slaying/Killer
        weapons: 1, Blade-type "slows Special trigger": -1). FEH floors this
        at 1; 0 means no Special equipped. An explicit assignment overrides."""
        if self._max_cooldown_override is not None:
            return self._max_cooldown_override
        if self.special is None:
            return 0
        slaying = sum(item.slaying for item in self.equipped_items)
        return max(1, self.special.cooldown - slaying)

    @max_cooldown.setter
    def max_cooldown(self, value: int) -> None:
        self._max_cooldown_override = value

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

        updates = {stat: 0 for stat in tie_breaker_order}
        for i in range(total_points):
            updates[sorted_stats[i % 5]] += 1

        self.base_stats = replace(self.base_stats, **{
            stat: getattr(self.base_stats, stat) + delta
            for stat, delta in updates.items()
            if delta > 0
        })

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

    def stat_before_bonuses(self, name: str) -> int:
        """base + Great Talent + skill stats: everything that isn't a buff or a
        debuff. Per-combat layers are added on top of this and capped once."""
        return (
            getattr(self.base_stats, name)
            + getattr(self.great_talent, name)
            + sum(getattr(item.visible_stats, name) for item in self.equipped_items)
        )

    def get_visible_stat(
        self, name: str, ignore_buffs: bool = False, ignore_debuffs: bool = False
    ) -> int:
        """The stat-screen value with the unit's own visible buffs and debuffs,
        capped at VISIBLE_STAT_CAP. Inside a simulation read
        CombatantState.visible_stat instead: it also sees the granted layers."""
        val = self.stat_before_bonuses(name)
        if not ignore_buffs:
            val += getattr(self.visible_buffs, name)
        if not ignore_debuffs:
            val -= getattr(self.visible_debuffs, name)
        return cap_visible_stat(name, val)

    def is_physical(self) -> bool:
        """Returns True if the unit's weapon type is physical (not magic/staff/beast)."""
        return self.weapon_type not in {
            WeaponType.TOME,
            WeaponType.STAFF,
            WeaponType.DRAGON,
            WeaponType.BEAST,
        }

