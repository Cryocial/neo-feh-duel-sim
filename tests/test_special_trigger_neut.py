"""
Tests for SPECIAL_TRIGGER_NEUT: prevents a unit's Special from triggering on
a strike even once its cooldown has reached 0. The cooldown is simply held at
0 (via the normal breath/guard charge path in _process_strike) until the
effect stops applying, at which point the Special fires on a later strike.

PREREQUISITES (must exist in source before these pass):
  - combatcalculator.py: CombatEngine._special_trigger_neutralized
  - combatcalculator.py: striker_special / target_special in _process_strike
    consult _special_trigger_neutralized
"""

import pytest

from backend.build import Unit
from backend.constants import MovementType, WeaponType, Color, EffectType, StrikeType
from backend.effects import Effect
from backend.combatcalculator import CombatEngine, CombatantState, Strike


def plain_unit(name="U") -> Unit:
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=50,
        atk=30,
        spd=30,
        defense=20,
        res=20,
    )


def neut_effect(strike="every_strike") -> Effect:
    return Effect(
        type=EffectType.SPECIAL_TRIGGER_NEUT,
        applied_by="foe",
        params={"strike": strike},
        conditions=[],
    )


def state_with(unit, on_strike_effects=None, cooldown=0) -> CombatantState:
    s = CombatantState(unit=unit, current_hp=unit.base_stats.hp, current_cooldown=cooldown)
    if on_strike_effects:
        s.effects_on_strike = list(on_strike_effects)
    return s


def first_strike(striker="attacker", target="defender") -> Strike:
    return Strike(striker, target, StrikeType.FIRST, is_first_hit=True)


@pytest.fixture
def engine():
    return CombatEngine(plain_unit("A"), plain_unit("D"))


# ── _special_trigger_neutralized (unit-level) ──────────────────────────────


def test_no_neut_effect_is_false(engine):
    state = state_with(plain_unit())
    assert engine._special_trigger_neutralized(state, first_strike()) is False


def test_every_strike_neut_blocks(engine):
    state = state_with(plain_unit(), [neut_effect()])
    assert engine._special_trigger_neutralized(state, first_strike()) is True


def test_strike_scoped_neut_respects_strike_matches(engine):
    state = state_with(plain_unit(), [neut_effect(strike="first_strike")])
    follow_up = Strike("attacker", "defender", StrikeType.FOLLOW_UP)
    assert engine._special_trigger_neutralized(state, first_strike()) is True
    assert engine._special_trigger_neutralized(state, follow_up) is False


# ── integration via _process_strike ────────────────────────────────────────


def _wire(engine, striker, target):
    engine.combatant_states = {"attacker": striker, "defender": target}
    for s in (striker, target):
        s.combat_stats = s.unit.base_stats
        s.defensive_stat = "defense"


def test_process_strike_blocks_special_when_neutralized(engine):
    striker = state_with(plain_unit("A"), on_strike_effects=[neut_effect()], cooldown=0)
    striker.unit.max_cooldown = 4
    target = state_with(plain_unit("D"), cooldown=5)
    _wire(engine, striker, target)

    engine._process_strike(first_strike())

    assert striker.special_use_count == 0
    assert striker.current_cooldown == 0  # held at 0, not reset to max_cooldown


def test_process_strike_triggers_special_without_neut(engine):
    striker = state_with(plain_unit("A"), cooldown=0)
    striker.unit.max_cooldown = 4
    target = state_with(plain_unit("D"), cooldown=5)
    _wire(engine, striker, target)

    engine._process_strike(first_strike())

    assert striker.special_use_count == 1
    assert striker.current_cooldown == striker.unit.max_cooldown
