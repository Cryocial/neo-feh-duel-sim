"""
Regression tests for engine bugs found in the 2026-09 audit. Each test pins
one bug that the rest of the suite did not cover:

  - HP% conditions read a stale start_of_combat_hp (and leaked it between
    simulations through the Unit)
  - start-of-turn grants never reached combat stats
  - any_of / all_of resolved prematurely when their branches had different
    timings
  - dragonflowers were distributed twice
  - DR_PIERCE was computed but never applied

Setup mirrors test_special.py: same color, both melee, attacker faster by 20
so it always gets the follow-up, defender slower so it never does. A 100 HP
defender survives the exchange so damage can be read off final HP.
"""

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20, **kwargs):
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
        **kwargs,
    )


def skill(name, slot, effects):
    return Skill(
        name=name, slot=slot, might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), effects=effects,
        allowed_movement_types=[], allowed_weapon_types=[],
    )


def status(name, effects):
    return Status(name=name, type="bonus", effects=effects)


def damage_dealt(result):
    return 100 - result["defender_final_hp"]


# ── HP% conditions and Unit isolation ────────────────────────────────────────


def test_hp_pct_condition_sees_current_hp_on_first_run():
    """A unit entering combat at 10/50 HP satisfies hp_below_pct 50 right away,
    and the same Unit gives the same answer when simulated a second time."""
    brash = skill("Brash", "a", [{
        "effect": "FLAT_DAMAGE_STRIKE",
        "target": "self",
        "params": {"flat": 10, "strike": "every_strike"},
        "conditions": [{"type": "hp_below_pct", "params": {"threshold": 50}}],
    }])
    attacker = make_unit("A", spd=30)
    attacker.a_slot = brash
    attacker.current_hp = 10
    defender = make_unit("D", hp=100, atk=25)

    first = CombatEngine(attacker, defender).simulate()
    second = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20 + 10)
    assert damage_dealt(first) == 60
    assert second == first


def test_simulation_does_not_write_back_to_the_unit():
    attacker = make_unit("A", spd=30)
    defender = make_unit("D", hp=100, atk=25)

    CombatEngine(attacker, defender).simulate()

    for unit in (attacker, defender):
        assert not hasattr(unit, "start_of_combat_hp")
        assert not hasattr(unit, "combat_stats")
        assert not hasattr(unit, "phantom_bonus")
