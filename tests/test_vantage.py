"""
VANTAGE - the defender strikes first.

Read from the DEFENDER's strike-sequence list, cancelled by VANTAGE_NEUT on the
attacker. It reorders the assembled packages:

    normal   attacker_first, defender_first, attacker_fu, defender_fu
    vantage  defender_first, attacker_first, defender_fu, attacker_fu

Order is observed through lethality: the defender is given enough Atk to one-shot
the attacker, so whoever strikes first decides whether the attacker ever lands a
hit. Note final HP can go negative on overkill, hence `<= 0` rather than `== 0`.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_defender, COMBAT_ORDER_HP


def test_vantage_lets_defender_strike_first():
    attacker = order_unit("A", hp=30, atk=40)
    defender = order_unit("D", atk=60)          # 60 - 20 = 40 >= attacker's 30 HP
    defender.active_statuses.append(seq_status("VANTAGE"))

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] <= 0             # died before striking
    assert result["defender_final_hp"] == COMBAT_ORDER_HP  # never took a hit


def test_without_vantage_attacker_strikes_first():
    """Same lethal defender, no Vantage: the attacker gets its hit in first."""
    attacker = order_unit("A", hp=30, atk=40)
    defender = order_unit("D", atk=60)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] <= 0     # still dies on the counter
    assert dealt_to_defender(result) == 20      # but landed its strike first


def test_vantage_neut_cancels_vantage():
    """VANTAGE_NEUT on the attacker restores normal order."""
    attacker = order_unit("A", hp=30, atk=40)
    attacker.active_statuses.append(seq_status("VANTAGE_NEUT"))
    defender = order_unit("D", atk=60)
    defender.active_statuses.append(seq_status("VANTAGE"))

    result = CombatEngine(attacker, defender).simulate()

    assert dealt_to_defender(result) == 20      # attacker struck first
