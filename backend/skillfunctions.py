# --- FORMULAS FOR CALCING SKILLS HERE ---
def potent_flat_40(unit, enemy=None):
    """Calculates the potent effectiveness as a flat 40% if the attacker's speed stat is higher than the defender's."""
    if unit.get_combat_spd() > enemy.get_combat_spd():
        return 0.40
    return 0.80


def potent_defense_scaling(unit, enemy=None):
    """Calculates the potent effectiveness."""
    if enemy is None:
        return 0.0  # Or whatever default makes sense for your UI

    def_difference = unit.get_combat_def() - enemy.get_combat_def()
    
    if def_difference <= 0:
        return 0.0
        
    return min(def_difference * 0.10, 0.50)

