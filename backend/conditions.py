from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Literal

Phase = Literal["pre_aoe", "start_of_combat", "post_sequence"]

# ── evaluator functions ──────────────────────────────────────────────────────


def _evaluate_unit_initiates(params: dict) -> Callable: ...


def _evaluate_foe_initiates(params: dict) -> Callable: ...


def _evaluate_spaces_moved(params: dict) -> Callable: ...


def _evaluate_ally_within_spaces(params: dict) -> Callable:
    min_allies = params["min_allies"]
    spaces = params["spaces"]
    ...


def _evaluate_foe_weapon_type(params: dict) -> Callable: ...


def _evaluate_hp_above_pct(params: dict) -> Callable:
    threshold = params["threshold"]
    target = params.get("unit", "self")

    def evaluate(unit, foe) -> bool:
        combatant = unit if target == "self" else foe
        return combatant.current_hp * 100 >= combatant.unit.base_stats.hp * threshold

    return evaluate


def _evaluate_cbt_spd_check(params: dict) -> Callable:
    margin = params.get("margin", 0)

    def evaluate(unit, foe) -> bool:
        return unit.combat_stats.spd >= foe.combat_stats.spd + margin

    return evaluate


def _evaluate_triggers_brave(params: dict) -> Callable: ...


CONDITION_REGISTRY: dict[str, (Phase, Callable[[dict], Callable])] = {
    "unit_initiates": ("pre_aoe", _evaluate_unit_initiates),
    "foe_initiates": ("pre_aoe", _evaluate_foe_initiates),
    "spaces_moved": ("pre_aoe", _evaluate_spaces_moved),
    "ally_within_spaces": ("pre_aoe", _evaluate_ally_within_spaces),
    "foe_weapon_type": ("pre_aoe", _evaluate_foe_weapon_type),
    "hp_above_pct": ("start_of_combat", _evaluate_hp_above_pct),
    "cbt_spd_check": ("start_of_combat", _evaluate_cbt_spd_check),
    "triggers_brave": ("post_sequence", _evaluate_triggers_brave),
}


@dataclass
class AtomicCondition:
    type: str
    params: dict
    phase: Phase
    func: Callable


@dataclass
class AnyOf:
    conditions: list[Condition]


Condition = AtomicCondition | AnyOf


# ── builders ─────────────────────────────────────────────────────────────────


def _build_atomic_condition(data: dict) -> AtomicCondition:
    type = data["type"]
    params = data.get("params", {})
    return AtomicCondition(
        type=type,
        params=params,
        phase=CONDITION_REGISTRY[type][0],
        func=CONDITION_REGISTRY[type][1](params),
    )


def _build_condition(data: dict) -> Condition:
    if "any_of" in data:
        return AnyOf(conditions=[_build_condition(c) for c in data["any_of"]])
    return _build_atomic_condition(data)


def build_conditions(data_list: list[dict]) -> list[Condition]:
    return [_build_condition(c) for c in data_list]
