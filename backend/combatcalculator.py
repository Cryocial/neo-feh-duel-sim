import math
from dataclasses import dataclass, field, replace
from typing import Literal

from .build import Unit, StatBlock, DivineVein, cap_visible_stat
from .constants import (
    COMBAT_STATS,
    Color,
    EffectType,
    MovementType,
    SpecialType,
    StrikeMatch,
    StrikeType,
    WeaponType,
)
from .effects import Effect, build_effect, EFFECT_LIST_MAP
from .conditions import Timing, Condition, check_condition
from .jsonbootupstuff import BONUS_DATABASE, PENALTY_DATABASE

UnitRole = Literal["attacker", "defender"]
StrikeRole = Literal["striker", "target"]

EFFECT_LISTS = (
    "effects_AoE",
    "effects_combat_stats",
    "effects_strike_sequence",
    "effects_pre_combat",
    "effects_on_strike",
    "effects_after_combat",
)


@dataclass
class CombatantState:
    unit: Unit
    current_hp: int
    current_cooldown: int
    combat_stats: StatBlock | None = None
    phantom_bonus: StatBlock = field(default_factory=StatBlock)
    defensive_stat: Literal["defense", "res"] | None = None
    cd_start_of_cbt: int = 0
    start_of_combat_hp: int = 0
    reflect_bucket: int = 0
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
    granted_great_talent: StatBlock = field(default_factory=StatBlock)
    effects_start_of_turn: list[Effect] = field(default_factory=list)
    granted_statuses: list = field(default_factory=list)
    effects_AoE: list[Effect] = field(default_factory=list)
    effects_combat_stats: list[Effect] = field(default_factory=list)
    effects_strike_sequence: list[Effect] = field(default_factory=list)
    effects_pre_combat: list[Effect] = field(default_factory=list)
    effects_on_strike: list[Effect] = field(default_factory=list)
    effects_after_combat: list[Effect] = field(default_factory=list)

    def visible_stat(
        self, name: str, ignore_buffs: bool = False, ignore_debuffs: bool = False
    ) -> int:
        """Visible stat INCLUDING per-combat start-of-turn grants.

        Start-of-turn grants (Hone, Ploy, etc.) are stored per-combat on this
        CombatantState rather than mutating the Unit, so anything reading visible
        stats during/after start-of-turn must go through here, not
        unit.get_visible_stat directly, or it won't see the grants.
        """
        value = self.unit.stat_before_bonuses(name) + getattr(self.granted_great_talent, name)
        if not ignore_buffs:
            value += self.visible_buff(name)
        if not ignore_debuffs:
            value -= self.visible_debuff(name)
        return cap_visible_stat(name, value)

    def visible_buff(self, name: str) -> int:
        """Visible bonuses don't stack: the unit's own buff and a granted one on
        the same stat resolve to the highest. Raw, before the visible cap."""
        return max(
            getattr(self.unit.visible_buffs, name),
            getattr(self.granted_visible_buffs, name),
        )

    def visible_debuff(self, name: str) -> int:
        """Same rule for penalties."""
        return max(
            getattr(self.unit.visible_debuffs, name),
            getattr(self.granted_visible_debuffs, name),
        )

    @property
    def great_talent_total(self) -> StatBlock:
        """What the unit brought into this combat plus what it gained here."""
        return self.unit.great_talent + self.granted_great_talent

    def cbt_stat_with_phantom(self, name: str) -> int:
            """Combat stat plus Phantom (Spd/Res/Def) bonuses, for checks that are
            explicitly allowed to see Phantom — e.g. Dodge's Spd-diff DR.
    
            Follow-up eligibility and Potent triggers must NOT use this: they read
            combat_stats directly, since Phantom is defined to boost Spd checks
            without affecting whether a follow-up attack happens.
            """
            if self.combat_stats is None:
                raise RuntimeError(
                    f"{self.unit.name}: combat_stats not initialized before Phantom check"
                )
    
            base = getattr(self.combat_stats, name)
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
    for own, other in ((attacker, defender), (defender, attacker)):
        _distribute_from(own.unit.equipped_items, own, other, "self", "foe")
        _distribute_from(own.unit.active_statuses, own, other, "self", "foe")
        if own.active_ally_divine_vein:
            _distribute_from([own.active_ally_divine_vein], own, other, "self", "foe")
        for support in own.unit.ally_supports:
            _distribute_from([support.skill], own, other, "ally", "enemy", support.color)
        # Styles are a player-phase action: only the initiator's count.
        if own.is_initiator:
            own.nb_styles += sum(s.grants_style for s in own.unit.equipped_items)
            own.nb_styles += sum(s.grants_style for s in own.unit.active_statuses)


def _distribute_from(sources, own, other, self_tag, foe_tag, source_color=None):
    """Routes each source's effects: target "self" into `own`'s lists tagged
    self_tag, target "foe" into `other`'s tagged foe_tag."""
    for source in sources:
        for desc in source.effects:
            is_self = desc["target"] == "self"
            effect = build_effect(
                desc, applied_by=self_tag if is_self else foe_tag, source_color=source_color
            )
            _add_to_bucket(own if is_self else other, effect)


def _owner_and_opponent(effect: Effect, holder: CombatantState, foe: CombatantState):
    """The side whose skill produced `effect`, then the other. Conditions and
    formulas evaluate from the owner's view; "foe" / "enemy" effects were put
    in the holder's list by the opposing side."""
    if effect.applied_by in ("foe", "enemy"):
        return foe, holder
    return holder, foe


def _bonuses_neutralized(state: CombatantState, foe: CombatantState) -> bool:
    """The foe's Lull (BONUS_NEUT) neutralizes this unit's visible bonuses:
    they count as absent for stats, doublers, Treachery and the like."""
    return any(e.type is EffectType.BONUS_NEUT for e in foe.effects_combat_stats)


def _penalties_neutralized(state: CombatantState) -> bool:
    """The unit's own PENALTY_NEUT: its visible penalties count as absent."""
    return any(e.type is EffectType.PENALTY_NEUT for e in state.effects_combat_stats)


def _great_talent_dict(total: StatBlock) -> dict[str, int]:
    return {stat: getattr(total, stat) for stat in COMBAT_STATS}


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
    owner, opponent = _owner_and_opponent(effect, unit_state, foe_state)
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

        self._apply_feud()

        self._range_calculation()

        self._resolve_aoe()

        for state in self.combatant_states.values():
            state.start_of_combat_hp = state.current_hp

        self._evaluate_conditions("post_aoe")

        self._apply_feud()

        self._combat_stat_calculations()

        self._evaluate_conditions("post_combat_stats")

        strike_sequence = self._determine_strike_sequence()

        self._evaluate_conditions("post_strike_sequence")

        self._resolve_combat(strike_sequence)

        self._resolve_after_combat()

        attacker = self.combatant_states["attacker"]
        defender = self.combatant_states["defender"]
        return {
            "attacker_final_hp": attacker.current_hp,
            "defender_final_hp": defender.current_hp,
            "attacker_great_talent": _great_talent_dict(attacker.great_talent_total),
            "defender_great_talent": _great_talent_dict(defender.great_talent_total),
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
                    if desc.get("effect") not in (
                        "GRANT_VISIBLE_BUFF",
                        "INFLICT_VISIBLE_DEBUFF",
                        "GRANT_STATUS",
                        "GRANT_GREAT_TALENT",
                    ):
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
                    owner, opponent = _owner_and_opponent(effect, state, foe)
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
        """Applies a single start-of-turn effect to the target's per-combat layers."""
        # Visible bonuses and penalties don't stack: highest wins per stat.
        if effect.type == EffectType.GRANT_VISIBLE_BUFF:
            target_state.granted_visible_buffs = replace(
                target_state.granted_visible_buffs,
                **{
                    stat: max(getattr(target_state.granted_visible_buffs, stat), amount)
                    for stat, amount in effect.params["stats"].items()
                },
            )
        elif effect.type == EffectType.INFLICT_VISIBLE_DEBUFF:
            target_state.granted_visible_debuffs = replace(
                target_state.granted_visible_debuffs,
                **{
                    stat: max(getattr(target_state.granted_visible_debuffs, stat), amount)
                    for stat, amount in effect.params["stats"].items()
                },
            )
        elif effect.type == EffectType.GRANT_GREAT_TALENT:
            self._grant_great_talent(target_state, effect.params)
        elif effect.type == EffectType.GRANT_STATUS:
            name = effect.params["status"]
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

    def _grant_great_talent(self, state: CombatantState, params: dict) -> None:
        """Raises the unit's Great Talent per stat toward the effect's `max`.
        Never lowers it and never pushes past the cap, so a unit already above
        this skill's cap (from a more generous source) is left alone. No `max`
        means uncapped; the visible cap still applies to the stat itself.
        """
        cap = params.get("max")
        total = state.great_talent_total
        updates = {}
        for stat, amount in params["stats"].items():
            have = getattr(total, stat)
            target = have + amount if cap is None else min(have + amount, cap)
            if target > have:
                updates[stat] = getattr(state.granted_great_talent, stat) + (target - have)
        if updates:
            state.granted_great_talent = replace(state.granted_great_talent, **updates)

    def _compute_counts(self):
        """Tallies bonus_count / penalty_count from final visible buffs/debuffs and
        active statuses. Previously never computed -> counting skills saw 0.

        """
        for role in ("attacker", "defender"):
            state = self.combatant_states[role]
            bonuses = penalties = 0
            for stat in COMBAT_STATS:
                if state.visible_buff(stat) > 0:
                    bonuses += 1
                if state.visible_debuff(stat) > 0:
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
            for list_name in EFFECT_LISTS:
                updated_conditions = []
                for effect in getattr(state, list_name):
                    keep, remaining_conditions = _evaluate_conditions_for_effect(
                        effect, state, foe_state, timing
                    )
                    if keep:
                        effect.conditions = remaining_conditions
                        updated_conditions.append(effect)
                setattr(state, list_name, updated_conditions)

    def _apply_feud(self):
        """FEUD sits on the unit whose allies' skills are disabled, the way
        FU_DENY sits on the unit that can't follow up. It strips "ally" effects
        on that unit and the "enemy" effects those allies put on the foe.

        Blue Feud 3: "disables skills of all blue foes, excluding foe in
        combat. If in combat against a blue foe, disables skills of all foes,
        excluding foe in combat." So with `colors` an ally is disabled if its
        own colour is listed, or every ally is if the unit itself is of a
        listed colour. Without `colors`, every ally. A Feud whose conditions
        haven't resolved yet does nothing, which is why this runs after each
        early condition pass.
        """
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe = self.combatant_states[foe_role]
            feuds = [
                e for e in state.effects_combat_stats
                if e.type is EffectType.FEUD and not e.conditions
            ]
            if not feuds:
                continue

            every_ally = False
            listed: set[str] = set()
            for feud in feuds:
                colors = feud.params.get("colors")
                if colors is None or state.unit.color.name in colors:
                    every_ally = True
                    break
                listed.update(colors)

            def disabled(effect):
                return every_ally or (
                    effect.source_color is not None and effect.source_color.name in listed
                )

            for name in EFFECT_LISTS:
                setattr(state, name, [
                    e for e in getattr(state, name)
                    if not (e.applied_by == "ally" and disabled(e))
                ])
                setattr(foe, name, [
                    e for e in getattr(foe, name)
                    if not (e.applied_by == "enemy" and disabled(e))
                ])

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
            chosen = self.attacker.chosen_range
            if min_range == max_range:
                self.combat_range = min_range
            elif chosen is None or not min_range <= chosen <= max_range:
                raise ValueError(
                    f"{self.attacker.name}: style allows range {min_range}-{max_range}, "
                    f"chosen_range must be set within it (got {chosen})"
                )
            else:
                self.combat_range = chosen
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
        ) and not any(
            e.type == EffectType.NEUT_HEXBLADE for e in foe_state.effects_pre_combat
        )
        if has_hexblade_aoe:
            visible_def = min(
                foe_state.visible_stat("defense"),
                foe_state.visible_stat("res"),
            )
        else:
            visible_def = (
                foe_state.visible_stat("defense")
                if state.unit.is_physical()
                else foe_state.visible_stat("res")
            )

        coefficient = trigger.params["coefficient"]
        visible_atk = state.visible_stat("atk")
        damage = max(0, math.floor(coefficient * (visible_atk - visible_def)))

        for e in state.effects_AoE:
            if e.type == EffectType.FLAT_DAMAGE_AOE:
                damage += self._resolve_formula(e.params, state, foe_state)


        perc_dr = 0.0
        for e in foe_state.effects_AoE:
            if e.type == EffectType.PERC_DR_AOE:
                dr_val = (
                    self._resolve_formula(e.params, foe_state, state) / 100.0
                )
                perc_dr = 1.0 - ((1.0 - perc_dr) * (1.0 - dr_val))

        damage = math.ceil(damage * (1.0 - perc_dr))

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
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]

        atk_ignore_debuffs = _penalties_neutralized(atk_state)
        def_ignore_debuffs = _penalties_neutralized(def_state)
        atk_ignore_buffs = _bonuses_neutralized(atk_state, def_state)
        def_ignore_buffs = _bonuses_neutralized(def_state, atk_state)

        atk_vals = {
            stat: atk_state.visible_stat(
                stat, ignore_buffs=atk_ignore_buffs, ignore_debuffs=atk_ignore_debuffs
            )
            for stat in ["hp", "atk", "spd", "defense", "res"]
        }
        def_vals = {
            stat: def_state.visible_stat(
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

                owner, opponent = _owner_and_opponent(effect, state, foe)

                magnitude = self._resolve_formula(effect.params, owner, opponent)
                if effect.type == EffectType.STAT_DAUNT:
                    magnitude = -abs(magnitude)

                stats = effect.params["stats"]
                updates = {s: getattr(state.combat_stats, s) + magnitude for s in stats}
                state.combat_stats = replace(state.combat_stats, **updates)

        # Doublers read the raw visible bonus / penalty per stat, including any
        # part the visible cap wasted, and add it to the uncapped combat stats.
        # Every source stacks. Neutralization (the foe's Lull for the bonus
        # side, the unit's own PENALTY_NEUT for the penalty side) zeroes the
        # unit's own half; see _doubler_deltas for what that leaves.
        for state, buffs_neutralized, penalties_neutralized in (
            (atk_state, atk_ignore_buffs, atk_ignore_debuffs),
            (def_state, def_ignore_buffs, def_ignore_debuffs),
        ):
            deltas = self._doubler_deltas(state, buffs_neutralized, penalties_neutralized)
            state.combat_stats = replace(
                state.combat_stats,
                **{s: getattr(state.combat_stats, s) + d for s, d in deltas.items() if d},
            )

        # Apply PHANTOM_STAT effects. These accumulate into phantom_bonus
        # instead of combat_stats, so it wont apply to normal follow ups and etc.
        for state, foe in ((atk_state, def_state), (def_state, atk_state)):
            for effect in state.effects_combat_stats:
                if effect.type != EffectType.PHANTOM_STAT:
                    continue

                owner, opponent = _owner_and_opponent(effect, state, foe)

                magnitude = self._resolve_formula(effect.params, owner, opponent)
                stats = effect.params["stats"]
                updates = {
                    s: getattr(state.phantom_bonus, s) + magnitude for s in stats
                }
                state.phantom_bonus = replace(state.phantom_bonus, **updates)

# ── Strike sequence calculation ──────────────────────────────────────────────

    def _doubler_deltas(
        self, state: CombatantState, buffs_neutralized: bool, penalties_neutralized: bool
    ) -> dict[str, int]:
        """Per-stat combat-stat change from the doubler family, each stat
        calculated independently:

          BONUS_DOUBLER    + the unit's raw visible buff
          FRINGE_BONUS     + the higher of that buff and the highest bonus among
                             allies within 2 spaces (user-entered on the Unit)
          PENALTY_DOUBLER  - the unit's raw visible debuff
          SABOTAGE         - the higher of that debuff and the allies' highest

        Neutralization (the foe's Lull for bonuses, the unit's own PENALTY_NEUT
        for penalties) zeroes the unit's OWN half only. The plain doublers have
        nothing else to read and go inert; Fringe and Sabotage keep working as
        long as an ally within 2 spaces supplies the value.
        """
        unit = state.unit
        has_allies = unit.allies_within_2_spaces > 0
        deltas = {s: 0 for s in COMBAT_STATS}
        for effect in state.effects_combat_stats:
            stats = effect.params.get("stats", COMBAT_STATS)
            if effect.type is EffectType.BONUS_DOUBLER and not buffs_neutralized:
                for s in stats:
                    deltas[s] += state.visible_buff(s)
            elif effect.type is EffectType.FRINGE_BONUS:
                for s in stats:
                    own = 0 if buffs_neutralized else state.visible_buff(s)
                    ally = getattr(unit.ally_bonuses_within_2_spaces, s) if has_allies else 0
                    deltas[s] += max(own, ally)
            elif effect.type is EffectType.PENALTY_DOUBLER and not penalties_neutralized:
                for s in stats:
                    deltas[s] -= state.visible_debuff(s)
            elif effect.type is EffectType.SABOTAGE:
                for s in stats:
                    own = 0 if penalties_neutralized else state.visible_debuff(s)
                    ally = getattr(unit.ally_penalties_within_2_spaces, s) if has_allies else 0
                    deltas[s] -= max(own, ally)
        return deltas

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

        attacker_spd_check = 1 if spd_diff >= 5 - atk_off_frozen + atk_def_frozen else 0
        defender_spd_check = 1 if -spd_diff >= 5 - def_off_frozen + def_def_frozen else 0

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

        # Armored foes also counter when the attacker's own weapon range matches
        # theirs, even if a style moved the engagement distance.
        defender_range = _base_combat_range(def_state.unit.weapon_type)
        defender_counterattack = (
            self.combat_range == defender_range
            or (
                def_state.unit.movement_type is MovementType.ARMOR
                and _base_combat_range(atk_state.unit.weapon_type) == defender_range
            )
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

        defender_vantage = any(
            e.type == EffectType.VANTAGE for e in def_state.effects_strike_sequence
        )
        if defender_vantage:
            defender_vantage = not any(
                e.type == EffectType.VANTAGE_NEUT
                for e in atk_state.effects_strike_sequence
            )

        def has_desperation(own, foe):
            return any(
                e.type == EffectType.DESPERATION for e in own.effects_strike_sequence
            ) and not any(
                e.type == EffectType.DESPERATION_NEUT for e in foe.effects_strike_sequence
            )

        # Desperation lands a side's follow-ups right after its own first strikes;
        # otherwise follow-ups queue after both sides' first strikes, same order.
        # Vantage only decides which side goes first.
        sides = [
            (defender_first, defender_followups, has_desperation(def_state, atk_state)),
            (attacker_first, attacker_followups, has_desperation(atk_state, def_state)),
        ]
        if not defender_vantage:
            sides.reverse()

        strike_sequence, deferred = [], []
        for first, followups, desperation in sides:
            strike_sequence += first
            if desperation:
                strike_sequence += followups
            else:
                deferred += followups
        strike_sequence += deferred

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
        """Processes BURN_DAMAGE, PRE_CBT_HEAL and BURN_HEAL.

        Burn damage and AoE damage are distinct: burn lands here, after every
        condition pass, so it never moves an HP check, while AoE damage
        (TRIGGER_AOE) landed back in _resolve_aoe, before the start-of-combat
        snapshot, and does. That is why BURN_HEAL refunds only what this phase
        took.
        """
        atk_state = self.combatant_states["attacker"]
        def_state = self.combatant_states["defender"]
        sides = (
            ("attacker", atk_state, def_state),
            ("defender", def_state, atk_state),
        )

        # Both sums resolve before either lands, so neither sees the other's damage.
        burn = {
            role: sum(
                self._resolve_formula(e.params, state, foe)
                for e in state.effects_pre_combat
                if e.type == EffectType.BURN_DAMAGE
            )
            for role, state, foe in sides
        }
        taken = {}
        for role, state, _ in sides:
            before = state.current_hp
            if burn[role] > 0:
                state.current_hp = max(1, state.current_hp - burn[role])
            taken[role] = before - state.current_hp

        for role, state, foe in sides:
            # Pre-combat heals don't stack: only the highest source applies...
            heal = max(
                (
                    self._resolve_formula(e.params, state, foe)
                    for e in state.effects_pre_combat
                    if e.type == EffectType.PRE_CBT_HEAL
                ),
                default=0,
            )
            # ...but BURN_HEAL refunds the HP burn actually cost, on top of
            # whichever heal won, and never more than was lost.
            if taken[role] and any(
                e.type == EffectType.BURN_HEAL for e in state.effects_pre_combat
            ):
                heal += taken[role]
            self._apply_healing(role, heal, phase="in_combat")

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
                # The AoE-time call can see conditions that only resolve later;
                # those effects are skipped here and picked up by the call
                # before the strike loop, once every pass has run.
                if effect.type != EffectType.SPECIAL_TRIGGER_NEUT or effect.conditions:
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
        ) and not any(
            e.type == EffectType.NEUT_HEXBLADE
            for e in target_state.effects_pre_combat
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

        # Reflected damage (REFLEX / BRIAR) is spent on the unit's next strike.
        true_damage = striker_state.reflect_bucket
        striker_state.reflect_bucket = 0
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
        if striker_state.unit.weapon_type is WeaponType.STAFF:
            if not self._staff_full_damage(striker_state):
                final_damage = math.trunc(final_damage * 0.5)
        pre_mitigation_damage = final_damage

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
                pierce_value = effect.params["value"] / 100.0
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
                    if piercable:
                        dr_val *= pierce_mult
                        perc_dr = 1.0 - ((1.0 - perc_dr) * (1.0 - dr_val))
                    else:
                        unpierceable_dr = 1.0 - ((1.0 - unpierceable_dr) * (1.0 - dr_val))
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
                e.type == EffectType.MIRACLE and e.params.get("special", False)
                for e in target_state.effects_on_strike
            )
            if not special_miracle:
                target_state.miracle_used = True

        # Reflex sources stack; Briar applies only its highest percent.
        mitigated_amount = pre_mitigation_damage - final_damage
        briar_pct = 0
        for effect in target_state.effects_on_strike:
            if effect.type not in (EffectType.REFLEX, EffectType.BRIAR):
                continue
            if not self._strike_matches(
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
                continue
            if effect.type is EffectType.REFLEX:
                target_state.reflect_bucket += mitigated_amount
            else:
                pct = self._resolve_formula(effect.params, target_state, striker_state)
                briar_pct = max(briar_pct, pct)
        if briar_pct:
            target_state.reflect_bucket += math.floor(pre_mitigation_damage * briar_pct / 100)
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
                    owner, opponent = _owner_and_opponent(e, unit_state, foe_state)
                    pct = self._resolve_formula(e.params, owner, opponent)
                    survive *= (100 - pct) / 100
                    found = True
                if not found:
                    return
                amount = math.ceil(amount * survive)

        if amount <= 0:
            return
        new_hp = unit_state.current_hp + amount
        unit_state.current_hp = min(unit_state.unit.max_hp, new_hp)

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
          - Special miracle: special == True (requires the target's Special
            charged/ready) and cannot be neutralized.
          - Skill miracle: otherwise. Once per combat (target_state.miracle_used),
            and neutralized by MIRACLE_NEUT (Fatal Smoke) on the attacker.

        Only checks; caller sets miracle_used for the skill-miracle case.
        """
        striker_state = self.combatant_states[strike.striker]
        target_state = self.combatant_states[strike.target]
        miracle_neut = any(
            e.type == EffectType.MIRACLE_NEUT for e in striker_state.effects_on_strike
        )
        for e in target_state.effects_on_strike:
            if e.type != EffectType.MIRACLE:
                continue
            if e.params.get("special", False):
                if target_miracle_triggers:
                    target_state.special_use_count += 1
                    target_state.current_cooldown = target_state.unit.max_cooldown
                    return True
            else:
                if not target_state.miracle_used and not miracle_neut:
                    return True
        return False

# ── After combat ─────────────────────────────────────────────────────────────
 
    def _resolve_after_combat(self):
        """Processes effects_after_combat: post-combat healing, damage and
        Great Talent. A unit that died gets nothing, and an effect whose
        source died (a foe's Savage Blow) never fires."""
        for role, foe_role in (("attacker", "defender"), ("defender", "attacker")):
            state = self.combatant_states[role]
            foe_state = self.combatant_states[foe_role]
            if state.current_hp <= 0:
                continue

            def live(effect):
                return foe_state.current_hp > 0 or effect.applied_by not in ("foe", "enemy")

            effects = [e for e in state.effects_after_combat if live(e)]

            heal = sum(
                self._resolve_formula(e.params, state, foe_state)
                for e in effects
                if e.type == EffectType.HEAL_POST_CBT
            )
            self._apply_healing(role, heal, phase="post_combat")

            dmg = sum(
                self._resolve_formula(e.params, state, foe_state)
                for e in effects
                if e.type == EffectType.DAMAGE_POST_CBT
            )
            if dmg > 0:
                state.current_hp = max(1, state.current_hp - dmg)

            for e in effects:
                if e.type == EffectType.GRANT_GREAT_TALENT_POST_CBT:
                    self._grant_great_talent(state, e.params)

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
                    # Treachery: nothing while the foe's Lull neutralizes the
                    # unit's bonuses; otherwise the raw buffs, even any part
                    # the visible cap wasted.
                    variable = (
                        0
                        if _bonuses_neutralized(unit_state, foe_state)
                        else sum(unit_state.visible_buff(s) for s in COMBAT_STATS)
                    )
                case "sum_foe_visible_debuffs":
                    # Dominance: nothing if the foe neutralizes its own penalties.
                    variable = (
                        0
                        if _penalties_neutralized(foe_state)
                        else sum(foe_state.visible_debuff(s) for s in COMBAT_STATS)
                    )
                case "unit_max_hp":
                    variable = unit_state.unit.max_hp
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
                    variable = cs.atk if cs else unit_state.visible_stat("atk")
                case "unit_cbt_spd":
                    variable = cs.spd if cs else unit_state.visible_stat("spd")
                case "unit_cbt_def":
                    variable = cs.defense if cs else unit_state.visible_stat("defense")
                case "unit_cbt_res":
                    variable = cs.res if cs else unit_state.visible_stat("res")
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
        raw = params.get("strike", StrikeMatch.EVERY_STRIKE)
        try:
            strike_match = StrikeMatch(raw)
        except ValueError:
            raise ValueError(f"Unknown strike value {raw!r} in _strike_matches") from None

        is_first = strike.strike_type is StrikeType.FIRST
        is_follow_up = strike.strike_type is StrikeType.FOLLOW_UP
        unit_triggers = striker_special_triggers if role == "striker" else target_special_triggers
        foe_triggers = target_special_triggers if role == "striker" else striker_special_triggers
        unit_ready = striker_special_ready if role == "striker" else target_special_ready
        foe_ready = target_special_ready if role == "striker" else striker_special_ready

        match strike_match:
            case StrikeMatch.EVERY_STRIKE:
                return True
            case StrikeMatch.FIRST_STRIKE:
                return is_first and not strike.brave_second_hit
            case StrikeMatch.FIRST_ATTACK:
                return is_first
            case StrikeMatch.FIRST_ATTACK_BRAVE:
                return is_first and strike.brave_second_hit
            case StrikeMatch.FIRST_FOLLOW_UP:
                return is_follow_up and not strike.brave_second_hit
            case StrikeMatch.FOLLOW_UP:
                return is_follow_up
            case StrikeMatch.FOLLOW_UP_BRAVE:
                return is_follow_up and strike.brave_second_hit
            case StrikeMatch.BOTH_FIRST_STRIKES:
                return not strike.brave_second_hit
            case StrikeMatch.BOTH_SECOND_STRIKES:
                return strike.brave_second_hit
            case StrikeMatch.CONSECUTIVE:
                return strike.consecutive
            case StrikeMatch.UNIT_SPECIAL_TRIGGERS:
                return unit_triggers
            case StrikeMatch.FOE_SPECIAL_TRIGGERS:
                return foe_triggers
            case StrikeMatch.UNIT_SPECIAL_READY:
                return unit_ready
            case StrikeMatch.FOE_SPECIAL_READY:
                return foe_ready
            case StrikeMatch.ANY_SPECIAL_READY:
                return striker_special_ready or target_special_ready
            case StrikeMatch.ANY_SPECIAL_READY_OR_TRIGGERED:
                return (
                    striker_special_ready or target_special_ready
                    or striker_special_used or target_special_used
                )
            case _:
                raise ValueError(f"{strike_match!r} has no rule in _strike_matches")
