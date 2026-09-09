"""
Structural properties of the engine that hold regardless of which skills are
involved. Each catches a whole class of bug rather than one instance:

  - simulate() is a pure function of its inputs: running it twice gives the
    same answer, and it never mutates the Unit objects it was given
  - build_effect rejects malformed effect dicts loudly, with the effect named
  - every EffectType is routed to a CombatantState list that exists; every
    condition timing is a real Timing; every STRIKE_VALUES / FORMULA_NAMES
    entry is actually handled by the engine, and unknown ones raise
  - the four reference tables in ARCHITECTURE.md match the code exactly, in
    both directions, so the doc cannot drift from the registries
"""

import copy
import dataclasses
import re
import typing
from pathlib import Path

import pytest

from backend.build import DivineVein, Skill, StatBlock, Status, Unit
from backend.combatcalculator import CombatantState, CombatEngine, Strike
from backend.conditions import CONDITION_REGISTRY, Timing
from backend.constants import (
    FORMULA_NAMES,
    STRIKE_VALUES,
    Color,
    EffectType,
    MovementType,
    SpecialType,
    StrikeType,
    WeaponType,
)
from backend.effects import EFFECT_LIST_MAP, build_effect
from conftest import make_state

DOC = Path(__file__).resolve().parent.parent / "doc" / "ARCHITECTURE.md"


# ── simulate() purity ────────────────────────────────────────────────────────


def _unit(name, **stats):
    base = dict(hp=50, atk=40, spd=10, defense=20, res=20)
    base.update(stats)
    return Unit(
        name=name, movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD, color=Color.RED, **base,
    )


def _skill(name, slot, effects, **overrides):
    fields = dict(
        name=name, slot=slot, might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), effects=effects,
        allowed_movement_types=[], allowed_weapon_types=[],
    )
    fields.update(overrides)
    return Skill(**fields)


def loaded_matchup():
    """Touches every phase: start-of-turn grant, AoE special, a post_aoe HP%
    condition, a pre-combat vein, per-strike DR, and a pre-damaged attacker."""
    attacker = _unit("A", spd=30)
    attacker.special = _skill("AoE", "special", [{
        "effect": "TRIGGER_AOE", "target": "self",
        "params": {"coefficient": 1.0}, "conditions": [],
    }], cooldown=2, special_type=SpecialType.AOE)
    attacker.pre_charge = 2
    attacker.c_slot = _skill("Hone", "c", [{
        "effect": "GRANT_VISIBLE_STAT", "target": "self",
        "params": {"stats": {"atk": 6}}, "conditions": [],
    }])
    attacker.a_slot = _skill("Brash", "a", [{
        "effect": "FLAT_DAMAGE_STRIKE", "target": "self",
        "params": {"flat": 10, "strike": "every_strike"},
        "conditions": [{"type": "hp_below_pct", "params": {"threshold": 100}}],
    }])
    attacker.current_hp = 40

    defender = _unit("D", hp=100, atk=30)
    defender.active_statuses.append(Status(name="Dodge", type="bonus", effects=[{
        "effect": "PERC_DR_STRIKE", "target": "self",
        "params": {"flat": 30, "strike": "every_strike", "piercable": True},
        "conditions": [],
    }]))
    vein = DivineVein(name="Flame", effects=[{
        "effect": "PRE_CBT_DAMAGE", "target": "foe",
        "params": {"flat": 7}, "conditions": [],
    }])
    return attacker, defender, vein


def test_simulate_is_repeatable_and_leaves_units_untouched():
    attacker, defender, vein = loaded_matchup()
    before = (copy.deepcopy(attacker.__dict__), copy.deepcopy(defender.__dict__))

    first = CombatEngine(attacker, defender, defender_divine_vein=vein).simulate()
    second = CombatEngine(attacker, defender, defender_divine_vein=vein).simulate()

    assert first["defender_final_hp"] < 100, "matchup must actually do something"
    assert second == first
    assert (attacker.__dict__, defender.__dict__) == before


# ── build_effect is the validation boundary ──────────────────────────────────


@pytest.mark.parametrize("desc,message", [
    ({"effect": "NOPE", "target": "self"}, "unknown effect type"),
    ({"effect": "FLAT_DAMAGE_STRIKE", "target": "sefl", "params": {"flat": 1}},
     "target must be"),
    ({"effect": "TRIGGER_AOE", "target": "self", "params": {}}, "missing params"),
    ({"effect": "FLAT_DAMAGE_STRIKE", "target": "self",
      "params": {"flat": 1, "strike": "on_foe_special"}}, "unknown strike"),
    ({"effect": "FLAT_DAMAGE_STRIKE", "target": "self",
      "params": {"formula": "bonus_count_plus_4"}}, "unknown formula"),
])
def test_build_effect_rejects_malformed_descriptions(desc, message):
    with pytest.raises(ValueError, match=message):
        build_effect(desc, applied_by="self")


# ── registries are internally consistent ─────────────────────────────────────


def test_every_effect_type_is_routed_to_a_state_list():
    assert set(EffectType) == set(EFFECT_LIST_MAP)


def test_effect_list_map_targets_are_combatant_state_fields():
    fields = {f.name for f in dataclasses.fields(CombatantState)}
    assert set(EFFECT_LIST_MAP.values()) <= fields


def test_condition_registry_timings_are_valid():
    valid = set(typing.get_args(Timing))
    for name, (timing, _) in CONDITION_REGISTRY.items():
        assert timing in valid, f"{name} has timing {timing!r}"


@pytest.mark.parametrize("value", sorted(STRIKE_VALUES))
def test_every_strike_value_is_handled(engine, value):
    strike = Strike("attacker", "defender", StrikeType.FIRST)
    engine._strike_matches(strike, "striker", {"strike": value})


def test_unknown_strike_value_raises(engine):
    strike = Strike("attacker", "defender", StrikeType.FIRST)
    with pytest.raises(ValueError, match="Unknown strike value"):
        engine._strike_matches(strike, "striker", {"strike": "on_foe_special"})


@pytest.mark.parametrize("name", sorted(FORMULA_NAMES))
def test_every_formula_name_resolves(engine, plain_unit, plain_foe, name):
    stats = StatBlock(hp=50, atk=30, spd=30, defense=30, res=30)
    unit = make_state(plain_unit, combat_stats=stats)
    foe = make_state(plain_foe, combat_stats=stats)
    engine._resolve_formula({"formula": name, "multiplier": 1}, unit, foe)


# ── ARCHITECTURE.md reference tables match the code ──────────────────────────


def _doc_section(start, end=None):
    text = DOC.read_text(encoding="utf-8")
    begin = text.index(start)
    return text[begin:text.index(end, begin)] if end else text[begin:]


def _first_column(section):
    return {m.group(1) for m in re.finditer(r"^\| `([^`]+)`", section, re.M)}


def test_doc_effect_tables_match_effect_type():
    documented = _first_column(_doc_section("### A - Effect Type Reference", "### B -"))
    assert documented == {e.value for e in EffectType}


def test_doc_strike_table_matches_strike_values():
    documented = _first_column(_doc_section("### B - `strike` Value Reference", "### C -"))
    assert documented == set(STRIKE_VALUES)


def test_doc_formula_table_matches_formula_names():
    documented = _first_column(_doc_section("### C - `formula` Value Reference", "### D -"))
    assert documented - {'""'} == FORMULA_NAMES - {""}


def test_doc_condition_table_matches_registry():
    documented = _first_column(_doc_section("### D - Condition Type Reference"))
    assert documented == set(CONDITION_REGISTRY)
