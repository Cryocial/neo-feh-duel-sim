import math
from dataclasses import dataclass, field
from typing import Literal

from .build import Unit, StatBlock
from .constants import StrikeType, EffectType
from .effects import Effect, build_effect, EFFECT_LIST_MAP
from .conditions import Phase, Condition, AtomicCondition, AnyOf

UnitRole = Literal["attacker", "defender"]


@dataclass
class CombatantState:
    unit: Unit
    current_hp: int
    current_cooldown: int
    combat_stats: StatBlock | None = None
    defensive_stat: Literal["defense", "res"] | None = None
    damage_mitigated_bucket: int = 0
    bonus_count: int = 0
    penalty_count: int = 0
    special_use_count: int = 0
    strike_count: int = 0
    has_entered_combat: bool = False
    effects_AoE: list[Effect] = field(default_factory=list)
    effects_start_of_combat: list[Effect] = field(default_factory=list)
    effects_strike_sequence: list[Effect] = field(default_factory=list)
    effects_pre_combat: list[Effect] = field(default_factory=list)
    effects_on_strike: list[Effect] = field(default_factory=list)
    effects_after_combat: list[Effect] = field(default_factory=list)


@dataclass
class Strike:
    """Represents a single attack in the combat sequence."""

    striker: UnitRole
    target: UnitRole
    strike_type: StrikeType
    brave_second_hit: bool = False
    consecutive: bool = False


def _distribute_effects(attacker: CombatantState, defender: CombatantState) -> None:
    attacker_skills = [
        attacker.unit.weapon,
        attacker.unit.special,
        attacker.unit.a_slot,
        attacker.unit.b_slot,
        attacker.unit.c_slot,
        attacker.unit.s_slot,
        attacker.unit.x_slot,
    ]
    for skill in attacker_skills:
        for desc in skill.effects:
            effect = build_effect(desc, applied_by="self")
            target = attacker if desc["target"] == "self" else defender
            _add_to_bucket(target, effect)

    for status in attacker.unit.active_statuses:
        for desc in status.effects:
            effect = build_effect(desc, applied_by=status.type)
            target = attacker if desc["target"] == "self" else defender
            _add_to_bucket(target, effect)

    defender_skills = [
        defender.unit.weapon,
        defender.unit.special,
        attacker.unit.a_slot,
        defender.unit.b_slot,
        defender.unit.c_slot,
        defender.unit.s_slot,
        defender.unit.x_slot,
    ]
    for skill in defender_skills:
        for desc in skill.effects:
            effect = build_effect(desc, applied_by="self")
            target = defender if desc["target"] == "self" else attacker
            _add_to_bucket(target, effect)

    for status in defender.unit.active_statuses:
        for desc in status.effects:
            effect = build_effect(desc, applied_by=status.type)
            target = defender if desc["target"] == "self" else attacker
            _add_to_bucket(target, effect)


def _add_to_bucket(state: CombatantState, effect: Effect) -> None:
    list_name = EFFECT_LIST_MAP.get(effect.type)
    if list_name is not None:
        getattr(state, list_name).append(effect)


def _evaluate_conditions_for_effect(
    effect: Effect,
    unit_state: CombatantState,
    foe_state: CombatantState,
    phase: Phase,
) -> tuple[bool, list[Condition]]:
    if effect.applied_by == "foe":
        owner, opponent = foe_state, unit_state
    else:
        owner, opponent = unit_state, foe_state
    return _check_phase(effect.conditions, phase, owner, opponent)


def _check_phase(
    conditions: list[Condition],
    phase: Phase,
    unit: CombatantState,
    foe: CombatantState,
) -> tuple[bool, list[Condition]]:
    remaining = []
    for cond in conditions:
        result = _check_condition(cond, phase, unit, foe)
        if result is False:
            return False, []
        if result is None:
            remaining.append(cond)
    return True, remaining


def _check_condition(
    cond: Condition,
    phase: Phase,
    unit: CombatantState,
    foe: CombatantState,
) -> bool | None:
    if isinstance(cond, AtomicCondition):
        if cond.phase != phase:
            return None
        return cond.func(unit, foe)
    return _check_anyof(cond, phase, unit, foe)


def _check_anyof(
    anyof: AnyOf,
    phase: Phase,
    unit: CombatantState,
    foe: CombatantState,
) -> bool | None:
    results = [_check_condition(c, phase, unit, foe) for c in anyof.conditions]
    phase_results = [r for r in results if r is not None]
    if not phase_results:
        return None
    return any(phase_results)


@dataclass
class CombatEngine:
    """
    The orchestrator for combat simulation.
    Handles the timeline of events from 'start of combat' to 'after combat'.
    """

    attacker: Unit
    defender: Unit
    combatant_states: dict[UnitRole, CombatantState] = field(init=False)

    def simulate(self) -> dict[str, int]:
        """Runs the full combat simulation following the 10-step timeline."""
        # 1. Initialize States & Distribute Effects
        self.combatant_states = {
            "attacker": CombatantState(
                unit=self.attacker,
                current_hp=self.attacker.current_hp,
                current_cooldown=self.attacker.max_cooldown - self.attacker.pre_charge,
            ),
            "defender": CombatantState(
                unit=self.defender,
                current_hp=self.defender.current_hp,
                current_cooldown=self.defender.max_cooldown - self.defender.pre_charge,
            ),
        }
        _distribute_effects(
            self.combatant_states["attacker"], self.combatant_states["defender"]
        )

        self._evaluate_conditions("pre_aoe")

        self._phase_AoE()

        self._combat_stat_calculations()

        self._evaluate_conditions("start_of_combat")

        strike_sequence = self._determine_strike_sequence()

        self._evaluate_conditions("post_sequence")

        self._phase_pre_combat()

        while (
            len(strike_sequence) > 0
            and self.combatant_states["attacker"].current_hp > 0
            and self.combatant_states["defender"].current_hp > 0
        ):
            strike = strike_sequence.pop(0)
            self._process_strike(strike)

        self._phase_after_combat()

        return {
            "attacker_final_hp": self.combatant_states["attacker"].current_hp,
            "defender_final_hp": self.combatant_states["defender"].current_hp,
        }

    def _evaluate_conditions(self, phase: Phase) -> None:
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe_state = self.combatant_states[foe_role]
            for list_name in (
                "effects_AoE",
                "effects_start_of_combat",
                "effects_strike_sequence",
                "effects_pre_combat",
                "effects_on_strike",
                "effects_after_combat",
            ):
                updated_conditions = []
                for effect in getattr(state, list_name):
                    keep, remaining_conditions = _evaluate_conditions_for_effect(
                        effect, state, foe_state, phase
                    )
                    if keep:
                        effect.conditions = remaining_conditions
                        updated_conditions.append(effect)
                setattr(state, list_name, updated_conditions)

    def _apply_healing(self, unit_state: CombatantState, amount: int):
        """Applies healing while checking for Deep Wounds effects."""
        # TODO DOUBLE CHECK THIS LATER
        if amount <= 0:
            return

        heal_multiplier = 1.0

        has_deep_wounds = any(
            e.type == EffectType.DEEP_WOUNDS_STRIKE
            for e in unit_state.effects_on_strike
        )
        neut_deep_wounds = any(
            e.type == EffectType.NEUT_DEEP_WOUNDS_STRIKE
            for e in unit_state.effects_on_strike
        )

        if has_deep_wounds and not neut_deep_wounds:
            heal_multiplier = 0.0

        amount = math.trunc(amount * heal_multiplier)
        if amount <= 0:
            return

        new_hp = unit_state.current_hp + amount
        unit_state.current_hp = min(unit_state.unit.base_stats.hp, new_hp)

    def _combat_stat_calculations(self):
        """Calculates combat stats incorporating STAT_BOOST and STAT_debuff effects."""
        # Initialize with visible stats
        atk_vals = {
            stat: self.attacker.get_visible_stat(stat)
            for stat in ["hp", "atk", "spd", "defense", "res"]
        }
        def_vals = {
            stat: self.defender.get_visible_stat(stat)
            for stat in ["hp", "atk", "spd", "defense", "res"]
        }

        self.combatant_states["attacker"].combat_stats = StatBlock(**atk_vals)
        self.combatant_states["defender"].combat_stats = StatBlock(**def_vals)

        # 2. Apply stat boosts/debuff
        for state, foe_state in [
            (self.combatant_states["attacker"], self.combatant_states["defender"]),
            (self.combatant_states["defender"], self.combatant_states["attacker"]),
        ]:
            for effect in state.effects_start_of_combat:
                if effect.type in (EffectType.STAT_BUFF, EffectType.STAT_DEBUFF):
                    stats_to_mod = effect.params.get("stats", [])
                    val = self._resolve_formula(effect.params, state, foe_state)

                    if effect.type == EffectType.STAT_DEBUFF:
                        val = -abs(val)

                    for stat in stats_to_mod:
                        current = getattr(state.combat_stats, stat)
                        setattr(state.combat_stats, stat, current + val)

        self.attacker.combat_stats = self.combatant_states["attacker"].combat_stats
        self.defender.combat_stats = self.combatant_states["defender"].combat_stats

        # Adaptive damage targeting
        self.combatant_states[
            "defender"
        ].defensive_stat = self._determine_defensive_stat(
            striker_state=self.combatant_states["attacker"],
            target_state=self.combatant_states["defender"],
        )

        self.combatant_states[
            "attacker"
        ].defensive_stat = self._determine_defensive_stat(
            striker_state=self.combatant_states["defender"],
            target_state=self.combatant_states["attacker"],
        )

    def _determine_defensive_stat(
        self, striker_state: CombatantState, target_state: CombatantState
    ) -> Literal["defense", "res"]:
        """Checks for Hexblade/Adaptive effects and returns the correct targeted stat."""
        target_stat = "defense" if striker_state.unit.is_physical() else "res"
        has_hexblade = any(
            e.type == EffectType.HEXBLADE_STRIKE
            for e in striker_state.effects_on_strike
        )

        if has_hexblade:
            if target_state.combat_stats.res < target_state.combat_stats.defense:
                target_stat = "res"
            else:
                target_stat = "defense"

        return target_stat

    def _determine_strike_sequence(self) -> list[Strike]:
        """Calculates the combat sequence using effects_strike_sequence instead of keywords."""
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        spd_diff = atk_state.combat_stats.spd - def_state.combat_stats.spd
        attacker_spd_check = 1 if spd_diff > 5 else 0
        defender_spd_check = 1 if spd_diff < -5 else 0

        nb_attacker_GFU = sum(
            1 for e in atk_state.effects_strike_sequence if e.type == EffectType.GFU
        )
        nb_defender_GFU = sum(
            1 for e in def_state.effects_strike_sequence if e.type == EffectType.GFU
        )

        nb_attacker_FU_denial = sum(
            1 for e in def_state.effects_strike_sequence if e.type == EffectType.FU_DENY
        )
        nb_defender_FU_denial = sum(
            1 for e in atk_state.effects_strike_sequence if e.type == EffectType.FU_DENY
        )

        attacker_off_NFU = (
            1
            if any(
                e.type == EffectType.FU_DENY for e in atk_state.effects_strike_sequence
            )
            else 0
        )
        attacker_def_NFU = (
            1
            if any(
                e.type == EffectType.FU_DENY for e in atk_state.effects_strike_sequence
            )
            else 0
        )
        defender_off_NFU = (
            1
            if any(
                e.type == EffectType.FU_DENY for e in def_state.effects_strike_sequence
            )
            else 0
        )
        defender_def_NFU = (
            1
            if any(
                e.type == EffectType.FU_DENY for e in def_state.effects_strike_sequence
            )
            else 0
        )

        attacker_FU = (
            nb_attacker_GFU * (1 - defender_def_NFU)
            - nb_defender_FU_denial * (1 - attacker_off_NFU)
            + attacker_spd_check
        )
        defender_FU = (
            nb_defender_GFU * (1 - attacker_def_NFU)
            - nb_attacker_FU_denial * (1 - defender_off_NFU)
            + defender_spd_check
        )

        # Check for Brave and Potent via effects
        attacker_brave = any(
            e.type == EffectType.BRAVE for e in atk_state.effects_strike_sequence
        )
        defender_brave = any(
            e.type == EffectType.BRAVE for e in def_state.effects_strike_sequence
        )

        attacker_potent = (
            any(e.type == EffectType.POTENT for e in atk_state.effects_strike_sequence)
            and spd_diff >= 25
        )
        defender_potent = (
            any(e.type == EffectType.POTENT for e in def_state.effects_strike_sequence)
            and spd_diff <= -25
        )

        attacker_brave_fu = attacker_brave and not attacker_potent
        defender_brave_fu = defender_brave and not defender_potent

        attacker_first = [Strike("attacker", "defender", StrikeType.FIRST)]
        if attacker_brave:
            attacker_first.append(
                Strike(
                    "attacker",
                    "defender",
                    StrikeType.FIRST,
                    brave_second_hit=True,
                    consecutive=True,
                )
            )

        attacker_followups = []
        if attacker_FU > 0:
            attacker_followups.append(
                Strike("attacker", "defender", StrikeType.FOLLOW_UP)
            )
            if attacker_brave_fu:
                attacker_followups.append(
                    Strike(
                        "attacker",
                        "defender",
                        StrikeType.FOLLOW_UP,
                        brave_second_hit=True,
                        consecutive=True,
                    )
                )
        if attacker_potent:
            attacker_followups.append(
                Strike("attacker", "defender", StrikeType.POTENT, consecutive=True)
            )

        defender_first = [Strike("defender", "attacker", StrikeType.FIRST)]
        if defender_brave:
            defender_first.append(
                Strike(
                    "defender",
                    "attacker",
                    StrikeType.FIRST,
                    brave_second_hit=True,
                    consecutive=True,
                )
            )

        defender_followups = []
        if defender_FU > 0:
            defender_followups.append(
                Strike("defender", "attacker", StrikeType.FOLLOW_UP)
            )
            if defender_brave_fu:
                defender_followups.append(
                    Strike(
                        "defender",
                        "attacker",
                        StrikeType.FOLLOW_UP,
                        brave_second_hit=True,
                        consecutive=True,
                    )
                )
        if defender_potent:
            defender_followups.append(
                Strike("defender", "attacker", StrikeType.POTENT, consecutive=True)
            )

        attacker_flash_effective = any(
            e.type == EffectType.FLASH for e in atk_state.effects_strike_sequence
        )
        if attacker_flash_effective:
            defender_first = []
            defender_followups = []

        attacker_package = attacker_first + attacker_followups
        defender_package = defender_first + defender_followups

        defender_vantage = any(
            e.type == EffectType.VANTAGE for e in def_state.effects_strike_sequence
        )
        attacker_desperation = any(
            e.type == EffectType.DESPERATION for e in atk_state.effects_strike_sequence
        )

        if defender_vantage and attacker_desperation:
            strike_sequence = (
                defender_first
                + attacker_first
                + attacker_followups
                + defender_followups
            )
        elif defender_vantage:
            strike_sequence = (
                defender_first
                + attacker_first
                + defender_followups
                + attacker_followups
            )
        elif attacker_desperation:
            strike_sequence = attacker_package + defender_package
        else:
            strike_sequence = (
                attacker_first
                + defender_first
                + attacker_followups
                + defender_followups
            )

        return strike_sequence

    def _phase_pre_combat(self):
        """Processes PRE_CBT_DAMAGE and PRE_CBT_HEAL."""
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        atk_state.unit.start_of_combat_hp = atk_state.current_hp
        def_state.unit.start_of_combat_hp = def_state.current_hp

        # Process Pre-Combat Damage
        atk_predmg = sum(
            self._resolve_formula(e.params, atk_state, def_state)
            for e in atk_state.effects_pre_combat
            if e.type == EffectType.PRE_CBT_DAMAGE
        )
        def_predmg = sum(
            self._resolve_formula(e.params, def_state, atk_state)
            for e in def_state.effects_pre_combat
            if e.type == EffectType.PRE_CBT_DAMAGE
        )

        if atk_predmg > 0:
            def_state.current_hp = max(1, def_state.current_hp - atk_predmg)
        if def_predmg > 0:
            atk_state.current_hp = max(1, atk_state.current_hp - def_predmg)

        # Process Pre-Combat Heal
        atk_preheal = sum(
            self._resolve_formula(e.params, atk_state, def_state)
            for e in atk_state.effects_pre_combat
            if e.type == EffectType.PRE_CBT_HEAL
        )
        def_preheal = sum(
            self._resolve_formula(e.params, def_state, atk_state)
            for e in def_state.effects_pre_combat
            if e.type == EffectType.PRE_CBT_HEAL
        )

        self._apply_healing(atk_state, atk_preheal)
        self._apply_healing(def_state, def_preheal)

    def _process_strike(self, strike: Strike):
        """Fully data-driven strike processing via effects_on_strike."""
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]

        raw_atk = striker_state.combat_stats.atk
        defensive_stat = getattr(target_state.combat_stats, target_state.defensive_stat)

        wta = self._get_wta_multiplier(striker_state.unit, target_state.unit)
        is_effective = any(
            e.type == EffectType.EFFECTIVE and self._strike_matches(strike, e.params)
            for e in striker_state.effects_on_strike
        )
        is_neut_effective = any(
            e.type == EffectType.NEUT_EFFECTIVE for e in target_state.effects_on_strike
        )

        if is_effective and not is_neut_effective:
            raw_atk = math.trunc(raw_atk * 1.5)

        modified_atk = math.trunc(raw_atk * wta)
        base_damage = max(0, modified_atk - defensive_stat)

        true_damage = 0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.FLAT_DAMAGE_STRIKE and self._strike_matches(
                strike, effect.params
            ):
                true_damage += self._resolve_formula(
                    effect.params, striker_state, target_state
                )

        final_damage = base_damage + true_damage
        pre_mitigation_damage = final_damage

        pierce_mult = 1.0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.DR_PIERCE and self._strike_matches(
                strike, effect.params
            ):
                pierce_value = effect.params.get("value", 0) / 100.0
                pierce_mult *= 1.0 - pierce_value

        base_dr = 0.0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.PERC_DR_STRIKE and self._strike_matches(
                strike, effect.params
            ):
                dr_val = (
                    self._resolve_formula(effect.params, target_state, striker_state)
                    / 100.0
                )
                base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - dr_val))

        effective_dr = base_dr * pierce_mult
        damage_multiplier = 1.0 - effective_dr
        final_damage = math.trunc(final_damage * damage_multiplier)

        flat_dr = 0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.FLAT_DR_STRIKE and self._strike_matches(
                strike, effect.params
            ):
                flat_dr += self._resolve_formula(
                    effect.params, target_state, striker_state
                )

        final_damage = max(0, final_damage - flat_dr)

        dmg_floor = None
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.DR_FLOOR and self._strike_matches(
                strike, effect.params
            ):
                floor = self._resolve_formula(
                    effect.params, target_state, striker_state
                )
                dmg_floor = floor if dmg_floor is None else min(dmg_floor, floor)

        if dmg_floor is not None and final_damage > dmg_floor:
            final_damage = dmg_floor

        mitigated_amount = pre_mitigation_damage - final_damage
        target_state.damage_mitigated_bucket += mitigated_amount
        target_state.current_hp -= final_damage

        hit_heal = 0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.HEAL_STRIKE and self._strike_matches(
                strike, effect.params
            ):
                hit_heal += self._resolve_formula(
                    effect.params, striker_state, target_state
                )
        self._apply_healing(striker_state, hit_heal)

        pulse_charge = 1
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.PULSE_STRIKE and self._strike_matches(
                strike, effect.params
            ):
                pulse_charge += self._resolve_formula(
                    effect.params, striker_state, target_state
                )
        striker_state.current_cooldown -= max(0, pulse_charge)
