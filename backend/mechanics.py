# --- FORMULAS FOR UNIT STATS ---
def _get_equipped_items(self):
        ```Returns a list of all currently equipped items (weapon, special, A/B/C/S/X slots).```
        all_slots = [
            self.weapon, self.special, self.a_slot, 
            self.b_slot, self.c_slot, self.s_slot, self.x_slot
        ]
        return [item for item in all_slots if item is not None]

        def get_potent_percentage(self, target_enemy=None):
        ```Calculates the total potent percentage \for this unit.```

        for item in self._get_equipped_items():
            if item.potent_logic is not None:
                return item.potent_logic(self, target_enemy)
                
        return 0.0
        def _apply_dragonflowers(self):
        ```Calculates the stat increases from dragonflowers and applies them to the base stats.```
        if self.dragonflower <= 0:
            return

        # list of dictionaries mapping the stats and their tie-breaker priority
        stat_list = [
            {"name": "hp", "value": self.base_hp, "tie_breaker": 1},
            {"name": "atk", "value": self.base_atk, "tie_breaker": 2},
            {"name": "spd", "value": self.base_spd, "tie_breaker": 3},
            {"name": "def", "value": self.base_def, "tie_breaker": 4},
            {"name": "res", "value": self.base_res, "tie_breaker": 5}
        ]

        # If 'value' is a tie, it falls back to 'tie_breaker' ascending (1 beats 2).
        stat_list.sort(key=lambda x: (-x["value"], x["tie_breaker"]))

        for i in range(self.dragonflower):
            stat_to_boost = stat_list[i % 5]["name"]
            if stat_to_boost == "hp":
                self.base_hp += 1
            elif stat_to_boost == "atk":
                self.base_atk += 1
            elif stat_to_boost == "spd":
                self.base_spd += 1
            elif stat_to_boost == "def":
                self.base_def += 1
            elif stat_to_boost == "res":
                self.base_res += 1


def _apply_merges(self):
        if self.merges <= 0:
            return

        # if above 1 merge remove the bane
        if self.merges > 1 and self.bane:
            recovery_amount = 4 if self.bane in self.superbane else 3
            
            if self.bane == "hp": self.base_hp += recovery_amount
            elif self.bane == "atk": self.base_atk += recovery_amount
            elif self.bane == "spd": self.base_spd += recovery_amount
            elif self.bane == "def": self.base_def += recovery_amount
            elif self.bane == "res": self.base_res += recovery_amount
            self.bane = None 

        # --- PART 2: Sorting for Distribution ---
        
        # Create the exact same tie-breaker list used for Dragonflowers
       

        # The unit is Neutral. First merge gives +1 to the top 3 stats.
        

        # --- The Standard Merge Loop ---
        


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