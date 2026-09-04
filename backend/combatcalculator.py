import math
from dataclasses import dataclass, field, replace
from typing import Literal

from .build import Unit, StatBlock, DivineVein
from .constants import Color, StrikeType, EffectType, WeaponType, SpecialType
from .effects import Effect, build_effect, EFFECT_LIST_MAP
from .conditions import Timing, Condition, check_condition
from .jsonbootupstuff import BONUS_DATABASE, PENALTY_DATABASE

UnitRole = Literal["attacker", "defender"]
StrikeRole = Literal["striker", "target"]


@dataclass
class CombatantState:
    unit: Unit
    current_hp: int
    current_cooldown: int
    combat_stats: StatBlock | None = None
    phantom_bonus: StatBlock = field(default_factory=StatBlock)
    defensive_stat: Literal["defense", "res"] | None = None
    cd_start_of_cbt: int = 0
    damage_mitigated_bucket: int = 0
    bonus_count: int = 0
    penalty_count: int = 0
    special_type: SpecialType = SpecialType.NONE
    special_denied: bool = False
    special_use_count: int = 0
    miracle_used: bool = False
    special_dr_count: dict[int, int] = field(default_factory=dict)
    twin_value: int = 0
    strike_count: int = 0
    has_entered_combat: bool = False
    is_initiator: bool = False
    triggers_brave: bool = False
    spaces_moved: int = 0
    style_enabled: bool = False
    nb_styles: int = 0
    active_ally_divine_vein: DivineVein | None = None
    granted_visible_buffs: StatBlock = field(default_factory=StatBlock)
    granted_visible_debuffs: StatBlock = field(default_factory=StatBlock)
    effects_start_of_turn: list[Effect] = field(default_factory=list)
    effects_AoE: list[Effect] = field(default_factory=list)
    effects_combat_stats: list[Effect] = field(default_factory=list)
    effects_strike_sequence: list[Effect] = field(default_factory=list)
    effects_pre_combat: list[Effect] = field(default_factory=list)
    effects_on_strike: list[Effect] = field(default_factory=list)
    effects_after_combat: list[Effect] = field(default_factory=list)

    def visible_stat(self, name: str) -> int:
        """Visible stat INCLUDING per-combat start-of-turn grants.

        Start-of-turn grants (Hone, Ploy, etc.) are stored per-combat on this
        CombatantState rather than mutating the Unit, so anything reading visible
        stats during/after start-of-turn must go through here, not
        unit.get_visible_stat directly, or it won't see the grants.
        """
        base = self.unit.get_visible_stat(name)
        base += getattr(self.granted_visible_buffs, name)
        base -= getattr(self.granted_visible_debuffs, name)
        return base

    def cbt_stat_with_phantom(self, name: str) -> int:
        """Combat stat plus Phantom (Spd/Res/Def) bonuses, for checks that are
        explicitly allowed to see Phantom — e.g. Dodge's Spd-diff DR.

        Follow-up eligibility and Potent triggers must NOT use this: they read
        combat_stats directly, since Phantom is defined to boost Spd checks
        without affecting whether a follow-up attack happens.
        """
        base = getattr(self.combat_stats, name, None)
        if base is None:
            base = self.unit.get_visible_stat(name)
        return base + getattr(self.phantom_bonus, name)


@dataclass
class Strike:
    striker: UnitRole
    target: UnitRole
    strike_type: StrikeType
    brave_second_hit: bool = False
    consecutive: bool = False
    potent_mult: float = 1.0



def _base_combat_range(weapon_type: WeaponType) -> int:
    return 2 if weapon_type in {WeaponType.BOW, WeaponType.DAGGER, WeaponType.TOME, WeaponType.STAFF} else 1


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
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = attacker if is_self else defender
            _add_to_bucket(target, effect)
        attacker.nb_styles += skill.grants_style

    for status in attacker.unit.active_statuses:
        for desc in status.effects:
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = attacker if is_self else defender
            _add_to_bucket(target, effect)
        attacker.nb_styles += status.grants_style

    if attacker.active_ally_divine_vein:
        for desc in attacker.active_ally_divine_vein.effects:
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = attacker if is_self else defender
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
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = defender if is_self else attacker
            _add_to_bucket(target, effect)

    for status in defender.unit.active_statuses:
        for desc in status.effects:
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = defender if is_self else attacker
            _add_to_bucket(target, effect)

    if defender.active_ally_divine_vein:
        for desc in defender.active_ally_divine_vein.effects:
            is_self = desc["target"] == "self"
            effect = build_effect(desc, applied_by="self" if is_self else "foe")
            target = defender if is_self else attacker
            _add_to_bucket(target, effect)

def _add_to_bucket(state: CombatantState, effect: Effect) -> None:
    list_name = EFFECT_LIST_MAP.get(effect.type)
    if list_name is None:
        raise KeyError(
            f"EffectType {effect.type} has no EFFECT_LIST_MAP entry — effect would be silently dropped"
        )
    getattr(state, list_name).append(effect)


def _evaluate_conditions_for_effect(
    effect: Effect,
    unit_state: CombatantState,
    foe_state: CombatantState,
    timing: Timing,
) -> tuple[bool, list[Condition]]:
    if effect.applied_by == "foe":
        owner, opponent = foe_state, unit_state
    else:
        owner, opponent = unit_state, foe_state
    remaining = []
    for cond in effect.conditions:
        result = check_condition(cond, timing, owner, opponent)
        if result is False:
            return False, []
        if result is None:
            remaining.append(cond)
    return True, remaining


@dataclass
class CombatEngine:
    """
    The orchestrator for combat simulation.
    Handles the timeline of events from 'start of combat' to 'after combat'.
    """

    attacker: Unit
    defender: Unit
    attacker_divine_vein: DivineVein | None = None
    defender_divine_vein: DivineVein | None = None
    combatant_states: dict[UnitRole, CombatantState] = field(init=False)
    combat_range: int = field(init=False, default=0)

# ── Simulation entry point ───────────────────────────────────────────────────

    def simulate(self) -> dict[str, int]:
        """Runs the full combat simulation following a 10-step timeline."""
        self.combatant_states = {
            "attacker": CombatantState(
                unit=self.attacker,
                current_hp=self.attacker.current_hp,
                current_cooldown=self.attacker.max_cooldown - self.attacker.pre_charge,
                is_initiator=True,
                style_enabled=self.attacker.style_enabled,
                active_ally_divine_vein=self.attacker_divine_vein,
                special_type=SpecialType.NONE if self.attacker.special is None else self.attacker.special.special_type
            ),
            "defender": CombatantState(
                unit=self.defender,
                current_hp=self.defender.current_hp,
                current_cooldown=self.defender.max_cooldown - self.defender.pre_charge,
                is_initiator=False,
                style_enabled=self.defender.style_enabled,
                active_ally_divine_vein=self.defender_divine_vein,
                special_type=SpecialType.NONE if self.defender.special is None else self.defender.special.special_type
            ),
        }
        self._initialize()

        self._compute_counts()

        _distribute_effects(
            self.combatant_states["attacker"], self.combatant_states["defender"]
        )

        self._evaluate_conditions("static")

        self._range_calculation()

        self._resolve_aoe()

        self._evaluate_conditions("post_aoe")

        self._combat_stat_calculations()

        self._evaluate_conditions("post_combat_stats")

        strike_sequence = self._determine_strike_sequence()

        self._evaluate_conditions("post_strike_sequence")

        self._resolve_combat(strike_sequence)

        self._resolve_after_combat()

        return {
            "attacker_final_hp": self.combatant_states["attacker"].current_hp,
            "defender_final_hp": self.combatant_states["defender"].current_hp,
        }

# ── Start of turn ────────────────────────────────────────────────────────────

    def _initialize(self):
        """Grants visible stats and statuses at start of turn (Hone, Ploy, etc.).

        Two passes so stat-dependent grants (Ploy reads visible Res) see the
        results of unconditional grants applied first. Grants are written
        per-combat onto CombatantState, never mutating the Unit, so repeated
        simulate() calls stay isolated.
        """
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe = self.combatant_states[foe_role]
            for skill in state.unit.equipped_items:
                for desc in skill.effects:
                    if desc.get("effect") not in ("GRANT_VISIBLE_STAT", "GRANT_STATUS"):
                        continue
                    target = desc["target"]
                    applied_by = "self" if target == "self" else "foe"
                    effect = build_effect(desc, applied_by=applied_by)
                    tgt = state if target == "self" else foe
                    tgt.effects_start_of_turn.append(effect)

        for conditional in (False, True):
            for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
                state = self.combatant_states[role]
                foe = self.combatant_states[foe_role]
                for effect in state.effects_start_of_turn:
                    if bool(effect.conditions) != conditional:
                        continue
                    owner = foe if effect.applied_by == "foe" else state
                    opponent = state if effect.applied_by == "foe" else foe
                    if not self._start_of_turn_conditions_pass(effect, owner, opponent):
                        continue
                    self._apply_grant(effect, state)

    def _start_of_turn_conditions_pass(self, effect, owner, opponent) -> bool:
        """Evaluates a start-of-turn effect's conditions (all must hold).
        Handles only flat atomic conditions; AnyOf/AllOf on grants not yet supported."""
        for cond in effect.conditions:
            if not cond.func(owner, opponent):
                return False
        return True

    def _apply_grant(self, effect, target_state):
        """Applies a single GRANT_* effect to the target's per-combat layers."""
        if effect.type == EffectType.GRANT_VISIBLE_STAT:
            stats = effect.params.get("stats", {})
            buff_updates, debuff_updates = {}, {}
            for stat, amount in stats.items():
                if amount >= 0:
                    buff_updates[stat] = (
                        getattr(target_state.granted_visible_buffs, stat) + amount
                    )
                else:
                    debuff_updates[stat] = getattr(
                        target_state.granted_visible_debuffs, stat
                    ) + abs(amount)
            if buff_updates:
                target_state.granted_visible_buffs = replace(
                    target_state.granted_visible_buffs, **buff_updates
                )
            if debuff_updates:
                target_state.granted_visible_debuffs = replace(
                    target_state.granted_visible_debuffs, **debuff_updates
                )
        elif effect.type == EffectType.GRANT_STATUS:
            name = effect.params.get("status")
            status = BONUS_DATABASE.get(name) or PENALTY_DATABASE.get(name)
            if status is None:
                raise KeyError(
                    f"GRANT_STATUS references unknown status '{name}' — not in BONUS/PENALTY_DATABASE"
                )
            already_have = any(
                s.name == status.name
                for s in target_state.unit.active_statuses
                + target_state.granted_statuses
            )
            if not already_have:
                target_state.granted_statuses.append(status)

    def _compute_counts(self):
        """Tallies bonus_count / penalty_count from final visible buffs/debuffs and
        active statuses. Previously never computed -> counting skills saw 0.

        """
        for role in ("attacker", "defender"):
            state = self.combatant_states[role]
            bonuses = penalties = 0
            for stat in ("atk", "spd", "defense", "res"):
                if getattr(state.granted_visible_buffs, stat) > 0:
                    bonuses += 1
                if getattr(state.granted_visible_debuffs, stat) > 0:
                    penalties += 1
                if getattr(state.unit.visible_buffs, stat) > 0:
                    bonuses += 1
                if getattr(state.unit.visible_debuffs, stat) > 0:
                    penalties += 1
            for status in state.unit.active_statuses:
                if status.type == "bonus":
                    bonuses += 1
                else:
                    penalties += 1
            state.bonus_count = bonuses
            state.penalty_count = penalties

# ── Condition evaluation ─────────────────────────────────────────────────────

    def _evaluate_conditions(self, timing: Timing) -> None:
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe_state = self.combatant_states[foe_role]
            for list_name in (
                "effects_AoE",
                "effects_combat_stats",
                "effects_strike_sequence",
                "effects_pre_combat",
                "effects_on_strike",
                "effects_after_combat",
            ):
                updated_conditions = []
                for effect in getattr(state, list_name):
                    keep, remaining_conditions = _evaluate_conditions_for_effect(
                        effect, state, foe_state, timing
                    )
                    if keep:
                        effect.conditions = remaining_conditions
                        updated_conditions.append(effect)
                setattr(state, list_name, updated_conditions)

# ── Combat Range calculation ─────────────────────────────────────────────────

    def _range_calculation(self):
        """Determines the distance this combat happens at: the attacker's base
        weapon range, overridden by a RANGE_EXTENSION from the attacker's own
        style, if any (only the initiator's engagement range matters here).
        """
        self.combat_range = _base_combat_range(self.attacker.weapon_type)

        atk_state = self.combatant_states["attacker"]
        for effect in atk_state.effects_combat_stats:
            if effect.type != EffectType.RANGE_EXTENSION:
                continue
            min_range = effect.params["min"]
            max_range = effect.params["max"]
            self.combat_range = (
                min_range if min_range == max_range else self.attacker.chosen_range
            )
            break

# ── Area of effect specials ──────────────────────────────────────────────────

    def _resolve_aoe(self):
        """Processes effects_AoE. Only the initiator can trigger an AoE special."""
        self._apply_special_denial()

        state = self.combatant_states["attacker"]
        foe_state = self.combatant_states["defender"]

        pulse = sum(
            self._resolve_formula(e.params, state, foe_state)
            for e in state.effects_AoE
            if e.type == EffectType.PULSE_AOE
        )
        state.current_cooldown -= max(0, pulse)

        trigger = next(
            (e for e in state.effects_AoE if e.type == EffectType.TRIGGER_AOE), None
        )
        if trigger is None or state.current_cooldown > 0 or state.special_denied:
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

        coefficient = trigger.params.get("coefficient", 0.0)
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

# ── Combat stats calculation ─────────────────────────────────────────────────
 
    def _combat_stat_calculations(self):
        """Calculates combat stats incorporating STAT_BOOST and STAT_DAUNT effects."""
        self.attacker.start_of_combat_hp = self.combatant_states["attacker"].current_hp
        self.defender.start_of_combat_hp = self.combatant_states["defender"].current_hp

        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        atk_ignore_debuffs = any(
            e.type == EffectType.PENALTY_NEUT for e in atk_state.effects_combat_stats
        )
        def_ignore_debuffs = any(
            e.type == EffectType.PENALTY_NEUT for e in def_state.effects_combat_stats
        )
        atk_ignore_buffs = any(
            e.type == EffectType.BONUS_NEUT for e in def_state.effects_combat_stats
        )
        def_ignore_buffs = any(
            e.type == EffectType.BONUS_NEUT for e in atk_state.effects_combat_stats
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
        # These live in effects_combat_stats and were previously never applied.
        for state, foe in ((atk_state, def_state), (def_state, atk_state)):
            for effect in state.effects_combat_stats:
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
                updates = {s: getattr(state.combat_stats, s) + magnitude for s in stats}
                state.combat_stats = replace(state.combat_stats, **updates)
        # Apply PHANTOM_STAT effects. These accumulate into phantom_bonus
        # instead of combat_stats, so it wont apply to normal follow ups and etc.
        for state, foe in ((atk_state, def_state), (def_state, atk_state)):
            for effect in state.effects_combat_stats:
                if effect.type != EffectType.PHANTOM_STAT:
                    continue

                if effect.applied_by == "foe":
                    owner, opponent = foe, state
                else:
                    owner, opponent = state, foe

                magnitude = self._resolve_formula(effect.params, owner, opponent)
                stats = effect.params.get("stats", [])
                updates = {
                    s: getattr(state.phantom_bonus, s) + magnitude for s in stats
                }
                state.phantom_bonus = replace(state.phantom_bonus, **updates)

        self.attacker.combat_stats = self.combatant_states["attacker"].combat_stats
        self.defender.combat_stats = self.combatant_states["defender"].combat_stats
        self.attacker.phantom_bonus = self.combatant_states["attacker"].phantom_bonus
        self.defender.phantom_bonus = self.combatant_states["defender"].phantom_bonus

# ── Strike sequence calculation ──────────────────────────────────────────────

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

        atk_state.triggers_brave = any(
            e.type == EffectType.BRAVE for e in atk_state.effects_strike_sequence
        )
        def_state.triggers_brave = any(
            e.type == EffectType.BRAVE for e in def_state.effects_strike_sequence
        )

        attacker_potent_mult = self._potent_active(
            atk_state.effects_strike_sequence,
            made_fu=attacker_FU > 0,
            triggers_brave=atk_state.triggers_brave,
        )
        defender_potent_mult = self._potent_active(
            def_state.effects_strike_sequence,
            made_fu=defender_FU > 0,
            triggers_brave=def_state.triggers_brave,
        )

        attacker_potent = attacker_potent_mult is not None
        defender_potent = defender_potent_mult is not None

        attacker_first = [Strike("attacker", "defender", StrikeType.FIRST)]
        if atk_state.triggers_brave:
            attacker_first.append(
                Strike(
                    "attacker",
                    "defender",
                    StrikeType.FIRST,
                    brave_second_hit=True,
                    consecutive=True,
                )
            )

        defender_first = [Strike("defender", "attacker", StrikeType.FIRST)]
        if def_state.triggers_brave:
            defender_first.append(
                Strike(
                    "defender",
                    "attacker",
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
            if atk_state.triggers_brave:
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
                Strike(
                    "attacker",
                    "defender",
                    StrikeType.POTENT,
                    consecutive=True,
                    potent_mult=attacker_potent_mult,
                )
            )

        defender_followups = []
        if defender_FU > 0:
            defender_followups.append(
                Strike("defender", "attacker", StrikeType.FOLLOW_UP)
            )
            if def_state.triggers_brave:
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
                Strike(
                    "defender",
                    "attacker",
                    StrikeType.POTENT,
                    consecutive=True,
                    potent_mult=defender_potent_mult,
                )
            )

        defender_counterattack = (
            self.combat_range == _base_combat_range(def_state.unit.weapon_type)
            or any(e.type == EffectType.COUNTERATTACK for e in def_state.effects_strike_sequence)
        )
                 
        defender_flash = any(
            e.type == EffectType.FLASH for e in def_state.effects_strike_sequence
        )
        defender_flash_neut = any(
            e.type == EffectType.FLASH_NEUT
            for e in def_state.effects_strike_sequence
        )

        if not defender_counterattack or (defender_flash and not defender_flash_neut):
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

    def _potent_active(self, effects, made_fu, triggers_brave):
        """Highest Potent multiplier among POTENT effects still in the strike
        sequence (their spd/patience condition already passed in the condition
        phase, so no spd check here). Returns None if none present.
        'Highest value applied; does not stack.'"""
        best = None
        for e in effects:
            if e.type != EffectType.POTENT:
                continue
            if (triggers_brave or made_fu) and "damage_pct_if_fu" in e.params:
                pct = e.params["damage_pct_if_fu"]
            else:
                pct = e.params["damage_pct"]
            mult = pct / 100
            best = mult if best is None else max(best, mult)
        return best

# ── Combat phase and mechanics ───────────────────────────────────────────────

    def _resolve_combat(self, strike_sequence: list[Strike]) -> None:
        """Runs the combat itself: the one-off effects that fill CombatantState
        fields read later, then the strike loop.

        cd_start_of_cbt is captured first: it is a snapshot of the cooldown as
        combat opens, read by PULSE effects capped on it.
        """
        for state in self.combatant_states.values():
            state.cd_start_of_cbt = state.current_cooldown

        self._resolve_pre_combat()

        self._apply_twin_effects()

        self._apply_special_denial()

        self.combatant_states["defender"].defensive_stat = (
            self._determine_defensive_stat(
                striker_state=self.combatant_states["attacker"],
                target_state=self.combatant_states["defender"],
            )
        )
        self.combatant_states["attacker"].defensive_stat = (
            self._determine_defensive_stat(
                striker_state=self.combatant_states["defender"],
                target_state=self.combatant_states["attacker"],
            )
        )

        while (
            len(strike_sequence) > 0
            and self.combatant_states["attacker"].current_hp > 0
            and self.combatant_states["defender"].current_hp > 0
        ):
            strike = strike_sequence.pop(0)
            self._process_strike(strike)

    def _resolve_pre_combat(self):
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

        if def_predmg > 0:
            def_state.current_hp = max(1, def_state.current_hp - def_predmg)
        if atk_predmg > 0:
            atk_state.current_hp = max(1, atk_state.current_hp - atk_predmg)

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

    def _apply_twin_effects(self):
        """Apply twin effect if needed.
        """
        for state in self.combatant_states.values():
            for effect in state.effects_pre_combat:
                if effect.type != EffectType.TWIN:
                    continue
                value = effect.params["value"]
                if value == -1:
                    state.twin_value = -1
                    break
                else:
                    state.twin_value = max(state.twin_value, value)

    def _apply_special_denial(self):
        """Deny a unit's special when a SPECIAL_TRIGGER_NEUT effect in its own
        list covers that special's type. The JSON key is the type's own name in
        lowercase ("aoe", "off", "def").

        AoE denial resolves before _resolve_aoe, the in-combat types before the
        strike loop, hence the flag.
        """
        for state in self.combatant_states.values():
            for effect in state.effects_pre_combat:
                if effect.type != EffectType.SPECIAL_TRIGGER_NEUT:
                    continue
                state.special_denied = (
                    state.special_denied
                    or state.special_type == SpecialType.AOE and effect.params.get("aoe", False)
                    or state.special_type == SpecialType.OFF and effect.params.get("off", False)
                    or state.special_type == SpecialType.DEF and effect.params.get("def", False)
                    or state.special_type == SpecialType.MIRACLE and effect.params.get("def", False)
                )

    def _determine_defensive_stat(
        self, striker_state: CombatantState, target_state: CombatantState
    ) -> Literal["defense", "res"]:
        """Checks for Hexblade/Adaptive effects and returns the correct targeted stat."""
        target_stat = "defense" if striker_state.unit.is_physical() else "res"
        has_hexblade = any(
            e.type == EffectType.HEXBLADE_STRIKE
            for e in striker_state.effects_pre_combat
        )

        if has_hexblade:
            if target_state.combat_stats.res < target_state.combat_stats.defense:
                target_stat = "res"
            else:
                target_stat = "defense"

        return target_stat

    def _process_strike(self, strike: Strike):
        """Fully data-driven strike processing via effects_on_strike."""
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]

        initial_use_count = target_state.special_use_count

        raw_atk = striker_state.combat_stats.atk
        defensive_stat = getattr(target_state.combat_stats, target_state.defensive_stat)

        for role, unit_state, foe_state in (
            ("striker", striker_state, target_state),
            ("target", target_state, striker_state),
        ):
            total_pulse = 0
            for e in unit_state.effects_on_strike:
                if e.type == EffectType.PULSE_STRIKE and self._strike_matches(strike, role, e.params):
                    pulse = self._resolve_formula(e.params, unit_state, foe_state)
                    if e.params.get("cap_cd_start_of_cbt", False):
                        pulse = min(pulse, unit_state.cd_start_of_cbt)
                    total_pulse += pulse

            total_scowl = sum(
                    self._resolve_formula(e.params, unit_state, foe_state)
                    for e in unit_state.effects_on_strike
                    if e.type == EffectType.SCOWL_STRIKE and self._strike_matches(strike, role, e.params)
            )

            unit_state.current_cooldown = max(
                0, unit_state.current_cooldown - total_pulse + total_scowl
            )

        striker_special_ready = striker_state.special_type is not SpecialType.NONE and striker_state.current_cooldown <= 0
        target_special_ready = target_state.special_type is not SpecialType.NONE and target_state.current_cooldown <= 0

        striker_special_triggers = striker_special_ready and striker_state.special_type == SpecialType.OFF and not striker_state.special_denied
        target_special_triggers = (
            target_special_ready
            and target_state.special_type == SpecialType.DEF
            and not target_state.special_denied
        )
        target_miracle_triggers = (
            target_special_ready
            and target_state.special_type == SpecialType.MIRACLE
            and not target_state.special_denied
        )

        striker_special_used = striker_state.special_use_count > 0
        target_special_used = target_state.special_use_count > 0

        wta = self._get_wta_multiplier(striker_state, target_state)
        is_effective = any(
            e.type == EffectType.EFFECTIVE
            and self._strike_matches(
                strike,
                "striker",
                e.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
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
                "striker",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                true_damage += self._resolve_formula(
                    effect.params, striker_state, target_state
                )

        final_damage = base_damage + true_damage
        pre_mitigation_damage = final_damage
        if striker_state.unit.weapon_type is WeaponType.STAFF:
            if not self._staff_full_damage(striker_state):
                final_damage = math.trunc(final_damage * 0.5)

        pierce_mult = 1.0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.DR_PIERCE and self._strike_matches(
                strike,
                "striker",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                pierce_value = effect.params.get("value", 0) / 100.0
                pierce_mult *= 1.0 - pierce_value

        perc_dr = 0.0
        unpierceable_dr = 0.0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.PERC_DR_STRIKE and self._strike_matches(
                strike,
                "target",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                piercable = effect.params["piercable"]
                if piercable:
                    can_trigger = True
                else:
                    trigger_count = target_state.special_dr_count.get(id(effect), 0)
                    max_triggers = effect.params.get("max_triggers", -1)
                    max_triggers = -1 if (max_triggers == -1 or target_state.twin_value == -1) else max(max_triggers, target_state.twin_value)
                    can_trigger = max_triggers == -1 or trigger_count < max_triggers

                if can_trigger:
                    dr_val = (
                        self._resolve_formula(effect.params, target_state, striker_state)
                        / 100.0
                    )
                    perc_dr = 1.0 - ((1.0 - perc_dr) * (1.0 - dr_val))
                    if not piercable:
                        target_state.special_dr_count[id(effect)] = trigger_count + 1

        effective_dr = 1.0 - ((1.0 - perc_dr) * (1.0 - unpierceable_dr))
        damage_multiplier = 1.0 - effective_dr
        final_damage = math.ceil(final_damage * damage_multiplier)
        if strike.strike_type is StrikeType.POTENT:
            final_damage = math.trunc(final_damage * strike.potent_mult)

        flat_dr = 0
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.FLAT_DR_STRIKE and self._strike_matches(
                strike,
                "target",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                flat_dr += self._resolve_formula(
                    effect.params, target_state, striker_state
                )

        final_damage = max(0, final_damage - flat_dr)

        dmg_floor = None
        for effect in target_state.effects_on_strike:
            if effect.type == EffectType.DR_FLOOR and self._strike_matches(
                strike,
                "target",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                floor = self._resolve_formula(
                    effect.params, target_state, striker_state
                )
                dmg_floor = floor if dmg_floor is None else min(dmg_floor, floor)

        if dmg_floor is not None and final_damage > dmg_floor:
            final_damage = dmg_floor

        lethal = final_damage >= target_state.current_hp
        if (
            lethal
            and target_state.current_hp > 1
            and self._miracle_survives(
                strike, target_miracle_triggers
            )
        ):
            final_damage = target_state.current_hp - 1  # survive at exactly 1 HP
            # Skill miracle is once-per-combat; special miracle is gated by
            # cooldown instead, so only burn the flag for skill miracle.
            special_miracle = any(
                e.type == EffectType.MIRACLE
                and e.params.get("strike") == "on_unit_special"
                for e in target_state.effects_on_strike
            )
            if not special_miracle:
                target_state.miracle_used = True

        mitigated_amount = pre_mitigation_damage - final_damage
        target_state.damage_mitigated_bucket += mitigated_amount
        target_state.current_hp -= final_damage

        hit_heal = 0
        for effect in striker_state.effects_on_strike:
            if effect.type == EffectType.HEAL_STRIKE and self._strike_matches(
                strike,
                "striker",
                effect.params,
                striker_special_ready=striker_special_ready,
                target_special_ready=target_special_ready,
                striker_special_triggers=striker_special_triggers,
                target_special_triggers=target_special_triggers,
                striker_special_used=striker_special_used,
                target_special_used=target_special_used,
            ):
                hit_heal += self._resolve_formula(
                    effect.params, striker_state, target_state
                )
        self._apply_healing(strike.striker, hit_heal, phase="in_combat")

        if striker_special_triggers:
            striker_state.special_use_count += 1
            striker_state.current_cooldown = striker_state.unit.max_cooldown
        else:
            striker_breath = any(
                e.type == EffectType.OFF_BREATH for e in striker_state.effects_on_strike
            )
            striker_guard = any(
                e.type == EffectType.DEF_GUARD for e in striker_state.effects_on_strike
            )
            striker_breath_neut = any(
                e.type == EffectType.BREATH_NEUT
                for e in striker_state.effects_on_strike
            )
            striker_guard_neut = any(
                e.type == EffectType.GUARD_NEUT for e in striker_state.effects_on_strike
            )

            striker_charge = (
                1
                + int(striker_breath and not striker_breath_neut)
                - int(striker_guard and not striker_guard_neut)
            )
            striker_state.current_cooldown = max(
                0, striker_state.current_cooldown - striker_charge
            )

        if target_special_triggers:
            target_state.special_use_count += 1
            target_state.current_cooldown = target_state.unit.max_cooldown
        if target_state.special_use_count == initial_use_count:
            target_breath = any(
                e.type == EffectType.DEF_BREATH for e in target_state.effects_on_strike
                )
            target_guard = any(
                e.type == EffectType.OFF_GUARD for e in target_state.effects_on_strike
                )
            target_breath_neut = any(
                e.type == EffectType.BREATH_NEUT for e in target_state.effects_on_strike
                                     )
            target_guard_neut = any(
                e.type == EffectType.GUARD_NEUT for e in target_state.effects_on_strike
                                    )

            target_charge = (
                1
                + int(target_breath and not target_breath_neut)
                - int(target_guard and not target_guard_neut)
            )
            target_state.current_cooldown = max(
                0, target_state.current_cooldown - target_charge
            )

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

    def _staff_full_damage(self, striker_state) -> bool:
        """True if a Wrathful-type effect makes this staff deal full (non-halved)
        damage. Checks for a STAFF_FULL_DAMAGE effect in the striker's on-strike
        list. Returns False by default, so staves halve damage unless a Wrathful
        effect is present."""
        return any(
            e.type == EffectType.STAFF_FULL_DAMAGE
            for e in striker_state.effects_on_strike
        )

    def _miracle_survives(
        self, strike, target_miracle_triggers
    ) -> bool:
        """True if a Miracle lets the target survive this lethal hit at 1 HP.

        Distinguished by the MIRACLE effect's params:
          - Special miracle: strike == "on_unit_special" (requires the target's
            special charged/ready) and cannot be bypassed by Fatal Smoke.
          - Skill miracle: otherwise. Once per combat (target_state.miracle_used),
            and bypassed by FATAL_SMOKE on the attacker.

        Only checks; caller sets miracle_used for the skill-miracle case.
        """
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]
        fatal_smoke = any(
            e.type == EffectType.FATAL_SMOKE for e in striker_state.effects_on_strike
        )
        for e in target_state.effects_on_strike:
            if e.type != EffectType.MIRACLE:
                continue
            is_special = e.params.get("strike") == "on_unit_special"
            if is_special:
                if target_miracle_triggers:
                    target_state.special_use_count += 1
                    target_state.current_cooldown = target_state.unit.max_cooldown
                    return True
            else:
                if not target_state.miracle_used and not fatal_smoke:
                    return True
        return False

# ── After combat ─────────────────────────────────────────────────────────────
 
    def _resolve_after_combat(self):
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

# ── Utils ──────────────────────────────────────────────────────────────────

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
                case "phantom_spd_diff":
                    # Distinct from the follow-up/Potent spd_diff locals in
                    # _determine_strike_sequence and _evaluate_potent_spd_check —
                    # this one is phantom-inclusive by name and by design.
                    variable = max(
                        0,
                        unit_state.cbt_stat_with_phantom("spd")
                        - foe_state.cbt_stat_with_phantom("spd"),
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
                    raise ValueError(f"Unknown formula '{formula}' in _resolve_formula")

        value = math.floor(variable * multiplier) + flat
        if min_val >= 0:
            value = max(value, min_val)
        if max_val >= 0:
            value = min(value, max_val)
        return value

    def _strike_matches(
        self,
        strike: Strike,
        role: StrikeRole,
        params: dict,
        *,
        striker_special_ready: bool = False,
        target_special_ready: bool = False,
        striker_special_triggers: bool = False,
        target_special_triggers: bool = False,
        striker_special_used: bool = False,
        target_special_used: bool = False,
    ) -> bool:
        """Checks whether `params['strike']` applies to the current strike.
        `role` tells which side of this strike owns the effect, so the
        "unit_*"/"foe_*" cases can be read from that owner's point of view.
        The four flags are absolute: `_ready` means the Special could trigger,
        `_triggers` means it actually does on this strike.
        """
        match params.get("strike", "every_strike"):
            case "every_strike":
                return True
            case "first_strike":
                return strike.strike_type is StrikeType.FIRST and not strike.brave_second_hit
            case "first_attack":
                return strike.strike_type is StrikeType.FIRST
            case "first_attack_brave":
                return strike.strike_type is StrikeType.FIRST and strike.brave_second_hit
            case "first_follow_up":
                return strike.strike_type is StrikeType.FOLLOW_UP and not strike.brave_second_hit
            case "follow_up":
                return strike.strike_type is StrikeType.FOLLOW_UP
            case "follow_up_brave":
                return strike.strike_type is StrikeType.FOLLOW_UP and strike.brave_second_hit
            case "both_first_strikes":
                return not strike.brave_second_hit
            case "both_second_strikes":
                return strike.brave_second_hit
            case "consecutive":
                return strike.consecutive
            case "unit_special_triggers":
                return (role == "striker" and striker_special_triggers) or (role == "target" and target_special_triggers)
            case "foe_special_triggers":
                return (role == "striker" and target_special_triggers) or (role == "target" and striker_special_triggers)
            case "unit_special_ready":
                return (role == "striker" and striker_special_ready) or (role == "target" and target_special_ready)
            case "foe_special_ready":
                return (role == "striker" and target_special_ready) or (role == "target" and striker_special_ready)
            case "any_special_ready":
                return striker_special_ready or target_special_ready
            case "any_special_ready_or_triggered":
                return (
                    striker_special_ready or target_special_ready
                    or striker_special_used or target_special_used
                )
            case _:
                return False
