"""
Tests for CombatEngine._compute_counts — the fix for the bug where
bonus_count / penalty_count were never assigned (always 0), so every
counting skill (Change of Fate, Empathy, Dominance) computed against zero.

_compute_counts tallies, per unit:
  +1 bonus  for each stat with a positive granted_visible_buff
  +1 bonus  for each stat with a positive unit.visible_buff
  +1 penalty for each stat with a positive granted_visible_debuff
  +1 penalty for each stat with a positive unit.visible_debuff
  +1 bonus/penalty per active_status (by status.type)

These tests drive counts through the full simulate() path and via the
visible-buff layers, then assert bonus_count / penalty_count land correctly.

NOTE: _compute_counts iterates unit.active_statuses but NOT granted_statuses,
so statuses granted at start of turn are not yet counted.
test_granted_status_is_counted is an expected failure until they are.
"""

import pytest

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name="U", color=Color.RED):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=40,
        atk=30,
        spd=20,
        defense=20,
        res=20,
    )


def engine_after_counts(attacker, defender):
    """Run simulate far enough that _compute_counts has executed, then read
    the counts off the combatant states. simulate() calls _compute_counts
    near the top, so a full run is fine for reading the resulting counts."""
    eng = CombatEngine(attacker, defender)
    eng.simulate()
    return eng


# ── baseline ──────────────────────────────────────────────────────────────────


def test_no_buffs_counts_zero():
    a, d = make_unit("A"), make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 0
    assert eng.combatant_states["attacker"].penalty_count == 0
    assert eng.combatant_states["defender"].bonus_count == 0
    assert eng.combatant_states["defender"].penalty_count == 0


# ── visible buffs on the unit ─────────────────────────────────────────────────


def test_visible_buffs_counted():
    a = make_unit("A")
    # two buffed stats -> 2 bonuses
    a.visible_buffs = StatBlock(atk=6, spd=6)
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 2
    assert eng.combatant_states["attacker"].penalty_count == 0


def test_visible_debuffs_counted():
    a = make_unit("A")
    d = make_unit("D")
    # one debuffed stat on the defender -> 1 penalty
    d.visible_debuffs = StatBlock(atk=5)
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["defender"].penalty_count == 1
    assert eng.combatant_states["defender"].bonus_count == 0


def test_buffs_and_debuffs_mixed():
    a = make_unit("A")
    a.visible_buffs = StatBlock(atk=6, defense=6, res=6)  # 3 bonuses
    a.visible_debuffs = StatBlock(spd=4)  # 1 penalty
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 3
    assert eng.combatant_states["attacker"].penalty_count == 1


# ── active statuses ───────────────────────────────────────────────────────────


def test_bonus_status_counted():
    a = make_unit("A")
    a.active_statuses.append(Status(name="Some Bonus", type="bonus", effects=[]))
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 1


def test_penalty_status_counted():
    a = make_unit("A")
    d = make_unit("D")
    d.active_statuses.append(Status(name="Some Penalty", type="penalty", effects=[]))
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["defender"].penalty_count == 1


def test_statuses_and_visible_combine():
    a = make_unit("A")
    a.visible_buffs = StatBlock(atk=6)  # 1 bonus
    a.active_statuses.append(Status(name="B", type="bonus", effects=[]))  # +1 bonus
    a.active_statuses.append(Status(name="P", type="penalty", effects=[]))  # +1 penalty
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 2
    assert eng.combatant_states["attacker"].penalty_count == 1


# ── documents a known gap: granted_statuses are NOT counted yet ────────────────


def breath_granter():
    """A C-slot skill granting its unit the Breath status at start of turn."""
    return Skill(
        name="Test Grant",
        slot="passive_c",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "GRANT_STATUS",
                "target": "self",
                "params": {"status": "Breath"},
                "conditions": [],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )


def test_start_of_turn_grant_gives_the_status():
    """The grant itself works, so the expected failure below can only be about
    the count."""
    a = make_unit("A")
    a.c_slot = breath_granter()
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    granted = eng.combatant_states["attacker"].granted_statuses
    assert [status.name for status in granted] == ["Breath"]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="_compute_counts iterates unit.active_statuses only, not granted_statuses",
)
def test_granted_status_is_counted():
    """Breath is a bonus, so a unit granted it at start of turn has one bonus.
    The count stays at 0 until _compute_counts reads granted_statuses; once it
    does, this test passes and its xfail marker must go."""
    a = make_unit("A")
    a.c_slot = breath_granter()
    d = make_unit("D")
    eng = engine_after_counts(a, d)
    assert eng.combatant_states["attacker"].bonus_count == 1
