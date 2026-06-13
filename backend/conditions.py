from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Literal, TYPE_CHECKING

#prevents circular imports with combatcalculator.py
if TYPE_CHECKING:
    from .combatcalculator import CombatantState

Phase = Literal["pre_aoe", "start_of_combat", "post_sequence"]

# ── evaluator functions ──────────────────────────────────────────────────────


def _evaluate_unit_initiates(params: dict) -> Callable:
    """Checks if the unit initiated combat (Player Phase)."""
    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        return getattr(unit, "is_initiator", False)
    return evaluate


def _evaluate_foe_initiates(params: dict) -> Callable:
    """Checks if the foe initiated combat (Enemy Phase)."""
    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        return getattr(foe, "is_initiator", False)
    return evaluate


def _evaluate_spaces_moved(params: dict) -> Callable:
    """Checks the number of spaces moved by the unit or foe (e.g., Clash skills)."""
    min_spaces = params.get("min_spaces", 1)
    target_str = params.get("target", "initiator")

    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        unit_moved = getattr(unit, "spaces_moved", 0)
        foe_moved = getattr(foe, "spaces_moved", 0)

        if target_str == "self":
            return unit_moved >= min_spaces
        elif target_str == "foe":
            return foe_moved >= min_spaces
        elif target_str == "either":
            return unit_moved >= min_spaces or foe_moved >= min_spaces
        elif target_str == "initiator":
            initiator = unit if getattr(unit, "is_initiator", False) else foe
            return getattr(initiator, "spaces_moved", 0) >= min_spaces

        return False

    return evaluate


def _evaluate_ally_within_spaces(params: dict) -> Callable:
    ...


def _evaluate_foe_weapon_type(params: dict) -> Callable:
    """Checks if the foe's weapon matches a specific list."""
    valid_types = params.get("types", [])

    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        return foe.unit.weapon_type.name in valid_types
    return evaluate


def _make_hp_pct_evaluator(compare: Callable[[float, float], bool]) -> Callable[[dict], Callable]:
    """Factory for HP-percentage-threshold conditions (hp_above_pct / hp_below_pct)."""
    def builder(params: dict) -> Callable:
        threshold = params.get("threshold", 0)
        target_str = params.get("target", "self")

        def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
            target = unit if target_str == "self" else foe
            pct = (target.unit.start_of_combat_hp / target.unit.base_stats.hp) * 100
            return compare(pct, threshold)

        return evaluate
    return builder


_evaluate_hp_above_pct = _make_hp_pct_evaluator(lambda pct, threshold: pct >= threshold)
_evaluate_hp_below_pct = _make_hp_pct_evaluator(lambda pct, threshold: pct < threshold)


def _evaluate_cbt_stat_check(params: dict) -> Callable:
    """Generic in-combat stat comparison (handles Spd, Def, Res, etc)."""
    stat = params.get("stat", "spd")
    margin = params.get("margin", 0)

    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        # Failsafe fallback to visible stats if combat stats aren't built yet
        unit_stat = getattr(unit.combat_stats, stat, unit.unit.get_visible_stat(stat))
        foe_stat = getattr(foe.combat_stats, stat, foe.unit.get_visible_stat(stat))
        return unit_stat >= (foe_stat + margin)

    return evaluate


def _evaluate_num_bonus_penalty_total(params: dict) -> Callable:
    """Checks total active effects."""
    min_count = params.get("min_count", 1)
    include_foe = params.get("include_foe", False)

    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        total = unit.bonus_count + unit.penalty_count
        if include_foe:
            total += foe.bonus_count + foe.penalty_count
        return total >= min_count
    return evaluate


def _evaluate_triggers_brave(params: dict) -> Callable:
    """Checks if the unit triggered the 'attacks twice' effect."""
    target_str = params.get("target", "self")

    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        target = unit if target_str == "self" else foe
        return any(e.type == "BRAVE" for e in target.effects_strike_sequence)

    return evaluate


def _evaluate_is_engaged(params: dict) -> Callable:
    """Salvaged from Fell Spirit: Checks if either unit is Engaged."""
    def evaluate(unit: 'CombatantState', foe: 'CombatantState') -> bool:
        return unit.unit.is_engaged or foe.unit.is_engaged
    return evaluate

# ── registry ─────────────────────────────────────────────────────────────────


CONDITION_REGISTRY: dict[str, tuple[Phase, Callable[[dict], Callable]]] = {
    "unit_initiates": ("pre_aoe", _evaluate_unit_initiates),
    "foe_initiates": ("pre_aoe", _evaluate_foe_initiates),
    "spaces_moved": ("pre_aoe", _evaluate_spaces_moved),
    "ally_within_spaces": ("pre_aoe", _evaluate_ally_within_spaces),
    "foe_weapon_type": ("pre_aoe", _evaluate_foe_weapon_type),
    "hp_above_pct": ("start_of_combat", _evaluate_hp_above_pct),
    "hp_below_pct": ("start_of_combat", _evaluate_hp_below_pct),
    "cbt_stat_check": ("start_of_combat", _evaluate_cbt_stat_check),
    "triggers_brave": ("post_sequence", _evaluate_triggers_brave),
    "bonus_penalty_total": ("pre_aoe", _evaluate_num_bonus_penalty_total),
    "is_engaged": ("pre_aoe", _evaluate_is_engaged),
}

# ── classes ─────────────────────────────────────────────────────────────────

@dataclass
class AtomicCondition:
    type: str
    params: dict
    phase: Phase
    func: Callable


@dataclass
class AnyOf:
    conditions: list[Condition]

@dataclass
class AllOf:
    conditions: list[Condition]

Condition = AtomicCondition | AnyOf | AllOf


# ── builders ─────────────────────────────────────────────────────────────────


def _build_atomic_condition(data: dict) -> AtomicCondition:
    c_type = data["type"]
    params = data.get("params", {})
    
    if c_type not in CONDITION_REGISTRY:
        raise ValueError(f"Unknown condition type: {c_type}")
        
    phase, func_builder = CONDITION_REGISTRY[c_type]
    
    return AtomicCondition(
        type=c_type,
        params=params,
        phase=phase,
        func=func_builder(params),
    )


def _build_condition(data: dict) -> Condition:
    if "any_of" in data:
        return AnyOf(conditions=[_build_condition(c) for c in data["any_of"]])
    if "all_of" in data:
        return AllOf(conditions=[_build_condition(c) for c in data["all_of"]])
    return _build_atomic_condition(data)

def build_conditions(data_list: list[dict]) -> list[Condition]:
    return [_build_condition(c) for c in data_list]
