"""
Tests for combat_range's default value (no style involved).

Rules verified:
  - combat_range defaults to the attacker's weapon range: 1 for melee
    weapon types, 2 for ranged weapon types (Bow/Dagger/Tome/Staff)

See test_style.py for the style-driven RANGE_EXTENSION override.
"""

from backend.build import Unit
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(
    name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20,
    weapon_type=WeaponType.SWORD,
):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def test_combat_range_defaults_to_melee():
    """No style at all -> combat_range is the weapon's base range (1 for Sword)."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD)
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 1


def test_combat_range_defaults_to_ranged():
    """No style at all -> combat_range is the weapon's base range (2 for Tome)."""
    attacker = make_unit("A", weapon_type=WeaponType.TOME)
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 2
