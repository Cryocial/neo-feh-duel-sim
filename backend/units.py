class Unit:
    def __init__(self, name, hp, atk, spd, defense, res, dragonflower, movementtype, weapontype, 
                 superboon=None, superbane=None, boon=None, bane=None, floret=None, bouquet=None, merges=0):
        
        # --- Core Identifiers ---
        self.name = name
        self.movementtype = movementtype
        self.weapontype = weapontype     

        # --- Base Stats ---
        self.hp = hp
        self.atk = atk
        self.spd = spd
        self.defense = defense 
        self.res = res

        # --- Temporary Map States (Visible) ---
        self.visible_buffs = {"atk": 0, "spd": 0, "def": 0, "res": 0}
        self.visible_debuffs = {"atk": 0, "spd": 0, "def": 0, "res": 0}

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

        
        self._apply_ivs_and_modifiers()
        self._apply_merges()
        self._apply_dragonflowers()

        # --- Equipment Slots ---
        self.weapon = None
        self.special = None
        self.a_slot = None
        self.b_slot = None
        self.c_slot = None
        self.s_slot = None
        self.x_slot = None
        
        

class Skill:
    def __init__(self, name, hpbonus=0, atkbonus=0, spdbonus=0, defbonus=0, resbonus=0, truedmg=0, truedr=0, percentdr=0.0, predamage=0, 
                 visualprecharge=0, incombatprecharge=0, difficultfollowups=None,
                 gfu=False, potentlogic = None, brave=False, nfu=False, effective=False, flash=False, adaptivedmg=False, ncd=False, aoe=False
                 ):
        self.name = name
        self.hpbonus = hpbonus
        self.atkbonus = atkbonus
        self.spdbonus = spdbonus
        self.defbonus = defbonus
        self.resbonus = resbonus
        self.truedmg = truedmg
        self.truedr = truedr
        self.percentdr = percentdr
