"""
Tests for the Style mechanic (grants_style / style_enabled / nb_styles),
including the RANGE_EXTENSION override it grants to combat_range.

Rules verified:
  - A style's effects apply only if style_enabled is True AND exactly one
    grants_style source (skill or status) is equipped/active
  - Equipping two style sources at once disables both, even when enabled
  - grants_style can come from either an equipped Skill or an active Status
  - RANGE_EXTENSION overrides combat_range: fixed value if min == max,
    otherwise the user-chosen unit.chosen_range

See test_range.py for combat_range's default (no style involved).
"""

from backend.build import Unit, Status, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(
    name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20,
    weapon_type=WeaponType.SWORD,
):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def style_atk_boost_status(amount=10, grants_style=True):
    """A bonus status granting a flat in-combat Atk boost, gated on style_enabled."""
    return Status(
        name="Test Style Status",
        type="bonus",
        grants_style=grants_style,
        effects=[
            {
                "effect": "STAT_BOOST",
                "target": "self",
                "params": {"stats": ["atk"], "flat": amount},
                "conditions": [{"type": "style_enabled", "params": {}}],
            }
        ],
    )


def style_atk_boost_skill(amount=10, grants_style=True):
    """An A-slot skill granting a flat in-combat Atk boost, gated on style_enabled."""
    return Skill(
        name="Test Style Skill",
        slot="passive_a",
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        allowed_movement_types=[],
        allowed_weapon_types=[],
        grants_style=grants_style,
        effects=[
            {
                "effect": "STAT_BOOST",
                "target": "self",
                "params": {"stats": ["atk"], "flat": amount},
                "conditions": [{"type": "style_enabled", "params": {}}],
            }
        ],
    )


def test_style_applies_when_enabled_with_single_style():
    """One style source + style_enabled=True -> the STAT_BOOST applies."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    attacker.active_statuses.append(style_atk_boost_status(10))
    attacker.style_enabled = True
    defender = make_unit("D", atk=10, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    # 40 + 10 (style) - 20 def = 30 damage
    assert result["defender_final_hp"] == 50 - 30


def test_style_does_not_apply_when_not_enabled():
    """One style source but style_enabled left False (default) -> no boost."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    attacker.active_statuses.append(style_atk_boost_status(10))
    # attacker.style_enabled stays False
    defender = make_unit("D", atk=10, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    # 40 - 20 def = 20 damage, style never activates
    assert result["defender_final_hp"] == 50 - 20


def test_style_does_not_apply_with_two_styles_equipped():
    """Two style sources equipped at once -> exclusivity rule disables BOTH,
    even though style_enabled is True."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    attacker.a_slot = style_atk_boost_skill(10)
    attacker.active_statuses.append(style_atk_boost_status(10))
    attacker.style_enabled = True
    defender = make_unit("D", atk=10, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    # nb_styles == 2 -> style_enabled condition is False for both -> no boost at all
    assert result["defender_final_hp"] == 50 - 20


# ── range mechanic ──────────────────────────────────────────────────────────


def style_range_status(min_range, max_range, grants_style=True):
    """A bonus status granting a RANGE_EXTENSION, gated on style_enabled."""
    return Status(
        name="Test Style Range",
        type="bonus",
        grants_style=grants_style,
        effects=[
            {
                "effect": "RANGE_EXTENSION",
                "target": "self",
                "params": {"min": min_range, "max": max_range},
                "conditions": [{"type": "style_enabled", "params": {}}],
            }
        ],
    )


def test_fixed_range_extension_applies_when_enabled():
    """min == max -> combat_range is forced to that fixed value, overriding the
    melee unit's base range of 1."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD)
    attacker.active_statuses.append(style_range_status(2, 2))
    attacker.style_enabled = True
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 2


def test_flexible_range_extension_uses_chosen_range():
    """min != max -> combat_range comes from the user's chosen_range dropdown
    value, not from the base weapon range."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD)
    attacker.active_statuses.append(style_range_status(1, 6))
    attacker.style_enabled = True
    attacker.chosen_range = 4
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 4


def test_range_extension_does_not_apply_when_not_enabled():
    """Style equipped but style_enabled left False -> combat_range stays at
    the base weapon range."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD)
    attacker.active_statuses.append(style_range_status(2, 2))
    # attacker.style_enabled stays False
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 1


def test_range_extension_does_not_apply_with_two_styles_equipped():
    """Two style sources equipped at once -> exclusivity rule disables both,
    combat_range stays at the base weapon range."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD)
    attacker.active_statuses.append(style_range_status(2, 2))
    attacker.active_statuses.append(style_range_status(3, 3))
    attacker.style_enabled = True
    defender = make_unit("D")

    engine = CombatEngine(attacker, defender)
    engine.simulate()

    assert engine.combat_range == 1
