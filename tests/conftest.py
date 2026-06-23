"""
Shared pytest fixtures for the FEH combat simulator tests.

These build small, round-numbered units so expected combat math is easy to
verify by hand. Use realistic stats only when a test specifically checks a
real skill's authentic numbers.
"""

import pytest

from backend.build import Unit
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine, CombatantState


@pytest.fixture
def plain_unit():
    """Round 50/30/30/30/30 sword infantry, no skills."""
    return Unit(
        name="Test Unit A",
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=50,
        atk=30,
        spd=30,
        defense=30,
        res=30,
    )


@pytest.fixture
def plain_foe():
    """A distinct second unit so attacker/defender never get confused."""
    return Unit(
        name="Test Unit B",
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.AXE,
        color=Color.BLUE,
        hp=50,
        atk=25,
        spd=20,
        defense=25,
        res=25,
    )


@pytest.fixture
def engine(plain_unit, plain_foe):
    """A CombatEngine instance. _resolve_formula doesn't touch engine state,
    so this is fine for unit-testing that method in isolation."""
    return CombatEngine(plain_unit, plain_foe)


def make_state(
    unit,
    *,
    bonus_count=0,
    penalty_count=0,
    spaces_moved=0,
    damage_mitigated_bucket=0,
    combat_stats=None,
):
    """Helper to build a CombatantState with specific fields set.

    Keyword-only so call sites read clearly at a glance.
    """
    state = CombatantState(
        unit=unit,
        current_hp=unit.base_stats.hp,
        current_cooldown=0,
    )
    state.bonus_count = bonus_count
    state.penalty_count = penalty_count
    state.spaces_moved = spaces_moved
    state.damage_mitigated_bucket = damage_mitigated_bucket
    state.combat_stats = combat_stats
    return state
