"""
Per-strike damage modifiers that sit after percentage reduction:

  FLAT_DR_STRIKE      flat reduction, subtracted after percent DR, floored at 0
  DR_FLOOR            caps the strike's damage at X; the lowest floor wins
  STAFF_FULL_DAMAGE   lifts the x0.5 a staff normally suffers

Setup: sword attacker at 40 Atk vs a 20 Def defender, 100 HP: 20 per hit.
"""

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20,
              weapon_type=WeaponType.SWORD):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def status(effect, params):
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": "self", "params": params, "conditions": [],
    }])


def defender(*statuses):
    unit = make_unit("D", hp=100)
    unit.active_statuses.extend(statuses)
    return unit


def dealt(attacker, foe):
    return 100 - CombatEngine(attacker, foe).simulate()["defender_final_hp"]


def test_flat_dr_strike_subtracts_from_the_hit():
    assert dealt(make_unit("A"), defender(status("FLAT_DR_STRIKE", {"flat": 5}))) == 15


def test_flat_dr_strike_comes_after_percent_dr():
    """50% first: ceil(10) = 10, then the flat 5."""
    half = status("PERC_DR_STRIKE", {"flat": 50, "strike": "every_strike", "piercable": True})

    assert dealt(make_unit("A"), defender(half, status("FLAT_DR_STRIKE", {"flat": 5}))) == 5


def test_dr_floor_caps_the_hit():
    assert dealt(make_unit("A"), defender(status("DR_FLOOR", {"flat": 1}))) == 1


def test_dr_floor_takes_the_lowest_floor():
    foe = defender(status("DR_FLOOR", {"flat": 3}), status("DR_FLOOR", {"flat": 1}))

    assert dealt(make_unit("A"), foe) == 1


def test_staff_damage_is_halved_unless_staff_full_damage():
    """A staff targets Res: 40 - 20 = 20, halved to 10; STAFF_FULL_DAMAGE
    keeps the 20."""
    staff = make_unit("A", weapon_type=WeaponType.STAFF)
    wrathful = make_unit("A", weapon_type=WeaponType.STAFF)
    wrathful.active_statuses.append(status("STAFF_FULL_DAMAGE", {}))

    assert dealt(staff, defender()) == 10
    assert dealt(wrathful, defender()) == 20
