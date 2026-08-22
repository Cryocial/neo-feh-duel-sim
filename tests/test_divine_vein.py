"""
Tests for the Divine Vein mechanic (CombatEngine.attacker_divine_vein /
defender_divine_vein -> CombatantState.active_ally_divine_vein).

Rules verified:
  - No vein selected -> no effect
  - A vein's target: self effects apply to whichever unit it's attached to
  - A vein's target: foe effects apply to that unit's opponent
  - Attacker and defender veins are both wired and resolved symmetrically
"""

from backend.build import Unit, DivineVein
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def stone_like_vein(amount=6):
    """Ally-buff vein: boosts whoever it's attached to (target: self)."""
    return DivineVein(
        name="Test Stone",
        effects=[
            {
                "effect": "STAT_BOOST",
                "target": "self",
                "params": {"stats": ["defense"], "flat": amount},
                "conditions": [],
            }
        ],
    )


def flame_like_vein(amount=7):
    """Hostile vein: damages the foe of whoever it's attached to (target: foe)."""
    return DivineVein(
        name="Test Flame",
        effects=[
            {
                "effect": "PRE_CBT_DAMAGE",
                "target": "foe",
                "params": {"flat": amount},
                "conditions": [],
            }
        ],
    )


def test_no_divine_vein_has_no_effect():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 20


def test_attacker_divine_vein_self_effect_applies_to_attacker():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, attacker_divine_vein=stone_like_vein(6)
    ).simulate()

    # Defender's counter: 30 atk - (20+6) def = 4 damage instead of 10
    assert result["attacker_final_hp"] == 50 - 4
    assert result["defender_final_hp"] == 50 - 20


def test_attacker_divine_vein_foe_effect_applies_to_defender():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, attacker_divine_vein=flame_like_vein(7)
    ).simulate()

    # Pre-combat: defender takes 7 flat damage before the strike sequence
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 7 - 20


def test_defender_divine_vein_self_effect_applies_to_defender():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, defender_divine_vein=stone_like_vein(6)
    ).simulate()

    # Attacker's strike: 40 atk - (20+6) def = 14 damage instead of 20
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 14


def test_defender_divine_vein_foe_effect_applies_to_attacker():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, defender_divine_vein=flame_like_vein(7)
    ).simulate()

    # Pre-combat: attacker takes 7 flat damage before the strike sequence
    assert result["attacker_final_hp"] == 50 - 7 - 10
    assert result["defender_final_hp"] == 50 - 20
