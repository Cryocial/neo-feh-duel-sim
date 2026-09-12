"""
FU_DENY - removes a follow-up.

The engine reads the denial term for a unit's own follow-up from that unit's
OWN strike-sequence list, so a denial is authored onto the unit whose follow-up
is being taken away. That matches the "one side only" modelling used elsewhere
(model the effect on the unit it acts upon), which means a real "inflicts foe
cannot follow up" skill is authored with "target": "foe" so it lands in the
victim's list.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_defender


def test_fu_deny_cancels_own_natural_follow_up():
    """FU_DENY in a unit's own list removes that unit's Spd-based follow-up."""
    attacker = order_unit("A", spd=25)
    attacker.active_statuses.append(seq_status("FU_DENY"))
    result = CombatEngine(attacker, order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 20


def test_fu_deny_cancels_own_gfu():
    """GFU (+1) and a denial (-1) on the same unit cancel to no follow-up."""
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    attacker.active_statuses.append(seq_status("FU_DENY"))
    result = CombatEngine(attacker, order_unit("D")).simulate()
    assert dealt_to_defender(result) == 20


def test_two_gfu_beat_one_denial():
    """GFU is counted: 2 - 1 = 1 > 0, so the follow-up still happens."""
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    attacker.active_statuses.append(seq_status("GFU"))
    attacker.active_statuses.append(seq_status("FU_DENY"))
    result = CombatEngine(attacker, order_unit("D")).simulate()
    assert dealt_to_defender(result) == 40
