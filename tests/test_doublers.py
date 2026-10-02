"""
The doubler family: in-combat stat changes equal to raw visible bonuses or
penalties, each stat calculated independently.

    BONUS_DOUBLER     + unit's own bonus         [Bonus Doubler] status = Bonus Doubler 3
    FRINGE_BONUS      + max(own, allies' highest) [Fringe Bonus] status = Bonus Doubler 4
    PENALTY_DOUBLER   - unit's own penalty       [Foe Penalty Doubler] status
    SABOTAGE          - max(own, allies' highest) [Sabotage] status

"Raw" is the point: the visible stat caps at 99, so a +6 buff on a 99-Atk unit
shows nothing, but the doubler still reads the 6 and adds it to the uncapped
combat stat. Allies aren't simulated; the user enters the highest bonus /
penalty per stat among allies within 2 spaces on the Unit, read only while
allies_within_2_spaces > 0. Every source stacks. The bonus side is inert under
the foe's Lull, the penalty side under the unit's own Neutralize Penalties.

Setup: one strike each. The attacker (40 Atk unless stated) hits a 20 Def foe;
the foe (25 Atk unless stated) counters the 20 Def attacker.
"""

from backend.build import Unit, Skill, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import BONUS_DATABASE, PENALTY_DATABASE, SKILL_DATABASE


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


def flag(effect, target="self"):
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": target, "params": {}, "conditions": [],
    }])


def foe_skill(effect):
    """A skill on its holder whose effect lands on the foe."""
    return Skill(
        name=effect, slot="passive_b", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{"effect": effect, "target": "foe", "params": {}, "conditions": []}],
    )


def hone_atk(amount):
    return Skill(
        name="Hone", slot="passive_c", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{
            "effect": "GRANT_VISIBLE_BUFF", "target": "self",
            "params": {"stats": {"atk": amount}}, "conditions": [],
        }],
    )


def buffed_attacker(buff=6, *statuses):
    attacker = make_unit("A")
    attacker.visible_buffs = StatBlock(atk=buff)
    attacker.active_statuses.extend(statuses)
    return attacker


def with_allies(unit, bonuses=None, penalties=None, count=1):
    unit.allies_within_2_spaces = count
    unit.ally_bonuses_within_2_spaces = StatBlock(**(bonuses or {}))
    unit.ally_penalties_within_2_spaces = StatBlock(**(penalties or {}))
    return unit


def fight(attacker, defender=None):
    return CombatEngine(attacker, defender or make_unit("D", hp=100, atk=25)).simulate()


def dealt(result):
    return 100 - result["defender_final_hp"]


# ── Bonus Doubler ────────────────────────────────────────────────────────────


def test_bonus_doubler_adds_the_raw_buff_in_combat():
    """+6 visible, and another +6 in combat: 40 -> 46 -> 52."""
    assert dealt(fight(buffed_attacker(6, flag("BONUS_DOUBLER")))) == 32


def test_bonus_doubler_still_reads_a_buff_the_cap_wasted():
    """99 + 6 shows 99, but the doubler reads the 6: combat Atk 105."""
    attacker = make_unit("A", atk=99)
    attacker.visible_buffs = StatBlock(atk=6)
    attacker.active_statuses.append(flag("BONUS_DOUBLER"))

    assert dealt(fight(attacker)) == 85


def test_bonus_doubler_is_inert_when_the_foes_lull_neutralizes_bonuses():
    foe = make_unit("D", hp=100, atk=25)
    foe.active_statuses.append(flag("BONUS_NEUT"))

    assert dealt(fight(buffed_attacker(6, flag("BONUS_DOUBLER")), foe)) == 20


def test_bonus_doubler_reads_the_highest_of_own_and_granted_buff():
    """Own +4 and a Hone +6 resolve to 6, not 10: 40 + 6 + 6."""
    attacker = buffed_attacker(4, flag("BONUS_DOUBLER"))
    attacker.c_slot = hone_atk(6)

    assert dealt(fight(attacker)) == 32


def test_bonus_doubler_sources_stack():
    assert dealt(fight(buffed_attacker(6, flag("BONUS_DOUBLER"), flag("BONUS_DOUBLER")))) == 38


# ── Fringe Bonus ─────────────────────────────────────────────────────────────


def test_fringe_bonus_takes_the_higher_of_own_and_allies_bonus():
    """Own +4, an ally within 2 spaces has +6: X = 6."""
    attacker = with_allies(buffed_attacker(4, flag("FRINGE_BONUS")), bonuses={"atk": 6})

    assert dealt(fight(attacker)) == 24 + 6


def test_fringe_bonus_falls_back_to_the_units_own_bonus():
    attacker = with_allies(buffed_attacker(6, flag("FRINGE_BONUS")), bonuses={"atk": 2})

    assert dealt(fight(attacker)) == 26 + 6


def test_fringe_bonus_ignores_the_ally_block_when_no_ally_is_within_2_spaces():
    attacker = with_allies(buffed_attacker(4, flag("FRINGE_BONUS")), bonuses={"atk": 6}, count=0)

    assert dealt(fight(attacker)) == 24 + 4


def test_fringe_bonus_is_inert_under_the_foes_lull():
    attacker = with_allies(buffed_attacker(4, flag("FRINGE_BONUS")), bonuses={"atk": 6})
    foe = make_unit("D", hp=100, atk=25)
    foe.active_statuses.append(flag("BONUS_NEUT"))

    assert dealt(fight(attacker, foe)) == 20


def test_fringe_bonus_stacks_with_bonus_doubler():
    """[Bonus Doubler] status plus Bonus Doubler 4: +6 and +6 on top of the +6."""
    attacker = with_allies(
        buffed_attacker(6, flag("BONUS_DOUBLER"), flag("FRINGE_BONUS")), bonuses={"atk": 6}
    )

    assert dealt(fight(attacker)) == 26 + 12


# ── Foe Penalty Doubler ──────────────────────────────────────────────────────


def debuffed_defender(atk=35, debuff=5):
    foe = make_unit("D", hp=100, atk=atk)
    foe.visible_debuffs = StatBlock(atk=debuff)
    return foe


def test_penalty_doubler_inflicts_the_raw_debuff():
    """Foe at 35 - 5 visible counters for 10; doubled, 25 counters for 5."""
    attacker = make_unit("A")
    attacker.b_slot = foe_skill("PENALTY_DOUBLER")

    assert fight(make_unit("A"), debuffed_defender())["attacker_final_hp"] == 40
    assert fight(attacker, debuffed_defender())["attacker_final_hp"] == 45


def test_penalty_doubler_is_inert_against_neutralize_penalties():
    """Neutralize Penalties lifts the -5 and leaves the doubler nothing to
    read: the foe counters at its full 35."""
    attacker = make_unit("A")
    attacker.b_slot = foe_skill("PENALTY_DOUBLER")
    foe = debuffed_defender()
    foe.active_statuses.append(flag("PENALTY_NEUT"))

    assert fight(attacker, foe)["attacker_final_hp"] == 35


def test_penalty_doubler_still_reads_a_debuff_the_cap_hid():
    """Foe at 99 with +6/-5 shows 99 and the debuff cost it nothing, but the
    doubler still reads the 5: combat Atk 94."""
    attacker = make_unit("A", hp=100)
    attacker.b_slot = foe_skill("PENALTY_DOUBLER")
    foe = make_unit("D", hp=100, atk=99)
    foe.visible_buffs = StatBlock(atk=6)
    foe.visible_debuffs = StatBlock(atk=5)

    assert fight(make_unit("A", hp=100), foe)["attacker_final_hp"] == 100 - 79
    assert fight(attacker, foe)["attacker_final_hp"] == 100 - 74


def test_penalty_doubler_sources_stack():
    attacker = make_unit("A")
    attacker.b_slot = foe_skill("PENALTY_DOUBLER")
    foe = debuffed_defender()
    foe.active_statuses.append(Status(name="FPD", type="penalty", effects=[{
        "effect": "PENALTY_DOUBLER", "target": "self", "params": {}, "conditions": [],
    }]))

    assert fight(attacker, foe)["attacker_final_hp"] == 50      # 35 - 5 - 5 - 5 = 20 -> 0


# ── Sabotage ─────────────────────────────────────────────────────────────────


def test_sabotage_takes_the_higher_of_own_and_allies_penalty():
    """Foe at 35 with -3 of its own; its ally within 2 has -5: X = 5."""
    foe = with_allies(debuffed_defender(debuff=3), penalties={"atk": 5})
    foe.active_statuses.append(Status(name="Sabotage", type="penalty", effects=[{
        "effect": "SABOTAGE", "target": "self", "params": {}, "conditions": [],
    }]))

    assert fight(make_unit("A"), foe)["attacker_final_hp"] == 50 - (35 - 3 - 5 - 20)


def test_sabotage_ignores_the_ally_block_when_no_ally_is_within_2_spaces():
    foe = with_allies(debuffed_defender(debuff=3), penalties={"atk": 5}, count=0)
    foe.active_statuses.append(Status(name="Sabotage", type="penalty", effects=[{
        "effect": "SABOTAGE", "target": "self", "params": {}, "conditions": [],
    }]))

    assert fight(make_unit("A"), foe)["attacker_final_hp"] == 50 - (35 - 3 - 3 - 20)


def test_sabotage_is_inert_against_neutralize_penalties():
    foe = with_allies(debuffed_defender(debuff=3), penalties={"atk": 5})
    foe.active_statuses.append(Status(name="Sabotage", type="penalty", effects=[{
        "effect": "SABOTAGE", "target": "self", "params": {}, "conditions": [],
    }]))
    foe.active_statuses.append(flag("PENALTY_NEUT"))

    assert fight(make_unit("A"), foe)["attacker_final_hp"] == 50 - (35 - 20)


# ── the JSON entries ─────────────────────────────────────────────────────────


def test_json_statuses_and_skills_are_wired_to_these_effects():
    attacker = buffed_attacker(6, BONUS_DATABASE["Bonus Doubler"])
    assert dealt(fight(attacker)) == 32

    attacker = with_allies(buffed_attacker(4, BONUS_DATABASE["Fringe Bonus"]), bonuses={"atk": 6})
    assert dealt(fight(attacker)) == 30

    attacker = buffed_attacker(6)
    attacker.a_slot = SKILL_DATABASE["Bonus Doubler 3"]
    assert dealt(fight(attacker)) == 32

    attacker = with_allies(buffed_attacker(4), bonuses={"atk": 6})
    attacker.a_slot = SKILL_DATABASE["Bonus Doubler 4"]
    assert dealt(fight(attacker)) == 30

    foe = debuffed_defender()
    foe.active_statuses.append(PENALTY_DATABASE["Foe Penalty Doubler"])
    assert fight(make_unit("A"), foe)["attacker_final_hp"] == 45

    foe = with_allies(debuffed_defender(debuff=3), penalties={"atk": 5})
    foe.active_statuses.append(PENALTY_DATABASE["Sabotage"])
    assert fight(make_unit("A"), foe)["attacker_final_hp"] == 43
