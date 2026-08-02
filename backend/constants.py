from enum import Enum, auto


class MovementType(Enum):
    INFANTRY = auto()
    ARMOR = auto()
    CAVALRY = auto()
    FLIER = auto()


class WeaponType(Enum):
    SWORD = auto()
    LANCE = auto()
    AXE = auto()
    BOW = auto()
    DAGGER = auto()
    TOME = auto()
    STAFF = auto()
    DRAGON = auto()
    BEAST = auto()


class Color(Enum):
    RED = auto()
    BLUE = auto()
    GREEN = auto()
    COLORLESS = auto()


class StatType(Enum):
    HP = "hp"
    ATK = "atk"
    SPD = "spd"
    DEF = "defense"
    RES = "res"


class StrikeType(Enum):
    FIRST = auto()
    FOLLOW_UP = auto()
    POTENT = auto()


class EffectType(str, Enum):
    # ── AoE ───────────────────────────────────────────────────────────────────
    TRIGGER_AOE = "TRIGGER_AOE"
    FLAT_DAMAGE_AOE = "FLAT_DAMAGE_AOE"
    FLAT_DR_AOE = "FLAT_DR_AOE"
    HEXBLADE_AOE = "HEXBLADE_AOE"
    PULSE_AOE = "PULSE_AOE"

    # ── Stat modifications ────────────────────────────────────────────────────
    STAT_BOOST = "STAT_BOOST"
    STAT_DAUNT = "STAT_DAUNT"
    BONUS_NEUT = "BONUS_NEUT"
    PENALTY_NEUT = "PENALTY_NEUT"
    PHANTOM_STAT = "PHANTOM_STAT"

    # ── Strike sequence ───────────────────────────────────────────────────────
    FU_DENY = "FU_DENY"
    OFF_NFU = "OFF_NFU"
    DEF_NFU = "DEF_NFU"
    GFU = "GFU"
    BRAVE = "BRAVE"
    POTENT = "POTENT"
    VANTAGE = "VANTAGE"
    VANTAGE_NEUT = "VANTAGE_NEUT"
    DESPERATION = "DESPERATION"
    DESPERATION_NEUT = "DESPERATION_NEUT"
    FLASH = "FLASH"
    FLASH_NEUT = "FLASH_NEUT"
    OFF_FROZEN = "OFF_FROZEN"
    DEF_FROZEN = "DEF_FROZEN"

    # ── Start of turn ─────────────────────────────────────────────────────────
    GRANT_VISIBLE_STAT = "GRANT_VISIBLE_STAT"
    GRANT_STATUS = "GRANT_STATUS"

    # ── Pre-combat ────────────────────────────────────────────────────────────
    PRE_CBT_DAMAGE = "PRE_CBT_DAMAGE"
    PRE_CBT_HEAL = "PRE_CBT_HEAL"

    # ── On-strike ─────────────────────────────────────────────────────────────
    DR_PIERCE = "DR_PIERCE"
    HEXBLADE_STRIKE = "HEXBLADE_STRIKE"
    EFFECTIVE = "EFFECTIVE"
    NEUT_EFFECTIVE = "NEUT_EFFECTIVE"
    SPECIAL_TRIGGER_NEUT = "SPECIAL_TRIGGER_NEUT"
    FLAT_DR_STRIKE = "FLAT_DR_STRIKE"
    PERC_DR_STRIKE = "PERC_DR_STRIKE"
    FLAT_DAMAGE_STRIKE = "FLAT_DAMAGE_STRIKE"
    PULSE_STRIKE = "PULSE_STRIKE"
    SCOWL_STRIKE = "SCOWL_STRIKE"
    HEAL_STRIKE = "HEAL_STRIKE"
    OFF_BREATH = "OFF_BREATH"
    DEF_BREATH = "DEF_BREATH"
    BREATH_NEUT = "BREATH_NEUT"
    OFF_GUARD = "OFF_GUARD"
    DEF_GUARD = "DEF_GUARD"
    GUARD_NEUT = "GUARD_NEUT"
    DR_FLOOR = "DR_FLOOR"
    DEEP_WOUNDS_IN_CBT = "DEEP_WOUNDS_IN_CBT"
    NEUT_DEEP_WOUNDS_IN_CBT = "NEUT_DEEP_WOUNDS_IN_CBT"
    REDUCE_DEEP_WOUNDS_IN_CBT = "REDUCE_DEEP_WOUNDS_IN_CBT"
    TRIANGLE_ADEPT = "TRIANGLE_ADEPT"
    CANCEL_AFFINITY = "CANCEL_AFFINITY"
    STAFF_FULL_DAMAGE = "STAFF_FULL_DAMAGE"
    MIRACLE = "MIRACLE"
    FATAL_SMOKE = "FATAL_SMOKE"
    # ── Post-combat ───────────────────────────────────────────────────────────
    HEAL_POST_CBT = "HEAL_POST_CBT"
    DAMAGE_POST_CBT = "DAMAGE_POST_CBT"
    DEEP_WOUNDS_POST_CBT = "DEEP_WOUNDS_POST_CBT"
    REDUCE_DEEP_WOUNDS_POST_CBT = "REDUCE_DEEP_WOUNDS_POST_CBT"
    NEUT_DEEP_WOUNDS_POST_CBT = "NEUT_DEEP_WOUNDS_POST_CBT"
