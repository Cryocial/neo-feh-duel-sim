"""
DESPERATION - the attacker's follow-up comes before the defender's counter.

Read from the ATTACKER's strike-sequence list, cancelled by DESPERATION_NEUT on
the defender:

    normal       attacker_first, defender_first, attacker_fu, defender_fu
    desperation  attacker_first, attacker_fu, defender_first, defender_fu
    with vantage defender_first, attacker_first, attacker_fu, defender_fu

Order is observed by making the attacker's two hits exactly lethal: with
Desperation both land before any counter, so the attacker takes nothing.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_attacker, COMBAT_ORDER_HP


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
