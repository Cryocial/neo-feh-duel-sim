"""
Tests for range-based counter eligibility (defender_counterattack) in
CombatEngine._determine_strike_sequence.

Rules verified:
  - The defender counters if combat_range matches their own base weapon
    range, or if they've been granted EffectType.COUNTERATTACK
  - A range mismatch without COUNTERATTACK blocks the counter, independently
    of Flash / Flash Neutralization
  - Flash still blocks the counter (and Flash Neutralization still cancels
    that block) when the range matches
  - A style-driven RANGE_EXTENSION feeds into this the same way a plain
    weapon-range mismatch does, whether it blocks or enables a counter

Setup: the attacker deals 40 - 20 = 20 when it targets Def and 40 - 10 = 30
as a Tome, which targets Res. The defender's counter deals 30 - 20 = 10.
"""

from backend.constants import WeaponType
from helpers import condition, effect, fight, make_unit, status

COUNTERATTACK = status(effect("COUNTERATTACK"))
FLASH = status(effect("FLASH"), kind="penalty")
FLASH_NEUT = status(effect("FLASH_NEUT"))


def defender(weapon_type=WeaponType.SWORD, statuses=()):
    return make_unit("D", atk=30, res=10, weapon_type=weapon_type, statuses=statuses)


def styled_attacker(combat_range):
    """A melee attacker whose enabled style forces combat_range."""
    style = status(
        effect(
            "RANGE_EXTENSION",
            {"min": combat_range, "max": combat_range},
            conditions=[condition("style_enabled")],
        ),
        grants_style=True,
    )
    attacker = make_unit("A", statuses=[style])
    attacker.style_enabled = True
    return attacker


def test_defender_counters_when_range_matches():
    """Melee attacker vs melee defender: combat_range (1) matches the
    defender's own base range, so the counter proceeds normally."""
    outcome = fight(make_unit("A"), defender())

    assert outcome.attacker_lost == 10
    assert outcome.defender_lost == 20


def test_defender_cannot_counter_on_range_mismatch():
    """Ranged (Tome) attacker vs melee defender: combat_range (2) doesn't
    match the defender's base range (1), and no COUNTERATTACK effect is
    present, so the defender cannot counter."""
    outcome = fight(make_unit("A", weapon_type=WeaponType.TOME), defender())

    assert outcome.attacker_lost == 0
    assert outcome.defender_lost == 30


def test_counterattack_effect_overrides_range_mismatch():
    """Same range mismatch as above, but the defender has been granted
    EffectType.COUNTERATTACK -> the counter proceeds despite the mismatch."""
    outcome = fight(
        make_unit("A", weapon_type=WeaponType.TOME),
        defender(statuses=[COUNTERATTACK]),
    )

    assert outcome.attacker_lost == 10
    assert outcome.defender_lost == 30


def test_flash_still_blocks_counter_when_range_matches():
    """Range matches (melee vs melee), but Flash without Flash Neutralization
    still blocks the counter."""
    outcome = fight(make_unit("A"), defender(statuses=[FLASH]))

    assert outcome.attacker_lost == 0
    assert outcome.defender_lost == 20


def test_flash_neutralization_restores_counter_when_range_matches():
    """Range matches, Flash is present but neutralized -> counter proceeds."""
    outcome = fight(make_unit("A"), defender(statuses=[FLASH, FLASH_NEUT]))

    assert outcome.attacker_lost == 10
    assert outcome.defender_lost == 20


def test_flash_neutralization_does_not_override_range_mismatch():
    """Range mismatch, no COUNTERATTACK effect, but Flash Neutralization is
    present anyway -> still cannot counter. Flash Neut only cancels Flash,
    it doesn't grant a range bypass -- the two gates must stay independent."""
    outcome = fight(
        make_unit("A", weapon_type=WeaponType.TOME),
        defender(statuses=[FLASH_NEUT]),
    )

    assert outcome.attacker_lost == 0
    assert outcome.defender_lost == 30


def test_style_range_extension_blocks_counter_on_mismatch():
    """A melee attacker whose style forces combat_range to 2 creates the same
    kind of mismatch as a Tome attacker would -- the melee defender (base
    range 1) cannot counter."""
    outcome = fight(styled_attacker(2), defender())

    assert outcome.attacker_lost == 0
    assert outcome.defender_lost == 20


def test_style_range_extension_enables_counter_on_match():
    """A melee attacker's style forces combat_range to 2, which now matches a
    ranged (Bow) defender's own base range -- a counter that would NOT happen
    without the style (attacker's base range is 1) now proceeds."""
    outcome = fight(styled_attacker(2), defender(weapon_type=WeaponType.BOW))

    assert outcome.attacker_lost == 10
    assert outcome.defender_lost == 20
