import math
from dataclasses import dataclass, field
from typing import Literal
from .build import Unit, StatBlock
from .constants import Color, StrikeType, MovementType, WeaponType, EffectType
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
        attacker.unit.weapon, attacker.unit.special,
        attacker.unit.a_slot, attacker.unit.b_slot, attacker.unit.c_slot,
        attacker.unit.s_slot, attacker.unit.x_slot
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
        defender.unit.weapon, defender.unit.special,
        attacker.unit.a_slot, defender.unit.b_slot, defender.unit.c_slot,
        defender.unit.s_slot, defender.unit.x_slot
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
        """
        Runs the full combat simulation and returns the final HP for both units.
        """
        attacker_state = CombatantState(
                unit=self.attacker,
                current_hp=self.attacker.current_hp,
                current_cooldown=self.attacker.max_cooldown - self.attacker.pre_charge,
            )
        defender_state = CombatantState(
                unit=self.defender,
                current_hp=self.defender.current_hp,
                current_cooldown=self.defender.max_cooldown - self.defender.pre_charge,
            )

        self.combatant_states = {
            "attacker": attacker_state,
            "defender": defender_state
        }

        _distribute_effects(attacker_state, defender_state)

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
            self._process_strike(strike)  # CD pulses and healing calc in there too

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
                "effects_AoE", "effects_start_of_combat", "effects_strike_sequence",
                "effects_pre_combat", "effects_on_strike", "effects_after_combat",
            ):
                updated_conditions = []
                for effect in getattr(state, list_name):
                    keep, remaining_conditions = _evaluate_conditions_for_effect(effect, state, foe_state, phase)
                    if keep:
                        effect.conditions = remaining_conditions
                        updated_conditions.append(effect)
                setattr(state, list_name, updated_conditions)

    def _apply_healing(self, unit: Unit, amount: int):
        """Enforces Deep Wounds, Imbue, and Max HP caps."""
        if amount <= 0:
            return
        heal_multiplier = 1.0

        if unit.has_keyword("deep_wounds") and not unit.has_keyword(
            "neutralize_deep_wounds"
        ):
            base_penalty = 1.0

            partial_stacks = unit.count_keyword("partial_deep_wounds")

            actual_penalty = base_penalty * (0.5**partial_stacks)

            heal_multiplier -= actual_penalty

            amount = math.trunc(amount * heal_multiplier)

        if amount <= 0:
            return

        new_hp = unit.current_hp + amount
        unit.current_hp = min(unit.base_stats.hp, new_hp)

    def _process_AoE(self, effect: Effect):
        """Applies AoE damage"""
        # TODO: include bonus damage and DR effects
        striker = self.combatant_states["attacker"]
        target = self.combatant_states["defender"]
        
        visible_atk = striker.unit.get_visible_stat("atk")
        visible_defensive_stat = target.unit.get_visible_stat("defense") if striker.unit.is_physical() else target.unit.get_visible_stat("res")
        
        coefficient = effect.params['coefficient']

        damage = max(0, math.floor(coefficient * (visible_atk - visible_defensive_stat)))
        target.current_hp = max(1, target.current_hp - damage)

    def _process_strike(self, strike: Strike):
        """Calculates and applies damage for a single weapon swing."""
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]

        striker = striker_state.unit
        target = target_state.unit

        raw_atk = striker_state.combat_stats.atk
        defensive_stat = (
            target_state.combat_stats.defense
            if target_state.defensive_stat == "defense"
            else target_state.combat_stats.res
        )

        special_triggered = False
        if striker_state.current_cooldown == 0 and striker.special is not None:
            is_defensive = "defensive_special" in striker.special.utilities.keywords
            is_aoe = "aoe_special" in striker.special.utilities.keywords
            if not is_defensive and not is_aoe:
                special_triggered = True

        wta = self._get_wta_multiplier(striker, target)

        # Effectiveness calculation
        is_effective = False
        if target.movement_type == MovementType.ARMOR and striker.has_keyword(
            "effective_armor"
        ):
            if not target.has_keyword("neutralize_effective_armor"):
                is_effective = True
        elif target.movement_type == MovementType.CAVALRY and striker.has_keyword(
            "effective_cavalry"
        ):
            if not target.has_keyword("neutralize_effective_cavalry"):
                is_effective = True
        elif target.movement_type == MovementType.FLIER and striker.has_keyword(
            "effective_flier"
        ):
            if not target.has_keyword("neutralize_effective_flying"):
                is_effective = True
        elif target.weapon_type == WeaponType.DRAGON and striker.has_keyword(
            "effective_dragon"
        ):
            if not target.has_keyword("neutralize_effective_dragon"):
                is_effective = True

        if is_effective:
            raw_atk = math.trunc(raw_atk * 1.5)

        modified_atk = math.trunc(raw_atk * wta)

        base_damage = max(0, modified_atk - defensive_stat)
        # ------------------------------------------------------------------------
        # CALCULATE DR PIERCE

        pierce_mult = 1.0

        if striker.has_keyword("pierce_100"):
            pierce_mult = 0.0

        if striker.has_keyword("pierce_special_100") and special_triggered:
            pierce_mult = 0.0

        if pierce_mult > 0.0:
            pierce_50_count = sum(
                1
                for item in striker.equipped_items
                if "pierce_50" in item.utilities.keywords
            )

            from .jsonbootupstuff import STATUS_EFFECT_DATABASE

            for status_name in striker.active_statuses:
                if status_data := STATUS_EFFECT_DATABASE.get(status_name):
                    if "pierce_50" in status_data["utilities"].keywords:
                        pierce_50_count += 1

            pierce_mult *= 0.5**pierce_50_count
        # ------------------------------------------------------------------------
        # true dmg stuff here
        true_damage = sum(
            item.utilities.truedmg_logic(striker, target)
            for item in striker.equipped_items
            if item.utilities.truedmg_logic is not None
        )

        true_damage += sum(
            item.utilities.truedmg
            for item in striker.equipped_items
            if hasattr(item.utilities, "truedmg")
        )

        for status_name in striker.active_statuses:
            status_data = STATUS_EFFECT_DATABASE.get(status_name)
            if status_data:
                utilities = status_data["utilities"]

                # Add flat status true damage
                true_damage += getattr(utilities, "truedmg", 0)

                # Add dynamic status true damage
                if getattr(utilities, "truedmg_logic", None) is not None:
                    true_damage += utilities.truedmg_logic(striker, target)
        # ------------------------------------------------------------------------
        final_damage = base_damage + true_damage
        pre_mitigation_damage = final_damage
        # for reflex
        mitigated_amount = 0
        # ------------------------------------------------------------------------
        # CALCULATE PERCENT DAMAGE REDUCTION
        base_dr = 0.0

        is_first_sequence = strike.strike_type is StrikeType.FIRST
        is_absolute_first_strike = (
            strike.strike_type is StrikeType.FIRST and not strike.brave_second_hit
        )

        # A CHECK FOR LEGACY DR THAT IS ONLY FIRST HIT (NO BRAVE)
        is_first_strike = (
            strike.strike_type is StrikeType.FIRST and not strike.brave_second_hit
        )
        for item in target.equipped_items:
            # check weapons/skills
            if is_first_strike:
                first_dr = getattr(item.utilities, "first_hit_percent_dr", 0.0)
                if first_dr > 0:
                    base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - first_dr))

            if is_first_sequence:
                seq_dr = getattr(item.utilities, "first_sequence_percent_dr", 0.0)
                if seq_dr > 0:
                    base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - seq_dr))

            perma_dr = getattr(item.utilities, "perma_percent_dr", 0.0)
            if perma_dr > 0:
                base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - perma_dr))

        # B. Check Active Statuses
        for status_name in target.active_statuses:
            if status_data := STATUS_EFFECT_DATABASE.get(status_name):
                utilities = status_data["utilities"]

                if is_absolute_first_strike:
                    status_first_dr = getattr(utilities, "first_hit_percent_dr", 0.0)
                    if status_first_dr > 0:
                        base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - status_first_dr))

                if is_first_sequence:
                    status_seq_dr = getattr(utilities, "first_sequence_percent_dr", 0.0)
                    if status_seq_dr > 0:
                        base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - status_seq_dr))

                status_perma_dr = getattr(utilities, "perma_percent_dr", 0.0)
                if status_perma_dr > 0:
                    base_dr = 1.0 - ((1.0 - base_dr) * (1.0 - status_perma_dr))

        # Apply Pierce & Calculate Post-% DR Damage
        effective_dr = base_dr * pierce_mult
        damage_multiplier = 1.0 - effective_dr
        final_damage = math.trunc(final_damage * damage_multiplier)
        # ------------------------------------
        # First-hit damage floor (Collapsed Star and similar)
        if is_first_sequence:
            for status_name in target.active_statuses:
                if status_data := STATUS_EFFECT_DATABASE.get(status_name):
                    if fn := status_data["utilities"].first_hit_dmg_floor_logic:
                        dmg_floor = fn(target, striker)
                        if final_damage > dmg_floor:
                            mitigated_amount += final_damage - dmg_floor
                            final_damage = dmg_floor
        # ------------------------------------
        dmg_floor = None

        for item in target.equipped_items:
            if getattr(item.utilities, "dmg_floor_logic", None):
                floor = item.utilities.dmg_floor_logic(target, striker, strike)
                if floor is not None:
                    dmg_floor = floor if dmg_floor is None else min(dmg_floor, floor)

        for status_name in target.active_statuses:
            if status_data := STATUS_EFFECT_DATABASE.get(status_name):
                utilities = status_data["utilities"]
                if getattr(utilities, "dmg_floor_logic", None):
                    floor = utilities.dmg_floor_logic(target, striker, strike)
                    if floor is not None:
                        dmg_floor = (
                            floor if dmg_floor is None else min(dmg_floor, floor)
                        )

        if dmg_floor is not None and final_damage > dmg_floor:
            mitigated_amount += final_damage - dmg_floor
            final_damage = dmg_floor
        # ------------------------------------

        mitigated_amount = pre_mitigation_damage - final_damage

        target.damage_mitigated_bucket += mitigated_amount

        target_state.current_hp -= final_damage

        hit_heal = sum(
            item.utilities.heal_hit_logic(striker, target)
            for item in striker.equipped_items
            if getattr(item.utilities, "heal_hit_logic", None)
        )
        self._apply_healing(striker, hit_heal)

        charge = (
            1
            + striker.get_pulse_amount("per_unit_attack", target)
            + target.get_pulse_amount("per_foe_attack", striker)
        )
        striker_state.current_cooldown -= max(0, charge)

    def _get_wta_multiplier(self, striker: Unit, target: Unit) -> float:
        """Calculates the final WTA multiplier, including Triangle Adept/Cancel Affinity."""
        advantage = self._check_color_advantage(striker, target)
        if advantage == 0:
            return 1.0

        mult = 1.0 + (0.20 * advantage)
        has_ta = striker.has_keyword("triangle_adept") or target.has_keyword(
            "triangle_adept"
        )
        has_ca = striker.has_keyword("cancel_affinity") or target.has_keyword(
            "cancel_affinity"
        )

        if has_ta and not has_ca:
            mult += 0.20 * advantage
        return mult

    def _check_color_advantage(self, striker: Unit, target: Unit) -> int:
        """Determines if the striker has color advantage (1), disadvantage (-1), or neutral (0)."""
        if striker.has_keyword("raven_tome") and target.color == Color.COLORLESS:
            return 1
        if target.has_keyword("raven_tome") and striker.color == Color.COLORLESS:
            return -1

        match striker.color:
            case Color.RED:
                return (
                    1
                    if target.color == Color.GREEN
                    else (-1 if target.color == Color.BLUE else 0)
                )
            case Color.GREEN:
                return (
                    1
                    if target.color == Color.BLUE
                    else (-1 if target.color == Color.RED else 0)
                )
            case Color.BLUE:
                return (
                    1
                    if target.color == Color.RED
                    else (-1 if target.color == Color.GREEN else 0)
                )
            case _:
                return 0

    def _resolve_formula(self, params: dict, unit_state: CombatantState, foe_state: CombatantState) -> int:
        formula = params.get("formula", "")
        multiplier = params.get("multiplier", 0)
        flat = params.get("flat", 0)
        min_val = params.get("min", 0)
        max_val = params.get("max", -1)
        variable = 0.0
        if formula:
            cs = unit_state.combat_stats
            match formula:
                case "unit_cbt_atk": 
                    variable = cs.atk if cs else unit_state.unit.get_visible_stat("atk")
                case "unit_cbt_spd":
                    variable = cs.spd if cs else unit_state.unit.get_visible_stat("spd")
                case "unit_cbt_def":
                    variable = cs.defense if cs else unit_state.unit.get_visible_stat("defense")
                case "unit_cbt_res":
                    variable = cs.res if cs else unit_state.unit.get_visible_stat("res")
                case "max_cooldown":
                    variable = unit_state.unit.max_cooldown
                case "num_bonus_and_penalties_on_unit":
                    variable = unit_state.bonus_count + unit_state.penalty_count

        value = math.floor(variable * multiplier) + flat
        if min_val >= 0: value = max(value, min_val)
        if max_val >= 0: value = min(value, max_val)
        return value

    def _strike_matches(self, strike: Strike, params: dict) -> bool:
        match params.get("strike", "every_strike"):
            case "every_strike":
                return True
            case "first_strike":
                return strike.strike_type is StrikeType.FIRST and not strike.brave_second_hit
            case "first_sequence":
                return strike.strike_type is StrikeType.FIRST
            case "first_strike_with_brave":
                return strike.strike_type is StrikeType.FIRST and strike.brave_second_hit

    def _start_of_turn(self):
        """"""
        # update cooldowns

    def _phase_AoE(self):
        """AoE"""
        for effect in self.combatant_states["attacker"].effects_AoE:
            if effect.type == EffectType.TRIGGER_AOE and self.combatant_states["attacker"].current_cooldown == 0:
                self._process_AoE(effect)

    def _combat_stat_calculations(self):
        """Calculates combat stats for both units."""
        atk_vals, def_vals = {}, {}
        for stat in ["hp", "atk", "spd", "defense", "res"]:
            atk_vals[stat] = self.attacker.get_combat_stat(stat, self.defender)
            def_vals[stat] = self.defender.get_combat_stat(stat, self.attacker)

        self.combatant_states["attacker"].combat_stats = StatBlock(**atk_vals)
        self.combatant_states["defender"].combat_stats = StatBlock(**def_vals)

        self.attacker.combat_stats = self.combatant_states["attacker"].combat_stats
        self.defender.combat_stats = self.combatant_states["defender"].combat_stats

        # Determine targeting for Attacker targeting Defender
        attacker_targets = "defense" if self.attacker.is_physical() else "res"
        for item in self.attacker.equipped_items:
            if item.utilities.adaptive_logic:
                attacker_targets = item.utilities.adaptive_logic(
                    self.attacker, self.defender
                )
        for s in self.attacker.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                if info["utilities"].adaptive_logic:
                    attacker_targets = info["utilities"].adaptive_logic(
                        self.attacker, self.defender
                    )
        self.combatant_states["defender"].defensive_stat = attacker_targets

        # Determine targeting for Defender targeting Attacker
        defender_targets = "defense" if self.defender.is_physical() else "res"
        for item in self.defender.equipped_items:
            if item.utilities.adaptive_logic:
                defender_targets = item.utilities.adaptive_logic(
                    self.defender, self.attacker
                )
        for s in self.defender.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                if info["utilities"].adaptive_logic:
                    defender_targets = info["utilities"].adaptive_logic(
                        self.defender, self.attacker
                    )
        self.combatant_states["attacker"].defensive_stat = defender_targets

    def _determine_strike_sequence(self) -> list[Strike]:
        """Determines the number and order of strikes."""
        # Assuming no effects preventing defender's counterattacks or effects that change attack priority
        spd_diff = (
            self.combatant_states["attacker"].combat_stats.spd
            - self.combatant_states["defender"].combat_stats.spd
        )
        attacker_spd_check = 1 if spd_diff > 5 else 0
        defender_spd_check = 1 if spd_diff < -5 else 0

        # check if they can counterattack while flashed
        defender_NCD = self.defender.count_keyword("NCD")
        attacker_Flash = self.attacker.count_keyword("flash")

        nb_attacker_GFU = self.attacker.count_keyword("guaranteed_follow_up")
        nb_defender_GFU = self.defender.count_keyword("guaranteed_follow_up")

        nb_attacker_FU_denial = self.defender.count_keyword("foe_cannot_follow_up")
        nb_defender_FU_denial = self.attacker.count_keyword("foe_cannot_follow_up")

        attacker_off_NFU = 1 if self.attacker.has_keyword("null_follow_up") else 0
        attacker_def_NFU = 1 if self.attacker.has_keyword("null_follow_up") else 0
        defender_off_NFU = 1 if self.defender.has_keyword("null_follow_up") else 0
        defender_def_NFU = 1 if self.defender.has_keyword("null_follow_up") else 0

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

        attacker_brave = self.attacker.has_keyword("brave_weapon")
        defender_brave = self.defender.has_keyword("brave_weapon")

        attacker_spd = self.combatant_states["attacker"].combat_stats.spd
        defender_spd = self.combatant_states["defender"].combat_stats.spd
        spd_diff = attacker_spd - defender_spd

        attacker_potent = self.attacker.has_keyword("potent") and spd_diff >= 25
        defender_potent = self.defender.has_keyword("potent") and spd_diff <= -25

        attacker_brave_fu = attacker_brave and not attacker_potent
        defender_brave_fu = defender_brave and not defender_potent

        attacker_first = [
            Strike("attacker", "defender", StrikeType.FIRST, is_first_hit=True)
        ]
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
            if attacker_brave_fu:  # brave doubles FU only if no potent
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

        # Standard desperation — PP Only
        attacker_desperation = self.attacker.has_keyword("desperation")

        # Special version — no initiation requirement, can apply on ep (Marth for example)
        attacker_desp_effect = self.attacker.has_keyword("dualphasedesperation")
        defender_desp_effect = self.defender.has_keyword("dualphasedesperation")

        attacker_flash_effective = (
            attacker_Flash > 0
            or self.defender.has_keyword("counterattacks_disrupted")
            and defender_NCD == 0
        )

        if attacker_flash_effective:
            defender_first = []
            defender_followups = []

        attacker_package = attacker_first + attacker_followups
        defender_package = defender_first + defender_followups

        attacker_package = attacker_first + attacker_followups
        defender_package = defender_first + defender_followups

        defender_vantage = self.defender.has_keyword("vantage")
        attacker_bunches = attacker_desperation or attacker_desp_effect
        defender_bunches = defender_desp_effect

        # psuedo code
        # if hardy bearing:
        # strike_sequence = ()
        if defender_vantage and defender_bunches:
            strike_sequence = defender_package + attacker_package
        elif defender_vantage:
            strike_sequence = (
                defender_first
                + attacker_first
                + defender_followups
                + attacker_followups
            )
        elif attacker_bunches:
            strike_sequence = attacker_package + defender_package
        elif defender_vantage and attacker_bunches:
            strike_sequence = (
                defender_first
                + attacker_first
                + attacker_followups
                + defender_followups
            )
        else:
            strike_sequence = (
                attacker_first
                + defender_first
                + attacker_followups
                + defender_followups
            )

        return strike_sequence

    def _phase_pre_combat(self):
        """Pre-combat damage and healing effects."""

        # 1. HP SNAPSHOT (For conditional HP checks)
        self.attacker.start_of_combat_hp = self.attacker.current_hp
        self.defender.start_of_combat_hp = self.defender.current_hp

        # 2. PRE-COMBAT DAMAGE
        atk_predmg = sum(
            item.utilities.predmg_logic(self.attacker, self.defender)
            for item in self.attacker.equipped_items
            if getattr(item.utilities, "predmg_logic", None)
        )
        def_predmg = sum(
            item.utilities.predmg_logic(self.defender, self.attacker)
            for item in self.defender.equipped_items
            if getattr(item.utilities, "predmg_logic", None)
        )

        if atk_predmg > 0:
            self.defender.current_hp = max(1, self.defender.current_hp - atk_predmg)

        if def_predmg > 0:
            self.attacker.current_hp = max(1, self.attacker.current_hp - def_predmg)

        # 3. START OF COMBAT HEALING
        for combatant, opponent in [
            (self.attacker, self.defender),
            (self.defender, self.attacker),
        ]:
            heal = sum(
                item.utilities.heal_start_logic(combatant, opponent)
                for item in combatant.equipped_items
                if getattr(item.utilities, "heal_start_logic", None)
            )
            self._apply_healing(combatant, heal)
        self.combatant_states[
            "attacker"
        ].current_cooldown -= self.attacker.get_pulse_amount(
            "before_first_attack", self.defender
        )
        self.combatant_states[
            "defender"
        ].current_cooldown -= self.defender.get_pulse_amount(
            "before_first_attack", self.attacker
        )

    def _phase_after_combat(self):
        # self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
        #     "after_combat", self.defender
        # )
        # self.defender.current_cooldown -= self.defender.get_pulse_amount(
        #     "after_combat", self.attacker
        # )
        pass
        ...


