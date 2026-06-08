import math
from dataclasses import dataclass, field
from .classes import Unit, StatBlock
from .constants import WeaponType, Color
from .jsonbootupstuff import STATUS_EFFECT_DATABASE


@dataclass
class Strike:
    """Represents a single attack in the combat sequence."""

    striker: Unit
    target: Unit


@dataclass
class CombatEngine:
    """
    The orchestrator for combat simulation.
    Handles the timeline of events from 'start of combat' to 'after combat'.
    """

    attacker: Unit
    defender: Unit
    attacker_combat_stats: StatBlock = field(init=False)  # in combat stats
    defender_combat_stats: StatBlock = field(init=False)
    attacker_targeted_stat: int = field(
        init=False
    )  # encoding which stat to use when attacker takes a hit: 0 for physical (def), 1 for magical (res)
    defender_targeted_stat: int = field(init=False)

    def simulate(self) -> dict[str, int]:
        """
        Runs the full combat simulation and returns the final HP for both units.
        """
        self._phase_before_combat()

        self._combat_stat_calculations()

        strike_sequence = self._determine_strike_sequence()

        self._phase_start_of_combat()

        while (
            len(strike_sequence) > 0
            and self.attacker.base_stats.hp > 0
            and self.defender.base_stats.hp > 0
        ):
            strike = strike_sequence.pop()
            self._process_strike(
                strike.striker, strike.target
            )  # CD pulses and healing calc in there too

        self._phase_before_first_attack()

        # tracks dmg mitigated for reflex
        self.attacker.damage_mitigated_bucket = 0
        self.defender.damage_mitigated_bucket = 0

        if self.attacker.base_stats.hp > 0:
            self._process_strike(self.attacker, self.defender)

        if self.defender.base_stats.hp > 0:
            self._process_strike(self.defender, self.attacker)

        self._phase_after_combat()

        return {
            "attacker_final_hp": self.attacker.base_stats.hp,
            "defender_final_hp": self.defender.base_stats.hp,
        }

    def _process_AoE(self, striker: Unit, target: Unit):
        """Applies AoE damage"""
        ...

    def _process_strike(self, striker: Unit, target: Unit):
        """Calculates and applies damage for a single weapon swing."""
        striker.current_cooldown -= striker.get_pulse_amount(
            "before_every_attack", target
        )

        raw_atk = striker.get_combat_stat("atk", target)
        is_magic = striker.weapon_type in {
            WeaponType.TOME,
            WeaponType.STAFF,
            WeaponType.DRAGON,
            WeaponType.BEAST,
        }
        defensive_stat = target.get_combat_stat(
            "res" if is_magic else "defense", striker
        )

        wta = self._get_wta_multiplier(striker, target)
        modified_atk = math.trunc(raw_atk * wta)

        base_damage = max(0, modified_atk - defensive_stat)

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
        final_damage = base_damage + true_damage

        #  CHECK FOR FIRST HIT DR TYPES
        # for reflex
        mitigated_amount = 0

        # ------------------------------------
        # Collapsed Star
        # TO DO: wait for a method to track when a attack is to be implemented:
        # ------------------------------------

        target.damage_mitigated_bucket += mitigated_amount
        new_hp = target.base_stats.hp - final_damage
        target.base_stats.hp = new_hp

        charge = (
            1
            + striker.get_pulse_amount("per_unit_attack", target)
            + target.get_pulse_amount("per_foe_attack", striker)
        )
        striker.current_cooldown -= max(0, charge)
        striker.combat_attacks_performed += 1

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

    def _phase_before_combat(self):
        """AOE"""
        if self.attacker.has_AoE:
            self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
                "before_combat", self.defender
            )
            if self.attacker.current_cooldown == 0:
                self._process_AoE(self.attacker, self.defender)

    def _combat_stat_calculations(self):
        """Calculates combat stats for both units."""
        atk_vals, def_vals = {}, {}
        for stat in ["hp", "atk", "spd", "defense", "res"]:
            atk_vals[stat] = self.attacker.get_combat_stat(stat, self.defender)
            def_vals[stat] = self.defender.get_combat_stat(stat, self.attacker)

        self.attacker_combat_stats = StatBlock(**atk_vals)
        self.defender_combat_stats = StatBlock(**def_vals)

        self.attacker_targeted_stat = 0 if self.defender.is_physical() else 1
        self.defender_targeted_stat = 0 if self.attacker.is_physical() else 1

    def _determine_strike_sequence(self) -> list[Strike]:
        """Determines the number and order of strikes."""
        ...

    def _phase_start_of_combat(self):
        """Pre-combat damage and healing effects."""
        ...

    def _phase_start_of_combat(self):
        self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
            "start_of_combat", self.defender
        )
        self.defender.current_cooldown -= self.defender.get_pulse_amount(
            "start_of_combat", self.attacker
        )

    def _phase_before_first_attack(self):
        self.defender.current_cooldown -= self.defender.get_pulse_amount(
            "before_first_attack", self.attacker
        )

    def _phase_after_combat(self):
        self.attacker.current_cooldown -= self.attacker.get_pulse_amount(
            "after_combat", self.defender
        )
        self.defender.current_cooldown -= self.defender.get_pulse_amount(
            "after_combat", self.attacker
        )
