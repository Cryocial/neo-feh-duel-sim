"""
Contains logic for specific skills and status effects.
These functions are resolved by name during the JSON bootup process.
"""

def reflex_true_dr(unit, enemy=None):
    """Example of a flat damage reduction skill."""
    return 7

def reflex_true_damage(unit, enemy=None):
    """Example of true damage that scales with mitigated damage."""
    boost = unit.damage_mitigated_bucket
    unit.damage_mitigated_bucket = 0 
    return boost

def potent_flat_40(unit, enemy=None):
    """Calculates potent effectiveness based on speed comparison."""
    if unit.get_combat_stat("spd", enemy) > enemy.get_combat_stat("spd", unit):
        return 0.40
    return 0.80

def potent_defense_scaling(unit, enemy=None):
    """Calculates potent effectiveness based on defense difference."""
    if enemy is None: return 0.0
    def_diff = unit.get_combat_stat("defense", enemy) - enemy.get_combat_stat("defense", unit)
    return min(max(0, def_diff) * 0.10, 0.50)

def creation_pulse(unit, target_enemy=None):
    """Grants cooldown reduction based on enemy penalty count."""
    return min(2, target_enemy.penalty_count) if target_enemy else 0

def change_of_fate_true_damage(unit, target_enemy=None):
    """Calculates true damage based on the unit's active bonus count."""
    return min(15, unit.bonus_count * 3)

def bonus_doubler(unit, target_enemy=None, effective_buffs=None):
    """
    Calculates the Bonus Doubler effect.
    Returns a dictionary of stat increases.
    """
    if effective_buffs is None:
        # Fallback if no specific effective buffs are provided
        effective_buffs = {
            "atk": unit.visible_buffs.atk,
            "spd": unit.visible_buffs.spd,
            "defense": unit.visible_buffs.defense,
            "res": unit.visible_buffs.res
        }
    return {stat: effective_buffs.get(stat, 0) for stat in ["atk", "spd", "defense", "res"]}
