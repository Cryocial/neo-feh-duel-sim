"""
Reflected damage. REFLEX returns the damage a hit had negated; BRIAR returns a
percentage of the hit's damage before any reduction. Both fill the target's
reflect_bucket, which its very next strike spends in full as true damage.

Setup: sword attacker at 40 Atk / 20 Def, Spd 30 so it strikes twice; defender
at 30 Atk / 20 Def, Spd 10, 100 HP. The attacker's raw hit is 20 and the
defender's counter is 10, so anything the counter deals above 10 is reflection.
"""

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20,
              weapon_type=WeaponType.SWORD):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def status(effect, params):
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": "self", "params": params, "conditions": [],
    }])


def half_dr(strike="first_strike"):
    return status("PERC_DR_STRIKE", {"flat": 50, "strike": strike, "piercable": True})


def reflex(strike="first_strike"):
    return status("REFLEX", {"strike": strike})


def briar(pct=40, strike="first_strike"):
    return status("BRIAR", {"flat": pct, "strike": strike})


def defender(*statuses):
    unit = make_unit("D", hp=100, atk=30)
    unit.active_statuses.extend(statuses)
    return unit


def taken_by_attacker(result):
    return 50 - result["attacker_final_hp"]


def test_reflex_returns_the_damage_it_negated():
    """First strike: 20 halved to 10, so 10 was negated. The counter deals its
    usual 10 plus the reflected 10."""
    result = CombatEngine(make_unit("A", spd=30), defender(half_dr(), reflex())).simulate()

    assert taken_by_attacker(result) == 20
    assert result["defender_final_hp"] == 100 - 10 - 20


def test_reflex_without_any_reduction_reflects_nothing():
    result = CombatEngine(make_unit("A", spd=30), defender(reflex())).simulate()

    assert taken_by_attacker(result) == 10


def test_briar_returns_a_share_of_the_unreduced_hit():
    """40% of the 20-damage first strike, floored: 8 on top of the counter."""
    result = CombatEngine(make_unit("A", spd=30), defender(briar(40))).simulate()

    assert taken_by_attacker(result) == 18


def test_briar_measures_before_the_reduction():
    """Even when the hit is halved to 10, Briar reads the 20 it started from."""
    result = CombatEngine(make_unit("A", spd=30), defender(half_dr(), briar(40))).simulate()

    assert taken_by_attacker(result) == 18


def test_briar_reads_the_staff_hit_after_its_halving():
    """A staff's x0.5 is part of the hit, not a reduction: 40 Atk vs 20 Res is
    20, halved to 10, and Briar reflects 40% of that 10 = 4. The defender needs
    COUNTERATTACK to answer a ranged foe at all."""
    attacker = make_unit("A", spd=30, weapon_type=WeaponType.STAFF)
    foe = defender(briar(40), status("COUNTERATTACK", {}))

    result = CombatEngine(attacker, foe).simulate()

    assert taken_by_attacker(result) == 14


def test_reflex_sources_stack():
    """Two Reflex effects on the same halved hit each return the 10 negated."""
    result = CombatEngine(make_unit("A", spd=30), defender(half_dr(), reflex(), reflex())).simulate()

    assert taken_by_attacker(result) == 10 + 20


def test_briar_uses_only_the_highest_percent():
    """40% and 20% Briar on the same 20-damage hit reflect 8, not 8 + 4."""
    result = CombatEngine(make_unit("A", spd=30), defender(briar(40), briar(20))).simulate()

    assert taken_by_attacker(result) == 18


def test_reflected_damage_is_spent_on_one_strike():
    """GFU gives the defender a follow-up, so the order is A1 D1 A2 D2. Reflex
    matches the first strike only: D1 carries the 10 reflected, D2 is plain."""
    foe = defender(half_dr(), reflex(), status("GFU", {}))

    result = CombatEngine(make_unit("A", spd=30), foe).simulate()

    assert taken_by_attacker(result) == 20 + 10


def test_reflect_bucket_refills_on_the_next_matching_hit():
    """Same exchange with both effects on every strike: A2 is halved too, so D2
    carries a fresh 10. Each counter spends only what the hit before it added."""
    foe = defender(half_dr("every_strike"), reflex("every_strike"), status("GFU", {}))

    result = CombatEngine(make_unit("A", spd=30), foe).simulate()

    assert taken_by_attacker(result) == 20 + 20
