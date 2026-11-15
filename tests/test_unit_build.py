"""
Tests for Unit construction (backend/build.py).

Rules verified:
  - dragonflowers are distributed once: n flowers add n stat points
  - an engaged unit gains one stat point per Engage ring level, capped at 10;
    the ring level is ignored while the unit is not engaged
  - max_cooldown is the Special's cooldown minus every equipped item's
    slaying, floored at 1, and 0 when no Special is equipped; an explicit
    assignment overrides it
"""

from backend.build import Unit, Skill, StatBlock
from backend.constants import MovementType, WeaponType, Color


def make_unit(name, **kwargs):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=50,
        atk=40,
        spd=10,
        defense=20,
        res=20,
        **kwargs,
    )


def skill(name, slot, **overrides):
    fields = dict(
        name=name,
        slot=slot,
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=StatBlock(),
        effects=[],
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )
    fields.update(overrides)
    return Skill(**fields)


def stat_total(unit):
    return sum(
        getattr(unit.base_stats, s) for s in ("hp", "atk", "spd", "defense", "res")
    )


# ── dragonflowers ────────────────────────────────────────────────────────────


def test_dragonflowers_are_applied_once():
    """5 flowers add 5 stat points total, one per stat in priority order."""
    plain = make_unit("A")
    flowered = make_unit("A", dragonflower=5)

    assert stat_total(flowered) - stat_total(plain) == 5
    for s in ("hp", "atk", "spd", "defense", "res"):
        assert getattr(flowered.base_stats, s) == getattr(plain.base_stats, s) + 1


# ── Engage stats ─────────────────────────────────────────────────────────────


def test_engaged_unit_receives_ring_level_stats_capped_at_ten():
    plain = make_unit("A")
    engaged = make_unit("A", is_engaged=True, engage_ring_level=4)
    capped = make_unit("A", is_engaged=True, engage_ring_level=15)

    assert engaged.is_engaged is True
    assert stat_total(engaged) - stat_total(plain) == 4
    assert stat_total(capped) - stat_total(plain) == 10


def test_unengaged_unit_ignores_ring_level():
    plain = make_unit("A")
    unit = make_unit("A", engage_ring_level=4)

    assert stat_total(unit) == stat_total(plain)


# ── max_cooldown derived from the Special ────────────────────────────────────


def test_max_cooldown_is_special_cooldown_minus_slaying():
    unit = make_unit("A")
    assert unit.max_cooldown == 0

    unit.special = skill("Special", "special", cooldown=3)
    assert unit.max_cooldown == 3

    unit.weapon = skill("Slaying", "weapon", slaying=1)
    assert unit.max_cooldown == 2


def test_max_cooldown_floors_at_one_and_honours_an_override():
    unit = make_unit("A")
    unit.special = skill("Special", "special", cooldown=2)
    unit.weapon = skill("Slaying", "weapon", slaying=2)
    assert unit.max_cooldown == 1

    unit.max_cooldown = 5
    assert unit.max_cooldown == 5
