"""
Visible bonuses and penalties don't stack: on each stat, the highest source
wins, whether it is the unit's own visible buff, a start-of-turn grant, or
two grants to the same stat. A stat with any bonus on it counts once toward
bonus_count.

Setup: one strike each, 40 Atk vs 20 Def deals 20, the foe counters the
20 Def attacker for atk - 20.
"""

from backend.build import Unit, Skill, StatBlock
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


def grant(effect, slot, stats, target="self"):
    return Skill(
        name=f"{effect} {slot}", slot=slot, might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{"effect": effect, "target": target, "params": {"stats": stats}, "conditions": []}],
    )


def dealt(result):
    return 100 - result["defender_final_hp"]


def test_own_buff_and_granted_buff_take_the_highest():
    """+4 own, +6 from Hone: 46, not 50."""
    attacker = make_unit("A")
    attacker.visible_buffs = StatBlock(atk=4)
    attacker.c_slot = grant("GRANT_VISIBLE_BUFF", "c", {"atk": 6})

    assert dealt(CombatEngine(attacker, make_unit("D", hp=100)).simulate()) == 26


def test_two_grants_to_the_same_stat_take_the_highest():
    attacker = make_unit("A")
    attacker.a_slot = grant("GRANT_VISIBLE_BUFF", "a", {"atk": 6})
    attacker.c_slot = grant("GRANT_VISIBLE_BUFF", "c", {"atk": 4})

    assert dealt(CombatEngine(attacker, make_unit("D", hp=100)).simulate()) == 26


def test_own_debuff_and_inflicted_debuff_take_the_highest():
    """Foe at 35 with -3 own and a -5 Ploy: 30 counters for 10, not 27 for 7."""
    attacker = make_unit("A")
    attacker.c_slot = grant("INFLICT_VISIBLE_DEBUFF", "c", {"atk": 5}, target="foe")
    foe = make_unit("D", hp=100, atk=35)
    foe.visible_debuffs = StatBlock(atk=3)

    assert CombatEngine(attacker, foe).simulate()["attacker_final_hp"] == 40


def test_a_stat_with_two_bonus_sources_counts_once():
    attacker = make_unit("A")
    attacker.visible_buffs = StatBlock(atk=4)
    attacker.c_slot = grant("GRANT_VISIBLE_BUFF", "c", {"atk": 6, "spd": 6})

    engine = CombatEngine(attacker, make_unit("D", hp=100))
    engine.simulate()

    assert engine.combatant_states["attacker"].bonus_count == 2
