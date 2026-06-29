import math
from dataclasses import dataclass, field, replace
from typing import Literal

from .build import Unit, StatBlock
from .constants import Color, StrikeType, EffectType
from .effects import Effect, build_effect, EFFECT_LIST_MAP
from .conditions import Phase, Condition, AtomicCondition, AnyOf, AllOf

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
    is_initiator: bool = False
    triggers_brave: bool = False
    spaces_moved: int = 0
    effects_AoE: list[Effect] = field(default_factory=list)
    effects_start_of_combat: list[Effect] = field(default_factory=list)
    effects_strike_sequence: list[Effect] = field(default_factory=list)
    effects_pre_combat: list[Effect] = field(default_factory=list)
    effects_on_strike: list[Effect] = field(default_factory=list)
    effects_after_combat: list[Effect] = field(default_factory=list)


@dataclass
class Strike:
    striker: UnitRole
    target: UnitRole
    strike_type: StrikeType
    brave_second_hit: bool = False
    consecutive: bool = False
    is_first_hit: bool = False
    potent_mult: float = 1.0


def _distribute_effects(attacker: CombatantState, defender: CombatantState) -> None:
    attacker_skills = filter(
        None,
        [
            attacker.unit.weapon,
            attacker.unit.special,
            attacker.unit.a_slot,
            attacker.unit.b_slot,
            attacker.unit.c_slot,
            attacker.unit.s_slot,
            attacker.unit.x_slot,
        ],
    )
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

    defender_skills = filter(
        None,
        [
            defender.unit.weapon,
            defender.unit.special,
            defender.unit.a_slot,
            defender.unit.b_slot,
            defender.unit.c_slot,
            defender.unit.s_slot,
            defender.unit.x_slot,
        ],
    )
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
    if isinstance(cond, AllOf):
        return _check_allof(cond, phase, unit, foe)
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


def _check_allof(
    allof: AllOf,
    phase: Phase,
    unit: CombatantState,
    foe: CombatantState,
) -> bool | None:
    results = [_check_condition(c, phase, unit, foe) for c in allof.conditions]
    phase_results = [r for r in results if r is not None]
    if not phase_results:
        return None
    return all(phase_results)


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
        """Runs the full combat simulation following a 10-step timeline."""
        self.combatant_states = {
            "attacker": CombatantState(
                unit=self.attacker,
                current_hp=self.attacker.current_hp,
                current_cooldown=self.attacker.max_cooldown - self.attacker.pre_charge,
                is_initiator=True,
            ),
            "defender": CombatantState(
                unit=self.defender,
                current_hp=self.defender.current_hp,
                current_cooldown=self.defender.max_cooldown - self.defender.pre_charge,
                is_initiator=False,
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

    def _apply_healing(self, role: UnitRole, amount: int, phase: str = "in_combat"):
        """Applies healing, with respect to the Deep Wounds effect.

        phase: "pre_combat" | "in_combat" | "post_combat"

        How it works:
        - Deep Wounds blocks ALL healing (all phases).
        - Neutralize Deep Wounds turns it off entirely.
        - Reduce Deep Wounds applies to pre_combat and in_combat by default;
            post_combat is still fully blocked UNLESS a post-combat-relief
            reduce effect is present (rn only L!Fae, but im adding this for a
            "just in case".
        - Reduce rounds the surviving heal UP (ceil).
        """
        if amount <= 0:
            return

        unit_state = self.combatant_states[role]
        foe_role: UnitRole = "defender" if role == "attacker" else "attacker"
        foe_state = self.combatant_states[foe_role]

        if phase == "post_combat":
            effects = unit_state.effects_after_combat
            dw_type = EffectType.DEEP_WOUNDS_POST_CBT
            neut_type = EffectType.NEUT_DEEP_WOUNDS_POST_CBT
            reduce_type = EffectType.REDUCE_DEEP_WOUNDS_POST_CBT
        else:
            effects = unit_state.effects_on_strike
            dw_type = EffectType.DEEP_WOUNDS_IN_CBT
            neut_type = EffectType.NEUT_DEEP_WOUNDS_IN_CBT
            reduce_type = EffectType.REDUCE_DEEP_WOUNDS_IN_CBT

        if any(e.type == dw_type for e in effects):
            if not any(e.type == neut_type for e in effects):
                survive = 1.0
                found = False
                for e in effects:
                    if e.type != reduce_type:
                        continue
                    # The effect sits in unit_state's list, but its formula may
                    # scale off whoever OWNS it. applied_by == "foe" means the foe
                    # inflicted it, so the foe's state is the formula's "unit".
                    if e.applied_by == "foe":
                        owner, opponent = foe_state, unit_state
                    else:
                        owner, opponent = unit_state, foe_state
                    pct = self._resolve_formula(e.params, owner, opponent)
                    survive *= (100 - pct) / 100
                    found = True
                if not found:
                    return
                amount = math.ceil(amount * survive)

        if amount <= 0:
            return
        new_hp = unit_state.current_hp + amount
        unit_state.current_hp = min(unit_state.unit.base_stats.hp, new_hp)

    def _phase_AoE(self):
        """Processes effects_AoE. Only the initiator can trigger an AoE special."""
        state = self.combatant_states["attacker"]
        foe_state = self.combatant_states["defender"]

        pulse = sum(
            self._resolve_formula(e.params, state, foe_state)
            for e in state.effects_AoE
            if e.type == EffectType.PULSE_AOE
        )
        state.current_cooldown -= max(0, pulse)

        triggers = [e for e in state.effects_AoE if e.type == EffectType.TRIGGER_AOE]
        if not triggers or state.current_cooldown > 0:
            return

        has_hexblade_aoe = any(
            e.type == EffectType.HEXBLADE_AOE for e in state.effects_AoE
        )
        if has_hexblade_aoe:
            visible_def = min(
                foe_state.unit.get_visible_stat("defense"),
                foe_state.unit.get_visible_stat("res"),
            )
        else:
            visible_def = (
                foe_state.unit.get_visible_stat("defense")
                if state.unit.is_physical()
                else foe_state.unit.get_visible_stat("res")
            )

        coefficient = triggers[0].params.get("coefficient", 0.0)
        visible_atk = state.unit.get_visible_stat("atk")
        damage = max(0, math.floor(coefficient * (visible_atk - visible_def)))

        for e in state.effects_AoE:
            if e.type == EffectType.FLAT_DAMAGE_AOE:
                damage += self._resolve_formula(e.params, state, foe_state)

        flat_dr = sum(
            self._resolve_formula(e.params, foe_state, state)
            for e in foe_state.effects_AoE
            if e.type == EffectType.FLAT_DR_AOE
        )
        damage = max(0, damage - flat_dr)

        foe_state.current_hp = max(1, foe_state.current_hp - damage)
        state.special_use_count += 1
        state.current_cooldown = state.unit.max_cooldown

    def _combat_stat_calculations(self):
        """Calculates combat stats incorporating STAT_BOOST and STAT_DAUNT effects."""
        self.attacker.start_of_combat_hp = self.combatant_states["attacker"].current_hp
        self.defender.start_of_combat_hp = self.combatant_states["defender"].current_hp

        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        atk_ignore_debuffs = any(
            e.type == EffectType.PENALTY_NEUT for e in atk_state.effects_start_of_combat
        )
        def_ignore_debuffs = any(
            e.type == EffectType.PENALTY_NEUT for e in def_state.effects_start_of_combat
        )
        atk_ignore_buffs = any(
            e.type == EffectType.BONUS_NEUT for e in def_state.effects_start_of_combat
        )
        def_ignore_buffs = any(
            e.type == EffectType.BONUS_NEUT for e in atk_state.effects_start_of_combat
        )

        atk_vals = {
            stat: self.attacker.get_visible_stat(
                stat, ignore_buffs=atk_ignore_buffs, ignore_debuffs=atk_ignore_debuffs
            )
            for stat in ["hp", "atk", "spd", "defense", "res"]
        }
        def_vals = {
            stat: self.defender.get_visible_stat(
                stat, ignore_buffs=def_ignore_buffs, ignore_debuffs=def_ignore_debuffs
            )
            for stat in ["hp", "atk", "spd", "defense", "res"]
        }

        atk_state.combat_stats = StatBlock(**atk_vals)
        def_state.combat_stats = StatBlock(**def_vals)

        # Apply in-combat STAT_BOOST / STAT_DAUNT effects.
        # These live in effects_start_of_combat and were previously never applied.
        for state, foe in ((atk_state, def_state), (def_state, atk_state)):
            for effect in state.effects_start_of_combat:
                if effect.type not in (EffectType.STAT_BOOST, EffectType.STAT_DAUNT):
                    continue

                # applied_by == "foe" means the foe inflicted this effect, so the
                # foe's state is the formula's "unit" (matches the healing/DW crossover).
                if effect.applied_by == "foe":
                    owner, opponent = foe, state
                else:
                    owner, opponent = state, foe

                magnitude = self._resolve_formula(effect.params, owner, opponent)
                if effect.type == EffectType.STAT_DAUNT:
                    magnitude = -abs(magnitude)

                stats = effect.params.get("stats", [])
                updates = {
                    s: getattr(state.combat_stats, s) + magnitude for s in stats
                }
                state.combat_stats = replace(state.combat_stats, **updates)

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
    
    def _potent_active(self, effects, spd_diff, is_attacker, made_fu, triggers_brave):
        current_mult = 0
        final_mult = 0
        potent_check = 0

        """Determine the highest multiplier for the potent hit. We need to add a condition to make sure the unit is allowed to meet each one in the first place."""
        current_mult = self._potent_check_10
        if final_mult < current_mult:
            final_mult = current_mult

        current_mult = self._potent_check_25
        if final_mult < current_mult:
            final_mult = current_mult

        current_mult = self._potent_check_30
        if final_mult < current_mult:
            final_mult = current_mult

        current_mult = self._potent_check_guarantee
        if final_mult < current_mult:
            final_mult = current_mult

        if final_mult > 0:
            return final_mult
        else:
            return None

    def _potent_check_10(self, effects, spd_diff, is_attacker):
        """Check the Potent damage multipler for potent effects that decrease the spd diff by 10"""
        potent_100 = 0
        for e in effects:
            if e.type == EffectType.POTENT:
                if spd_diff + 5 >= 0:
                    potent_100 = 1
        return potent_100
    
    def _potent_check_25(self, effects, spd_diff, is_attacker, made_fu, triggers_brave):
        """Check the Potent damage multipler for potent effects that decrease the spd diff by 25"""
        mult_25 = 0
        for e in effects:
            if e.type == EffectType.POTENT:
                if spd_diff + 20 >= 0:
                    if (triggers_brave or made_fu) and "damage_pct_if_fu" in e.params:
                        pct_25 = e.params["damage_pct_if_fu"]
                    else:
                        pct_25 = e.params.get("damage_pct", 100)
                    mult_25 = pct_25 / 100
        return mult_25

    def _potent_check_30(self, effects, spd_diff, is_attacker, made_fu, triggers_brave):
        """Check the Potent damage multipler for potent effects that decrease the spd diff by 30"""
        mult_30 = 0
        for e in effects:
            if e.type == EffectType.POTENT:
                if spd_diff + 25 >= 0:
                    if (triggers_brave or made_fu) and "damage_pct_if_fu" in e.params:
                        pct_30 = e.params["damage_pct_if_fu"]
                    else:
                        pct_30 = e.params.get("damage_pct", 100)
                    mult_30 = pct_30 / 100
        return mult_30

    def _potent_check_guarantee(self, effects, spd_diff, is_attacker, made_fu, triggers_brave):
        """Check the Potent damage multipler for guaranteed potent effects (like patience)"""
        mult_pat = 0
        """Not sure what to use for this check"""
        for e in effects:
            if e.type == EffectType.POTENT:
                if (triggers_brave or made_fu) and "damage_pct_if_fu" in e.params:
                    pct_pat = e.params["damage_pct_if_fu"]
                else:
                    pct_pat = e.params.get("damage_pct", 100)
                mult_pat = pct_pat / 100
        return mult_pat

    """Legacy Function?
    def _potent_active(self, effects, spd_diff, is_attacker, made_fu):
        relevant_diff = spd_diff if is_attacker else -spd_diff
        best_mult = None
        for e in effects:
            if e.type == EffectType.POTENT:
                threshold = e.params.get("spd_threshold", 25)
                if relevant_diff >= threshold:
                    if made_fu and "damage_pct_if_fu" in e.params:
                        pct = e.params["damage_pct_if_fu"]
                    else:
                        pct = e.params.get("damage_pct", 100)
                    mult = pct / 100.0
                    if best_mult is None or mult > best_mult:
                        best_mult = mult
        return best_mult
    """

    # TODO CHECK POTENT LOGIC TMR

    def _determine_strike_sequence(self) -> list[Strike]:
        """Calculates the combat sequence using effects_strike_sequence instead of keywords."""
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        spd_diff = atk_state.combat_stats.spd - def_state.combat_stats.spd

        atk_off_frozen = sum(
            self._resolve_formula(e.params, atk_state, def_state)
            for e in atk_state.effects_strike_sequence
            if e.type == EffectType.OFF_FROZEN
        )  # easier FU for attacker granted in attacker list

        atk_def_frozen = sum(
            self._resolve_formula(e.params, atk_state, def_state)
            for e in atk_state.effects_strike_sequence
            if e.type == EffectType.DEF_FROZEN
        )  # harder FU for attacker inflicted in attacker list

        def_off_frozen = sum(
            self._resolve_formula(e.params, def_state, atk_state)
            for e in def_state.effects_strike_sequence
            if e.type == EffectType.OFF_FROZEN
        )  # easier FU for defender granted in defender list

        def_def_frozen = sum(
            self._resolve_formula(e.params, def_state, atk_state)
            for e in def_state.effects_strike_sequence
            if e.type == EffectType.DEF_FROZEN
        )  # harder FU for attacker inflicted in defender list

        attacker_spd_check = 1 if spd_diff > 5 - atk_off_frozen + atk_def_frozen else 0
        defender_spd_check = 1 if -spd_diff > 5 - def_off_frozen + def_def_frozen else 0

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

        attacker_OFF_NFU = (
            1
            if any(
                e.type == EffectType.OFF_NFU for e in atk_state.effects_strike_sequence
            )
            else 0
        )
        attacker_DEF_NFU = (
            1
            if any(
                e.type == EffectType.DEF_NFU for e in atk_state.effects_strike_sequence
            )
            else 0
        )
        defender_OFF_NFU = (
            1
            if any(
                e.type == EffectType.OFF_NFU for e in def_state.effects_strike_sequence
            )
            else 0
        )
        defender_DEF_NFU = (
            1
            if any(
                e.type == EffectType.DEF_NFU for e in def_state.effects_strike_sequence
            )
            else 0
        )

        attacker_FU = (
            nb_attacker_GFU * (1 - defender_DEF_NFU)
            - nb_defender_FU_denial * (1 - attacker_OFF_NFU)
            + attacker_spd_check
        )
        defender_FU = (
            nb_defender_GFU * (1 - attacker_DEF_NFU)
            - nb_attacker_FU_denial * (1 - defender_OFF_NFU)
            + defender_spd_check
        )

        attacker_brave = any(
            e.type == EffectType.BRAVE for e in atk_state.effects_strike_sequence
        )
        defender_brave = any(
            e.type == EffectType.BRAVE for e in def_state.effects_strike_sequence
        )
        atk_state.triggers_brave = attacker_brave
        def_state.triggers_brave = defender_brave

        attacker_potent_mult = self._potent_active(
            atk_state.effects_strike_sequence,
            spd_diff,
            is_attacker=True,
            made_fu=attacker_FU > 0,
        )
        defender_potent_mult = self._potent_active(
            def_state.effects_strike_sequence,
            spd_diff,
            is_attacker=False,
            made_fu=defender_FU > 0,
        )

        attacker_potent = attacker_potent_mult is not None
        defender_potent = defender_potent_mult is not None

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

        defender_flash = any(
            e.type == EffectType.FLASH for e in def_state.effects_strike_sequence
        )
        if defender_flash:
            defender_flash_neut = any(
                e.type == EffectType.FLASH_NEUT
                for e in def_state.effects_strike_sequence
            )
            if not defender_flash_neut:
                defender_first = []
                defender_followups = []

        attacker_package = attacker_first + attacker_followups
        defender_package = defender_first + defender_followups

        defender_vantage = any(
            e.type == EffectType.VANTAGE for e in def_state.effects_strike_sequence
        )
        if defender_vantage:
            defender_vantage = not any(
                e.type == EffectType.VANTAGE_NEUT
                for e in atk_state.effects_strike_sequence
            )

        attacker_desperation = any(
            e.type == EffectType.DESPERATION for e in atk_state.effects_strike_sequence
        )
        if attacker_desperation:
            attacker_desperation = not any(
                e.type == EffectType.DESPERATION_NEUT
                for e in def_state.effects_strike_sequence
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

        if strike_sequence:
            strike_sequence[0].is_first_hit = True
            for i in range(1, len(strike_sequence)):
                strike_sequence[i].consecutive = (
                    strike_sequence[i].striker == strike_sequence[i - 1].striker
                )

        return strike_sequence

    def _phase_pre_combat(self):
        """Processes PRE_CBT_DAMAGE and PRE_CBT_HEAL."""
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

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

        self._apply_healing("attacker", atk_preheal, phase="in_combat")
        self._apply_healing("defender", def_preheal, phase="in_combat")

    def _process_strike(self, strike: Strike):
        """Fully data-driven strike processing via effects_on_strike."""
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]

        raw_atk = striker_state.combat_stats.atk
        defensive_stat = getattr(target_state.combat_stats, target_state.defensive_stat)

        # Does either side's Special trigger on this exact strike?
        # TODO: target-side cooldown charging from being attacked isn't
        # implemented yet, so target_special only reflects its starting value.
        striker_special = striker_state.current_cooldown <= 0
        target_special = target_state.current_cooldown <= 0

        wta = self._get_wta_multiplier(striker_state, target_state)
        is_effective = any(
            e.type == EffectType.EFFECTIVE
            and self._strike_matches(
                strike,
                e.params,
                unit_special=striker_special,
                foe_special=target_special,
            )
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
                strike,
                effect.params,
                unit_special=striker_special,
                foe_special=target_special,
            ):
                true_damage += self._resolve_formula(
                    effect.params, striker_state, target_state
                )

        final_damage = base_damage + true_damage
        pre_mitigation_damage = final_damage

        pierce_mult = 1.0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.DR_PIERCE and self._strike_matches(
                strike,
                effect.params,
                unit_special=striker_special,
                foe_special=target_special,
            ):
                pierce_value = effect.params.get("value", 0) / 100.0
                pierce_mult *= 1.0 - pierce_value

        perc_dr = 0.0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.PERC_DR_STRIKE and self._strike_matches(
                strike,
                effect.params,
                unit_special=target_special,
                foe_special=striker_special,
            ):
                dr_val = (
                    self._resolve_formula(effect.params, target_state, striker_state)
                    / 100.0
                )
                perc_dr = 1.0 - ((1.0 - perc_dr) * (1.0 - dr_val))

        effective_dr = perc_dr * pierce_mult
        damage_multiplier = 1.0 - effective_dr
        final_damage = math.trunc(final_damage * damage_multiplier)

        flat_dr = 0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.FLAT_DR_STRIKE and self._strike_matches(
                strike,
                effect.params,
                unit_special=target_special,
                foe_special=striker_special,
            ):
                flat_dr += self._resolve_formula(
                    effect.params, target_state, striker_state
                )

        final_damage = max(0, final_damage - flat_dr)

        dmg_floor = None
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.DR_FLOOR and self._strike_matches(
                strike,
                effect.params,
                unit_special=target_special,
                foe_special=striker_special,
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
                strike,
                effect.params,
                unit_special=striker_special,
                foe_special=target_special,
            ):
                hit_heal += self._resolve_formula(
                    effect.params, striker_state, target_state
                )
        self._apply_healing(strike.striker, hit_heal, phase="in_combat")
        pulse_charge = 1
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.PULSE_STRIKE and self._strike_matches(
                strike,
                effect.params,
                unit_special=striker_special,
                foe_special=target_special,
            ):
                pulse_charge += self._resolve_formula(
                    effect.params, striker_state, target_state
                )

        if striker_special:
            striker_state.special_use_count += 1
            striker_state.current_cooldown = striker_state.unit.max_cooldown
        striker_state.current_cooldown -= max(0, pulse_charge)

        striker_state.strike_count += 1

    def _check_color_advantage(
        self, striker_state: CombatantState, target_state: CombatantState
    ) -> int:
        """Returns 1 (advantage), -1 (disadvantage), or 0 (neutral) based on the color triangle.

        TODO: Raven-Tome-style "treat Colorless as the weapon's color" effects
        have no EffectType yet — once added, check for them here before the
        plain color comparison.
        """
        striker_color = striker_state.unit.color
        target_color = target_state.unit.color

        match striker_color:
            case Color.RED:
                return (
                    1
                    if target_color == Color.GREEN
                    else (-1 if target_color == Color.BLUE else 0)
                )
            case Color.GREEN:
                return (
                    1
                    if target_color == Color.BLUE
                    else (-1 if target_color == Color.RED else 0)
                )
            case Color.BLUE:
                return (
                    1
                    if target_color == Color.RED
                    else (-1 if target_color == Color.GREEN else 0)
                )
            case _:
                return 0

    def _get_wta_multiplier(
        self, striker_state: CombatantState, target_state: CombatantState
    ) -> float:
        """Calculates the WTA multiplier.

        Base advantage is ±20%. Triangle Adept (on either combatant) amplifies
        an EXISTING advantage to a larger value (default ±40%). Cancel Affinity
        on either side neutralizes the Triangle Adept amplification, reverting
        to the base ±20%.
        """
        advantage = self._check_color_advantage(striker_state, target_state)
        if advantage == 0:
            return 1.0

        magnitude = 0.20

        ta_effects = [
            e
            for e in striker_state.effects_on_strike + target_state.effects_on_strike
            if e.type == EffectType.TRIANGLE_ADEPT
        ]
        cancel_affinity = any(
            e.type == EffectType.CANCEL_AFFINITY
            for e in striker_state.effects_on_strike + target_state.effects_on_strike
        )

        if ta_effects and not cancel_affinity:
            magnitude = max(
                self._resolve_formula(e.params, striker_state, target_state) / 100
                if e.params
                else 0.40
                for e in ta_effects
            )

        return 1.0 + (magnitude * advantage)

    def _resolve_formula(
        self, params: dict, unit_state: CombatantState, foe_state: CombatantState
    ) -> int:
        """Resolves a {formula, multiplier, flat, min, max} param block into a number."""
        formula = params.get("formula", "")
        multiplier = params.get("multiplier", 0)
        flat = params.get("flat", 0)
        min_val = params.get("min", 0)
        max_val = params.get("max", -1)
        variable = 0.0

        if formula:
            cs = unit_state.combat_stats
            match formula:
                case "bonus_count":
                    variable = unit_state.bonus_count
                case "debuff_count":
                    variable = foe_state.penalty_count
                case "all_bonus_penalty_both":  # mainly for empathy
                    variable = (
                        unit_state.bonus_count
                        + unit_state.penalty_count
                        + foe_state.bonus_count
                        + foe_state.penalty_count
                    )
                case "spaces_moved":
                    variable = unit_state.spaces_moved
                case "sum_visible_buffs":
                    vb = unit_state.unit.visible_buffs
                    variable = (
                        max(0, vb.atk)
                        + max(0, vb.spd)
                        + max(0, vb.defense)
                        + max(0, vb.res)
                    )
                case "sum_foe_visible_debuffs":
                    vd = foe_state.unit.visible_debuffs
                    variable = (
                        max(0, vd.atk)
                        + max(0, vd.spd)
                        + max(0, vd.defense)
                        + max(0, vd.res)
                    )
                case "mitigated_bucket":  # Reflex
                    variable = unit_state.damage_mitigated_bucket
                case "unit_max_hp":
                    variable = unit_state.unit.base_stats.hp
                case "spd_diff":
                    variable = max(
                        0, unit_state.combat_stats.spd - foe_state.combat_stats.spd
                    )
                case "foe_penalty_count":
                    variable = foe_state.penalty_count
                case "unit_cbt_atk":
                    variable = cs.atk if cs else unit_state.unit.get_visible_stat("atk")
                case "unit_cbt_spd":
                    variable = cs.spd if cs else unit_state.unit.get_visible_stat("spd")
                case "unit_cbt_def":
                    variable = (
                        cs.defense
                        if cs
                        else unit_state.unit.get_visible_stat("defense")
                    )
                case "unit_cbt_res":
                    variable = cs.res if cs else unit_state.unit.get_visible_stat("res")
                case "max_cooldown":
                    variable = unit_state.unit.max_cooldown
                case "num_bonus_and_penalties_on_unit":
                    variable = unit_state.bonus_count + unit_state.penalty_count
                case _:
                    variable = 0.0

        value = math.floor(variable * multiplier) + flat
        if min_val >= 0:
            value = max(value, min_val)
        if max_val >= 0:
            value = min(value, max_val)
        return value

    def _strike_matches(
        self,
        strike: Strike,
        params: dict,
        *,
        unit_special: bool = False,
        foe_special: bool = False,
    ) -> bool:
        """Checks whether `params['strike']` applies to the current strike.

        `unit_special`/`foe_special` indicate whether the effect-owning unit's
        or their opponent's Special triggers on this exact strike — used for
        "on_unit_special" / "on_foe_special" (Dragon Fang, Arcane Cake).
        """
        match params.get("strike", "every_strike"):
            case "every_strike":
                return True
            case "first_strike":
                return (
                    strike.strike_type is StrikeType.FIRST
                    and not strike.brave_second_hit
                )
            case "first_sequence":
                return strike.strike_type is StrikeType.FIRST
            case "first_strike_with_brave":
                return (
                    strike.strike_type is StrikeType.FIRST and strike.brave_second_hit
                )
            case "on_unit_special":
                return unit_special
            case "on_foe_special":
                return foe_special
            case _:
                return False

    def _phase_after_combat(self):
        """Processes effects_after_combat: post-combat healing/damage."""
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe_state = self.combatant_states[foe_role]

            heal = sum(
                self._resolve_formula(e.params, state, foe_state)
                for e in state.effects_after_combat
                if e.type == EffectType.HEAL_POST_CBT
            )
            self._apply_healing(role, heal, phase="post_combat")

            dmg = sum(
                self._resolve_formula(e.params, state, foe_state)
                for e in state.effects_after_combat
                if e.type == EffectType.DAMAGE_POST_CBT
            )
            if dmg > 0:
                foe_state.current_hp = max(1, foe_state.current_hp - dmg)
