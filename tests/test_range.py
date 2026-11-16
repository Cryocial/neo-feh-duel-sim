"""
Tests for combat_range's default value (no style involved).

Rules verified:
  - combat_range defaults to the attacker's weapon range: 1 for melee
    weapon types, 2 for ranged weapon types (Bow/Dagger/Tome/Staff)

See test_style.py for the style-driven RANGE_EXTENSION override.
"""

from backend.constants import WeaponType
from helpers import fight, make_unit


def test_combat_range_defaults_to_melee():
    """No style at all -> combat_range is the weapon's base range (1 for Sword)."""
    outcome = fight(make_unit("A", weapon_type=WeaponType.SWORD), make_unit("D"))

    assert outcome.engine.combat_range == 1


def test_combat_range_defaults_to_ranged():
    """No style at all -> combat_range is the weapon's base range (2 for Tome)."""
    outcome = fight(make_unit("A", weapon_type=WeaponType.TOME), make_unit("D"))

    assert outcome.engine.combat_range == 2
