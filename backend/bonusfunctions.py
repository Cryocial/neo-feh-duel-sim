"""
Contains logic for specific skills and status effects.
These functions are resolved by name during the JSON bootup process.
"""

"""Omni Boost"""
def omni_boost(unit, enemy=None):
    omni_boost = 0
    if unit.change_of_fate:
        omni_boost += 5
    if unit.dark_emblem:
        omni_boost += 5
    if unit.divinely_inspiring:
        omni_boost += min(unit.ally_three_spaces * 3, 6)
    if unit.dosage:
        omni_boost += 5
    if unit.drain_cancel:
        omni_boost += 4
    if unit.empathy:
        total_effects = unit.bonus_count + unit.penalty_count
        if enemy is not None:
            total_effects += enemy.bonus_count + enemy.penalty_count
        omni_boost += min(total_effects, 7)
    if unit.future_witness:
        omni_boost += 5
    if unit.incited:
        omni_boost += min(unit.spaces_moved, 3)
    if unit.prof_guidance:
        omni_boost += 5
    if unit.radiant_hero:
        omni_boost += 5
    if unit.rally_spectrum:
        omni_boost += 5
    if unit.truly_incited:
        omni_boost += min(unit.spaces_moved * 2, 8)
    return [omni_boost, omni_boost, omni_boost, omni_boost]

"""Single Stat Boosts and Bonus Doublers (WIP)"""
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

"""Anathema and Omni Debuff"""
def anathema(unit, enemy=None):
    anathema = 0
    if unit.anathema:
        anathema += 4
    return [anathema, anathema, anathema]
def omni_debuff(unit, enemy=None):
    omni_debuff = 0
    if unit.fell_spirit
        if unit.engage or enemy.engage
            omni_debuff += 6
        else
            omni_bebuff += 4
    return [omni_debuff, omni_debuff, omni_debuff, omni_debuff]


"""Foe Penalty Douber and Draconic Hex (WIP)"""

"""True Damage"""

def true_damage(unit, enemy=None):
    true_damage = 0
    """Calculates true damage based on the unit's active bonus count."""
    if unit.change_of_fate
        true_damage += min(15, unit.bonus_count * 3)
    if unit.treachery
        buffs = unit.visible_buffs
        true_damage += max(0, buffs.atk) + max(0, buffs.spd) + max(0, buffs.defense) + max(0, buffs.res)
    if unit.dominance and enemy is not None:
        debuffs = enemy.visible_debuffs
        true_damage += max(0, debuffs.atk) + max(0, debuffs.spd) + max(0, debuffs.defense) + max(0, debuffs.res)
    return true_damage

def reflex_true_damage(unit, enemy=None):
    """Example of true damage that scales with mitigated damage."""
    boost = unit.damage_mitigated_bucket
    unit.damage_mitigated_bucket = 0 
    return boost

"""True DR"""
def bonus_true_dr(unit, enemy=None):
    true_dr = 0
    if unit.fire_emblem:
        true_dr += 10
    if unit.future_witness:
        true_dr += 7
    if unit.radiant_hero:
        true_dr += 10
    if unit.reflex:
        true_dr += 7
    return true_dr

def all_bonus_true_dr (unit, enemy=None):
    all_true_dr = 0
    if unit.divine_nectar:
        all true_dr += 10
    return all_true_dr

"""Special Jumps"""
def special_jump(unit, target_enemy=None):
    special_jump = 0
    if unit.rally_spectrum
        if unit.slaying or unit.slaying2 or unit.brave
            special_jump += 1
        else:
            special_jump += 2
    """Grants cooldown reduction based on enemy penalty count."""
    if unit.creation_pulse
        special_jump = min(2, target_enemy.penalty_count) if target_enemy else 0
    return special_jump

"""Potent"""
def potent_40_or_80(unit, enemy=None):
    """Calculates potent effectiveness based on speed comparison."""
    if unit.get_combat_stat("spd", enemy) > enemy.get_combat_stat("spd", unit):
        return 0.40
    return 0.80

def potent_defense_scaling(unit, enemy=None):
    """Calculates potent effectiveness based on defense difference."""
    if enemy is None: return 0.0
    def_diff = unit.get_combat_stat("defense", enemy) - enemy.get_combat_stat("defense", unit)
    return min(max(0, def_diff) * 0.10, 0.50)

""" Legacy Code"""
