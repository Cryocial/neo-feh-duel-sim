"""
Tests for the Divine Vein mechanic (CombatEngine.attacker_divine_vein /
defender_divine_vein -> CombatantState.active_ally_divine_vein).

Rules verified:
  - No vein selected -> no effect
  - A vein's target: self effects apply to whichever unit it's attached to
  - A vein's target: foe effects apply to that unit's opponent
  - Attacker and defender veins are both wired and resolved symmetrically
  - The Water vein from divine_veins.json halves the foe's piercable percent DR
  - The Stone vein from divine_veins.json takes 10 off the strike the foe's
    Special triggers on
"""

from backend.build import Unit, DivineVein, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, SpecialType, Color
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import DIVINE_VEINS_DATABASE


def make_unit(name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def stone_like_vein(amount=6):
    """Ally-buff vein: boosts whoever it's attached to (target: self)."""
    return DivineVein(
        name="Test Stone",
        effects=[
            {
                "effect": "STAT_BOOST",
                "target": "self",
                "params": {"stats": ["defense"], "flat": amount},
                "conditions": [],
            }
        ],
    )


def flame_like_vein(amount=7):
    """Hostile vein: damages the foe of whoever it's attached to (target: foe)."""
    return DivineVein(
        name="Test Flame",
        effects=[
            {
                "effect": "BURN_DAMAGE",
                "target": "foe",
                "params": {"flat": amount},
                "conditions": [],
            }
        ],
    )


def test_no_divine_vein_has_no_effect():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 20


def test_attacker_divine_vein_self_effect_applies_to_attacker():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, attacker_divine_vein=stone_like_vein(6)
    ).simulate()

    # Defender's counter: 30 atk - (20+6) def = 4 damage instead of 10
    assert result["attacker_final_hp"] == 50 - 4
    assert result["defender_final_hp"] == 50 - 20


def test_attacker_divine_vein_foe_effect_applies_to_defender():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, attacker_divine_vein=flame_like_vein(7)
    ).simulate()

    # Pre-combat: defender takes 7 flat damage before the strike sequence
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 7 - 20


def test_defender_divine_vein_self_effect_applies_to_defender():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, defender_divine_vein=stone_like_vein(6)
    ).simulate()

    # Attacker's strike: 40 atk - (20+6) def = 14 damage instead of 20
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 14


def test_defender_divine_vein_foe_effect_applies_to_attacker():
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=10)

    result = CombatEngine(
        attacker, defender, defender_divine_vein=flame_like_vein(7)
    ).simulate()

    # Pre-combat: attacker takes 7 flat damage before the strike sequence
    assert result["attacker_final_hp"] == 50 - 7 - 10
    assert result["defender_final_hp"] == 50 - 20


# ── Water, from divine_veins.json ────────────────────────────────────────────


def test_water_vein_pierces_the_foes_percent_dr():
    """The Water vein's DR_PIERCE halves the foe's piercable percent DR: 40%
    becomes 20%, so the 20-damage strike of the unit standing on it deals
    ceil(20 * 0.8) = 16 instead of ceil(20 * 0.6) = 12. The Spd-5 the vein
    also inflicts changes nothing here: at Spd 14 the foe is never 5 slower,
    so each unit strikes once."""
    attacker = make_unit("A", atk=40, defense=20, spd=10)
    defender = make_unit("D", atk=30, defense=20, spd=14)
    defender.active_statuses.append(
        Status(
            name="Test DR",
            type="bonus",
            effects=[
                {
                    "effect": "PERC_DR_STRIKE",
                    "target": "self",
                    "params": {"flat": 40, "strike": "every_strike", "piercable": True},
                    "conditions": [],
                }
            ],
        )
    )

    plain = CombatEngine(attacker, defender).simulate()
    on_water = CombatEngine(
        attacker, defender, attacker_divine_vein=DIVINE_VEINS_DATABASE["Water"]
    ).simulate()

    assert plain["defender_final_hp"] == 50 - 12
    assert on_water["defender_final_hp"] == 50 - 16


# ── Stone, from divine_veins.json ────────────────────────────────────────────


def test_stone_vein_takes_10_off_the_strike_the_foes_special_triggers_on():
    """The unit on a Stone vein gets Def/Res+6 and takes 10 less from the foe's
    Special. The attacker is 20 Spd faster and strikes twice, its Special
    adding 10 to the first strike only. Against 26 Def both strikes end at 14:
    the vein takes the Special's 10 back off."""
    attacker = make_unit("A", atk=40, defense=20, spd=30)
    attacker.special = Skill(
        name="Test Special",
        slot="special",
        might=0,
        slaying=0,
        cooldown=3,
        visible_stats=StatBlock(),
        effects=[
            {
                "effect": "FLAT_DAMAGE_STRIKE",
                "target": "self",
                "params": {"flat": 10, "strike": "unit_special_triggers"},
                "conditions": [],
            }
        ],
        allowed_movement_types=[],
        allowed_weapon_types=[],
        special_type=SpecialType.OFF,
    )
    attacker.pre_charge = 3  # ready on the first strike
    defender = make_unit("D", hp=100, atk=30, defense=20, spd=10)

    plain = CombatEngine(attacker, defender).simulate()
    on_stone = CombatEngine(
        attacker, defender, defender_divine_vein=DIVINE_VEINS_DATABASE["Stone"]
    ).simulate()

    # no vein: 20 + 10, then 20
    assert plain["defender_final_hp"] == 100 - 30 - 20
    # Stone: 14 + 10 - 10, then 14
    assert on_stone["defender_final_hp"] == 100 - 14 - 14
