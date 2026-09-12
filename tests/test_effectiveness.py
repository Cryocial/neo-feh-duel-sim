"""
EFFECTIVE multiplies the striker's Atk by 1.5 (truncated) before the weapon
triangle; NEUT_EFFECTIVE on the target cancels it outright.

The engine applies EFFECTIVE whenever the effect is present: the
movement_types / weapon_types lists name the units the skill is meant for,
and matching them is done upstream when the effect is built, not here.

Setup: sword attacker vs a 20 Def defender, 100 HP, one strike each.
"""

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


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


def effective():
    return Status(name="Effective", type="bonus", effects=[{
        "effect": "EFFECTIVE", "target": "self",
        "params": {"movement_types": ["INFANTRY"], "weapon_types": []},
        "conditions": [],
    }])


def neut_effective():
    return Status(name="Neut Effective", type="bonus", effects=[{
        "effect": "NEUT_EFFECTIVE", "target": "self",
        "params": {"movement_types": ["INFANTRY"], "weapon_types": []},
        "conditions": [],
    }])


def dealt(attacker, defender):
    return 100 - CombatEngine(attacker, defender).simulate()["defender_final_hp"]


def test_effective_multiplies_atk_by_one_and_a_half():
    attacker = make_unit("A")
    attacker.active_statuses.append(effective())

    assert dealt(attacker, make_unit("D", hp=100)) == 60 - 20


def test_effective_truncates():
    attacker = make_unit("A", atk=41)          # 61.5 -> 61
    attacker.active_statuses.append(effective())

    assert dealt(attacker, make_unit("D", hp=100)) == 61 - 20


def test_neut_effective_on_the_target_cancels_it():
    attacker = make_unit("A")
    attacker.active_statuses.append(effective())
    defender = make_unit("D", hp=100)
    defender.active_statuses.append(neut_effective())

    assert dealt(attacker, defender) == 20
