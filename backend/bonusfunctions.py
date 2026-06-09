"""
Contains logic for specific skills and status effects.
These functions are resolved by name during the JSON bootup process.
"""


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
    if unit.has_keyword("divine_nectar") and getattr(unit, "first_combat_of_turn", True):
        dr += 10

def heal_start_of_combat(unit, enemy=None):
    """Triggers after pre-combat damage/AoE, before swing 0."""
    heal = 0
    
    if unit.has_keyword("divine_nectar"):
        heal += 20
    # bol/imbue goes here    
    return heal

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
