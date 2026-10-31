"""
HEXBLADE_STRIKE / HEXBLADE_AOE make the striker target the lower of the foe's
Def and Res. NEUT_HEXBLADE on the foe cancels both, restoring the stat the
striker's weapon would normally hit.

Setup: sword attacker (physical, so Def) at 40 Atk, Spd 30 so it strikes
twice; defender at 30 Def / 10 Res, 100 HP, Spd 10. Per hit: 10 against Def,
30 against Res.
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


def flag(effect):
    """A presence-flag status carrying one parameterless effect on its holder."""
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": "self", "params": {}, "conditions": [],
    }])


def aoe_special():
    return Skill(
        name="AoE", slot="special", might=0, slaying=0, cooldown=1,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        special_type=SpecialType.AOE,
        effects=[{
            "effect": "TRIGGER_AOE", "target": "self",
            "params": {"coefficient": 1.0}, "conditions": [],
        }],
    )


def lopsided_defender():
    return make_unit("D", hp=100, atk=25, defense=30, res=10)


def damage_dealt(result):
    return 100 - result["defender_final_hp"]


def test_sword_targets_def_by_default():
    result = CombatEngine(make_unit("A", spd=30), lopsided_defender()).simulate()

    assert damage_dealt(result) == 20            # 2 x (40 - 30)


def test_hexblade_strike_targets_the_lower_stat():
    attacker = make_unit("A", spd=30)
    attacker.active_statuses.append(flag("HEXBLADE_STRIKE"))

    result = CombatEngine(attacker, lopsided_defender()).simulate()

    assert damage_dealt(result) == 60            # 2 x (40 - 10)


def test_neut_hexblade_restores_the_weapons_stat():
    attacker = make_unit("A", spd=30)
    attacker.active_statuses.append(flag("HEXBLADE_STRIKE"))
    defender = lopsided_defender()
    defender.active_statuses.append(flag("NEUT_HEXBLADE"))

    result = CombatEngine(attacker, defender).simulate()

    assert damage_dealt(result) == 20


def test_hexblade_aoe_targets_the_lower_stat():
    attacker = make_unit("A", spd=30)
    attacker.special = aoe_special()
    attacker.pre_charge = 1
    attacker.active_statuses.append(flag("HEXBLADE_AOE"))

    result = CombatEngine(attacker, lopsided_defender()).simulate()

    assert damage_dealt(result) == 30 + 20       # AoE 40 - 10, then 2 x (40 - 30)


def test_neut_hexblade_also_covers_the_aoe():
    attacker = make_unit("A", spd=30)
    attacker.special = aoe_special()
    attacker.pre_charge = 1
    attacker.active_statuses.append(flag("HEXBLADE_AOE"))
    defender = lopsided_defender()
    defender.active_statuses.append(flag("NEUT_HEXBLADE"))

    result = CombatEngine(attacker, defender).simulate()

    assert damage_dealt(result) == 10 + 20       # AoE 40 - 30, then 2 x (40 - 30)
