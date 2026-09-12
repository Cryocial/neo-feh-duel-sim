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


class SpecialType(Enum):
    NONE = auto()
    AOE = auto()
    OFF = auto()
    DEF = auto()
    MIRACLE = auto()
    OTHER = auto()


class EffectType(str, Enum):
    # ── AoE ───────────────────────────────────────────────────────────────────
    TRIGGER_AOE = "TRIGGER_AOE"
    FLAT_DAMAGE_AOE = "FLAT_DAMAGE_AOE"
    FLAT_DR_AOE = "FLAT_DR_AOE"
    PERC_DR_AOE = "PERC_DR_AOE"
    HEXBLADE_AOE = "HEXBLADE_AOE"
    PULSE_AOE = "PULSE_AOE"

    # ── Start-of-combat effects ───────────────────────────────────────────────
    STAT_BOOST = "STAT_BOOST"
    STAT_DAUNT = "STAT_DAUNT"
    BONUS_NEUT = "BONUS_NEUT"
    PENALTY_NEUT = "PENALTY_NEUT"
    FEUD = "FEUD"
    PHANTOM_STAT = "PHANTOM_STAT"
    RANGE_EXTENSION = "RANGE_EXTENSION"

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
    COUNTERATTACK = "COUNTERATTACK"
    FLASH = "FLASH"
    FLASH_NEUT = "FLASH_NEUT"
    OFF_FROZEN = "OFF_FROZEN"
    DEF_FROZEN = "DEF_FROZEN"

    # ── Start of turn ─────────────────────────────────────────────────────────
    GRANT_VISIBLE_BUFF = "GRANT_VISIBLE_BUFF"
    INFLICT_VISIBLE_DEBUFF = "INFLICT_VISIBLE_DEBUFF"
    GRANT_STATUS = "GRANT_STATUS"
    GRANT_GREAT_TALENT = "GRANT_GREAT_TALENT"

    # ── Pre-combat ────────────────────────────────────────────────────────────
    PRE_CBT_DAMAGE = "PRE_CBT_DAMAGE"
    PRE_CBT_HEAL = "PRE_CBT_HEAL"

    # ── On-strike ─────────────────────────────────────────────────────────────
    DR_PIERCE = "DR_PIERCE"
    HEXBLADE_STRIKE = "HEXBLADE_STRIKE"
    NEUT_HEXBLADE = "NEUT_HEXBLADE"
    EFFECTIVE = "EFFECTIVE"
    NEUT_EFFECTIVE = "NEUT_EFFECTIVE"
    SPECIAL_TRIGGER_NEUT = "SPECIAL_TRIGGER_NEUT"
    FLAT_DR_STRIKE = "FLAT_DR_STRIKE"
    PERC_DR_STRIKE = "PERC_DR_STRIKE"
    TWIN = "TWIN"
    FLAT_DAMAGE_STRIKE = "FLAT_DAMAGE_STRIKE"
    REFLEX = "REFLEX"
    BRIAR = "BRIAR"
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
    MIRACLE_NEUT = "MIRACLE_NEUT"
    # ── Post-combat ───────────────────────────────────────────────────────────
    HEAL_POST_CBT = "HEAL_POST_CBT"
    GRANT_GREAT_TALENT_POST_CBT = "GRANT_GREAT_TALENT_POST_CBT"
    DAMAGE_POST_CBT = "DAMAGE_POST_CBT"
    DEEP_WOUNDS_POST_CBT = "DEEP_WOUNDS_POST_CBT"
    REDUCE_DEEP_WOUNDS_POST_CBT = "REDUCE_DEEP_WOUNDS_POST_CBT"
    NEUT_DEEP_WOUNDS_POST_CBT = "NEUT_DEEP_WOUNDS_POST_CBT"


class StrikeMatch(str, Enum):
    """Every params["strike"] value CombatEngine._strike_matches understands.
    build_effect validates against STRIKE_VALUES at simulation start, so a typo
    fails loudly instead of matching nothing. Keep in sync with Appendix B of
    ARCHITECTURE.md."""
    EVERY_STRIKE = "every_strike"
    FIRST_STRIKE = "first_strike"
    FIRST_ATTACK = "first_attack"
    FIRST_ATTACK_BRAVE = "first_attack_brave"
    FIRST_FOLLOW_UP = "first_follow_up"
    FOLLOW_UP = "follow_up"
    FOLLOW_UP_BRAVE = "follow_up_brave"
    BOTH_FIRST_STRIKES = "both_first_strikes"
    BOTH_SECOND_STRIKES = "both_second_strikes"
    CONSECUTIVE = "consecutive"
    UNIT_SPECIAL_TRIGGERS = "unit_special_triggers"
    FOE_SPECIAL_TRIGGERS = "foe_special_triggers"
    UNIT_SPECIAL_READY = "unit_special_ready"
    FOE_SPECIAL_READY = "foe_special_ready"
    ANY_SPECIAL_READY = "any_special_ready"
    ANY_SPECIAL_READY_OR_TRIGGERED = "any_special_ready_or_triggered"


STRIKE_VALUES: frozenset[str] = frozenset(m.value for m in StrikeMatch)

# Every formula CombatEngine._resolve_formula understands ("" = flat only).
# Keep in sync with Appendix C of ARCHITECTURE.md.
FORMULA_NAMES: frozenset[str] = frozenset({
    "",
    "bonus_count",
    "all_bonus_penalty_both",
    "spaces_moved",
    "sum_visible_buffs",
    "sum_foe_visible_debuffs",
    "unit_max_hp",
    "phantom_spd_diff",
    "foe_penalty_count",
    "unit_cbt_atk",
    "unit_cbt_spd",
    "unit_cbt_def",
    "unit_cbt_res",
    "max_cooldown",
    "num_bonus_and_penalties_on_unit",
})

# The four stats Great Talent can raise, and the only ones the visible cap
# applies to (HP fixtures in the tests run past 99 on purpose).
COMBAT_STATS = ("atk", "spd", "defense", "res")

# A visible stat never displays above this, buffs included. Anything past it
# is "useless" for the stat itself but still exists as a bonus value.
VISIBLE_STAT_CAP = 99
