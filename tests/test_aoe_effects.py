"""
FLAT_DAMAGE_AOE adds to the pre-combat AoE hit; PULSE_AOE lowers the Special
cooldown right before the AoE check, so a Special one charge short still fires.

Setup: sword attacker at 40 Atk, Spd 10; defender at 20 Def, Spd 10, 100 HP.
The AoE hit is 40 - 20 = 20 on visible stats, then the single combat strike
deals another 20.
"""

from backend.build import Unit, Skill, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color, SpecialType
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def aoe_special(cooldown):
    return Skill(
        name="AoE", slot="special", might=0, slaying=0, cooldown=cooldown,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        special_type=SpecialType.AOE,
        effects=[{
            "effect": "TRIGGER_AOE", "target": "self",
            "params": {"coefficient": 1.0}, "conditions": [],
        }],
    )


def status(effect, params):
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": "self", "params": params, "conditions": [],
    }])


def dealt(result):
    return 100 - result["defender_final_hp"]


def test_flat_damage_aoe_adds_to_the_aoe_hit():
    attacker = make_unit("A")
    attacker.special = aoe_special(cooldown=1)
    attacker.pre_charge = 1
    attacker.active_statuses.append(status("FLAT_DAMAGE_AOE", {"flat": 5}))

    result = CombatEngine(attacker, make_unit("D", hp=100)).simulate()

    assert dealt(result) == (20 + 5) + 20


def test_pulse_aoe_readies_a_special_one_charge_short():
    """Cooldown 2 with one pre-charge is still at 1, so no AoE; PULSE_AOE 1
    brings it to 0 in time."""
    def attacker(with_pulse):
        unit = make_unit("A")
        unit.special = aoe_special(cooldown=2)
        unit.pre_charge = 1
        if with_pulse:
            unit.active_statuses.append(status("PULSE_AOE", {"flat": 1}))
        return unit

    assert dealt(CombatEngine(attacker(False), make_unit("D", hp=100)).simulate()) == 20
    assert dealt(CombatEngine(attacker(True), make_unit("D", hp=100)).simulate()) == 40
