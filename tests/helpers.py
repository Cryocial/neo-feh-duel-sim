"""
Shared builders for the tests.

A test builds its units and what they carry with these, runs one combat with
fight(), and asserts on what the combat did. The "Testing" section of
doc/ARCHITECTURE.md says which carrier to use when.
"""

from dataclasses import dataclass

from backend.build import Skill, StatBlock, Status, Unit
from backend.combatcalculator import CombatantState, CombatEngine
from backend.constants import Color, MovementType, WeaponType


def make_unit(
    name,
    *,
    hp=50,
    atk=40,
    spd=10,
    defense=20,
    res=20,
    color=Color.RED,
    weapon_type=WeaponType.SWORD,
    statuses=(),
    **unit_fields,
):
    """A red sword infantry unit. Two units built with the defaults share a
    colour, a Spd and a range: no weapon-triangle multiplier, no follow-up,
    and each lands one strike of 40 - 20 = 20.

    statuses become the unit's active statuses. Anything else Unit accepts
    (weapon, special, a_slot, merges...) passes through unit_fields."""
    unit = Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
        **unit_fields,
    )
    unit.active_statuses.extend(statuses)
    return unit


def effect(name, params=None, *, target="self", conditions=()):
    """One effect description, the shape the JSON files store."""
    return {
        "effect": name,
        "target": target,
        "params": dict(params or {}),
        "conditions": list(conditions),
    }


def condition(kind, **params):
    """One condition description, for effect(..., conditions=[...])."""
    return {"type": kind, "params": params}


def status(*effects, kind="bonus", name="Test Status", grants_style=False):
    """A fake status carrying effects: the default carrier."""
    return Status(
        name=name, type=kind, effects=list(effects), grants_style=grants_style
    )


def skill(*effects, slot="passive_a", name="Test Skill", **fields):
    """A fake skill carrying effects, every other field neutral unless given."""
    neutral = dict(
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )
    neutral.update(fields)
    return Skill(name=name, slot=slot, effects=list(effects), **neutral)


def special(special_type, *effects, cooldown=1, name="Test Special"):
    """A fake Special, with a cooldown of 1 unless given."""
    return skill(
        *effects,
        slot="special",
        name=name,
        cooldown=cooldown,
        special_type=special_type,
    )


@dataclass
class Fight:
    """What one simulated combat did. HP lost is counted from the HP the unit
    entered combat with, so a test never repeats that HP as a literal."""

    engine: CombatEngine
    attacker_hp: int
    defender_hp: int
    attacker_lost: int
    defender_lost: int

    @property
    def attacker(self) -> CombatantState:
        return self.engine.combatant_states["attacker"]

    @property
    def defender(self) -> CombatantState:
        return self.engine.combatant_states["defender"]


def fight(attacker, defender, *, attacker_vein=None, defender_vein=None):
    """Simulates attacker initiating on defender."""
    engine = CombatEngine(
        attacker,
        defender,
        attacker_divine_vein=attacker_vein,
        defender_divine_vein=defender_vein,
    )
    result = engine.simulate()
    return Fight(
        engine=engine,
        attacker_hp=result["attacker_final_hp"],
        defender_hp=result["defender_final_hp"],
        attacker_lost=attacker.current_hp - result["attacker_final_hp"],
        defender_lost=defender.current_hp - result["defender_final_hp"],
    )
