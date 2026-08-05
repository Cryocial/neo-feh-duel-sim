"""
Integration tests for the Style mechanic (grants_style / style_enabled / nb_styles).

Rules under test:
  - A style's effects only apply if the unit toggled style_enabled AND has
    exactly one grants_style source (skill or status) equipped/active.
  - Equipping two style sources at once disables both, even if enabled.
  - grants_style can come from either an equipped Skill or an active Status.

Setup choices that keep expected damage exact and hand-verifiable (mirrors
test_combat_integration.py): same color (no weapon-triangle multiplier),
physical attacker (damage = atk - def), no other skills/follow-ups.
"""

from backend.build import Unit, Status, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color
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
