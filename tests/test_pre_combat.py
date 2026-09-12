"""
Pre-combat damage and healing (PRE_CBT_DAMAGE / PRE_CBT_HEAL), resolved in
_resolve_pre_combat before the strike loop.

Rules verified:
  - PRE_CBT_DAMAGE sources STACK: every source lands, floored at 1 HP
  - PRE_CBT_HEAL sources DON'T stack: only the highest single source heals
    (three Imbue-style sources of 20, 20 and 10 restore 20, not 50)
  - healing still caps at max HP

Setup: same colour, both melee, equal Spd, so the exchange is exactly one
strike each. The attacker (40 Atk) hits the 20-Def defender for 20; the
defender (25 Atk) counters the 20-Def attacker for 5. Pre-combat HP changes
are therefore read straight off attacker_final_hp + 5.
"""

from backend.build import Unit, Status
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


def heal(amount):
    return Status(name=f"Heal {amount}", type="bonus", effects=[{
        "effect": "PRE_CBT_HEAL",
        "target": "self",
        "params": {"flat": amount},
        "conditions": [],
    }])


def damage_foe(amount):
    """Held by one unit, damages the OTHER before combat (Flame vein pattern)."""
    return Status(name=f"Damage {amount}", type="bonus", effects=[{
        "effect": "PRE_CBT_DAMAGE",
        "target": "foe",
        "params": {"flat": amount},
        "conditions": [],
    }])


def attacker_hp_before_counter(result):
    return result["attacker_final_hp"] + 5


def test_pre_combat_heal_takes_the_highest_source_only():
    attacker = make_unit("A")
    attacker.current_hp = 20
    for amount in (20, 20, 10):
        attacker.active_statuses.append(heal(amount))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    # 20 + 20, not 20 + 50
    assert attacker_hp_before_counter(result) == 40


def test_pre_combat_heal_single_source_still_applies():
    attacker = make_unit("A")
    attacker.current_hp = 20
    attacker.active_statuses.append(heal(15))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 35


def test_pre_combat_heal_caps_at_max_hp():
    attacker = make_unit("A")
    attacker.current_hp = 45
    attacker.active_statuses.append(heal(20))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 50


def test_pre_combat_damage_sources_stack():
    attacker = make_unit("A")
    defender = make_unit("D", hp=100, atk=25)
    for amount in (7, 7, 4):
        defender.active_statuses.append(damage_foe(amount))

    result = CombatEngine(attacker, defender).simulate()

    # 50 - (7 + 7 + 4)
    assert attacker_hp_before_counter(result) == 32
