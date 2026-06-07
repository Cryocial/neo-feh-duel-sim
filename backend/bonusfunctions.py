# --- ONLY USED FOR IMPLEMENTING THE LOGIC OF A CERTAIN BONUS EFFECT, NOT FOR ANYTHING ELSE ---
from .jsonbootupstuff import STATUS_EFFECT_DATABASE, LOGIC_REGISTRY

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

def get_pulse_amount(self, phase_name):
    """Scans all equipped items and statuses for a pulse during a specific phase."""
    total_pulse = 0
    
    # 1. Scan equipped skills
    for item in self._get_equipped_items():
        # dict.get() safely returns 0 if the phase_name isn't in the dictionary!
        # VALID PHASES: "start_of_turn", "before_first_attack", "before_every_attack", "before_follow_up", "end_of_combat", "before_foe_attacks", "per_unit_attack", "per_foe_attack    "
        modifier = item.utilities.cooldown_modifiers.get(phase_name, 0)
        
        if callable(modifier):
            total_pulse += modifier(self, target_enemy)
        else:
            total_pulse += modifier

    # 2. Scan active map statuses
    for status_name in self.active_statuses:
        if status_name in STATUS_EFFECT_DATABASE:
            status_utility = STATUS_EFFECT_DATABASE[status_name].get("utilities")
            if status_utility:
                
                # Grab the modifier from the map status
                modifier = status_utility.cooldown_modifiers.get(phase_name, 0)
                
                if callable(modifier):
                    total_pulse += modifier(self, target_enemy)
                else:
                    total_pulse += modifier
                
    return total_pulse

def change_of_fate_true_damage(unit, target_enemy=None):
    """Calculates true damage: 3 x number of active map bonuses (max 15)"""
    bonus_count = 0
    
    for status in unit.active_statuses:
        status_info = STATUS_EFFECT_DATABASE.get(status, {})
        if status_info.get("type") == "bonus":
            bonus_count += 1
    total_damage = bonus_count * 3
    return min(15, total_damage)


#map the location of where the logic functions are in the codebase, so we can call them by string reference from the JSON
# left side = location of the funtion in the visualbonuses.json, right side = the function that is located in this file.
LOGIC_REGISTRY = {
    "reflex_logic": {
        "truedr_logic": reflex_true_dr,
        "truedmg_logic": reflex_true_damage
    },
    "bd_logic": {
        # to
    },
    "potent_logic": {
        "potent_logic": potent_defense_scaling
    },
    "changeoffate_logic": {
        "truedmg_logic": change_of_fate_true_damage
    }
}