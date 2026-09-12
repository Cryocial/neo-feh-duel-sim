"""
Burn damage and start-of-combat healing (BURN_DAMAGE / PRE_CBT_HEAL /
BURN_HEAL), resolved in _resolve_pre_combat before the strike loop.

Burn damage is not AoE damage: burn lands after every condition pass and so
never moves an HP check, while AoE damage (TRIGGER_AOE) lands before the
start-of-combat snapshot and does. Both are pinned below.

Rules verified:
  - BURN_DAMAGE sources STACK: every source lands, floored at 1 HP
  - PRE_CBT_HEAL sources DON'T stack: only the highest single source heals
    (three Imbue-style sources of 20, 20 and 10 restore 20, not 50)
  - healing still caps at max HP

Setup: same colour, both melee, equal Spd, so the exchange is exactly one
strike each. The attacker (40 Atk) hits the 20-Def defender for 20; the
defender (25 Atk) counters the 20-Def attacker for 5. Pre-combat HP changes
are therefore read straight off attacker_final_hp + 5.
"""

from backend.build import Unit, Skill, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color, SpecialType
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import SKILL_DATABASE


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


def heal(amount):
    return Status(name=f"Heal {amount}", type="bonus", effects=[{
        "effect": "PRE_CBT_HEAL",
        "target": "self",
        "params": {"flat": amount},
        "conditions": [],
    }])


def damage_foe(amount):
    """Held by one unit, damages the OTHER before combat (Flame vein pattern)."""
    return Status(name=f"Damage {amount}", type="bonus", effects=[{
        "effect": "BURN_DAMAGE",
        "target": "foe",
        "params": {"flat": amount},
        "conditions": [],
    }])


def attacker_hp_before_counter(result):
    return result["attacker_final_hp"] + 5


def test_pre_combat_heal_takes_the_highest_source_only():
    attacker = make_unit("A")
    attacker.current_hp = 20
    for amount in (20, 20, 10):
        attacker.active_statuses.append(heal(amount))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    # 20 + 20, not 20 + 50
    assert attacker_hp_before_counter(result) == 40


def test_pre_combat_heal_single_source_still_applies():
    attacker = make_unit("A")
    attacker.current_hp = 20
    attacker.active_statuses.append(heal(15))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 35


def test_pre_combat_heal_caps_at_max_hp():
    attacker = make_unit("A")
    attacker.current_hp = 45
    attacker.active_statuses.append(heal(20))
    defender = make_unit("D", hp=100, atk=25)

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 50


def burn_heal():
    return Status(name="Burn Heal", type="bonus", effects=[{
        "effect": "BURN_HEAL",
        "target": "self",
        "params": {},
        "conditions": [],
    }])


def aoe_attacker(hp=50, **stats):
    """An attacker whose AoE Special is charged and ready to fire."""
    unit = make_unit("A", hp=hp, **stats)
    unit.special = Skill(
        name="AoE", slot="special", might=0, slaying=0, cooldown=1,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        special_type=SpecialType.AOE,
        effects=[{
            "effect": "TRIGGER_AOE", "target": "self",
            "params": {"coefficient": 1.0}, "conditions": [],
        }],
    )
    unit.pre_charge = 1
    return unit


def test_burn_damage_sources_stack():
    attacker = make_unit("A")
    defender = make_unit("D", hp=100, atk=25)
    for amount in (7, 7, 4):
        defender.active_statuses.append(damage_foe(amount))

    result = CombatEngine(attacker, defender).simulate()

    # 50 - (7 + 7 + 4)
    assert attacker_hp_before_counter(result) == 32


# ── BURN_HEAL: refunding what burn cost ──────────────────────────────────────


def test_burn_heal_is_added_on_top_of_the_highest_heal():
    """20/50, burn 10, a 20 heal and a burn refund: 20 - 10 + (20 + 10)."""
    attacker = make_unit("A")
    attacker.current_hp = 20
    attacker.active_statuses.append(heal(20))
    attacker.active_statuses.append(burn_heal())
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(damage_foe(10))

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 40


def test_burn_heal_refunds_only_the_hp_burn_actually_cost():
    """19 HP against 99 burn floors at 1, so it cost 18: refund 18, not 99."""
    attacker = make_unit("A")
    attacker.current_hp = 19
    attacker.active_statuses.append(heal(20))
    attacker.active_statuses.append(burn_heal())
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(damage_foe(99))

    result = CombatEngine(attacker, defender).simulate()

    assert attacker_hp_before_counter(result) == 1 + 20 + 18


def test_burn_heal_does_nothing_without_burn():
    attacker = make_unit("A")
    attacker.current_hp = 20
    attacker.active_statuses.append(burn_heal())

    result = CombatEngine(attacker, make_unit("D", hp=100, atk=25)).simulate()

    assert attacker_hp_before_counter(result) == 20


def test_burn_heal_does_not_refund_aoe_damage():
    """The defender eats 20 from the AoE and 20 from the strike; its BURN_HEAL
    finds no burn to refund, so nothing comes back."""
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(burn_heal())

    result = CombatEngine(aoe_attacker(), defender).simulate()

    assert result["defender_final_hp"] == 100 - 20 - 20


# ── the two phases are not interchangeable ───────────────────────────────────


def hp_gated_defender():
    """Its +6 Atk needs HP >= 90%, so a counter of 11 means the gate held and
    5 means it failed."""
    unit = make_unit("D", hp=100, atk=25)
    unit.a_slot = Skill(
        name="HP gate", slot="passive_a", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
        effects=[{
            "effect": "STAT_BOOST", "target": "self",
            "params": {"stats": ["atk"], "flat": 6},
            "conditions": [{"type": "hp_above_pct", "params": {"threshold": 90}}],
        }],
    )
    return unit


def test_aoe_damage_is_seen_by_hp_conditions():
    """AoE lands before the start-of-combat snapshot: 80/100 fails the gate."""
    result = CombatEngine(aoe_attacker(hp=200), hp_gated_defender()).simulate()

    assert 200 - result["attacker_final_hp"] == 5


def test_burn_damage_is_not_seen_by_hp_conditions():
    """The same 20, dealt as burn, lands after every condition pass, so the
    defender is still at 100% when the gate is checked."""
    attacker = make_unit("A", hp=200)
    attacker.active_statuses.append(damage_foe(20))

    result = CombatEngine(attacker, hp_gated_defender()).simulate()

    assert 200 - result["attacker_final_hp"] == 11


# ── Breath of Life 4, from skills.json ───────────────────────────────────────


def test_breath_of_life_4_heals_40_percent_and_refunds_burn_when_def_wins():
    """Def 25 vs 20: 40% of 50 max HP, plus the 10 burn cost back."""
    attacker = make_unit("A", defense=25)
    attacker.current_hp = 20
    attacker.c_slot = SKILL_DATABASE["Breath of Life 4"]
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(damage_foe(10))

    result = CombatEngine(attacker, defender).simulate()

    # 20 - 10 burn + (20 heal + 10 refund), then a 25-25 counter for 0
    assert result["attacker_final_hp"] == 40


def test_breath_of_life_4_heals_20_percent_and_refunds_nothing_when_def_loses():
    """Def 15 vs 20: the 20% branch, and no refund since the gate failed."""
    attacker = make_unit("A", defense=15)
    attacker.current_hp = 20
    attacker.c_slot = SKILL_DATABASE["Breath of Life 4"]
    defender = make_unit("D", hp=100, atk=25)
    defender.active_statuses.append(damage_foe(10))

    result = CombatEngine(attacker, defender).simulate()

    # 20 - 10 burn + 10 heal, then a 25-15 counter for 10
    assert result["attacker_final_hp"] == 10
