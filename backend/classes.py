class StatBlock:
    def __init__(self, hp=0, atk=0, spd=0, defense=0, res=0):
        self.hp = hp
        self.atk = atk
        self.spd = spd
        self.defense = defense
        self.res = res
    
class UtilityBlock:
    def __init__(self, truedr=0, truedrlogic=None, truedmg=0, truedmg_logic=None, 
                 percentdr=0.0, potent_logic=None, specialcdmod=0, specialcdmod_logic=None, keywords=None, grants_statuses=None):
        
        self.truedr = truedr
        self.truedrlogic = truedrlogic
        self.truedmg = truedmg
        self.truedmg_logic = truedmg_logic
        self.percentdr = percentdr
        self.potent_logic = potent_logic
        self.specialcdmod = specialcdmod
        self.specialcdmod_logic = specialcdmod_logic
        self.cooldown_modifiers = cooldown_modifiers if cooldown_modifiers else {}
        self.keywords = keywords if keywords else []

        self.grants_statuses = grants_statuses if grants_statuses else []

class Unit:
    def __init__(self, name, movement_type, weapon_type, 
                 hp, atk, spd, defense, res, 
                 dragonflower=0, merges=0,
                 superboon=None, superbane=None, boon=None, bane=None, floret=None, bouquet=None, 
                 weapon=None, special=None, a_slot=None, b_slot=None, c_slot=None, s_slot=None, x_slot=None):
        
        # --- Core Identifiers ---
        self.name = name
        self.movement_type = movement_type
        self.weapon_type = weapon_type     

        # --- Base Stats ---
        self.base_stats = StatBlock(hp=hp, atk=atk, spd=spd, defense=defense, res=res)
        
        # --- Temporary Map States (Visible) ---
        self.visible_buffs = StatBlock()
        self.visible_debuffs = StatBlock()

        # --- Out-of-Combat Stat Modifiers ---
        self.dragonflower = dragonflower
        self.merges = merges
        self.summonersupport = None
        self.aided = None

        # Temporary map buffs/debuffs (StatBlocks)
        self.visible_buffs = StatBlock()
        self.visible_debuffs = StatBlock()
        self.bonus_count = 0
        self.penalty_count = 0
        self.active_statuses = []

        # --- IVs and Special Assets ---
        self.boon = boon 
        self.bane = bane
        self.floret = floret 
        self.bouquet = bouquet 

        self.superboon = superboon if superboon else []
        self.superbane = superbane if superbane else []

        # --- Run Modifiers ---
        self._apply_ivs_and_modifiers()
        self._apply_merges()
        self._apply_dragonflowers()

        # --- Equipment Slots ---
        self.weapon = weapon
        self.special = special
        self.a_slot = a_slot
        self.b_slot = b_slot
        self.c_slot = c_slot
        self.s_slot = s_slot
        self.x_slot = x_slot
        
        
class Skill:
    def __init__(self, name, slot, visible_stats=None, combat_stats=None, utilities=None):
        self.name = name
        self.slot = slot
        self.visible_stats = visible_stats if visible_stats else StatBlock()
        self.combat_stats = combat_stats if combat_stats else StatBlock()
        self.utilities = utilities if utilities else UtilityBlock()
