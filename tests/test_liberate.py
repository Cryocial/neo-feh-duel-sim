"""
Tests for the four Liberate statuses from statuses.json (Atk / Spd / Def / Res
Liberate).

Rules verified:
  - each grants its own stat + (the unit's bonus count + 4) during combat, and
    nothing to the other stats
  - the status is itself one of those bonuses, so alone it is worth +5
  - the boost caps at +8

Setup: every stat at 30 on both sides, read straight off the in-combat stats,
so no damage math is involved.
"""

import pytest

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import BONUS_DATABASE

LIBERATES = [
    ("Atk Liberate", "atk"),
    ("Spd Liberate", "spd"),
    ("Def Liberate", "defense"),
    ("Res Liberate", "res"),
]


def make_unit(name):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=50,
        atk=30,
        spd=30,
        defense=30,
        res=30,
    )


def in_combat_stats(unit):
    engine = CombatEngine(unit, make_unit("D"))
    engine.simulate()
    return engine.combatant_states["attacker"].combat_stats


@pytest.mark.parametrize("name,stat", LIBERATES)
def test_liberate_grants_bonus_count_plus_4_to_its_stat(name, stat):
    """Alone, the status is the unit's only bonus: 1 + 4 = +5."""
    unit = make_unit("A")
    unit.active_statuses.append(BONUS_DATABASE[name])

    stats = in_combat_stats(unit)

    for other in ("atk", "spd", "defense", "res"):
        assert getattr(stats, other) == 30 + (5 if other == stat else 0)


@pytest.mark.parametrize("name,stat", LIBERATES)
def test_liberate_caps_at_8(name, stat):
    """Four more bonuses bring the count to 5: 5 + 4 = 9, capped at +8."""
    unit = make_unit("A")
    unit.active_statuses.append(BONUS_DATABASE[name])
    for i in range(4):
        unit.active_statuses.append(Status(name=f"Bonus {i}", type="bonus", effects=[]))

    assert getattr(in_combat_stats(unit), stat) == 30 + 8
