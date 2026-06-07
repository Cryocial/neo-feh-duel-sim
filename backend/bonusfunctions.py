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

#map the location of where the logic functions are in the codebase, so we can call them by string reference from the JSON
LOGIC_REGISTRY = {
    "reflective_logic": {
        "truedr_logic": reflective_true_dr,
        "truedmg_logic": reflective_true_damage
    },
    "bonus_doubler_logic": {
        # to
}
}