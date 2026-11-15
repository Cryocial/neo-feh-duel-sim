"""
Tests for max HP (Unit.max_hp), which counts the visible +HP granted by
equipped skills (HP+5 etc.) on top of the base stat.

Rules verified:
  - current HP defaults to max HP until it is set explicitly
  - healing caps at max HP, not at the base HP stat
  - HP% conditions divide by max HP, not by the base HP stat

Setup: same colour, both melee. A 40 Atk attacker hits the 20 Def defender
for 20; the 25 Atk defender counters the 20 Def attacker for 5.
"""

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


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


def skill(name, slot, effects=(), visible_stats=StatBlock()):
    return Skill(
        name=name,
        slot=slot,
        might=0,
        slaying=0,
        cooldown=0,
        visible_stats=visible_stats,
        effects=list(effects),
        allowed_movement_types=[],
        allowed_weapon_types=[],
    )


def hp_weapon(bonus):
    """A weapon granting visible HP+bonus, so max HP is base HP + bonus."""
    return skill("HP Weapon", "weapon", visible_stats=StatBlock(hp=bonus))


def test_current_hp_defaults_to_max_hp_with_skill_bonus():
    unit = make_unit("A")
    unit.weapon = hp_weapon(5)

    assert unit.max_hp == 55
    assert unit.current_hp == 55

    unit.current_hp = 10
    assert unit.current_hp == 10


def test_healing_caps_at_max_hp_not_base_hp():
    """45/55 heals 20 on its own strike and stops at 55, then eats one
    5-damage counter: 50. A base-HP cap would have stopped the heal at 50."""
    attacker = make_unit("A")
    attacker.weapon = hp_weapon(5)
    attacker.current_hp = 45
    attacker.active_statuses.append(
        Status(
            name="Heal",
            type="bonus",
            effects=[
                {
                    "effect": "HEAL_STRIKE",
                    "target": "self",
                    "params": {"flat": 20, "strike": "every_strike"},
                    "conditions": [],
                }
            ],
        )
    )
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50


def test_hp_pct_condition_divides_by_max_hp():
    """27/55 is 49%, so hp_below_pct 50 passes; against base HP 50 it would
    be 54% and fail."""
    brash = skill(
        "Brash",
        "passive_a",
        [
            {
                "effect": "FLAT_DAMAGE_STRIKE",
                "target": "self",
                "params": {"flat": 10, "strike": "every_strike"},
                "conditions": [{"type": "hp_below_pct", "params": {"threshold": 50}}],
            }
        ],
    )
    attacker = make_unit("A", spd=30)
    attacker.weapon = hp_weapon(5)
    attacker.a_slot = brash
    attacker.current_hp = 27
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    # 2 x (40 - 20 + 10)
    assert result["defender_final_hp"] == 100 - 60
