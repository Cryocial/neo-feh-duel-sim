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

import pytest

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine, CombatantState
from backend.conditions import build_conditions, check_condition


def make_unit(
    name, hp=50, atk=40, spd=10, defense=20, res=20,
    weapon_type=WeaponType.SWORD, movement_type=MovementType.INFANTRY, **kwargs,
):
    return Unit(
        name=name,
        movement_type=movement_type,
        weapon_type=weapon_type,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
        **kwargs,
    )


def skill(name, slot, effects=(), **overrides):
    fields = dict(
        name=name, slot=slot, might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), effects=list(effects),
        allowed_movement_types=[], allowed_weapon_types=[],
    )
    fields.update(overrides)
    return Skill(**fields)


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


# ── Dragonflowers ────────────────────────────────────────────────────────────


def stat_total(unit):
    return sum(
        getattr(unit.base_stats, s) for s in ("hp", "atk", "spd", "defense", "res")
    )


def test_dragonflowers_are_applied_once():
    """5 flowers add 5 stat points total, one per stat in priority order."""
    plain = make_unit("A")
    flowered = make_unit("A", dragonflower=5)

    assert stat_total(flowered) - stat_total(plain) == 5
    for s in ("hp", "atk", "spd", "defense", "res"):
        assert getattr(flowered.base_stats, s) == getattr(plain.base_stats, s) + 1


# ── DR_PIERCE ────────────────────────────────────────────────────────────────


def percent_dr(pct, piercable):
    params = {"flat": pct, "strike": "every_strike", "piercable": piercable}
    if not piercable:
        params["max_triggers"] = -1
    return status("DR", [{
        "effect": "PERC_DR_STRIKE", "target": "self", "params": params, "conditions": [],
    }])


def pierce(value):
    return skill("Pierce", "a", [{
        "effect": "DR_PIERCE",
        "target": "self",
        "params": {"value": value, "strike": "every_strike"},
        "conditions": [],
    }])


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


# ── Max HP includes equipped-skill HP ────────────────────────────────────────


def hp_weapon(bonus):
    return skill("HP Weapon", "weapon", visible_stats=StatBlock(hp=bonus))


def test_current_hp_defaults_to_max_hp_with_skill_bonus():
    unit = make_unit("A")
    unit.weapon = hp_weapon(5)

    assert unit.max_hp == 55
    assert unit.current_hp == 55

    unit.current_hp = 10
    assert unit.current_hp == 10


def test_healing_caps_at_max_hp_not_base_hp():
    """45/55 + a 20 HP pre-combat heal reaches 55, then eats one 5-damage
    counter: 50. A base-HP cap would have stopped the heal at 50."""
    attacker = make_unit("A")
    attacker.weapon = hp_weapon(5)
    attacker.current_hp = 45
    attacker.active_statuses.append(status("Heal", [{
        "effect": "PRE_CBT_HEAL", "target": "self", "params": {"flat": 20}, "conditions": [],
    }]))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50


def test_hp_pct_condition_divides_by_max_hp():
    """27/55 is 49%, so hp_below_pct 50 passes; against base HP 50 it would
    be 54% and fail."""
    brash = skill("Brash", "a", [{
        "effect": "FLAT_DAMAGE_STRIKE",
        "target": "self",
        "params": {"flat": 10, "strike": "every_strike"},
        "conditions": [{"type": "hp_below_pct", "params": {"threshold": 50}}],
    }])
    attacker = make_unit("A", spd=30)
    attacker.weapon = hp_weapon(5)
    attacker.a_slot = brash
    attacker.current_hp = 27
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20 + 10)
    assert damage_dealt(result) == 60


# ── max_cooldown derived from the Special ────────────────────────────────────


def test_max_cooldown_is_special_cooldown_minus_slaying():
    unit = make_unit("A")
    assert unit.max_cooldown == 0

    unit.special = skill("Special", "special", cooldown=3)
    assert unit.max_cooldown == 3

    unit.weapon = skill("Slaying", "weapon", slaying=1)
    assert unit.max_cooldown == 2


def test_max_cooldown_floors_at_one_and_honours_an_override():
    unit = make_unit("A")
    unit.special = skill("Special", "special", cooldown=2)
    unit.weapon = skill("Slaying", "weapon", slaying=2)
    assert unit.max_cooldown == 1

    unit.max_cooldown = 5
    assert unit.max_cooldown == 5


# ── Engage stats ─────────────────────────────────────────────────────────────


def test_engaged_unit_receives_ring_level_stats_capped_at_ten():
    plain = make_unit("A")
    engaged = make_unit("A", is_engaged=True, engage_ring_level=4)
    capped = make_unit("A", is_engaged=True, engage_ring_level=15)

    assert engaged.is_engaged is True
    assert stat_total(engaged) - stat_total(plain) == 4
    assert stat_total(capped) - stat_total(plain) == 10


def test_unengaged_unit_ignores_ring_level():
    plain = make_unit("A")
    unit = make_unit("A", engage_ring_level=4)

    assert stat_total(unit) == stat_total(plain)


# ── ally_within_spaces 1_space ───────────────────────────────────────────────


def test_ally_within_one_space_condition_evaluates():
    cond = build_conditions([{
        "type": "ally_within_spaces", "params": {"check": "1_space", "min_allies": 1},
    }])[0]
    unit = condition_state(make_unit("A"), is_initiator=True)
    foe = condition_state(make_unit("F"), is_initiator=False)

    assert check_condition(cond, "static", unit, foe) is False
    unit.unit.allies_within_1_space = 1
    assert check_condition(cond, "static", unit, foe) is True


# ── Flexible style range needs chosen_range ──────────────────────────────────


def style_range(min_range, max_range):
    return Status(
        name="Style Range", type="bonus", grants_style=True,
        effects=[{
            "effect": "RANGE_EXTENSION",
            "target": "self",
            "params": {"min": min_range, "max": max_range},
            "conditions": [{"type": "style_enabled", "params": {}}],
        }],
    )


def test_flexible_style_range_without_chosen_range_raises():
    attacker = make_unit("A")
    attacker.active_statuses.append(style_range(1, 6))
    attacker.style_enabled = True
    defender = make_unit("D")

    with pytest.raises(ValueError, match="chosen_range"):
        CombatEngine(attacker, defender).simulate()

    attacker.chosen_range = 9
    with pytest.raises(ValueError, match="chosen_range"):
        CombatEngine(attacker, defender).simulate()


# ── Armored foes counter on the attacker's original range ────────────────────


def styled_sword_attacker(style_range_value):
    attacker = make_unit("A", defense=20)
    attacker.active_statuses.append(style_range(style_range_value, style_range_value))
    attacker.style_enabled = True
    return attacker


def test_armored_melee_foe_counters_a_styled_melee_attacker():
    """A sword attacking from 3 spaces is still a range-1 unit; an armored
    sword foe counters on that original range."""
    attacker = styled_sword_attacker(3)
    defender = make_unit("D", atk=30, movement_type=MovementType.ARMOR)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10


def test_non_armored_melee_foe_still_cannot_counter_a_styled_melee_attacker():
    attacker = styled_sword_attacker(3)
    defender = make_unit("D", atk=30)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50


def test_armored_ranged_foe_cannot_counter_a_range_three_style():
    """Neither the engagement distance (3) nor the attacker's original range
    (1) matches a bow's range of 2."""
    attacker = styled_sword_attacker(3)
    defender = make_unit(
        "D", atk=30, weapon_type=WeaponType.BOW, movement_type=MovementType.ARMOR
    )

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50


def test_armor_rule_is_not_a_free_distant_counter():
    """A tome attacking an armored sword at its normal range 2: the original
    range (2) doesn't match the armor's range (1) either, so no counter."""
    attacker = make_unit("A", weapon_type=WeaponType.TOME, defense=20, res=20)
    defender = make_unit("D", atk=30, movement_type=MovementType.ARMOR)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50
