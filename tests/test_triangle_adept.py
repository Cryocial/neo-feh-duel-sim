"""
Tests for CombatEngine._get_wta_multiplier (Weapon Triangle + Triangle Adept).

Rules verified:
  - No color advantage -> multiplier 1.0 (TA is irrelevant when neutral)
  - Plain advantage -> 1.20, plain disadvantage -> 0.80
  - Triangle Adept (on EITHER combatant) amplifies an existing advantage
    to its params value (default 40% -> 1.40 / 0.60)
  - Cancel Affinity (on either side) neutralizes the TA amplification,
    reverting to base ±20%

PREREQUISITES (must exist in source before these pass):
  - constants.py: EffectType.TRIANGLE_ADEPT, EffectType.CANCEL_AFFINITY
  - effects.py EFFECT_LIST_MAP: both routed to "effects_on_strike"
  - combatcalculator.py: the TA-aware _get_wta_multiplier
"""

import pytest

from backend.build import Unit
from backend.constants import MovementType, WeaponType, Color, EffectType
from backend.effects import Effect
from backend.combatcalculator import CombatEngine, CombatantState


# ── helpers ───────────────────────────────────────────────────────────────────


def colored_unit(color: Color, name="U") -> Unit:
    """A minimal unit of a given color. Weapon type is arbitrary here since
    WTA is color-based; stats are round and irrelevant to the multiplier."""
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=40,
        atk=30,
        spd=30,
        defense=20,
        res=20,
    )


def state_with(unit: Unit, on_strike_effects=None) -> CombatantState:
    s = CombatantState(unit=unit, current_hp=unit.base_stats.hp, current_cooldown=0)
    if on_strike_effects:
        s.effects_on_strike = list(on_strike_effects)
    return s


def ta_effect(pct=40) -> Effect:
    return Effect(
        type=EffectType.TRIANGLE_ADEPT,
        applied_by="self",
        params={"flat": pct},
        conditions=[],
    )


def ta_effect_no_params() -> Effect:
    return Effect(
        type=EffectType.TRIANGLE_ADEPT, applied_by="self", params={}, conditions=[]
    )


def cancel_affinity_effect() -> Effect:
    return Effect(
        type=EffectType.CANCEL_AFFINITY, applied_by="self", params={}, conditions=[]
    )


@pytest.fixture
def engine():
    # RED attacker vs GREEN defender = attacker has advantage by default.
    return CombatEngine(colored_unit(Color.RED, "A"), colored_unit(Color.GREEN, "D"))


# ── base weapon triangle (no TA) ──────────────────────────────────────────────


def test_neutral_matchup_is_one(engine):
    # RED striker vs RED target -> no advantage
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_multiplier(striker, target) == 1.0


def test_advantage_base(engine):
    # RED beats GREEN -> +20%
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.20)


def test_disadvantage_base(engine):
    # RED into BLUE -> -20%
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.BLUE))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(0.80)


def test_colorless_is_neutral(engine):
    striker = state_with(colored_unit(Color.COLORLESS))
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_multiplier(striker, target) == 1.0


# ── Triangle Adept amplification ──────────────────────────────────────────────


def test_ta_on_striker_amplifies_advantage(engine):
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.40)


def test_ta_on_target_also_amplifies(engine):
    # TA on the disadvantaged target still amplifies the striker's advantage
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN), [ta_effect(40)])
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.40)


def test_ta_amplifies_disadvantage(engine):
    # RED into BLUE with TA -> -40%
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.BLUE))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(0.60)


def test_ta_default_magnitude_when_no_params(engine):
    striker = state_with(colored_unit(Color.RED), [ta_effect_no_params()])
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.40)


def test_ta_irrelevant_when_neutral(engine):
    # TA present but no color advantage -> stays 1.0 (TA never CREATES advantage)
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_multiplier(striker, target) == 1.0


# ── Cancel Affinity ───────────────────────────────────────────────────────────


def test_cancel_affinity_neutralizes_ta(engine):
    # advantage + TA, but target has Cancel Affinity -> back to base 1.20
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.GREEN), [cancel_affinity_effect()])
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.20)


def test_cancel_affinity_on_striker_side_also_works(engine):
    striker = state_with(
        colored_unit(Color.RED), [ta_effect(40), cancel_affinity_effect()]
    )
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.20)


def test_cancel_affinity_without_ta_leaves_base(engine):
    # CA present, no TA -> base advantage unaffected
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN), [cancel_affinity_effect()])
    assert engine._get_wta_multiplier(striker, target) == pytest.approx(1.20)
