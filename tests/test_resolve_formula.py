"""
Tests for CombatEngine._resolve_formula.

The pipeline is:  value = floor(variable * multiplier) + flat
                  then clamp to [min, max]  (min default 0, max default -1 = no cap)

Key behaviors verified here:
  - flat-only (empty formula) returns just flat
  - multiplier + flat compose correctly with floor()
  - min defaults to 0, so results never go negative unless min is set negative
  - max defaults to -1 (no cap); a non-negative max clamps
  - each named formula reads the field it claims to
"""

from backend.build import StatBlock
from conftest import make_state


# ── basic pipeline ────────────────────────────────────────────────────────────


def test_empty_formula_flat_only(engine, plain_unit, plain_foe):
    params = {"formula": "", "multiplier": 0, "flat": 5}
    result = engine._resolve_formula(
        params, make_state(plain_unit), make_state(plain_foe)
    )
    assert result == 5


def test_empty_formula_no_flat_is_zero(engine, plain_unit, plain_foe):
    params = {"formula": ""}
    result = engine._resolve_formula(
        params, make_state(plain_unit), make_state(plain_foe)
    )
    assert result == 0


def test_multiplier_with_floor(engine, plain_unit, plain_foe):
    # bonus_count = 3, multiplier 0.5 -> floor(1.5) = 1, + flat 0
    params = {"formula": "bonus_count", "multiplier": 0.5, "flat": 0}
    state = make_state(plain_unit, bonus_count=3)
    result = engine._resolve_formula(params, state, make_state(plain_foe))
    assert result == 1


def test_multiplier_plus_flat(engine, plain_unit, plain_foe):
    # bonus_count = 3, multiplier 3 -> 9, + flat 2 = 11
    params = {"formula": "bonus_count", "multiplier": 3, "flat": 2}
    state = make_state(plain_unit, bonus_count=3)
    result = engine._resolve_formula(params, state, make_state(plain_foe))
    assert result == 11


# ── clamping ──────────────────────────────────────────────────────────────────


def test_max_caps_result(engine, plain_unit, plain_foe):
    # bonus_count 10 + flat 4 = 14, capped at 8 (the Liberate pattern)
    params = {"formula": "bonus_count", "multiplier": 1, "flat": 4, "max": 8}
    state = make_state(plain_unit, bonus_count=10)
    result = engine._resolve_formula(params, state, make_state(plain_foe))
    assert result == 8


def test_below_max_not_capped(engine, plain_unit, plain_foe):
    # bonus_count 1 + flat 4 = 5, under the cap of 8
    params = {"formula": "bonus_count", "multiplier": 1, "flat": 4, "max": 8}
    state = make_state(plain_unit, bonus_count=1)
    result = engine._resolve_formula(params, state, make_state(plain_foe))
    assert result == 5


def test_min_defaults_to_zero_no_negatives(engine, plain_unit, plain_foe):
    # No formula, negative flat -> would be -5, but min defaults to 0
    params = {"formula": "", "flat": -5}
    result = engine._resolve_formula(
        params, make_state(plain_unit), make_state(plain_foe)
    )
    assert result == 0


def test_explicit_negative_min_allows_negative(engine, plain_unit, plain_foe):
    # min set negative -> the 0-floor is lifted
    params = {"formula": "", "flat": -5, "min": -10}
    result = engine._resolve_formula(
        params, make_state(plain_unit), make_state(plain_foe)
    )
    assert result == -5


def test_max_negative_one_means_no_cap(engine, plain_unit, plain_foe):
    # max = -1 sentinel -> large value passes through uncapped
    params = {"formula": "bonus_count", "multiplier": 10, "flat": 0, "max": -1}
    state = make_state(plain_unit, bonus_count=9)  # 90
    result = engine._resolve_formula(params, state, make_state(plain_foe))
    assert result == 90


# ── named formulas: counts ────────────────────────────────────────────────────


def test_bonus_count(engine, plain_unit, plain_foe):
    params = {"formula": "bonus_count", "multiplier": 1}
    state = make_state(plain_unit, bonus_count=4)
    assert engine._resolve_formula(params, state, make_state(plain_foe)) == 4


def test_foe_penalty_count(engine, plain_unit, plain_foe):
    params = {"formula": "foe_penalty_count", "multiplier": 1}
    foe = make_state(plain_foe, penalty_count=3)
    assert engine._resolve_formula(params, make_state(plain_unit), foe) == 3


def test_all_bonus_penalty_both(engine, plain_unit, plain_foe):
    # empathy: own bonus+penalty plus foe bonus+penalty
    params = {"formula": "all_bonus_penalty_both", "multiplier": 1}
    unit = make_state(plain_unit, bonus_count=2, penalty_count=1)
    foe = make_state(plain_foe, bonus_count=1, penalty_count=3)
    assert engine._resolve_formula(params, unit, foe) == 7  # 2+1+1+3


def test_num_bonus_and_penalties_on_unit(engine, plain_unit, plain_foe):
    params = {"formula": "num_bonus_and_penalties_on_unit", "multiplier": 1}
    unit = make_state(plain_unit, bonus_count=2, penalty_count=2)
    assert engine._resolve_formula(params, unit, make_state(plain_foe)) == 4


# ── named formulas: movement / hp / bucket ────────────────────────────────────


def test_spaces_moved(engine, plain_unit, plain_foe):
    params = {"formula": "spaces_moved", "multiplier": 1, "max": 3}
    state = make_state(plain_unit, spaces_moved=5)  # capped to 3
    assert engine._resolve_formula(params, state, make_state(plain_foe)) == 3


def test_unit_max_hp_with_multiplier(engine, plain_unit, plain_foe):
    # 50 max hp * 0.4 = 20 (imbue-style heal)
    params = {"formula": "unit_max_hp", "multiplier": 0.4}
    assert (
        engine._resolve_formula(params, make_state(plain_unit), make_state(plain_foe))
        == 20
    )


def test_mitigated_bucket(engine, plain_unit, plain_foe):
    params = {"formula": "mitigated_bucket", "multiplier": 1}
    state = make_state(plain_unit, damage_mitigated_bucket=12)
    assert engine._resolve_formula(params, state, make_state(plain_foe)) == 12


# ── named formulas: combat-stat dependent ─────────────────────────────────────


def test_spd_diff_positive(engine, plain_unit, plain_foe):
    # combat spd 35 vs 20 -> diff 15
    unit = make_state(
        plain_unit, combat_stats=StatBlock(hp=50, atk=30, spd=35, defense=30, res=30)
    )
    foe = make_state(
        plain_foe, combat_stats=StatBlock(hp=50, atk=25, spd=20, defense=25, res=25)
    )
    params = {"formula": "spd_diff", "multiplier": 1}
    assert engine._resolve_formula(params, unit, foe) == 15


def test_spd_diff_floored_at_zero_when_slower(engine, plain_unit, plain_foe):
    # unit slower -> spd_diff case does max(0, ...) internally -> 0
    unit = make_state(
        plain_unit, combat_stats=StatBlock(hp=50, atk=30, spd=10, defense=30, res=30)
    )
    foe = make_state(
        plain_foe, combat_stats=StatBlock(hp=50, atk=25, spd=30, defense=25, res=25)
    )
    params = {"formula": "spd_diff", "multiplier": 4, "max": 40}
    assert engine._resolve_formula(params, unit, foe) == 0


def test_unit_cbt_atk_uses_combat_stats_when_present(engine, plain_unit, plain_foe):
    unit = make_state(
        plain_unit, combat_stats=StatBlock(hp=50, atk=44, spd=30, defense=30, res=30)
    )
    params = {"formula": "unit_cbt_atk", "multiplier": 0.5}  # dragon fang style
    assert engine._resolve_formula(params, unit, make_state(plain_foe)) == 22


def test_unknown_formula_falls_back_to_flat(engine, plain_unit, plain_foe):
    # unrecognized formula name -> variable stays 0, only flat applies
    params = {"formula": "this_formula_does_not_exist", "multiplier": 5, "flat": 3}
    result = engine._resolve_formula(
        params, make_state(plain_unit), make_state(plain_foe)
    )
    assert result == 3
