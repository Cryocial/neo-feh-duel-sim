
# --- FORMULAS FOR CALCING POTENT ---
def potent_flat_40(attacker, defender=None):
    return 0.40  # It's always 40%, enemy or not


def potent_defense_scaling(attacker, defender=None):
    if defender is None:
        return 0.0  # Or whatever default makes sense for your UI

    def_difference = attacker.get_total_def() - defender.get_total_def()
    
    if def_difference <= 0:
        return 0.0
        
    return min(def_difference * 0.10, 0.50)


# --- FORMULAS FOR CALCING POTENT ---
#todo add the actual stuff here