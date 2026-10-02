"""
Great Talent and the 99 visible-stat cap.

Great Talent is a permanent per-game stat layer, entered per stat on the Unit
like dragonflowers and raised by GRANT_GREAT_TALENT (start of turn, counts for
this combat) or GRANT_GREAT_TALENT_POST_CBT (after combat, reported in the
result only). Each stat is raised separately toward the effect's `max`, never
lowered, never pushed past the cap. It is not a bonus: Lull can't see it.

Visible Atk/Spd/Def/Res cap at 99 on the final sum, buffs and debuffs
included. A buff past the cap is "useless" for the stat but still exists as
a bonus; a Lull only removes the part of a buff actually in use, and
Neutralize Penalties only gives back the part of a debuff that was actually
lowering the stat. HP is deliberately not capped here so fixtures can use
big round numbers.

Setup: one strike each. The attacker (40 Atk unless stated) hits a 20 Def
foe; the 25 Atk foe counters the 20 Def attacker for 5.
"""

import pytest

from backend.build import Unit, Skill, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine
from backend.effects import build_effect


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


def grant(effect, stats, cap=None):
    params = {"stats": stats}
    if cap is not None:
        params["max"] = cap
    return Skill(
        name="Talent", slot="c", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{"effect": effect, "target": "self", "params": params, "conditions": []}],
    )


def lull():
    return Status(name="Lull", type="bonus", effects=[{
        "effect": "BONUS_NEUT", "target": "self", "params": {}, "conditions": [],
    }])


def neutralize_penalties():
    return Status(name="Neut Pen", type="bonus", effects=[{
        "effect": "PENALTY_NEUT", "target": "self", "params": {}, "conditions": [],
    }])


def fight(attacker):
    return CombatEngine(attacker, make_unit("D", hp=100, atk=25)).simulate()


def dealt(result):
    return 100 - result["defender_final_hp"]


# ── the stat layer ───────────────────────────────────────────────────────────


def test_great_talent_adds_to_the_visible_stat():
    assert dealt(fight(make_unit("A", great_talent={"atk": 5}))) == 25


def test_start_of_turn_grant_counts_for_this_combat_and_stops_at_the_cap():
    """18 + 4 would be 22; the cap of 20 allows only +2."""
    attacker = make_unit("A", great_talent={"atk": 18})
    attacker.c_slot = grant("GRANT_GREAT_TALENT", {"atk": 4}, cap=20)

    result = fight(attacker)

    assert dealt(result) == 40
    assert result["attacker_great_talent"]["atk"] == 20


def test_grant_never_lowers_a_unit_already_past_its_cap():
    attacker = make_unit("A", great_talent={"atk": 25})
    attacker.c_slot = grant("GRANT_GREAT_TALENT", {"atk": 2}, cap=20)

    result = fight(attacker)

    assert dealt(result) == 45
    assert result["attacker_great_talent"]["atk"] == 25


def test_grant_without_max_is_uncapped():
    attacker = make_unit("A", great_talent={"atk": 25})
    attacker.c_slot = grant("GRANT_GREAT_TALENT", {"atk": 2})

    assert dealt(fight(attacker)) == 47


def test_each_stat_is_capped_on_its_own():
    attacker = make_unit("A", great_talent={"atk": 19, "spd": 1})
    attacker.c_slot = grant("GRANT_GREAT_TALENT", {"atk": 3, "spd": 3}, cap=20)

    talent = fight(attacker)["attacker_great_talent"]

    assert talent == {"atk": 20, "spd": 4, "defense": 0, "res": 0}


def test_post_combat_grant_shows_in_the_result_but_not_in_this_fight():
    attacker = make_unit("A")
    attacker.c_slot = grant("GRANT_GREAT_TALENT_POST_CBT", {"atk": 2}, cap=20)

    result = fight(attacker)

    assert dealt(result) == 20
    assert result["attacker_great_talent"]["atk"] == 2


def test_the_unit_itself_is_never_mutated():
    attacker = make_unit("A", great_talent={"atk": 5})
    attacker.c_slot = grant("GRANT_GREAT_TALENT", {"atk": 2}, cap=20)

    result = fight(attacker)

    assert result["attacker_great_talent"]["atk"] == 7
    assert attacker.great_talent.atk == 5


# ── the 99 cap ───────────────────────────────────────────────────────────────


def test_visible_stats_cap_at_99():
    assert dealt(fight(make_unit("A", atk=95, great_talent={"atk": 10}))) == 79


def test_a_buff_past_the_cap_is_useless_and_lull_finds_nothing_to_remove():
    attacker = make_unit("A", atk=95, great_talent={"atk": 10})
    attacker.visible_buffs = StatBlock(atk=6)
    foe = make_unit("D", hp=100, atk=25)
    foe.active_statuses.append(lull())

    assert dealt(fight(attacker)) == 79
    assert dealt(CombatEngine(attacker, foe).simulate()) == 79


def test_lull_removes_only_the_part_of_a_buff_in_use():
    """96 + 6 shows as 99, so only 3 of the buff is in use; Lull drops to 96."""
    attacker = make_unit("A", atk=96)
    attacker.visible_buffs = StatBlock(atk=6)
    foe = make_unit("D", hp=100, atk=25)
    foe.active_statuses.append(lull())

    assert dealt(fight(attacker)) == 79
    assert dealt(CombatEngine(attacker, foe).simulate()) == 76


def test_lull_removes_a_whole_buff_that_is_fully_in_use():
    attacker = make_unit("A", atk=90)
    attacker.visible_buffs = StatBlock(atk=6)
    foe = make_unit("D", hp=100, atk=25)
    foe.active_statuses.append(lull())

    assert dealt(fight(attacker)) == 76
    assert dealt(CombatEngine(attacker, foe).simulate()) == 70


def test_debuff_and_buff_past_the_cap_still_show_99():
    """99 + 6 - 5 is not 94: the cap sits on the final sum."""
    attacker = make_unit("A", atk=99)
    attacker.visible_buffs = StatBlock(atk=6)
    attacker.visible_debuffs = StatBlock(atk=5)

    assert dealt(fight(attacker)) == 79


def test_neutralize_penalties_gives_nothing_when_the_debuff_did_nothing():
    attacker = make_unit("A", atk=99)
    attacker.visible_buffs = StatBlock(atk=6)
    attacker.visible_debuffs = StatBlock(atk=5)
    attacker.active_statuses.append(neutralize_penalties())

    assert dealt(fight(attacker)) == 79


def test_neutralize_penalties_restores_only_the_part_of_a_debuff_in_use():
    """97 + 6 - 5 shows 98, so the debuff only cost 1; neutralizing it gives
    back 1, not 5."""
    attacker = make_unit("A", atk=97)
    attacker.visible_buffs = StatBlock(atk=6)
    attacker.visible_debuffs = StatBlock(atk=5)

    assert dealt(fight(attacker)) == 78
    attacker.active_statuses.append(neutralize_penalties())
    assert dealt(fight(attacker)) == 79


def test_neutralize_penalties_restores_a_debuff_that_was_fully_in_use():
    attacker = make_unit("A", atk=90)
    attacker.visible_debuffs = StatBlock(atk=5)

    assert dealt(fight(attacker)) == 65
    attacker.active_statuses.append(neutralize_penalties())
    assert dealt(fight(attacker)) == 70


# ── validation ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("stats,message", [
    ({"hp": 2}, "must be among"),
    ({"atk": -2}, "must be >= 0"),
])
def test_great_talent_grants_are_validated_at_load(stats, message):
    desc = {"effect": "GRANT_GREAT_TALENT", "target": "self",
            "params": {"stats": stats, "max": 20}, "conditions": []}
    with pytest.raises(ValueError, match=message):
        build_effect(desc, applied_by="self")
