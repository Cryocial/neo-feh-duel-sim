"""
Contains logic for specific skills and status effects.
These functions are resolved by name during the JSON bootup process.
"""

import math
from .constants import StrikeType


def single_boost(unit, enemy=None):
    """Aggregates all dynamic single-stat boosts."""
    single_boosts = {stat: 0 for stat in ["atk", "spd", "defense", "res"]}
    if unit.has_keyword("atk_liberate"):
        single_boosts["atk"] += min(8, unit.bonus_count + 4)
    if unit.has_keyword("spd_liberate"):
        single_boosts["spd"] += min(8, unit.bonus_count + 4)
    if unit.has_keyword("def_liberate"):
        single_boosts["defense"] += min(8, unit.bonus_count + 4)
    if unit.has_keyword("res_liberate"):
        single_boosts["res"] += min(8, unit.bonus_count + 4)
    if unit.has_keyword("paranoia") and unit.current_hp < unit.base_stats.hp:
        single_boosts["atk"] += 5
    return {stat: single_boosts[stat] for stat in ["atk", "spd", "defense", "res"]}


def omni_boost(unit, enemy=None):
    """Aggregates all dynamic omni-stat boosts."""
    boost = 0
    if unit.has_keyword("divinely_inspiring"):
        boost += min(unit.ally_three_spaces * 3, 6)
    if unit.has_keyword("empathy"):
        total_effects = unit.bonus_count + unit.penalty_count
        if enemy is not None:
            total_effects += enemy.bonus_count + enemy.penalty_count
        boost += min(total_effects, 7)
    if unit.has_keyword("incited"):
        boost += min(unit.spaces_moved, 3)
    if unit.has_keyword("truly_incited"):
        boost += min(unit.spaces_moved * 2, 8)

    return {stat: boost for stat in ["atk", "spd", "defense", "res"]}


def omni_debuff(unit, enemy=None):
    """Aggregates all dynamic omni-stat debuffs."""
    debuff = 0
    if unit.has_keyword("fell_spirit") and enemy is not None:
        if unit.is_engaged or enemy.is_engaged:
            debuff -= 6
        else:
            debuff -= 4
    return {stat: debuff for stat in ["atk", "spd", "defense", "res"]}


def bonus_doubler(unit, target_enemy=None):
    """Calculates the Bonus Doubler effect."""
    return {
        stat: getattr(unit.visible_buffs, stat, 0)
        for stat in ["atk", "spd", "defense", "res"]
    }


def true_damage(unit, target_enemy=None):
    """Aggregates all dynamic true damage."""
    total = 0

    if unit.has_keyword("change_of_fate"):
        total += min(15, unit.bonus_count * 3)

    if unit.has_keyword("treachery"):
        buffs = unit.visible_buffs
        total += (
            max(0, buffs.atk)
            + max(0, buffs.spd)
            + max(0, buffs.defense)
            + max(0, buffs.res)
        )

    if unit.has_keyword("dominance") and target_enemy is not None:
        debuffs = target_enemy.visible_debuffs
        total += (
            max(0, debuffs.atk)
            + max(0, debuffs.spd)
            + max(0, debuffs.defense)
            + max(0, debuffs.res)
        )

    if unit.has_keyword("reflex"):
        total += unit.damage_mitigated_bucket
        unit.damage_mitigated_bucket = 0

    return total


def true_dr(unit, target_enemy=None):
    """Aggregates conditional True Damage Reduction."""
    dr = 0
    if unit.has_keyword("divine_nectar") and getattr(
        unit, "first_combat_of_turn", False
    ):
        dr += 10
    return dr


def percent_dr(unit, target_enemy=None):
    """Aggregates conditional  Damage Reduction."""
    dr = 0.0
    if unit.has_keyword("dodge") and target_enemy is not None:
        unit_spd = unit.get_combat_stat("spd", target_enemy)
        enemy_spd = target_enemy.get_combat_stat("spd", unit)
        spd_diff = unit_spd - enemy_spd
        if spd_diff > 0:
            max_dodge = min(10, spd_diff)
            dr += (max_dodge * 4) / 100
    return dr


def hexblade_logic(unit, target_enemy=None):
    """Hexblade status: Targets the lower of foe's Def/Res."""
    if target_enemy is None:
        return None

    # combat_stats is set in combatcalculator before this would be called
    if target_enemy.combat_stats.defense < target_enemy.combat_stats.res:
        return "def"
    return "res"


def set_to_one(unit, target_enemy, strike):
    """Set Incoming Damage = 1"""
    # NOTE FOR FUTURE, THIS FUNCTION CAN BE CHANGED TO SET TO ANY FLAT NUMBER THATS NOT 1, IF NEEDED
    is_first_sequence = strike.strike_type is StrikeType.FIRST

    if unit.has_keyword("collapsed_star") and is_first_sequence:
        return 1
    return None


def heal_start_of_combat(unit, target_enemy=None):
    """Triggers after pre-combat damage/AoE, before swing 0."""
    heal = 0

    if unit.has_keyword("divine_nectar"):
        heal += 20
    # bol/imbue goes here
    if unit.has_keyword("imbue"):
        heal += math.trunc(0.4 * unit.base_stats.hp)
    if unit.has_keyword("bol4") and target_enemy is not None:
        unit_def = unit.get_combat_stat("defense", target_enemy)
        enemy_def = target_enemy.get_combat_stat("defense", unit)
        if unit_def >= (enemy_def - 5):
            heal += math.trunc(0.4 * unit.base_stats.hp)
        else:
            heal += math.trunc(0.2 * unit.base_stats.hp)
    return heal


def heal_on_hit(unit, target_enemy=None):
    """Triggers strictly after a unit lands a weapon swing."""
    heal = 0
    if unit.has_keyword("profs_guidance"):
        heal += 7
    return heal


def pre_combat_damage(unit, target_enemy=None):
    """Aggregates all pre-combat damage dealt TO the enemy."""
    dmg = 0
    # placeholder
    return dmg


def special_jump(unit, target_enemy=None):
    """Aggregates all special cooldown jumps."""
    jump = 0

    if unit.has_keyword("rally_spectrum"):
        if unit.has_keyword("slaying") or unit.has_keyword("brave_weapon"):
            jump += 1
        else:
            jump += 2

    if unit.has_keyword("creation_pulse") and target_enemy is not None:
        jump += min(2, target_enemy.penalty_count)

    return jump


def pre_hit_special_charge(unit, enemy=None):
    """Aggregates all special charge gains before the unit is hit."""
    charge = 0

    if unit.has_keyword("divinely_inspiring"):
        count = 67676767676767  # wait for RZL's function for ally checks
        if count >= 2:
            charge += 2
        elif count >= 1:
            charge += 1

    return charge

def potent_follow(unit, target_enemy=None):
    """Returns the % potent if any (not sure what condition for follow up is and what to do for rift effects)."""
    potent = 0
    unit_spd = unit.get_combat_stat("spd", target_enemy)
    enemy_spd = target_enemy.get_combat_stat("spd", unit)
    spd_diff = unit_spd - enemy_spd

    """Diff 30"""
    if spd_diff + 25 >= 0:
        if unit.has_keyword("decisive"):
            if not unit.has_keyword("brave") and not unit.has_keyword("follow_up"):
                potent = 100
            else:
                if potent < 50:
                    potent = 50

    """Diff 25"""
    if spd_diff + 20 >= 0:
        if unit.has_keyword("potent_follow"):
            if not unit.has_keyword("brave") and not unit.has_keyword("follow_up"):
                if potent < 70:
                    potent = 70
            else:
                if potent < 30:
                    potent = 30
        if unit.has_keyword("potent_4") or unit.has_keyword("axe_of_dusk") or unit.has_keyword("potent_assault"):
            if not unit.has_keyword("brave") and not unit.has_keyword("follow_up"):
                if potent < 80:
                    potent = 80
            else:
                if potent < 40:
                    potent = 40
        if unit.has_keyword("ilian_greatlance"):
            if not unit.has_keyword("brave") and not unit.has_keyword("follow_up"):
                potent = 100
            else:
                if potent < 50:
                    potent = 50

    """Diff 10"""
    if spd_diff + 5 >= 0:
        if unit.has_keyword("ice_falchion") or unit.has_keyword("ilian_longsword"):
            potent = 100
    
    """Patience (Not sure what spd to use here)"""
    if unit.base_stats.spd >= 30:
        if not unit.has_keyword("brave") and not unit.has_keyword("follow_up"):
            potent = 100
        else:
            if potent < 50:
                potent = 50

    return potent