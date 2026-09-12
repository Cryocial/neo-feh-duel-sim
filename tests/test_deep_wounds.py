"""
Healing and the [Deep Wounds] family, in combat and after it.

In combat (PRE_CBT_HEAL, HEAL_STRIKE) DEEP_WOUNDS_IN_CBT blocks all healing,
NEUT_DEEP_WOUNDS_IN_CBT switches that off, and REDUCE_DEEP_WOUNDS_IN_CBT lets a
percentage through, rounded up. After combat the same three exist as
*_POST_CBT and gate HEAL_POST_CBT. DAMAGE_POST_CBT sits on the unit that takes
the damage, like BURN_DAMAGE, and floors at 1 HP.

Setup: one strike each. The 40 Atk attacker deals 20 to the 20 Def foe; the
25 Atk foe counters the 20 Def attacker for 5.
"""

from backend.build import Unit, Skill, StatBlock, Status
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


def status(effect, params=None, kind="bonus"):
    return Status(name=effect, type=kind, effects=[{
        "effect": effect, "target": "self", "params": params or {}, "conditions": [],
    }])


def attacker_at(hp, *statuses):
    unit = make_unit("A")
    unit.current_hp = hp
    unit.active_statuses.extend(statuses)
    return unit


def final_hp(attacker, defender=None):
    return CombatEngine(attacker, defender or make_unit("D", hp=100, atk=25)).simulate()["attacker_final_hp"]


# ── in combat ────────────────────────────────────────────────────────────────


def test_pre_combat_heal_applies_before_the_counter():
    assert final_hp(attacker_at(20, status("PRE_CBT_HEAL", {"flat": 20}))) == 20 + 20 - 5


def test_deep_wounds_blocks_in_combat_healing():
    unit = attacker_at(20, status("PRE_CBT_HEAL", {"flat": 20}), status("DEEP_WOUNDS_IN_CBT", kind="penalty"))

    assert final_hp(unit) == 20 - 5


def test_neutralize_deep_wounds_restores_in_combat_healing():
    unit = attacker_at(
        20,
        status("PRE_CBT_HEAL", {"flat": 20}),
        status("DEEP_WOUNDS_IN_CBT", kind="penalty"),
        status("NEUT_DEEP_WOUNDS_IN_CBT"),
    )

    assert final_hp(unit) == 20 + 20 - 5


def test_reduce_deep_wounds_lets_a_share_through_rounded_up():
    """50% of a 20 heal survives: ceil(10) = 10."""
    unit = attacker_at(
        20,
        status("PRE_CBT_HEAL", {"flat": 20}),
        status("DEEP_WOUNDS_IN_CBT", kind="penalty"),
        status("REDUCE_DEEP_WOUNDS_IN_CBT", {"flat": 50}),
    )

    assert final_hp(unit) == 20 + 10 - 5


def test_deep_wounds_also_blocks_heal_strike():
    heal_on_hit = status("HEAL_STRIKE", {"flat": 5, "strike": "every_strike"})

    assert final_hp(attacker_at(20, heal_on_hit)) == 20 + 5 - 5
    assert final_hp(attacker_at(20, heal_on_hit, status("DEEP_WOUNDS_IN_CBT", kind="penalty"))) == 20 - 5


# ── after combat ─────────────────────────────────────────────────────────────


def test_heal_post_cbt_heals_after_the_fight():
    assert final_hp(attacker_at(30, status("HEAL_POST_CBT", {"flat": 10}))) == 30 - 5 + 10


def test_deep_wounds_post_cbt_blocks_it_and_neut_restores_it():
    blocked = attacker_at(30, status("HEAL_POST_CBT", {"flat": 10}), status("DEEP_WOUNDS_POST_CBT", kind="penalty"))
    restored = attacker_at(
        30,
        status("HEAL_POST_CBT", {"flat": 10}),
        status("DEEP_WOUNDS_POST_CBT", kind="penalty"),
        status("NEUT_DEEP_WOUNDS_POST_CBT"),
    )

    assert final_hp(blocked) == 30 - 5
    assert final_hp(restored) == 30 - 5 + 10


def test_reduce_deep_wounds_post_cbt_lets_a_share_through():
    unit = attacker_at(
        30,
        status("HEAL_POST_CBT", {"flat": 10}),
        status("DEEP_WOUNDS_POST_CBT", kind="penalty"),
        status("REDUCE_DEEP_WOUNDS_POST_CBT", {"flat": 50}),
    )

    assert final_hp(unit) == 30 - 5 + 5


def savage_blow(amount):
    """A skill on its holder that damages the foe after combat."""
    return Skill(
        name="Savage Blow", slot="passive_c", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{"effect": "DAMAGE_POST_CBT", "target": "foe", "params": {"flat": amount}, "conditions": []}],
    )


def test_damage_post_cbt_hits_the_unit_it_sits_on():
    attacker = make_unit("A")
    attacker.c_slot = savage_blow(7)

    result = CombatEngine(attacker, make_unit("D", hp=100, atk=25)).simulate()

    assert result["defender_final_hp"] == 100 - 20 - 7
    assert result["attacker_final_hp"] == 50 - 5


def test_damage_post_cbt_floors_at_one_hp():
    attacker = make_unit("A")
    attacker.c_slot = savage_blow(7)

    result = CombatEngine(attacker, make_unit("D", hp=25, atk=25)).simulate()

    assert result["defender_final_hp"] == 1                # 25 - 20 = 5, then -7 floors


# ── the dead get nothing ─────────────────────────────────────────────────────


def test_a_dead_unit_is_not_healed_after_combat():
    """5 HP, takes the 5-damage counter, dies: HEAL_POST_CBT must not revive it."""
    assert final_hp(attacker_at(5, status("HEAL_POST_CBT", {"flat": 10}))) == 0


def test_a_dead_foes_post_combat_damage_never_fires():
    """The 20-HP foe dies to the first strike before it can counter, so its
    Savage Blow (sitting on the attacker as a foe-sourced effect) is void."""
    defender = make_unit("D", hp=20, atk=25)
    defender.c_slot = savage_blow(7)

    result = CombatEngine(make_unit("A"), defender).simulate()

    assert result["defender_final_hp"] == 0
    assert result["attacker_final_hp"] == 50
