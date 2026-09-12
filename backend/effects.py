from dataclasses import dataclass
from typing import Literal
from .constants import COMBAT_STATS, Color, EffectType, STRIKE_VALUES, FORMULA_NAMES
from .conditions import Condition, build_conditions

EFFECT_LIST_MAP: dict[EffectType, str] = {
    # ── AoE ──────────────────────────────────────────────────────────────
    EffectType.TRIGGER_AOE: "effects_AoE",
    EffectType.FLAT_DAMAGE_AOE: "effects_AoE",
    EffectType.FLAT_DR_AOE: "effects_AoE",
    EffectType.PERC_DR_AOE: "effects_AoE",
    EffectType.HEXBLADE_AOE: "effects_AoE",
    EffectType.PULSE_AOE: "effects_AoE",
    # ── Combat stats ─────────────────────────────────────────────────────
    EffectType.STAT_BOOST: "effects_combat_stats",
    EffectType.STAT_DAUNT: "effects_combat_stats",
    EffectType.BONUS_NEUT: "effects_combat_stats",
    EffectType.PENALTY_NEUT: "effects_combat_stats",
    EffectType.FEUD: "effects_combat_stats",
    EffectType.BONUS_DOUBLER: "effects_combat_stats",
    EffectType.PENALTY_DOUBLER: "effects_combat_stats",
    EffectType.FRINGE_BONUS: "effects_combat_stats",
    EffectType.SABOTAGE: "effects_combat_stats",
    EffectType.PHANTOM_STAT: "effects_combat_stats",
    EffectType.RANGE_EXTENSION: "effects_combat_stats",
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
    EffectType.COUNTERATTACK: "effects_strike_sequence",
    EffectType.FLASH: "effects_strike_sequence",
    EffectType.FLASH_NEUT: "effects_strike_sequence",
    EffectType.OFF_FROZEN: "effects_strike_sequence",
    EffectType.DEF_FROZEN: "effects_strike_sequence",
    # ── Start of turn ────────────────────────────────────────────────────
    EffectType.GRANT_VISIBLE_BUFF: "effects_start_of_turn",
    EffectType.INFLICT_VISIBLE_DEBUFF: "effects_start_of_turn",
    EffectType.GRANT_STATUS: "effects_start_of_turn",
    EffectType.GRANT_GREAT_TALENT: "effects_start_of_turn",
    # ── Pre-combat ───────────────────────────────────────────────────────
    EffectType.PRE_CBT_DAMAGE: "effects_pre_combat",
    EffectType.PRE_CBT_HEAL: "effects_pre_combat",
    # ── On-strike ────────────────────────────────────────────────────────
    EffectType.TWIN: "effects_pre_combat",
    EffectType.DR_PIERCE: "effects_on_strike",
    EffectType.HEXBLADE_STRIKE: "effects_pre_combat",
    EffectType.NEUT_HEXBLADE: "effects_pre_combat",
    EffectType.EFFECTIVE: "effects_on_strike",
    EffectType.NEUT_EFFECTIVE: "effects_on_strike",
    EffectType.SPECIAL_TRIGGER_NEUT: "effects_pre_combat",
    EffectType.FLAT_DR_STRIKE: "effects_on_strike",
    EffectType.PERC_DR_STRIKE: "effects_on_strike",
    EffectType.FLAT_DAMAGE_STRIKE: "effects_on_strike",
    EffectType.REFLEX: "effects_on_strike",
    EffectType.BRIAR: "effects_on_strike",
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
    EffectType.MIRACLE_NEUT: "effects_on_strike",
    # ── Post-combat ──────────────────────────────────────────────────────
    EffectType.HEAL_POST_CBT: "effects_after_combat",
    EffectType.GRANT_GREAT_TALENT_POST_CBT: "effects_after_combat",
    EffectType.DAMAGE_POST_CBT: "effects_after_combat",
    EffectType.DEEP_WOUNDS_POST_CBT: "effects_after_combat",
    EffectType.NEUT_DEEP_WOUNDS_POST_CBT: "effects_after_combat",
    EffectType.REDUCE_DEEP_WOUNDS_POST_CBT: "effects_after_combat",
}


@dataclass
class Effect:
    type: EffectType
    applied_by: Literal["self", "foe", "ally", "enemy"]
    params: dict
    conditions: list[Condition]
    source_color: Color | None = None  # the ally's colour for ally/enemy effects


# Params the engine reads with [] rather than .get(); missing keys fail here,
# at simulation start, with the effect named, instead of a bare KeyError later.
REQUIRED_PARAMS: dict[EffectType, frozenset[str]] = {
    EffectType.TRIGGER_AOE: frozenset({"coefficient"}),
    EffectType.RANGE_EXTENSION: frozenset({"min", "max"}),
    EffectType.TWIN: frozenset({"value"}),
    EffectType.DR_PIERCE: frozenset({"value"}),
    EffectType.POTENT: frozenset({"damage_pct"}),
    EffectType.PERC_DR_STRIKE: frozenset({"piercable"}),
    EffectType.STAT_BOOST: frozenset({"stats"}),
    EffectType.STAT_DAUNT: frozenset({"stats"}),
    EffectType.PHANTOM_STAT: frozenset({"stats"}),
    EffectType.GRANT_VISIBLE_BUFF: frozenset({"stats"}),
    EffectType.INFLICT_VISIBLE_DEBUFF: frozenset({"stats"}),
    EffectType.GRANT_STATUS: frozenset({"status"}),
    EffectType.GRANT_GREAT_TALENT: frozenset({"stats"}),
    EffectType.GRANT_GREAT_TALENT_POST_CBT: frozenset({"stats"}),
}

# One effect per phase Great Talent can be granted in; a new way of granting it
# is a new member here, a list-map entry, and one call to _grant_great_talent.
GREAT_TALENT_TYPES = frozenset({
    EffectType.GRANT_GREAT_TALENT,
    EffectType.GRANT_GREAT_TALENT_POST_CBT,
})

def validate_effect_desc(desc: dict) -> list[str]:
    """Returns every problem with a raw effect dict, empty if it is well-formed.
    Shared by build_effect (raises) and the data-integrity tests (reports)."""
    problems = []
    try:
        effect_type = EffectType(desc.get("effect"))
    except ValueError:
        return [f"unknown effect type {desc.get('effect')!r}"]
    if effect_type not in EFFECT_LIST_MAP:
        problems.append(f"{effect_type.value} has no EFFECT_LIST_MAP entry")
    if desc.get("target") not in ("self", "foe"):
        problems.append(f"target must be 'self' or 'foe', got {desc.get('target')!r}")
    params = desc.get("params", {})
    missing = REQUIRED_PARAMS.get(effect_type, frozenset()) - params.keys()
    if missing:
        problems.append(f"{effect_type.value} missing params {sorted(missing)}")
    if "strike" in params and params["strike"] not in STRIKE_VALUES:
        problems.append(f"unknown strike value {params['strike']!r}")
    if "formula" in params and params["formula"] not in FORMULA_NAMES:
        problems.append(f"unknown formula {params['formula']!r}")
    magnitude_types = {EffectType.GRANT_VISIBLE_BUFF, EffectType.INFLICT_VISIBLE_DEBUFF}
    if effect_type in magnitude_types | GREAT_TALENT_TYPES:
        negative = {k: v for k, v in params.get("stats", {}).items() if v < 0}
        if negative:
            problems.append(
                f"{effect_type.value} stats are magnitudes and must be >= 0, got {negative}"
            )
    if effect_type in GREAT_TALENT_TYPES:
        unknown = sorted(set(params.get("stats", {})) - set(COMBAT_STATS))
        if unknown:
            problems.append(f"{effect_type.value} stats must be among {COMBAT_STATS}, got {unknown}")
    if effect_type is EffectType.FEUD:
        unknown = [c for c in params.get("colors", []) if c not in Color.__members__]
        if unknown:
            problems.append(f"FEUD colors must be Color names, got {unknown}")
    if effect_type is EffectType.BRIAR and "flat" not in params and not params.get("formula"):
        problems.append("BRIAR needs a percent: 'flat' or a 'formula'")
    return problems


def build_effect(desc: dict, applied_by: str, source_color: Color | None = None) -> Effect:
    problems = validate_effect_desc(desc)
    if problems:
        raise ValueError(f"Malformed effect {desc.get('effect')!r}: " + "; ".join(problems))
    return Effect(
        type=EffectType(desc["effect"]),
        applied_by=applied_by,
        params=desc.get("params", {}),
        conditions=build_conditions(desc.get("conditions", [])),
        source_color=source_color,
    )
