"""
Tests for CombatEngine._get_wta_percent (Weapon Triangle + Triangle Adept).

Rules verified:
  - No color advantage -> 0 (TA is irrelevant when neutral)
  - Plain advantage -> +20, plain disadvantage -> -20
  - Triangle Adept (on EITHER combatant) amplifies an existing advantage
    to its params value (default 40% -> +40 / -40)
  - Cancel Affinity (on either side) neutralizes the TA amplification,
    reverting to base ±20%
  - In a full combat, with the effects carried by a status, that percent of
    the striker's Atk is truncated, then added to Atk, before Def is
    subtracted

PREREQUISITES (must exist in source before these pass):
  - constants.py: EffectType.TRIANGLE_ADEPT, EffectType.CANCEL_AFFINITY
  - effects.py EFFECT_LIST_MAP: both routed to "effects_on_strike"
  - combatcalculator.py: the TA-aware _get_wta_percent
"""

import pytest

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color, EffectType
from backend.effects import Effect
from backend.combatcalculator import CombatEngine, CombatantState


# ── helpers ───────────────────────────────────────────────────────────────────


def colored_unit(color: Color, name="U", atk=30, defense=20) -> Unit:
    """A minimal unit of a given color. Weapon type is arbitrary here since
    WTA is color-based; stats are round and irrelevant to the percent."""
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=40,
        atk=atk,
        spd=30,
        defense=defense,
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


def test_neutral_matchup_is_zero(engine):
    # RED striker vs RED target -> no advantage
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_percent(striker, target) == 0


def test_advantage_base(engine):
    # RED beats GREEN -> +20%
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_percent(striker, target) == 20


def test_disadvantage_base(engine):
    # RED into BLUE -> -20%
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.BLUE))
    assert engine._get_wta_percent(striker, target) == -20


def test_colorless_is_neutral(engine):
    striker = state_with(colored_unit(Color.COLORLESS))
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_percent(striker, target) == 0


# ── Triangle Adept amplification ──────────────────────────────────────────────


def test_ta_on_striker_amplifies_advantage(engine):
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_percent(striker, target) == 40


def test_ta_on_target_also_amplifies(engine):
    # TA on the disadvantaged target still amplifies the striker's advantage
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN), [ta_effect(40)])
    assert engine._get_wta_percent(striker, target) == 40


def test_ta_amplifies_disadvantage(engine):
    # RED into BLUE with TA -> -40%
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.BLUE))
    assert engine._get_wta_percent(striker, target) == -40


def test_ta_default_magnitude_when_no_params(engine):
    striker = state_with(colored_unit(Color.RED), [ta_effect_no_params()])
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_percent(striker, target) == 40


def test_ta_irrelevant_when_neutral(engine):
    # TA present but no color advantage -> stays 0 (TA never CREATES advantage)
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.RED))
    assert engine._get_wta_percent(striker, target) == 0


# ── Cancel Affinity ───────────────────────────────────────────────────────────


def test_cancel_affinity_neutralizes_ta(engine):
    # advantage + TA, but target has Cancel Affinity -> back to base +20
    striker = state_with(colored_unit(Color.RED), [ta_effect(40)])
    target = state_with(colored_unit(Color.GREEN), [cancel_affinity_effect()])
    assert engine._get_wta_percent(striker, target) == 20


def test_cancel_affinity_on_striker_side_also_works(engine):
    striker = state_with(
        colored_unit(Color.RED), [ta_effect(40), cancel_affinity_effect()]
    )
    target = state_with(colored_unit(Color.GREEN))
    assert engine._get_wta_percent(striker, target) == 20


def test_cancel_affinity_without_ta_leaves_base(engine):
    # CA present, no TA -> base advantage unaffected
    striker = state_with(colored_unit(Color.RED))
    target = state_with(colored_unit(Color.GREEN), [cancel_affinity_effect()])
    assert engine._get_wta_percent(striker, target) == 20


# ── through a full combat ─────────────────────────────────────────────────────
#
# The tests above hand-build the states. These carry the effects in a status
# and run simulate(): RED initiates on GREEN, 40 Atk against 20 Def each way
# unless given, equal Spd so each side strikes once. The triangle's percent of
# Atk is added or taken away, and Def comes off after: 48 - 20 at +20%,
# 32 - 20 at -20%.


def holding(effect, params=None) -> Status:
    """A status carrying one effect on its holder."""
    return Status(
        name=effect,
        type="bonus",
        effects=[
            {
                "effect": effect,
                "target": "self",
                "params": params or {},
                "conditions": [],
            }
        ],
    )


def duel(attacker_statuses=(), defender_statuses=(), atk=40, defense=20):
    """Returns the damage RED dealt to GREEN and the damage it took back.
    Both units have the same Atk and the same Def."""
    attacker = colored_unit(Color.RED, "A", atk=atk, defense=defense)
    attacker.active_statuses.extend(attacker_statuses)
    defender = colored_unit(Color.GREEN, "D", atk=atk, defense=defense)
    defender.active_statuses.extend(defender_statuses)
    result = CombatEngine(attacker, defender).simulate()
    return (
        defender.current_hp - result["defender_final_hp"],
        attacker.current_hp - result["attacker_final_hp"],
    )


def test_plain_advantage_in_combat():
    dealt, taken = duel()
    assert dealt == 48 - 20
    assert taken == 32 - 20


def test_triangle_adept_in_a_status_amplifies_both_directions():
    """One TRIANGLE_ADEPT, on the attacker: its strike goes to +40% and the
    foe's counter to -40%."""
    dealt, taken = duel(attacker_statuses=[holding("TRIANGLE_ADEPT", {"flat": 40})])
    assert dealt == 56 - 20
    assert taken == 24 - 20


def test_triangle_adept_on_the_disadvantaged_unit_does_the_same():
    dealt, taken = duel(defender_statuses=[holding("TRIANGLE_ADEPT", {"flat": 40})])
    assert dealt == 56 - 20
    assert taken == 24 - 20


def test_cancel_affinity_in_a_status_restores_the_base_triangle():
    dealt, taken = duel(
        attacker_statuses=[holding("TRIANGLE_ADEPT", {"flat": 40})],
        defender_statuses=[holding("CANCEL_AFFINITY")],
    )
    assert dealt == 48 - 20
    assert taken == 32 - 20


# ── rounding ──────────────────────────────────────────────────────────────────
#
# The percent of Atk is truncated on its own, then added to Atk or taken from
# it. That is not the same as truncating Atk × 0.8, and it has to be worked
# out in whole numbers: as floats, 45 × 1.4 is 62.99999999999999. Def is set
# per case so that no strike is lethal.


@pytest.mark.parametrize(
    "atk, defense, expected",
    [
        (45, 30, 63 - 30),
        (85, 90, 119 - 90),
        (90, 90, 126 - 90),
    ],
)
def test_triangle_adept_boost_is_exact(atk, defense, expected):
    """40% of 45, 85 and 90 Atk is a whole 18, 34 and 36: nothing to truncate."""
    dealt, _ = duel(
        attacker_statuses=[holding("TRIANGLE_ADEPT", {"flat": 40})],
        atk=atk,
        defense=defense,
    )
    assert dealt == expected


@pytest.mark.parametrize(
    "atk, defense, dealt, taken",
    [
        (33, 20, 39 - 20, 27 - 20),
        (51, 30, 61 - 30, 41 - 30),
    ],
)
def test_triangle_percent_is_truncated_before_it_is_applied(atk, defense, dealt, taken):
    """20% of 33 Atk is 6.6, which counts as 6 both ways: 39 at an advantage
    and 27 at a disadvantage, where trunc(33 × 0.8) is 26."""
    assert duel(atk=atk, defense=defense) == (dealt, taken)


def test_triangle_adept_percent_is_truncated_before_it_is_applied():
    """40% of 33 Atk is 13.2, which counts as 13 both ways: 46 at an advantage
    and 20 at a disadvantage, where trunc(33 × 0.6) is 19."""
    dealt, taken = duel(
        attacker_statuses=[holding("TRIANGLE_ADEPT", {"flat": 40})],
        atk=33,
        defense=10,
    )
    assert dealt == 46 - 10
    assert taken == 20 - 10
