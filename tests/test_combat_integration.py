"""
Integration tests for the full simulate() pipeline.

The headline test here (test_stat_boost_increases_damage) is a REGRESSION GUARD
for the bug where _combat_stat_calculations never applied STAT_BOOST/STAT_DAUNT
effects. Before the fix, a unit with an in-combat Atk boost dealt identical
damage to one without — these tests would have caught that.

Setup choices that keep expected damage exact and hand-verifiable:
  - same color (RED vs RED) so there is NO weapon-triangle multiplier (wta = 1.0)
  - physical attacker so the targeted defensive stat is Def
  - no specials / no other skills, so damage per hit = atk - def
"""

import pytest

from backend.build import Unit, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,  # physical -> targets Def
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def atk_boost_status(amount=10):
    """A bonus status granting a flat in-combat Atk boost via STAT_BOOST."""
    return Status(
        name="Test Atk Boost",
        type="bonus",
        effects=[
            {
                "effect": "STAT_BOOST",
                "target": "self",
                "params": {"stats": ["atk"], "flat": amount},
                "conditions": [],
            }
        ],
    )


# ── baseline: no skills, pure stat combat ─────────────────────────────────────


def test_plain_combat_runs_and_deals_damage():
    """Two equal-speed units, attacker 40 atk vs 20 def -> 20 dmg per hit.
    No follow-ups (spd equal), so attacker hits once, defender retaliates once."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    # Defender takes 40-20 = 20. Attacker takes 30-20 = 10.
    assert result["defender_final_hp"] == 50 - 20
    assert result["attacker_final_hp"] == 50 - 10


# ── the regression guard ──────────────────────────────────────────────────────


def test_stat_boost_increases_damage():
    """A +10 Atk STAT_BOOST must raise damage dealt by 10 per hit.

    Before the _combat_stat_calculations fix, the boost was silently dropped
    and this assertion failed (boosted damage == unboosted damage)."""
    # Unboosted: 40 atk - 20 def = 20 damage to defender
    plain_atk = make_unit("A_plain", atk=40, defense=20, spd=10)
    plain_def = make_unit("D1", atk=10, defense=20, spd=10)
    unboosted = CombatEngine(plain_atk, plain_def).simulate()
    unboosted_dealt = 50 - unboosted["defender_final_hp"]

    # Boosted: same unit but +10 Atk in combat -> 50 atk - 20 def = 30 damage
    boosted_atk = make_unit("A_boost", atk=40, defense=20, spd=10)
    boosted_atk.active_statuses.append(atk_boost_status(10))
    boosted_def = make_unit("D2", atk=10, defense=20, spd=10)
    boosted = CombatEngine(boosted_atk, boosted_def).simulate()
    boosted_dealt = 50 - boosted["defender_final_hp"]

    assert boosted_dealt == unboosted_dealt + 10


def test_stat_boost_exact_damage():
    """Pin the exact number: 40 atk +10 boost - 20 def = 30 damage on the one hit."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    attacker.active_statuses.append(atk_boost_status(10))
    defender = make_unit("D", atk=10, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()
    assert result["defender_final_hp"] == 50 - 30


def test_stat_boost_multiple_stats():
    """A boost listing several stats applies to all of them. Boost Atk and Def:
    Atk raises damage dealt; Def is irrelevant to the attacker's own offense
    here but confirms multi-stat application doesn't crash. Def (not Spd) is the
    second stat deliberately, so the boost can't accidentally create a follow-up."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    attacker.active_statuses.append(
        Status(
            name="Atk/Def Boost",
            type="bonus",
            effects=[
                {
                    "effect": "STAT_BOOST",
                    "target": "self",
                    "params": {"stats": ["atk", "defense"], "flat": 6},
                    "conditions": [],
                }
            ],
        )
    )
    defender = make_unit("D", atk=10, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()
    # 40+6 atk - 20 def = 26 damage, single hit (spd still equal -> no follow-up)
    assert result["defender_final_hp"] == 50 - 26
