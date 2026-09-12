"""
Scenario booleans the user sets on a Unit and the conditions that read them.
The engine never counts turns or tracks transformation; it just checks:

    is_transformed       Unit.is_transformed
    savior               Unit.is_savior
    turn_window          Unit.turn_window_active  ("turns 1-4" currently holds)

Each condition takes target: "self" | "foe". A +6 Atk STAT_BOOST gated on the
condition shows whether it held: 26 dealt if it did, 20 if not.
"""

import pytest

from backend.build import Unit, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine

FLAGS = [
    ("is_transformed", "is_transformed"),
    ("savior", "is_savior"),
    ("turn_window", "turn_window_active"),
]


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def gated_boost(condition, target="self"):
    return Skill(
        name="Gated", slot="a", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{
            "effect": "STAT_BOOST", "target": "self",
            "params": {"stats": ["atk"], "flat": 6},
            "conditions": [{"type": condition, "params": {"target": target}}],
        }],
    )


def dealt(result):
    return 100 - result["defender_final_hp"]


@pytest.mark.parametrize("condition,attr", FLAGS)
def test_flag_off_by_default_so_the_boost_does_not_apply(condition, attr):
    attacker = make_unit("A")
    attacker.a_slot = gated_boost(condition)

    assert getattr(attacker, attr) is False
    assert dealt(CombatEngine(attacker, make_unit("D", hp=100)).simulate()) == 20


@pytest.mark.parametrize("condition,attr", FLAGS)
def test_flag_on_self_enables_the_boost(condition, attr):
    attacker = make_unit("A")
    attacker.a_slot = gated_boost(condition)
    setattr(attacker, attr, True)

    assert dealt(CombatEngine(attacker, make_unit("D", hp=100)).simulate()) == 26


@pytest.mark.parametrize("condition,attr", FLAGS)
def test_target_foe_reads_the_foes_flag(condition, attr):
    attacker = make_unit("A")
    attacker.a_slot = gated_boost(condition, target="foe")
    foe = make_unit("D", hp=100)
    setattr(foe, attr, True)

    assert dealt(CombatEngine(attacker, foe).simulate()) == 26
    assert dealt(CombatEngine(attacker, make_unit("D", hp=100)).simulate()) == 20
