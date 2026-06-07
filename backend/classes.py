class StatBlock:
    def __init__(self, hp=0, atk=0, spd=0, defense=0, res=0):
        self.hp = hp
        self.atk = atk
        self.spd = spd
        self.defense = defense
        self.res = res
    
class UtilityBlock:
    def __init__(self, truedmg=0, percentdr=0.0, gfu=False, nfu=False, potent_logic=None):
        self.truedmg = truedmg
        self.percentdr = percentdr
        self.gfu = gfu
        self.nfu = nfu
        self.potent_logic = potent_logic

class Unit:
    def __init__(self, name, movementtype, weapontype, 
                 hp, atk, spd, defense, res, 
                 dragonflower=0, merges=0,
                 superboon=None, superbane=None, boon=None, bane=None, floret=None, bouquet=None, 
                 weapon=None, special=None, a_slot=None, b_slot=None, c_slot=None, s_slot=None, x_slot=None):
        
        # --- Core Identifiers ---
        self.name = name
        self.movementtype = movementtype
        self.weapontype = weapontype     

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
