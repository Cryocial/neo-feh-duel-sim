"""
OFF_NFU - neutralises a denial aimed at its holder's own follow-up.

It zeroes the denial term in the follow-up arithmetic:

    ... - <denial> * (1 - attacker_OFF_NFU) ...

so it can only ever restore a follow-up that a denial removed. It never creates
one by itself.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_defender


def test_off_nfu_restores_a_denied_follow_up():
    attacker = order_unit("A", spd=25)
    attacker.active_statuses.append(seq_status("FU_DENY"))
    attacker.active_statuses.append(seq_status("OFF_NFU"))
    result = CombatEngine(attacker, order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 40


def test_off_nfu_alone_creates_nothing():
    """With no denial to cancel and no Spd gap, OFF_NFU must not conjure a
    follow-up on its own."""
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("OFF_NFU"))
    result = CombatEngine(attacker, order_unit("D")).simulate()
    assert dealt_to_defender(result) == 20
