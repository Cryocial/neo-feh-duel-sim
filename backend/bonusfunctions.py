# --- ONLY USED FOR IMPLEMENTING THE LOGIC OF A CERTAIN BONUS EFFECT, NOT FOR ANYTHING ELSE ---
from .jsonbootupstuff import STATUS_EFFECT_DATABASE, LOGIC_REGISTRY

def has_keyword(self, target_keyword):
    """Scans equipment and active statuses to see if the unit has a specific keyword."""
    for item in self._get_equipped_items():
        if target_keyword in item.utilities.keywords:
            return True
    
    for status in self.active_statuses:
        if status in STATUS_EFFECT_DATABASE:
            status_utility = STATUS_EFFECT_DATABASE[status].get("utilities", {})
            
            if target_keyword in status_utility.get("keywords", []):
                return True
                
    return False
    
def reflex_true_dr(unit, enemy=None):
    return 7

def reflex_true_damage(unit, enemy=None):
    boost = unit.damage_mitigated_bucket
    unit.damage_mitigated_bucket = 0 
    return boost

# --- FORMULAS FOR CALCING SKILLS HERE ---
def potent_flat_40(unit, enemy=None):
    """Calculates the potent effectiveness as a flat 40% if the attacker's speed stat is higher than the defender's."""
    if unit.get_combat_spd() > enemy.get_combat_spd():
        return 0.40
    return 0.80


def potent_defense_scaling(unit, enemy=None):
    """Calculates the potent effectiveness."""
    if enemy is None:
        return 0.0

    def_difference = unit.get_combat_def() - enemy.get_combat_def()
    
    if def_difference <= 0:
        return 0.0
        
    return min(def_difference * 0.10, 0.50)


def creation_pulse(unit, target_enemy=None):
    """Grants pulse equal to the number of penalties on the enemy."""
    if target_enemy is None:
        return 0
    pulse = target_enemy.penalty_count
    return min(2, pulse)

def change_of_fate_true_damage(unit, target_enemy=None):
    """Calculates true damage: 3 x number of active map bonuses (max 15)"""
    total_damage = unit.bonus_count * 3
    return min(15, total_damage)

def bonus_doubler(unit, target_enemy=None, effective_buffs=None):
    """Calculates Bonus Doubler using the pre-calculated effective buffs."""
    
    bd_stats = {"atk": 0, "spd": 0, "defense": 0, "res": 0}
    
    # Safety fallback: If no effective buffs were passed, use the raw ones
    if effective_buffs is None:
        effective_buffs = unit.visible_buffs 
        
    for stat in ["atk", "spd", "defense", "res"]:
        bd_stats[stat] = effective_buffs.get(stat, 0)
        
    return bd_stats
    
#--- map the location of where the logic functions are in the codebase, so we can call them by string reference from the JSON--- 
# left side = location of the funtion in the visualbonuses.json, right side = the function that is located in this file.
LOGIC_REGISTRY = {
    "bd_logic": {
        "dynamic_stats_logic": bonus_doubler
    },
    "changeoffate_logic": {
        "truedmg_logic": change_of_fate_true_damage
    },
    "creation_pulse_logic": creation_pulse,

}