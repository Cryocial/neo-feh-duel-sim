from dataclasses import dataclass
from typing import Literal
from .constants import EffectType
from .conditions import Condition, build_conditions

EFFECT_LIST_MAP: dict[EffectType, str] = {
    # ── AoE ──────────────────────────────────────────────────────────────
    EffectType.TRIGGER_AOE: "effects_AoE",
    EffectType.FLAT_DAMAGE_AOE: "effects_AoE",
    EffectType.FLAT_DR_AOE: "effects_AoE",
    EffectType.HEXBLADE_AOE: "effects_AoE",
    EffectType.PULSE_AOE: "effects_AoE",
    # ── Stat modifications ──────────────────────────────────────────────
    EffectType.STAT_BOOST: "effects_start_of_combat",
    EffectType.STAT_DAUNT: "effects_start_of_combat",
    EffectType.BONUS_NEUT: "effects_start_of_combat",
    EffectType.PENALTY_NEUT: "effects_start_of_combat",
    # ── Strike sequence ─────────────────────────────────────────────────
    EffectType.FU_DENY: "effects_strike_sequence",
    EffectType.OFF_NFU: "effects_strike_sequence",
    EffectType.DEF_NFU: "effects_strike_sequence",
    EffectType.GFU: "effects_strike_sequence",
    EffectType.BRAVE: "effects_strike_sequence",
    EffectType.POTENT: "effects_strike_sequence",
    EffectType.VANTAGE: "effects_strike_sequence",
    EffectType.VANTAGE_NEUT: "effects_strike_sequence",
    EffectType.DESPERATION: "effects_strike_sequence",
    EffectType.DESPERATION_NEUT: "effects_strike_sequence",
    EffectType.FLASH: "effects_strike_sequence",
    EffectType.FLASH_NEUT: "effects_strike_sequence",
    EffectType.OFF_FROZEN: "effects_strike_sequence",
    EffectType.DEF_FROZEN: "effects_strike_sequence",
    # ── Start of turn ────────────────────────────────────────────────────
    EffectType.GRANT_VISIBLE_STAT: "effects_start_of_turn",
    EffectType.GRANT_STATUS: "effects_start_of_turn",
    # ── Pre-combat ───────────────────────────────────────────────────────
    EffectType.PRE_CBT_DAMAGE: "effects_pre_combat",
    EffectType.PRE_CBT_HEAL: "effects_pre_combat",
    # ── On-strike ────────────────────────────────────────────────────────
    EffectType.DR_PIERCE: "effects_on_strike",
    EffectType.HEXBLADE_STRIKE: "effects_on_strike",
    EffectType.EFFECTIVE: "effects_on_strike",
    EffectType.NEUT_EFFECTIVE: "effects_on_strike",
    EffectType.SPECIAL_TRIGGER_NEUT: "effects_on_strike",
    EffectType.FLAT_DR_STRIKE: "effects_on_strike",
    EffectType.PERC_DR_STRIKE: "effects_on_strike",
    EffectType.FLAT_DAMAGE_STRIKE: "effects_on_strike",
    EffectType.PULSE_STRIKE: "effects_on_strike",
    EffectType.SCOWL_STRIKE: "effects_on_strike",
    EffectType.HEAL_STRIKE: "effects_on_strike",
    EffectType.OFF_BREATH: "effects_on_strike",
    EffectType.DEF_BREATH: "effects_on_strike",
    EffectType.BREATH_NEUT: "effects_on_strike",
    EffectType.OFF_GUARD: "effects_on_strike",
    EffectType.DEF_GUARD: "effects_on_strike",
    EffectType.GUARD_NEUT: "effects_on_strike",
    EffectType.DR_FLOOR: "effects_on_strike",
    EffectType.DEEP_WOUNDS_IN_CBT: "effects_on_strike",
    EffectType.NEUT_DEEP_WOUNDS_IN_CBT: "effects_on_strike",
    EffectType.REDUCE_DEEP_WOUNDS_IN_CBT: "effects_on_strike",
    EffectType.TRIANGLE_ADEPT: "effects_on_strike",
    EffectType.CANCEL_AFFINITY: "effects_on_strike",
    EffectType.STAFF_FULL_DAMAGE: "effects_on_strike",
    EffectType.MIRACLE: "effects_on_strike",
    EffectType.FATAL_SMOKE: "effects_on_strike",
    # ── Post-combat ──────────────────────────────────────────────────────
    EffectType.HEAL_POST_CBT: "effects_after_combat",
    EffectType.DAMAGE_POST_CBT: "effects_after_combat",
    EffectType.DEEP_WOUNDS_POST_CBT: "effects_after_combat",
    EffectType.NEUT_DEEP_WOUNDS_POST_CBT: "effects_after_combat",
    EffectType.REDUCE_DEEP_WOUNDS_POST_CBT: "effects_after_combat",
}


@dataclass
class Effect:
    type: EffectType
    applied_by: Literal["bonus", "penalty", "self", "foe", "ally", "enemy"]
    params: dict
    conditions: list[Condition]


def build_effect(desc: dict, applied_by: str) -> Effect:
    return Effect(
        type=EffectType(desc["effect"]),
        applied_by=applied_by,
        params=desc.get("params", {}),
        conditions=build_conditions(desc.get("conditions", [])),
    )
