"""
Tests for the Twin mechanic (EffectType.TWIN raising the trigger cap of
non-piercable PERC_DR_STRIKE effects) and its interaction with piercable
PERC_DR_STRIKE effects.

Rules verified:
  - piercable=True effects always trigger, on every matching strike, and are
    never affected by Twin or by any trigger cap
  - piercable=False effects are capped by their own params["max_triggers"],
    combined with the unit's Twin bonus via max(base, twin)
  - each PERC_DR_STRIKE effect tracks its own trigger count independently
    (keyed by effect identity), so one capped-out effect does not block a
    different effect on the same unit
  - Twin value == -1 removes the cap entirely (unlimited triggers)

Setup: the attacker gets BRAVE (2 hits) or BRAVE + a large Spd lead (3 hits,
2 brave + 1 follow-up) so the defender's self-protection DR effects face
repeated strikes within a single combat. Damage is always 40 atk - 20 def =
20 per hit before any DR, both units melee so range/counter checks don't
interfere. Only defender_final_hp is asserted -- the defender's own counter
damage to the attacker is irrelevant to what's being tested here.
"""

from backend.build import Unit, Status, Skill, StatBlock
from backend.constants import MovementType, WeaponType, SpecialType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def brave_status():
    return Status(
        name="Test Brave",
        type="bonus",
        effects=[{"effect": "BRAVE", "target": "self", "params": {}, "conditions": []}],
    )


def piercable_dr_status(pct, strike):
    return Status(
        name="Test Piercable DR",
        type="bonus",
        effects=[
            {
                "effect": "PERC_DR_STRIKE",
                "target": "self",
                "params": {"flat": pct, "strike": strike, "piercable": True},
                "conditions": [],
            }
        ],
    )


def special_dr_status(name, pct, strike, max_triggers):
    return Status(
        name=name,
        type="bonus",
        effects=[
            {
                "effect": "PERC_DR_STRIKE",
                "target": "self",
                "params": {
                    "flat": pct,
                    "strike": strike,
                    "piercable": False,
                    "max_triggers": max_triggers,
                },
                "conditions": [],
            }
        ],
    )


def twin_status(value):
    return Status(
        name="Test Twin",
        type="bonus",
        effects=[{"effect": "TWIN", "target": "self", "params": {"value": value}, "conditions": []}],
    )


def test_non_piercable_dr_caps_without_twin():
    """No Twin: the effect's own max_triggers=1 caps it at a single trigger."""
    attacker = make_unit("A", atk=40, defense=20, spd=20)
    defender = make_unit("D", atk=10, defense=20, spd=10)
    defender.active_statuses.append(special_dr_status("Special DR", 30, "every_strike", max_triggers=1))

    result = CombatEngine(attacker, defender).simulate()

    # Hit 1: 20 * 0.7 = 14 (triggers, count -> 1)
    # Hit 2: cap reached, full 20.
    assert result["defender_final_hp"] == 50 - 14 - 20


def test_twin_affects_only_non_piercable_DR():
    """Both a piercable and a non-piercable DR are present. The
    piercable one exhausts its cap on hit 1 while the
    non-piercable one still applies on hit 2 regardless."""
    attacker = make_unit("A", atk=40, defense=20, spd=20)
    defender = make_unit("D", atk=10, defense=20, spd=10)
    defender.active_statuses.append(piercable_dr_status(30, "first_strike"))
    defender.active_statuses.append(special_dr_status("Special DR", 30, "every_strike", max_triggers=1))
    defender.active_statuses.append(twin_status(2))

    result = CombatEngine(attacker, defender).simulate()

    # Hit 1: both apply -> (1-0.3) * (1-0.3) = 0.49 -> 20 * 0.49 = 10
    # Hit 2: only non piercable -> 20 * 0.7 = 14
    assert result["defender_final_hp"] == 50 - 10 - 14


def test_only_highest_twin_value_applies():
    """Two Twin effects are active with different value,
    only the highest applies"""
    attacker = make_unit("A", atk=40, defense=20, spd=20)
    attacker.active_statuses.append(brave_status())
    defender = make_unit("D", atk=10, defense=20, spd=10)
    defender.active_statuses.append(special_dr_status("Special DR", 50, "every_strike", max_triggers=2))
    defender.active_statuses.append(twin_status(3))
    defender.active_statuses.append(twin_status(4))

    result = CombatEngine(attacker, defender).simulate()

    # All hits: DR applies -> 20 * 0.5 = 10
    assert result["defender_final_hp"] == 50 - 10 - 10 - 10 - 10


def test_twin_infinite_removes_cap():
    """Twin value -1 removes the cap entirely, regardless of the effect's
    own max_triggers."""
    attacker = make_unit("A", atk=40, defense=20, spd=20)
    attacker.active_statuses.append(brave_status())
    defender = make_unit("D", atk=10, defense=20, spd=10)
    defender.active_statuses.append(special_dr_status("Special DR", 50, "every_strike", max_triggers=1))
    defender.active_statuses.append(twin_status(-1))

    result = CombatEngine(attacker, defender).simulate()

    # All hits: DR applies -> 20 * 0.5 = 10
    assert result["defender_final_hp"] == 50 - 10 - 10 - 10 - 10


def test_effects_on_different_strikes_are_independently_tracked():
    """Two non-piercable effects trigger on different hits:
    one on "first_attack" (both hits of the brave first attack, but no
    follow-up), one on "any_special_ready_or_triggered" (only when the
    attacker's Special is ready). The attacker's max_cooldown=1 means its
    Special isn't ready for hit 1, but becomes ready for hit 2 after
    charging +1."""
    attacker = make_unit("A", atk=40, defense=20, spd=20)
    attacker.special = Skill(
        name="Special", slot="special", might=0, slaying=0, cooldown=1,
        visible_stats=StatBlock(), effects=[],
        allowed_movement_types=[], allowed_weapon_types=[],
        special_type=SpecialType.OFF,
    )
    attacker.max_cooldown = 1
    attacker.active_statuses.append(brave_status())
    defender = make_unit("D", atk=10, defense=20, spd=10)
    defender.active_statuses.append(special_dr_status("X", 30, "first_attack", max_triggers=1))
    defender.active_statuses.append(special_dr_status("Y", 60, "any_special_ready_or_triggered", max_triggers=1))
    defender.active_statuses.append(twin_status(2))

    result = CombatEngine(attacker, defender).simulate()

    # Hit 1: Special not ready yet, only X applies -> 20 * 0.7 = 14
    # Hit 2: Special now ready, both apply -> (1-0.3) * (1-0.6) = 0.28 -> 20 * 0.28 = 6
    # Hit 3: cap reached for X, only Y applies -> 20 * 0.4 = 8
    # Hit 4: cap reached for both; full 20
    assert result["defender_final_hp"] == 50 - 14 - 6 - 8 - 20


def test_different_effects_have_independent_caps_with_twin():
    """Two different non-piercable effects with different base max_triggers
    (1 and 3), same Twin bonus (2): X's effective cap becomes 2, Y's stays 3
    (Twin doesn't lower an already-higher base). With 3 strikes (2 brave +
    1 follow-up, guaranteed by a large Spd lead), X drops out on strike 3
    while Y still applies."""
    attacker = make_unit("A", atk=40, defense=20, spd=50)
    attacker.active_statuses.append(brave_status())
    defender = make_unit("D", atk=10, defense=20, spd=0)
    defender.active_statuses.append(special_dr_status("X", 30, "every_strike", max_triggers=1))
    defender.active_statuses.append(special_dr_status("Y", 50, "every_strike", max_triggers=3))
    defender.active_statuses.append(twin_status(2))

    result = CombatEngine(attacker, defender).simulate()

    # Hit 1 & 2: both apply -> (1-0.3) * (1-0.5) = 0.35 -> 20 * 0.35 = 7
    # Hit 3: X capped out (2/2), only Y applies -> 20 * 0.5 = 10
    # Hit 4: cap reached for both; full 20
    assert result["defender_final_hp"] == 50 - 7 - 7 - 10 - 20
