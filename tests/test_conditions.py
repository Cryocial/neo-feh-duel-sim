"""
Tests for condition evaluation (backend/conditions.py).

Rules verified:
  - an HP% condition reads the HP the unit enters combat with, on the first
    simulation and on every repeat of it
  - any_of / all_of stay pending while one of their branches belongs to a
    later timing, and resolve once that timing is reached
  - a decisive branch settles the node at once, without waiting for the rest
  - ally_within_spaces reads the 1_space proximity count
  - is_engaged passes when either combatant is Engaged
"""

from backend.build import Unit, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine, CombatantState
from backend.conditions import build_conditions, check_condition


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20):
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
    )


def condition_state(unit, *, is_initiator):
    """25/50 HP, so hp_below_pct 100 passes and hp_below_pct 0 fails."""
    return CombatantState(
        unit=unit, current_hp=25, current_cooldown=0, is_initiator=is_initiator
    )


# ── HP% conditions ───────────────────────────────────────────────────────────


def test_hp_pct_condition_sees_current_hp_on_first_run():
    """A unit entering combat at 10/50 HP satisfies hp_below_pct 50 right away,
    and the same Unit gives the same answer when simulated a second time."""
    attacker = make_unit("A", spd=30)
    attacker.a_slot = Skill(
        name="Brash",
        slot="passive_a",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "FLAT_DAMAGE_STRIKE",
                "target": "self",
                "params": {"flat": 10, "strike": "every_strike"},
                "conditions": [{"type": "hp_below_pct", "params": {"threshold": 50}}],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )
    attacker.current_hp = 10
    defender = make_unit("D", hp=100, atk=25)

    first = CombatEngine(attacker, defender).simulate()
    second = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20 + 10)
    assert first["defender_final_hp"] == 100 - 60
    assert second == first


# ── any_of / all_of across timings ───────────────────────────────────────────


def test_any_of_waits_for_a_later_timing_branch():
    """unit_initiates fails at static timing but hp_below_pct passes at
    post_aoe: the any_of must stay pending, then resolve True."""
    cond = build_conditions(
        [
            {
                "any_of": [
                    {"type": "unit_initiates"},
                    {"type": "hp_below_pct", "params": {"threshold": 100}},
                ]
            }
        ]
    )[0]
    unit = condition_state(make_unit("A"), is_initiator=False)
    foe = condition_state(make_unit("F"), is_initiator=True)

    assert check_condition(cond, "static", unit, foe) is None
    assert check_condition(cond, "post_aoe", unit, foe) is True


def test_all_of_waits_for_a_later_timing_branch():
    """foe_initiates passes at static timing but hp_below_pct fails at
    post_aoe: the all_of must stay pending, then resolve False."""
    cond = build_conditions(
        [
            {
                "all_of": [
                    {"type": "foe_initiates"},
                    {"type": "hp_below_pct", "params": {"threshold": 0}},
                ]
            }
        ]
    )[0]
    unit = condition_state(make_unit("A"), is_initiator=False)
    foe = condition_state(make_unit("F"), is_initiator=True)

    assert check_condition(cond, "static", unit, foe) is None
    assert check_condition(cond, "post_aoe", unit, foe) is False


def test_composites_short_circuit_on_a_decisive_branch():
    """A passing any_of branch and a failing all_of branch each decide their
    node at static timing, with the post_aoe branch still unevaluated."""
    unit = condition_state(make_unit("A"), is_initiator=True)
    foe = condition_state(make_unit("F"), is_initiator=False)
    any_of = build_conditions(
        [
            {
                "any_of": [
                    {"type": "unit_initiates"},
                    {"type": "hp_below_pct", "params": {"threshold": 0}},
                ]
            }
        ]
    )[0]
    all_of = build_conditions(
        [
            {
                "all_of": [
                    {"type": "foe_initiates"},
                    {"type": "hp_below_pct", "params": {"threshold": 100}},
                ]
            }
        ]
    )[0]

    assert check_condition(any_of, "static", unit, foe) is True
    assert check_condition(all_of, "static", unit, foe) is False


# ── ally_within_spaces ───────────────────────────────────────────────────────


def test_ally_within_one_space_condition_evaluates():
    cond = build_conditions(
        [
            {
                "type": "ally_within_spaces",
                "params": {"check": "1_space", "min_allies": 1},
            }
        ]
    )[0]
    unit = condition_state(make_unit("A"), is_initiator=True)
    foe = condition_state(make_unit("F"), is_initiator=False)

    assert check_condition(cond, "static", unit, foe) is False
    unit.unit.allies_within_1_space = 1
    assert check_condition(cond, "static", unit, foe) is True


# ── is_engaged ───────────────────────────────────────────────────────────────


def test_is_engaged_condition_passes_when_either_unit_is_engaged():
    cond = build_conditions([{"type": "is_engaged"}])[0]
    unit = condition_state(make_unit("A"), is_initiator=True)
    foe = condition_state(make_unit("F"), is_initiator=False)

    assert check_condition(cond, "static", unit, foe) is False
    foe.unit.is_engaged = True
    assert check_condition(cond, "static", unit, foe) is True
    foe.unit.is_engaged = False
    unit.unit.is_engaged = True
    assert check_condition(cond, "static", unit, foe) is True
