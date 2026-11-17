"""
Tests for the Divine Nectar status from statuses.json.

Rules verified:
  - restores 20 HP as combat begins
  - takes 10 off every one of the foe's strikes, in the unit's first combat of
    the turn only (first_combat_of_turn)
  - neutralizes Deep Wounds during combat (NEUT_DEEP_WOUNDS_IN_CBT lifting
    DEEP_WOUNDS_IN_CBT), for its own heal and for any other in-combat heal

Setup: same colour, both melee. A 40 Atk unit hits 20 Def for 20, a 25 Atk
unit hits 20 Def for 5.
"""

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import BONUS_DATABASE


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


def with_nectar(unit):
    unit.active_statuses.append(BONUS_DATABASE["Divine Nectar"])
    return unit


def status(name, kind, effect, params):
    return Status(
        name=name,
        type=kind,
        effects=[
            {"effect": effect, "target": "self", "params": params, "conditions": []}
        ],
    )


# ── the heal ─────────────────────────────────────────────────────────────────


def test_divine_nectar_restores_20_hp_as_combat_begins():
    """20/50 comes back to 40, then takes the 5-damage counter. Not the unit's
    first combat, so the damage reduction stays out of the picture."""
    attacker = with_nectar(make_unit("A"))
    attacker.current_hp = 20
    attacker.first_combat_of_turn = False
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 20 + 20 - 5


# ── the damage reduction ─────────────────────────────────────────────────────


def test_divine_nectar_takes_10_off_every_strike_in_the_first_combat():
    """The attacker is 20 Spd faster and strikes twice for 20: both strikes
    lose 10, not only the first."""
    attacker = make_unit("A", spd=30)
    defender = with_nectar(make_unit("D", hp=100, atk=25))

    result = CombatEngine(attacker, defender).simulate()

    assert result["defender_final_hp"] == 100 - 10 - 10


def test_divine_nectar_reduces_nothing_after_the_first_combat():
    attacker = make_unit("A", spd=30)
    defender = with_nectar(make_unit("D", hp=100, atk=25))
    defender.first_combat_of_turn = False

    result = CombatEngine(attacker, defender).simulate()

    assert result["defender_final_hp"] == 100 - 20 - 20


# ── Deep Wounds ──────────────────────────────────────────────────────────────


def wounded_attacker():
    """20/50, under Deep Wounds, with a 20 HP heal on each of its strikes."""
    unit = make_unit("A")
    unit.current_hp = 20
    unit.active_statuses.append(
        status("Deep Wounds", "penalty", "DEEP_WOUNDS_IN_CBT", {})
    )
    unit.active_statuses.append(
        status("Strike Heal", "bonus", "HEAL_STRIKE", {"flat": 20})
    )
    return unit


def test_deep_wounds_blocks_the_strike_heal_without_divine_nectar():
    """Guards the test below: the strike heal is refused, and the counter takes
    the unit from 20 to 15."""
    result = CombatEngine(wounded_attacker(), make_unit("D", hp=100, atk=25)).simulate()

    assert result["attacker_final_hp"] == 20 - 5


def test_divine_nectar_neutralizes_deep_wounds_during_combat():
    """Its own 20 HP lands as combat begins (40), the strike heal tops the
    unit up to its 50 max HP, and the 5-damage counter loses 10."""
    attacker = with_nectar(wounded_attacker())

    result = CombatEngine(attacker, make_unit("D", hp=100, atk=25)).simulate()

    assert result["attacker_final_hp"] == 50
