"""
End-to-end tests for the start-of-turn phase (_phase_start_of_turn +
_apply_grant + the visible_stat accessor + _compute_counts).

The headline scenario is Ploy: at start of turn, if the unit's visible Res
beats the foe's, inflict a visible stat penalty on the foe. This exercises the
whole chain:
  - GRANT_VISIBLE_STAT effect with target "foe"
  - a visible_stat_check condition gating it
  - the grant landing in the foe's granted_visible_debuffs (per-combat)
  - CombatantState.visible_stat() reflecting the debuff
  - _compute_counts tallying it as a penalty on the foe

Requires (must be present in source):
  - EffectType.GRANT_VISIBLE_STAT
  - "visible_stat_check" condition registered under the "start_of_turn" phase
  - _apply_grant / _phase_start_of_turn wired into simulate()
"""

import pytest

from backend.build import Unit, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, res=20, **stats):
    base = dict(hp=40, atk=30, spd=20, defense=20, res=res)
    base.update(stats)
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        **base,
    )


def atk_ploy_skill():
    """A C-slot 'Atk Ploy': if unit's visible Res >= foe's Res, inflict Atk-5
    on the foe at start of turn."""
    return Skill(
        name="Atk Ploy",
        slot="c_slot",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "GRANT_VISIBLE_STAT",
                "target": "foe",
                "params": {"stats": {"atk": -5}},
                "conditions": [
                    {
                        "type": "visible_stat_check",
                        "params": {
                            "stat": "res",
                            "margin": 0,
                            "comparison": "greater_or_equal",
                        },
                    }
                ],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )


def run(attacker, defender):
    eng = CombatEngine(attacker, defender)
    eng.simulate()
    return eng


# ── Ploy triggers (unit's Res wins) ───────────────────────────────────────────


def test_ploy_inflicts_debuff_when_res_wins():
    # attacker Res 30 vs defender Res 20 -> Ploy fires
    attacker = make_unit("A", res=30)
    attacker.c_slot = atk_ploy_skill()
    defender = make_unit("D", res=20)

    eng = run(attacker, defender)
    def_state = eng.combatant_states["defender"]

    # foe's granted Atk debuff should be 5
    assert def_state.granted_visible_debuffs.atk == 5
    # and the visible_stat accessor reflects it: 30 base atk - 5 = 25
    assert def_state.visible_stat("atk") == 25


def test_ploy_debuff_counts_as_penalty():
    attacker = make_unit("A", res=30)
    attacker.c_slot = atk_ploy_skill()
    defender = make_unit("D", res=20)

    eng = run(attacker, defender)
    # the inflicted debuff should register in the foe's penalty_count
    assert eng.combatant_states["defender"].penalty_count == 1


# ── Ploy does NOT trigger (unit's Res loses) ──────────────────────────────────


def test_ploy_no_debuff_when_res_loses():
    # attacker Res 15 vs defender Res 20 -> Ploy condition fails
    attacker = make_unit("A", res=15)
    attacker.c_slot = atk_ploy_skill()
    defender = make_unit("D", res=20)

    eng = run(attacker, defender)
    def_state = eng.combatant_states["defender"]

    assert def_state.granted_visible_debuffs.atk == 0
    assert def_state.visible_stat("atk") == 30  # unchanged
    assert def_state.penalty_count == 0


def test_ploy_boundary_equal_res_triggers():
    # equal Res, greater_or_equal -> Ploy fires (>= includes ties)
    attacker = make_unit("A", res=20)
    attacker.c_slot = atk_ploy_skill()
    defender = make_unit("D", res=20)

    eng = run(attacker, defender)
    assert eng.combatant_states["defender"].granted_visible_debuffs.atk == 5


# ── a self-targeted grant (Hone-style) ────────────────────────────────────────


def test_self_visible_grant():
    """A start-of-turn self buff lands in the unit's own granted_visible_buffs
    and shows through visible_stat."""
    attacker = make_unit("A")
    attacker.c_slot = Skill(
        name="Self Hone",
        slot="c_slot",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "GRANT_VISIBLE_STAT",
                "target": "self",
                "params": {"stats": {"atk": 6, "spd": 6}},
                "conditions": [],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )
    defender = make_unit("D")

    eng = run(attacker, defender)
    atk_state = eng.combatant_states["attacker"]
    assert atk_state.granted_visible_buffs.atk == 6
    assert atk_state.granted_visible_buffs.spd == 6
    assert atk_state.visible_stat("atk") == 36  # 30 + 6
    # two buffed stats -> 2 bonuses
    assert atk_state.bonus_count == 2
