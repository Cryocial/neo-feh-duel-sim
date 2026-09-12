"""
Conditions with no other home: each gates a +6 Atk STAT_BOOST on the attacker
so the outcome reads as 26 dealt (held) or 20 (didn't).

  first_combat_of_turn   Unit.first_combat_of_turn, target self|foe
  foe_weapon_type        foe's weapon type is in `types`
  bonus_penalty_total    unit's bonus + penalty count (+ the foe's with
                         include_foe) reaches min_count
  hp_above_pct           start-of-combat HP% >= threshold
  cbt_stat_sum_check     sum of the unit's listed combat stats vs the foe's
  triggers_brave         the target makes a Brave double strike

Setup: one strike each, 40 Atk vs 20 Def deals 20. Buffs used to drive counts
go on Def/Res so they don't move the damage or the follow-up check.
"""

from backend.build import Unit, Skill, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20,
              weapon_type=WeaponType.SWORD):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def gated(condition, params=None, effect="STAT_BOOST", effect_params=None):
    return Skill(
        name="Gated", slot="passive_a", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{
            "effect": effect, "target": "self",
            "params": effect_params or {"stats": ["atk"], "flat": 6},
            "conditions": [{"type": condition, "params": params or {}}],
        }],
    )


def dealt(attacker, defender=None):
    foe = defender or make_unit("D", hp=100)
    return 100 - CombatEngine(attacker, foe).simulate()["defender_final_hp"]


def test_first_combat_of_turn():
    attacker = make_unit("A")
    attacker.a_slot = gated("first_combat_of_turn")
    assert dealt(attacker) == 26

    attacker.first_combat_of_turn = False
    assert dealt(attacker) == 20


def test_first_combat_of_turn_can_read_the_foe():
    attacker = make_unit("A")
    attacker.a_slot = gated("first_combat_of_turn", {"target": "foe"})
    foe = make_unit("D", hp=100)
    foe.first_combat_of_turn = False

    assert dealt(attacker, foe) == 20


def test_foe_weapon_type():
    attacker = make_unit("A")
    attacker.a_slot = gated("foe_weapon_type", {"types": ["SWORD", "LANCE"]})
    assert dealt(attacker) == 26

    attacker.a_slot = gated("foe_weapon_type", {"types": ["BOW"]})
    assert dealt(attacker) == 20


def test_bonus_penalty_total_counts_the_unit_and_optionally_the_foe():
    attacker = make_unit("A")
    attacker.visible_buffs = StatBlock(defense=4, res=4)          # 2 bonuses
    foe = make_unit("D", hp=100)
    foe.visible_debuffs = StatBlock(res=3)                        # 1 penalty

    attacker.a_slot = gated("bonus_penalty_total", {"min_count": 2})
    assert dealt(attacker, foe) == 26

    attacker.a_slot = gated("bonus_penalty_total", {"min_count": 3})
    assert dealt(attacker, foe) == 20

    attacker.a_slot = gated("bonus_penalty_total", {"min_count": 3, "include_foe": True})
    assert dealt(attacker, foe) == 26


def test_hp_above_pct():
    attacker = make_unit("A")
    attacker.current_hp = 40                                      # 80%

    attacker.a_slot = gated("hp_above_pct", {"threshold": 80})
    assert dealt(attacker) == 26

    attacker.a_slot = gated("hp_above_pct", {"threshold": 81})
    assert dealt(attacker) == 20


def test_cbt_stat_sum_check():
    """Spd + Def: attacker 10 + 20 = 30 against the foe's 30. Gates an
    on-strike effect, since that list is read after the post_combat_stats
    pass that resolves this condition."""
    true_damage = {"flat": 6, "strike": "every_strike"}

    attacker = make_unit("A")
    attacker.a_slot = gated(
        "cbt_stat_sum_check", {"stats": ["spd", "defense"], "margin": 0},
        effect="FLAT_DAMAGE_STRIKE", effect_params=true_damage,
    )
    assert dealt(attacker) == 26

    attacker.a_slot = gated(
        "cbt_stat_sum_check", {"stats": ["spd", "defense"], "margin": 1},
        effect="FLAT_DAMAGE_STRIKE", effect_params=true_damage,
    )
    assert dealt(attacker) == 20


def test_triggers_brave():
    """+5 true damage on each hit, but only while the unit attacks twice."""
    brave = Status(name="Brave", type="bonus", effects=[{
        "effect": "BRAVE", "target": "self", "params": {}, "conditions": [],
    }])
    bonus_when_brave = gated(
        "triggers_brave", {"target": "self"},
        effect="FLAT_DAMAGE_STRIKE", effect_params={"flat": 5, "strike": "every_strike"},
    )

    attacker = make_unit("A")
    attacker.a_slot = bonus_when_brave
    assert dealt(attacker) == 20

    attacker.active_statuses.append(brave)
    assert dealt(attacker) == 25 + 25
