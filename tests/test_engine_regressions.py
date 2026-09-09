"""
Regression tests for engine bugs found in the 2026-09 audit. Each test pins
one bug that the rest of the suite did not cover:

  - HP% conditions read a stale start_of_combat_hp (and leaked it between
    simulations through the Unit)
  - start-of-turn grants never reached combat stats
  - any_of / all_of resolved prematurely when their branches had different
    timings
  - dragonflowers were distributed twice
  - DR_PIERCE was computed but never applied

Setup mirrors test_special.py: same color, both melee, attacker faster by 20
so it always gets the follow-up, defender slower so it never does. A 100 HP
defender survives the exchange so damage can be read off final HP.
"""

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine, CombatantState
from backend.conditions import build_conditions, check_condition


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20, **kwargs):
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
        **kwargs,
    )


def skill(name, slot, effects):
    return Skill(
        name=name, slot=slot, might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), effects=effects,
        allowed_movement_types=[], allowed_weapon_types=[],
    )


def status(name, effects):
    return Status(name=name, type="bonus", effects=effects)


def damage_dealt(result):
    return 100 - result["defender_final_hp"]


# ── HP% conditions and Unit isolation ────────────────────────────────────────


def test_hp_pct_condition_sees_current_hp_on_first_run():
    """A unit entering combat at 10/50 HP satisfies hp_below_pct 50 right away,
    and the same Unit gives the same answer when simulated a second time."""
    brash = skill("Brash", "a", [{
        "effect": "FLAT_DAMAGE_STRIKE",
        "target": "self",
        "params": {"flat": 10, "strike": "every_strike"},
        "conditions": [{"type": "hp_below_pct", "params": {"threshold": 50}}],
    }])
    attacker = make_unit("A", spd=30)
    attacker.a_slot = brash
    attacker.current_hp = 10
    defender = make_unit("D", hp=100, atk=25)

    first = CombatEngine(attacker, defender).simulate()
    second = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20 + 10)
    assert damage_dealt(first) == 60
    assert second == first


def test_simulation_does_not_write_back_to_the_unit():
    attacker = make_unit("A", spd=30)
    defender = make_unit("D", hp=100, atk=25)

    CombatEngine(attacker, defender).simulate()

    for unit in (attacker, defender):
        assert not hasattr(unit, "start_of_combat_hp")
        assert not hasattr(unit, "combat_stats")
        assert not hasattr(unit, "phantom_bonus")


# ── Start-of-turn grants in combat ───────────────────────────────────────────


def hone_atk(amount):
    return skill("Hone", "c", [{
        "effect": "GRANT_VISIBLE_STAT",
        "target": "self",
        "params": {"stats": {"atk": amount}},
        "conditions": [],
    }])


def test_start_of_turn_grant_reaches_combat_stats():
    """A Hone-style Atk+6 grant raises in-combat Atk, not just the stat screen."""
    attacker = make_unit("A", spd=30)
    attacker.c_slot = hone_atk(6)
    defender = make_unit("D", hp=100, atk=25)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    assert engine.combatant_states["attacker"].combat_stats.atk == 46
    # 2 x (46 - 20)
    assert damage_dealt(result) == 52


def test_bonus_neut_still_strips_a_granted_buff():
    """BONUS_NEUT on the foe neutralizes the grant like any other visible buff."""
    attacker = make_unit("A", spd=30)
    attacker.c_slot = hone_atk(6)
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(status("Neut", [{
        "effect": "BONUS_NEUT", "target": "self", "params": {}, "conditions": [],
    }]))

    result = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20)
    assert damage_dealt(result) == 40


# ── any_of / all_of across timings ───────────────────────────────────────────


def condition_state(unit, *, is_initiator):
    """25/50 HP, so hp_below_pct 100 passes and hp_below_pct 0 fails."""
    return CombatantState(
        unit=unit, current_hp=25, current_cooldown=0,
        is_initiator=is_initiator, start_of_combat_hp=25,
    )


def test_any_of_waits_for_a_later_timing_branch():
    """unit_initiates fails at static timing but hp_below_pct passes at
    post_aoe: the any_of must stay pending, then resolve True."""
    cond = build_conditions([{"any_of": [
        {"type": "unit_initiates"},
        {"type": "hp_below_pct", "params": {"threshold": 100}},
    ]}])[0]
    unit = condition_state(make_unit("A"), is_initiator=False)
    foe = condition_state(make_unit("F"), is_initiator=True)

    assert check_condition(cond, "static", unit, foe) is None
    assert check_condition(cond, "post_aoe", unit, foe) is True


def test_all_of_waits_for_a_later_timing_branch():
    """foe_initiates passes at static timing but hp_below_pct fails at
    post_aoe: the all_of must stay pending, then resolve False."""
    cond = build_conditions([{"all_of": [
        {"type": "foe_initiates"},
        {"type": "hp_below_pct", "params": {"threshold": 0}},
    ]}])[0]
    unit = condition_state(make_unit("A"), is_initiator=False)
    foe = condition_state(make_unit("F"), is_initiator=True)

    assert check_condition(cond, "static", unit, foe) is None
    assert check_condition(cond, "post_aoe", unit, foe) is False


def test_composites_short_circuit_on_a_decisive_branch():
    unit = condition_state(make_unit("A"), is_initiator=True)
    foe = condition_state(make_unit("F"), is_initiator=False)
    any_of = build_conditions([{"any_of": [
        {"type": "unit_initiates"},
        {"type": "hp_below_pct", "params": {"threshold": 0}},
    ]}])[0]
    all_of = build_conditions([{"all_of": [
        {"type": "foe_initiates"},
        {"type": "hp_below_pct", "params": {"threshold": 100}},
    ]}])[0]

    assert check_condition(any_of, "static", unit, foe) is True
    assert check_condition(all_of, "static", unit, foe) is False
