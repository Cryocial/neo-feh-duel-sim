from dataclasses import dataclass
from typing import Literal
from .constants import EffectType
from .conditions import Condition, build_conditions

EFFECT_LIST_MAP: dict[EffectType, str] = {
    EffectType.TRIGGER_AOE:      "effects_AoE",
    EffectType.FLAT_DAMAGE_AOE:  "effects_AoE",
    # ...
    EffectType.STAT_BOOST:       "effects_start_of_combat",
    EffectType.STAT_DAUNT:       "effects_start_of_combat",
    # ...
    EffectType.FU_DENY:          "effects_strike_sequence",
    # ...
}


@dataclass
class Effect:
    type:       EffectType
    applied_by: Literal["bonus", "penalty", "self", "foe", "ally", "enemy"]
    params:     dict
    conditions: list[Condition]


def build_effect(desc: dict, applied_by: str) -> Effect:
    return Effect(
        type=EffectType(desc["effect"]),
        applied_by=applied_by,
        params=desc.get("params", {}),
        conditions=build_conditions(desc.get("conditions", [])),
    )