"""
DESPERATION - a unit's follow-up comes right after its own first strike.

Read from the holder's strike-sequence list, cancelled by DESPERATION_NEUT on
the opponent. Either side can hold it (L!Seliph's prf grants it on defence):

    normal            attacker_first, defender_first, attacker_fu, defender_fu
    atk desperation   attacker_first, attacker_fu, defender_first, defender_fu
    def desperation   attacker_first, defender_first, defender_fu, attacker_fu
    vantage           defender_first, attacker_first, defender_fu, attacker_fu
    vantage + atk d.  defender_first, attacker_first, attacker_fu, defender_fu
    vantage + def d.  defender_first, defender_fu, attacker_first, attacker_fu

Order is observed by making the desperate side's two hits exactly lethal: they
land back to back, so the other side never gets its follow-up (or, under
Vantage + defender Desperation, never strikes at all).
"""

from backend.combatcalculator import CombatEngine
from conftest import (
    COMBAT_ORDER_HP,
    dealt_to_attacker,
    dealt_to_defender,
    order_unit,
    seq_status,
)


def test_desperation_puts_follow_up_before_the_counter():
    attacker = order_unit("A", spd=25, atk=40)
    attacker.active_statuses.append(seq_status("DESPERATION"))
    defender = order_unit("D", hp=40, spd=20)      # 2 x 20 damage = exactly lethal

    result = CombatEngine(attacker, defender).simulate()

    assert result["defender_final_hp"] == 0
    assert result["attacker_final_hp"] == COMBAT_ORDER_HP   # never countered


def test_without_desperation_counter_lands_between_strikes():
    """Same numbers without Desperation: the defender counters after the
    attacker's first strike, so the attacker does take damage."""
    attacker = order_unit("A", spd=25, atk=40)
    defender = order_unit("D", hp=40, spd=20)

    result = CombatEngine(attacker, defender).simulate()

    assert result["defender_final_hp"] == 0
    assert dealt_to_attacker(result) == 20        # got one counter in


def test_desperation_neut_cancels_desperation():
    attacker = order_unit("A", spd=25, atk=40)
    attacker.active_statuses.append(seq_status("DESPERATION"))
    defender = order_unit("D", hp=40, spd=20)
    defender.active_statuses.append(seq_status("DESPERATION_NEUT"))

    result = CombatEngine(attacker, defender).simulate()

    assert dealt_to_attacker(result) == 20        # counter landed between hits


def test_vantage_and_desperation_together():
    """Both active: defender_first, attacker_first, attacker_fu, defender_fu.
    The defender opens, then the attacker's two strikes land back to back."""
    attacker = order_unit("A", spd=25, atk=40)
    attacker.active_statuses.append(seq_status("DESPERATION"))
    defender = order_unit("D", hp=40, spd=20, atk=30)
    defender.active_statuses.append(seq_status("VANTAGE"))

    result = CombatEngine(attacker, defender).simulate()

    # defender opens for 30-20=10, then the attacker's 2x20 finishes it
    assert result["defender_final_hp"] == 0
    assert dealt_to_attacker(result) == 10        # only the opening hit landed


# ── defender-side desperation ────────────────────────────────────────────────
#
# Both sides need a follow-up for the defender's Desperation to have anything
# to reorder: the attacker is 5 Spd faster (natural follow-up) and the slower
# defender carries GFU. The attacker has exactly 40 HP, so the defender's
# 2 x 20 is lethal; how much the attacker dealt before dying tells the order.


def fragile_attacker():
    return order_unit("A", hp=40, spd=25)


def defender_with_gfu(*effects):
    defender = order_unit("D", spd=20)
    for name in ("GFU", *effects):
        defender.active_statuses.append(seq_status(name))
    return defender


def test_defender_desperation_puts_its_follow_up_before_the_attackers():
    """attacker_first, defender_first, defender_fu, attacker_fu: the defender's
    two hits land back to back after the opener, so the attacker's follow-up
    never comes."""
    result = CombatEngine(fragile_attacker(), defender_with_gfu("DESPERATION")).simulate()

    assert result["attacker_final_hp"] == 0
    assert dealt_to_defender(result) == 20        # only the opener landed


def test_without_defender_desperation_attacker_follow_up_lands_between():
    """Same numbers, no Desperation: attacker_fu comes before defender_fu, so
    the attacker gets both of its hits in before dying."""
    result = CombatEngine(fragile_attacker(), defender_with_gfu()).simulate()

    assert result["attacker_final_hp"] == 0
    assert dealt_to_defender(result) == 40        # opener + follow-up


def test_desperation_neut_on_attacker_cancels_defender_desperation():
    attacker = fragile_attacker()
    attacker.active_statuses.append(seq_status("DESPERATION_NEUT"))

    result = CombatEngine(attacker, defender_with_gfu("DESPERATION")).simulate()

    assert dealt_to_defender(result) == 40        # normal interleaving restored


def test_vantage_and_defender_desperation_together():
    """defender_first, defender_fu, attacker_first, attacker_fu: the defender
    strikes twice before the attacker moves at all."""
    result = CombatEngine(
        fragile_attacker(), defender_with_gfu("VANTAGE", "DESPERATION")
    ).simulate()

    assert result["attacker_final_hp"] == 0
    assert dealt_to_defender(result) == 0         # never got to strike


def test_vantage_alone_still_lets_attacker_strike_between():
    """Vantage without Desperation: defender_first, attacker_first, defender_fu.
    The attacker lands its opener before the defender's follow-up kills it."""
    result = CombatEngine(fragile_attacker(), defender_with_gfu("VANTAGE")).simulate()

    assert result["attacker_final_hp"] == 0
    assert dealt_to_defender(result) == 20
