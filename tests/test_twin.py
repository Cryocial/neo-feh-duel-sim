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
interfere. Only the damage the defender takes is asserted -- the defender's
own counter damage to the attacker is irrelevant to what's being tested here.
"""

from backend.constants import SpecialType
from helpers import effect, fight, make_unit, special, status

BRAVE = status(effect("BRAVE"))


def piercable_dr(pct, strike):
    return status(
        effect("PERC_DR_STRIKE", {"flat": pct, "strike": strike, "piercable": True})
    )


def capped_dr(pct, strike, max_triggers):
    """A non-piercable DR, the kind max_triggers and Twin apply to."""
    return status(
        effect(
            "PERC_DR_STRIKE",
            {
                "flat": pct,
                "strike": strike,
                "piercable": False,
                "max_triggers": max_triggers,
            },
        )
    )


def twin(value):
    return status(effect("TWIN", {"value": value}))


def test_non_piercable_dr_caps_without_twin():
    """No Twin: the effect's own max_triggers=1 caps it at a single trigger."""
    attacker = make_unit("A", spd=20)
    defender = make_unit(
        "D", atk=10, statuses=[capped_dr(30, "every_strike", max_triggers=1)]
    )

    outcome = fight(attacker, defender)

    # Hit 1: 20 * 0.7 = 14 (triggers, count -> 1)
    # Hit 2: cap reached, full 20.
    assert outcome.defender_lost == 14 + 20


def test_twin_affects_only_non_piercable_DR():
    """Both a piercable and a non-piercable DR are present. The
    piercable one exhausts its cap on hit 1 while the
    non-piercable one still applies on hit 2 regardless."""
    attacker = make_unit("A", spd=20)
    defender = make_unit(
        "D",
        atk=10,
        statuses=[
            piercable_dr(30, "first_strike"),
            capped_dr(30, "every_strike", max_triggers=1),
            twin(2),
        ],
    )

    outcome = fight(attacker, defender)

    # Hit 1: both apply -> (1-0.3) * (1-0.3) = 0.49 -> 20 * 0.49 = 10
    # Hit 2: only non piercable -> 20 * 0.7 = 14
    assert outcome.defender_lost == 10 + 14


def test_only_highest_twin_value_applies():
    """Two Twin effects are active with different value,
    only the highest applies"""
    attacker = make_unit("A", spd=20, statuses=[BRAVE])
    defender = make_unit(
        "D",
        atk=10,
        statuses=[capped_dr(50, "every_strike", max_triggers=2), twin(3), twin(4)],
    )

    outcome = fight(attacker, defender)

    # All hits: DR applies -> 20 * 0.5 = 10
    assert outcome.defender_lost == 10 + 10 + 10 + 10


def test_twin_infinite_removes_cap():
    """Twin value -1 removes the cap entirely, regardless of the effect's
    own max_triggers."""
    attacker = make_unit("A", spd=20, statuses=[BRAVE])
    defender = make_unit(
        "D",
        atk=10,
        statuses=[capped_dr(50, "every_strike", max_triggers=1), twin(-1)],
    )

    outcome = fight(attacker, defender)

    # All hits: DR applies -> 20 * 0.5 = 10
    assert outcome.defender_lost == 10 + 10 + 10 + 10


def test_effects_on_different_strikes_are_independently_tracked():
    """Two non-piercable effects trigger on different hits:
    one on "first_attack" (both hits of the brave first attack, but no
    follow-up), one on "any_special_ready_or_triggered" (only when the
    attacker's Special is ready). The attacker's max_cooldown=1 means its
    Special isn't ready for hit 1, but becomes ready for hit 2 after
    charging +1."""
    attacker = make_unit(
        "A", spd=20, special=special(SpecialType.OFF), statuses=[BRAVE]
    )
    x = capped_dr(30, "first_attack", max_triggers=1)
    y = capped_dr(60, "any_special_ready_or_triggered", max_triggers=1)
    defender = make_unit("D", atk=10, statuses=[x, y, twin(2)])

    outcome = fight(attacker, defender)

    # Hit 1: Special not ready yet, only X applies -> 20 * 0.7 = 14
    # Hit 2: Special now ready, both apply -> (1-0.3) * (1-0.6) = 0.28 -> 20 * 0.28 = 6
    # Hit 3: cap reached for X, only Y applies -> 20 * 0.4 = 8
    # Hit 4: cap reached for both; full 20
    assert outcome.defender_lost == 14 + 6 + 8 + 20


def test_different_effects_have_independent_caps_with_twin():
    """Two different non-piercable effects with different base max_triggers
    (1 and 3), same Twin bonus (2): X's effective cap becomes 2, Y's stays 3
    (Twin doesn't lower an already-higher base). With 3 strikes (2 brave +
    1 follow-up, guaranteed by a large Spd lead), X drops out on strike 3
    while Y still applies."""
    attacker = make_unit("A", spd=50, statuses=[BRAVE])
    x = capped_dr(30, "every_strike", max_triggers=1)
    y = capped_dr(50, "every_strike", max_triggers=3)
    defender = make_unit("D", atk=10, spd=0, statuses=[x, y, twin(2)])

    outcome = fight(attacker, defender)

    # Hit 1 & 2: both apply -> (1-0.3) * (1-0.5) = 0.35 -> 20 * 0.35 = 7
    # Hit 3: X capped out (2/2), only Y applies -> 20 * 0.5 = 10
    # Hit 4: cap reached for both; full 20
    assert outcome.defender_lost == 7 + 7 + 10 + 20
