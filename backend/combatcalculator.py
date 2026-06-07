import math

def check_color_advantage(attacker, defender):
    """Returns 1 for Advantage, -1 for Disadvantage, 0 for Neutral."""
    
    # 1. Check for Raven Tomes first
    if attacker.has_keyword("raven_tome") and defender.color == "Colorless":
        return 1
    if defender.has_keyword("raven_tome") and attacker.color == "Colorless":
        return -1

    # 2. Standard Weapon Triangle
    advantage_map = {"Red": "Green", "Green": "Blue", "Blue": "Red"}
    
    if advantage_map.get(attacker.color) == defender.color:
        return 1
    elif advantage_map.get(defender.color) == attacker.color:
        return -1
        
    return 0


def get_wta_multiplier(attacker, defender):
    """Calculates the Weapon Triangle multiplier for the attacker's damage."""
    base_multiplier = 1.0
    advantage_state = check_color_advantage(attacker, defender) 
    
    if advantage_state == 0:
        return base_multiplier
        
    base_multiplier += (0.20 * advantage_state)
    
    # Check for Triangle Adept / Cancel Affinity
    has_ta = attacker.has_keyword("triangle_adept") or defender.has_keyword("triangle_adept")
    has_ca = attacker.has_keyword("cancel_affinity") or defender.has_keyword("cancel_affinity")
    
    # Apply TA if CA isn't shutting it down
    if has_ta and not has_ca:
        base_multiplier += (0.20 * advantage_state)
        
    return base_multiplier


def calculate_effective_buffs(unit, enemy):
    """Calculates visible buffs after enemy Lulls are applied."""
    effective_buffs = {"atk": 0, "spd": 0, "defense": 0, "res": 0}
    
    for stat in ["atk", "spd", "defense", "res"]:
        # Assumes Lull keywords look like "lull_atk", "lull_spd", etc.
        lull_keyword = f"lull_{stat}"
        if enemy.has_keyword(lull_keyword):
            effective_buffs[stat] = 0
        else:
            effective_buffs[stat] = getattr(unit.visible_buffs, stat, 0)
            
    return effective_buffs


def process_single_strike(striker, target):
    """Handles a single swing of a weapon, including mid-combat pulses and damage."""
    
    # 1. "Before Every Attack" Phase
    striker.current_cooldown -= striker.get_pulse_amount("before_every_attack", target)
    
    # 2. Calculate final stats (assuming get_combat_atk uses effective_buffs)
    raw_atk = striker.get_combat_atk(target) 
    defensive_stat = target.get_combat_res(striker) if magic_weapon else target.get_combat_def(striker)
    wta_multiplier = get_wta_multiplier(striker, target)
    
    # FEH applies the WTA multiplier to Atk and truncates the decimal BEFORE subtracting Def/Res
    modified_atk = math.trunc(raw_atk * wta_multiplier)
    
    # Determine if we target Def or Res
    magic_weapons = ["Tome", "Staff", "Dragon", "Beast"]
    defensive_stat = target.get_combat_res(striker) if magic_weapon else target.get_combat_def(striker)
        
    # 3. Base Damage (Cannot go below 0)
    base_damage = max(0, modified_atk - defensive_stat)
    
    # 4. True Damage
    true_damage = 0
    if striker.utilities.truedmg_logic is not None:
        true_damage += striker.utilities.truedmg_logic(striker, target)
        
    # 5. Final Damage Calculation & Application
    final_damage = base_damage + true_damage
    target.base_stats.hp -= final_damage
    
    # 6. The "Swing" Charge
    swing_charge = 1 + striker.get_pulse_amount("per_unit_attack", target) + target.get_pulse_amount("per_foe_attack", striker)
    striker.current_cooldown -= max(0, swing_charge)


def simulate_combat(attacker, defender):
    """The Master Timeline. Dictates the order of operations for the entire fight."""
    
    # --- PHASE 1: Start of Combat ---
    attacker.current_cooldown -= attacker.get_pulse_amount("start_of_combat", defender)
    defender.current_cooldown -= defender.get_pulse_amount("start_of_combat", attacker)
    
    # --- PHASE 2: Before First Attack (Defensive Specials) ---
    defender.current_cooldown -= defender.get_pulse_amount("before_first_attack", attacker)
    
    # --- PHASE 3: The Clash ---
    if attacker.base_stats.hp > 0:
        process_single_strike(attacker, defender)
        
    # Standard counterattack check (You will add range/sweep checks here later)
    if defender.base_stats.hp > 0: 
        process_single_strike(defender, attacker)
        
    # --- PHASE 4: After Combat ---
    attacker.current_cooldown -= attacker.get_pulse_amount("after_combat", defender)
    defender.current_cooldown -= defender.get_pulse_amount("after_combat", attacker)

    return {
        "attacker_final_hp": attacker.base_stats.hp,
        "defender_final_hp": defender.base_stats.hp
    }