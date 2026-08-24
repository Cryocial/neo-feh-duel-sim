"""
Tests for Special triggering (SpecialType + the ready/triggers distinction).

Rules verified:
  - an OFF Special triggers on the unit's own attacks, never while being hit
  - a DEF Special triggers while the unit is being hit, never on its own attacks
  - a Special with no type (or no Special at all) never triggers and is never
    considered ready
  - "unit_special_ready" matches whenever the cooldown is at 0, whether or not
    the Special actually triggers on that strike
  - triggering resets the cooldown to max_cooldown; not triggering charges it

Setup: same color (no weapon-triangle multiplier), both melee (so the defender
can always counter), no follow-up unless a Spd gap is set on purpose. Specials
carry max_cooldown=1, so they are not ready on the first strike but become
ready after charging once.
"""

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, SpecialType, Color
from backend.combatcalculator import CombatEngine


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


def give_special(unit, special_type, effects, max_cooldown=1):
    unit.special = Skill(
        name="Test Special", slot="special", might=0, slaying=0, cooldown=max_cooldown,
        visible_stats=StatBlock(), effects=effects,
        allowed_movement_types=[], allowed_weapon_types=[],
        special_type=special_type,
    )
    unit.max_cooldown = max_cooldown
    return unit


def flat_damage(amount, strike):
    return {
        "effect": "FLAT_DAMAGE_STRIKE",
        "target": "self",
        "params": {"flat": amount, "strike": strike},
        "conditions": [],
    }


def heal(amount, strike):
    return {
        "effect": "HEAL_STRIKE",
        "target": "self",
        "params": {"flat": amount, "strike": strike},
        "conditions": [],
    }


def denial_status(types):
    """Granted by the opposing unit: target "foe" lands the effect in the
    denied unit's own list, which is where _apply_special_denial reads it."""
    return Status(
        name="Test Denial",
        type="bonus",
        effects=[{
            "effect": "SPECIAL_TRIGGER_NEUT",
            "target": "foe",
            "params": types,
            "conditions": [],
        }],
    )


def trigger_aoe(coefficient):
    return {
        "effect": "TRIGGER_AOE",
        "target": "self",
        "params": {"coefficient": coefficient},
        "conditions": [],
    }


def perc_dr(pct, strike, piercable, max_triggers=1):
    params = {"flat": pct, "strike": strike, "piercable": piercable}
    if not piercable:
        params["max_triggers"] = max_triggers
    return {
        "effect": "PERC_DR_STRIKE",
        "target": "self",
        "params": params,
        "conditions": [],
    }


def test_off_special_deals_flat_damage_on_trigger():
    """An offensive Special adds damage on the unit's own attack, and only once
    its cooldown has reached 0."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [flat_damage(10, "unit_special_triggers")])
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: cooldown 1, not ready -> 30 - 20 = 10. Charges to 0
    # D1: 25 - 20 = 5 to the attacker
    # A2: offensive special ready, it triggers -> 10 + 10 = 20
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 20
    # Triggers on A2 and resets
    assert engine.combatant_states["attacker"].current_cooldown == 1
    assert engine.combatant_states["attacker"].special_use_count == 1


def test_off_special_heals_on_trigger():
    """Same shape, but the Special restores HP instead of adding damage."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [heal(15, "unit_special_triggers")])
    defender = make_unit("D", atk=40, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: 10 damage
    # D1: 40 - 20 = 20 to the attacker
    # A2: offensive special ready, it triggers -> heals 15
    assert result["attacker_final_hp"] == 50 - 20 + 15
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Triggers on A2 and resets
    assert engine.combatant_states["attacker"].current_cooldown == 1
    assert engine.combatant_states["attacker"].special_use_count == 1


def test_off_special_with_capped_special_dr():
    """An offensive Special that also grants a non-piercable DR gated on its own
    readiness (Ice Wall shape): the DR is capped by max_triggers, the damage
    bonus still needs an actual trigger."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [
        flat_damage(10, "unit_special_triggers"),
        perc_dr(50, "unit_special_ready", piercable=False, max_triggers=1),
    ])
    defender = make_unit("D", atk=40, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 10 damage
    # D1: attacker special is now ready, so the DR applies -> 20 * 0.5 = 10
    # A2: special is ready and triggers -> 10 + 10 = 20 damage
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 10 - 20
    # Triggers on A2 and resets
    assert engine.combatant_states["attacker"].current_cooldown == 1
    assert engine.combatant_states["attacker"].special_use_count == 1


def test_off_special_with_piercable_dr_is_uncapped():
    """Same idea but the DR is piercable, so max_triggers does not apply and it
    reduces both of the defender's strikes."""
    attacker = make_unit("A", atk=30, spd=10, defense=20)
    give_special(attacker, SpecialType.OFF, [
        perc_dr(50, "every_strike", piercable=True),
    ])
    defender = make_unit("D", atk=40, spd=30, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: 10 damage
    # D1 & D2 attacker special grants piercable DR -> (20 * 0.5) = 10
    assert result["attacker_final_hp"] == 50 - 10 - 10
    assert result["defender_final_hp"] == 50 - 10
    # Ready at D1 but never triggers, so it floors at 0
    assert engine.combatant_states["attacker"].current_cooldown == 0
    assert engine.combatant_states["attacker"].special_use_count == 0


def test_def_special_triggers_when_struck():
    """A defensive Special triggers while being attacked, and notably NOT on the
    unit's own counterattack."""
    attacker = make_unit("A", atk=40, spd=30, defense=20)
    defender = make_unit("D", atk=25, spd=10, defense=20)
    give_special(defender, SpecialType.DEF, [
        perc_dr(50, "unit_special_triggers", piercable=False, max_triggers=1),
    ])

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: defender special isn't ready -> 20 damage
    # D1: defender special is ready but doesn't trigger while attacking -> 5
    # A2: defender dpecial is ready and triggers -> 20 * 0.5 = 10
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 20 - 10
    # Triggers on A2 and resets
    assert engine.combatant_states["defender"].current_cooldown == 1
    assert engine.combatant_states["defender"].special_use_count == 1


def test_def_special_also_granting_damage_on_readiness():
    """A defensive Special whose damage bonus is gated on readiness rather than
    on triggering, so it applies on the unit's own counterattack."""
    attacker = make_unit("A", atk=40, spd=10, defense=20)
    defender = make_unit("D", atk=25, spd=20, defense=20)
    give_special(defender, SpecialType.DEF, [
        perc_dr(50, "unit_special_triggers", piercable=False, max_triggers=1),
        flat_damage(10, "any_special_ready_or_triggered"),
    ],
    max_cooldown=2)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: defender special is not ready -> 20 damage
    # D1: defender special is not -> 5 damage
    # D2: defender special is ready but doesn't trigger while attacking.
    #     Still, damage applies -> 25 - 20 + 10
    assert result["attacker_final_hp"] == 50 - 5 - 15
    assert result["defender_final_hp"] == 50 - 20
    # Ready at D2 but never triggers, so it floors at 0
    assert engine.combatant_states["defender"].current_cooldown == 0
    assert engine.combatant_states["defender"].special_use_count == 0


def test_untyped_special_never_triggers():
    """A Special left at SpecialType.NONE (e.g. not yet classified in the JSON)
    is never ready and never triggers."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.NONE, [flat_damage(10, "unit_special_triggers")])
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: 10 damage
    # D1: 5 damage
    # A2: 10 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Charged by all three strikes and never reset, so it floors at 0
    assert engine.combatant_states["attacker"].current_cooldown == 0
    assert engine.combatant_states["attacker"].special_use_count == 0


def test_no_special_at_all_is_never_ready():
    """A unit with no special equipped is never ready, so readiness gated
    effects never apply."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    attacker.active_statuses.append(
        Status(name="Readiness bonus", type="bonus",
               effects=[flat_damage(10, "unit_special_ready")])
    )
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: 10 damage
    # D1: 5 damage
    # A2: 10 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Never ready, so it never triggers
    assert engine.combatant_states["attacker"].special_use_count == 0


def test_aoe_special_fires_before_combat_and_not_during():
    """An AoE special resolves before any strike, and must not fire again as an
    offensive special once its cooldown is back to 0."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.AOE, [trigger_aoe(0.5)])
    attacker.pre_charge = 1  # ready before combat starts
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # AoE: 0.5 * (30 - 20) = 5 damage
    # A1: special is not ready -> 10 damage
    # D1: 5 damage
    # A2: special is ready but an AoE special doesn't trigger in combat -> 10 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 5 - 10 - 10
    # Triggers on the AoE phase only
    assert engine.combatant_states["attacker"].special_use_count == 1
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_other_special_is_ready_but_never_triggers():
    """A special resolved outside combat (staff heals, etc.) counts as ready,
    but never triggers during a fight."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OTHER, [
        flat_damage(10, "unit_special_triggers"),
        flat_damage(5, "unit_special_ready"),
    ])
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 10 damage
    # D1: 5 damage
    # A2: special is ready but doesn't trigger in combat.
    #     Still, damage applies -> 30 - 20 + 5
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 15
    # Ready at A2 but never triggers, so it floors at 0
    assert engine.combatant_states["attacker"].special_use_count == 0
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_special_triggering_twice_is_counted_twice():
    """With Brave and a follow-up the attacker strikes four times, enough to
    charge and spend a 1 cooldown special twice."""
    attacker = make_unit("A", atk=25, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [flat_damage(5, "unit_special_triggers")])
    attacker.active_statuses.append(
        Status(name="Test Brave", type="bonus",
               effects=[{"effect": "BRAVE", "target": "self", "params": {}, "conditions": []}])
    )
    defender = make_unit("D", atk=25, spd=10, defense=20)

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 5 damage
    # A2: offensive special ready, it triggers -> 5 + 5 = 10
    # D1: 5 damage
    # A3: offensive special ready, it triggers -> 5 + 5 = 10
    # A4: special is not ready -> 5 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 5 - 10 - 10 - 5
    # Triggers on A2 and A3, then resets
    assert engine.combatant_states["attacker"].special_use_count == 2
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_denied_off_special_does_not_trigger():
    """The foe denies offensive specials, so the attacker's never triggers."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [flat_damage(10, "unit_special_triggers")])
    defender = make_unit("D", atk=25, spd=10, defense=20)
    defender.active_statuses.append(denial_status({"off": True}))

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 10 damage
    # D1: 5 damage
    # A2: special is ready but denied, it doesn't trigger -> 10 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Never triggers, so it never resets
    assert engine.combatant_states["attacker"].special_use_count == 0
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_denied_def_special_does_not_trigger():
    """Same on the defensive side: the denied special grants no DR."""
    attacker = make_unit("A", atk=40, spd=30, defense=20)
    attacker.active_statuses.append(denial_status({"def": True}))
    defender = make_unit("D", atk=25, spd=10, defense=20)
    give_special(defender, SpecialType.DEF, [
        perc_dr(50, "unit_special_triggers", piercable=False, max_triggers=1),
    ])

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: defender special is not ready -> 20 damage
    # D1: 5 damage
    # A2: defender special is ready but denied, the DR doesn't apply -> 20 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 20 - 20
    # Never triggers, so it never resets
    assert engine.combatant_states["defender"].special_use_count == 0
    assert engine.combatant_states["defender"].current_cooldown == 0


def test_denied_aoe_special_does_not_fire_before_combat():
    """AoE denial resolves before _phase_AoE, so no pre-combat damage lands."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.AOE, [trigger_aoe(0.5)])
    attacker.pre_charge = 1
    defender = make_unit("D", atk=25, spd=10, defense=20)
    defender.active_statuses.append(denial_status({"aoe": True}))

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # AoE: special is ready but denied, no damage
    # A1: 10 damage
    # D1: 5 damage
    # A2: 10 damage
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Never triggers, so it never resets
    assert engine.combatant_states["attacker"].special_use_count == 0
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_denial_does_not_affect_readiness():
    """Denial blocks the trigger only: the special still counts as ready, so
    readiness gated effects keep applying."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [
        flat_damage(10, "unit_special_triggers"),
        flat_damage(5, "unit_special_ready"),
    ])
    defender = make_unit("D", atk=25, spd=10, defense=20)
    defender.active_statuses.append(denial_status({"off": True}))

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 10 damage
    # D1: 5 damage
    # A2: special is ready but denied, it doesn't trigger.
    #     Still, damage applies -> 30 - 20 + 5
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 15
    # Ready at A2 but never triggers, so it floors at 0
    assert engine.combatant_states["attacker"].special_use_count == 0
    assert engine.combatant_states["attacker"].current_cooldown == 0


def test_denied_special_does_not_satisfy_foe_special_triggers():
    """Both units carry an offensive special, only the attacker's is denied.
    The defender's DR is keyed on the foe triggering, so it never applies,
    while the defender's own special still triggers."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [flat_damage(10, "unit_special_triggers")])
    defender = make_unit("D", atk=25, spd=10, defense=20)
    give_special(defender, SpecialType.OFF, [
        flat_damage(5, "unit_special_triggers"),
        perc_dr(50, "foe_special_triggers", piercable=False, max_triggers=1),
    ])
    # target "foe" lands the denial in the attacker's list only
    defender.active_statuses.append(denial_status({"off": True}))

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: neither special is ready -> 10 damage
    # D1: defender special ready, it triggers -> 5 + 5 = 10 damage
    # A2: attacker special is ready but denied, it doesn't trigger.
    #     The DR depending on the foe triggering doesn't apply either -> 10 damage
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 10 - 10
    # Same type on both units, but only the attacker's is denied
    assert engine.combatant_states["attacker"].special_use_count == 0
    assert engine.combatant_states["defender"].special_use_count == 1


def test_aoe_denial_leaves_an_offensive_special_alone():
    """A denial that only covers AoE doesn't touch an offensive special."""
    attacker = make_unit("A", atk=30, spd=30, defense=20)
    give_special(attacker, SpecialType.OFF, [flat_damage(10, "unit_special_triggers")])
    defender = make_unit("D", atk=25, spd=10, defense=20)
    defender.active_statuses.append(denial_status({"aoe": True}))

    engine = CombatEngine(attacker, defender)
    result = engine.simulate()

    # A1: special is not ready -> 10 damage
    # D1: 5 damage
    # A2: offensive special ready, it triggers -> 10 + 10 = 20
    assert result["attacker_final_hp"] == 50 - 5
    assert result["defender_final_hp"] == 50 - 10 - 20
    # Triggers on A2 and resets
    assert engine.combatant_states["attacker"].special_use_count == 1
    assert engine.combatant_states["attacker"].current_cooldown == 1
