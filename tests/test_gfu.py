"""
GFU - guaranteed follow-up.

Adds a follow-up for its holder regardless of Spd. It is COUNTED, not a flag:

    attacker_FU = nb_attacker_GFU * (1 - defender_DEF_NFU) - <denial> + spd_check

so two GFUs can out-arithmetic one denial. The engine still appends at most one
follow-up strike (`if attacker_FU > 0`), so a higher total is not more strikes.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_attacker, dealt_to_defender


def test_gfu_grants_follow_up_without_spd():
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    result = CombatEngine(attacker, order_unit("D")).simulate()
    assert dealt_to_defender(result) == 40
    assert dealt_to_attacker(result) == 20


def test_gfu_on_defender_grants_its_follow_up():
    defender = order_unit("D")
    defender.active_statuses.append(seq_status("GFU"))
    result = CombatEngine(order_unit("A"), defender).simulate()
    assert dealt_to_attacker(result) == 40
    assert dealt_to_defender(result) == 20


def test_both_sides_gfu():
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    defender = order_unit("D")
    defender.active_statuses.append(seq_status("GFU"))
    result = CombatEngine(attacker, defender).simulate()
    assert dealt_to_defender(result) == 40
    assert dealt_to_attacker(result) == 40


def test_only_one_follow_up_however_many_gfu():
    """Two GFUs are not two extra strikes - the engine appends at most one."""
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    attacker.active_statuses.append(seq_status("GFU"))
    result = CombatEngine(attacker, order_unit("D")).simulate()
    assert dealt_to_defender(result) == 40
