"""
Tests for DR_PIERCE, which weakens the foe's percent damage reduction.

Rules verified:
  - a piercable PERC_DR_STRIKE source is reduced by the pierce before it
    applies (40% DR pierced by 50% is 20%)
  - a non-piercable (Special-grade) source is left alone

Setup: same colour, both melee, attacker faster by 20 so it strikes twice
for 20 each before any reduction. The 100 HP defender survives the exchange,
so damage is read off its final HP.
"""

from backend.build import Unit, Skill, Status, StatBlock
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


def percent_dr(pct, piercable):
    params = {"flat": pct, "strike": "every_strike", "piercable": piercable}
    if not piercable:
        params["max_triggers"] = -1
    return Status(
        name="DR",
        type="bonus",
        effects=[
            {
                "effect": "PERC_DR_STRIKE",
                "target": "self",
                "params": params,
                "conditions": [],
            }
        ],
    )


def pierce(value):
    return Skill(
        name="Pierce",
        slot="passive_a",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "DR_PIERCE",
                "target": "self",
                "params": {"value": value, "strike": "every_strike"},
                "conditions": [],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )


def damage_dealt(result):
    return 100 - result["defender_final_hp"]


def test_dr_pierce_weakens_pierceable_percent_dr():
    """40% DR pierced by 50% becomes 20%: 2 x ceil(20 * 0.8) = 32, not 24."""
    attacker = make_unit("A", spd=30)
    attacker.a_slot = pierce(50)
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(percent_dr(40, piercable=True))

    result = CombatEngine(attacker, defender).simulate()

    assert damage_dealt(result) == 32


def test_dr_pierce_leaves_special_dr_alone():
    """piercable: false sources are immune: 2 x ceil(20 * 0.6) = 24."""
    attacker = make_unit("A", spd=30)
    attacker.a_slot = pierce(50)
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(percent_dr(40, piercable=False))

    result = CombatEngine(attacker, defender).simulate()

    assert damage_dealt(result) == 24
