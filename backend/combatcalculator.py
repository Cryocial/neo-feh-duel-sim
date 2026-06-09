import math
from dataclasses import dataclass, field
from typing import Literal
from .classes import Unit, StatBlock
from .constants import Color, StrikeType, MovementType, WeaponType
from .jsonbootupstuff import STATUS_EFFECT_DATABASE

UnitRole = Literal["attacker", "defender"]


@dataclass
class CombatantState:
    unit: Unit
    current_hp: int
    current_cooldown: int
    combat_stats: StatBlock | None = None
    defensive_stat: Literal["def", "res"] | None = None


@dataclass
class Strike:
    """Represents a single attack in the combat sequence."""

    striker: UnitRole
    target: UnitRole
    strike_type: StrikeType
    brave_second_hit: bool = False
    consecutive: bool = False


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
        self.combatant_states = {
            "attacker": CombatantState(
                unit=self.attacker,
                current_hp=self.attacker.current_hp,
                current_cooldown=self.attacker.current_cooldown,
            ),
            "defender": CombatantState(
                unit=self.defender,
                current_hp=self.defender.current_hp,
                current_cooldown=self.defender.current_cooldown,
            ),
        }

        self._start_of_turn()

        self._phase_before_combat()

        self._combat_stat_calculations()

        strike_sequence = self._determine_strike_sequence()

        self._phase_start_of_combat()

        # tracks dmg mitigated for reflex
        self.attacker.damage_mitigated_bucket = 0
        self.defender.damage_mitigated_bucket = 0

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

    def _process_AoE(self, striker: Unit, target: Unit):
        """Applies AoE damage"""
        # TODO: include bonus damage and DR effects
        striker = self.combatant_states["attacker"]
        target = self.combatant_states["defender"]
        
        coefficient = striker.unit.special.utilities.aoe_coefficient
        visible_atk = striker.unit.get_visible_stat("atk")
        visible_defensive_stat = target.unit.get_visible_stat("defense") if striker.unit.is_physical() else target.unit.get_visible_stat("res")
        
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
            if target_state.defensive_stat == "def"
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
        if target.movement_type == MovementType.ARMOR and striker.has_keyword("effective_armor"):
            if not target.has_keyword("neutralize_effective_armor"):
                is_effective = True
        elif target.movement_type == MovementType.CAVALRY and striker.has_keyword("effective_cavalry"):
            if not target.has_keyword("neutralize_effective_cavalry"):
                is_effective = True
        elif target.movement_type == MovementType.FLIER and striker.has_keyword("effective_flier"):
            if not target.has_keyword("neutralize_effective_flying"):
                is_effective = True
        elif target.weapon_type == WeaponType.DRAGON and striker.has_keyword("effective_dragon"):
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

    def _start_of_turn(self):
        """"""
        # update cooldowns

    def _phase_before_combat(self):
        """AoE"""
        if self.attacker.has_AoE:
            self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
                "before_AoE", self.defender
            )
            if self.attacker.current_cooldown == 0:
                self._process_AoE()

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
        attacker_targets = "def" if self.attacker.is_physical() else "res"
        for item in self.attacker.equipped_items:
            if item.utilities.adaptive_logic:
                attacker_targets = item.utilities.adaptive_logic(self.attacker, self.defender)
        for s in self.attacker.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                if info["utilities"].adaptive_logic:
                    attacker_targets = info["utilities"].adaptive_logic(self.attacker, self.defender)
        self.combatant_states["defender"].defensive_stat = attacker_targets

        # Determine targeting for Defender targeting Attacker
        defender_targets = "def" if self.defender.is_physical() else "res"
        for item in self.defender.equipped_items:
            if item.utilities.adaptive_logic:
                defender_targets = item.utilities.adaptive_logic(self.defender, self.attacker)
        for s in self.defender.active_statuses:
            if info := STATUS_EFFECT_DATABASE.get(s):
                if info["utilities"].adaptive_logic:
                    defender_targets = info["utilities"].adaptive_logic(self.defender, self.attacker)
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

        nb_attacker_GFU = (
            0  # TODO: count the number of "Unit makes a guaranteed follow-up attack"
        )
        nb_defender_GFU = (
            0  # TODO: count the number of "Unit makes a guaranteed follow-up attack"
        )

        nb_attacker_FU_denial = (
            0  # TODO: count the number of "Foe cannot make a follow-up attack" layers
        )
        nb_defender_FU_denial = (
            0  # TODO: count the number of "Foe cannot make a follow-up attack" layers
        )

        attacker_off_NFU = 0  # TODO: 1 if attacker has "neutralizes effects that prevent unit's followup attacks"
        defender_off_NFU = 0  # TODO: 1 if defender has "neutralizes effects that prevent unit's followup attacks"

        attacker_def_NFU = 0  # TODO: 1 if attacker has "neutralizes effects that guarantee foe's follow-up attacks"
        defender_def_NFU = 0  # TODO: 1 if defender has "neutralizes effects that guarantee foe's follow-up attacks"

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

        attacker_brave = False  # TODO: check wether attacker can attack twice
        defender_brave = False  # TODO: check wether defender can attack twice

        attacker_potent = (
            False  # TODO check wether attacker can trigger a potent attack
        )
        defender_potent = (
            False  # TODO check wether defender can trigger a potent attack
        )

        strike_sequence = []

        strike_sequence.append(
            Strike("attacker", "defender", StrikeType.FIRST, False, False)
        )
        if attacker_brave:
            strike_sequence.append(
                Strike("attacker", "defender", StrikeType.FIRST, True, True)
            )

        strike_sequence.append(
            Strike("defender", "attacker", StrikeType.FIRST, False, False)
        )
        if defender_brave:
            strike_sequence.append(
                Strike("defender", "attacker", StrikeType.FIRST, True, True)
            )

        if attacker_FU > 0:
            strike_sequence.append(
                Strike("attacker", "defender", StrikeType.FOLLOW_UP, False, False)
            )
            if attacker_brave:
                strike_sequence.append(
                    Strike("attacker", "defender", StrikeType.FOLLOW_UP, True, True)
                )
        if attacker_potent:
            strike_sequence.append(
                Strike("attacker", "defender", StrikeType.POTENT, False, True)
            )

        if defender_FU > 0:
            strike_sequence.append(
                Strike("defender", "attacker", StrikeType.FOLLOW_UP, False, False)
            )
            if defender_brave:
                strike_sequence.append(
                    Strike("defender", "attacker", StrikeType.FOLLOW_UP, True, True)
                )
        if defender_potent:
            strike_sequence.append(
                Strike("defender", "attacker", StrikeType.POTENT, False, True)
            )

        return strike_sequence

    def _phase_start_of_combat(self):
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

    def _phase_after_combat(self):
        # self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
        #     "after_combat", self.defender
        # )
        # self.defender.current_cooldown -= self.defender.get_pulse_amount(
        #     "after_combat", self.attacker
        # )
        ...
