# --- FORMULAS FOR UNIT STATS ---
def _get_equipped_items(self):
        """Returns a list of all currently equipped items (weapon, special, A/B/C/S/X slots)."""
        all_slots = [
            self.weapon, self.special, self.a_slot, 
            self.b_slot, self.c_slot, self.s_slot, self.x_slot
        ]
        return [item for item in all_slots if item is not None]

        def get_potent_percentage(self, target_enemy=None):
        """Calculates the total potent percentage for this unit."""

        for item in self._get_equipped_items():
            if item.potent_logic is not None:
                return item.potent_logic(self, target_enemy)
                
        return 0.0
        def _apply_dragonflowers(self):
        """Calculates the stat increases from dragonflowers and applies them to the base stats."""
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


def apply_visible_buff(self, stat, amount):
    """Applies a visible buff to the specified stat."""

    self.visible_buffs[stat] = max(self.visible_buffs[stat], amount)

def apply_visible_debuff(self, stat, amount):
    """Applies a visible debuff to the specified stat."""
    self.visible_debuffs[stat] = max(self.visible_debuffs[stat], amount)

def _apply_merges(self):
    """Calculates the stat increases from merges and applies them to the base stats."""
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
        
        # tie breaker
       stat_list = [
            {"name": "hp", "value": self.base_hp, "tie_breaker": 1},
            {"name": "atk", "value": self.base_atk, "tie_breaker": 2},
            {"name": "spd", "value": self.base_spd, "tie_breaker": 3},
            {"name": "def", "value": self.base_def, "tie_breaker": 4},
            {"name": "res", "value": self.base_res, "tie_breaker": 5}
        ]
        stat_list.sort(key=lambda x: (-x["value"], x["tie_breaker"]))

        # neutral, first merge gives +1 to the top 3 stats.
        if not self.boon and not self.bane:
            for i in range(3):
                stat_to_boost = stat_list[i]["name"]
                if stat_to_boost == "hp": self.base_hp += 1
                elif stat_to_boost == "atk": self.base_atk += 1
                elif stat_to_boost == "spd": self.base_spd += 1
                elif stat_to_boost == "def": self.base_def += 1
                elif stat_to_boost == "res": self.base_res += 1

        # stat distribution 
        total_stat_points = self.merges * 2
        
        for i in range(total_stat_points):
            # This modulo logic automatically recreates the exact table sequence from your image
            stat_to_boost = stat_list[i % 5]["name"]
            
            # Apply the +1 to the ACTUAL Level 40 stats
            if stat_to_boost == "hp": self.base_hp += 1
            elif stat_to_boost == "atk": self.base_atk += 1
            elif stat_to_boost == "spd": self.base_spd += 1
            elif stat_to_boost == "def": self.base_def += 1
            elif stat_to_boost == "res": self.base_res += 1
        
def _apply_stat_change(self, stat_name, is_asset):
    """Applies the stat change from a boon or bane to the base stats."""
        modifier = 0
        if is_asset:
            modifier = 4 if stat_name in self.superboon else 3
        else:
            modifier = -4 if stat_name in self.superbane else -3

        if stat_name == "hp": self.base_hp += modifier
        elif stat_name == "atk": self.base_atk += modifier
        elif stat_name == "spd": self.base_spd += modifier
        elif stat_name == "def": self.base_def += modifier
        elif stat_name == "res": self.base_res += modifier

    def _apply_ivs_and_modifiers(self):
        """Applies the stat changes from boon, bane, and floret to the base stats."""
        if self.bane:
            self._apply_stat_change(self.bane, is_asset=False)
        if self.boon:
            self._apply_stat_change(self.boon, is_asset=True)
        if self.floret and self.floret != self.boon:
            self._apply_stat_change(self.floret, is_asset=True)

# --- Calculating the Stat Screen Numbers ---
def get_visible_atk(self):
    """Calculates the visible attack stat, including base, weapon might, and visible buffs/debuffs."""
    weapon_might = self.weapon.might if self.weapon else 0
    return self.base_atk + weapon_might + self.visible_buffs["atk"] - self.visible_debuffs["atk"]

def get_visible_def(self):
    """Calculates the visible defense stat, including base, weapon might, and visible buffs/debuffs."""
    weapon_might = self.weapon.might if self.weapon else 0
    return self.base_def + weapon_might + self.visible_buffs["def"] - self.visible_debuffs["def"]

def get_visible_spd(self):
    """Calculates the visible speed stat, including base, weapon might, and visible buffs/debuffs."""
    weapon_might = self.weapon.might if self.weapon else 0
    return self.base_spd + weapon_might + self.visible_buffs["spd"] - self.visible_debuffs["spd"]

def get_visible_res(self):
    """Calculates the visible resistance stat, including base, weapon might, and visible buffs/debuffs."""
    weapon_might = self.weapon.might if self.weapon else 0
    return self.base_res + weapon_might + self.visible_buffs["res"] - self.visible_debuffs["res"]

def get_combat_atk(self):
        total_atk = self.get_visible_atk()
        for item in self._get_equipped_items():
            total_atk += item.atkbonus
        return total_atk

def get_combat_def(self):
        total_def = self.get_visible_def()
        for item in self._get_equipped_items():
            total_def += item.defbonus
        return total_def
def get_combat_spd(self):
        total_spd = self.get_visible_spd()
        for item in self._get_equipped_items():
            total_spd += item.spdbonus
        return total_spd
def get_combat_res(self):
        total_res = self.get_visible_res()
        for item in self._get_equipped_items():
            total_res += item.resbonus
        return total_res


# --- FORMULAS FOR CALCING SKILLS HERE ---
def potent_flat_40(attacker, defender=None):
    if attacker > defender:
        return 0.40 
    return 0.80


def potent_defense_scaling(attacker, defender=None):
    """Calculates the potent effectiveness."""
    if defender is None:
        return 0.0  # Or whatever default makes sense for your UI

    def_difference = attacker.get_total_def() - defender.get_total_def()
    
    if def_difference <= 0:
        return 0.0
        
    return min(def_difference * 0.10, 0.50)



