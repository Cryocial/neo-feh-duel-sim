"""
DEF_NFU - neutralises the FOE's guaranteed follow-up.

It zeroes the foe's GFU term:

    attacker_FU = nb_attacker_GFU * (1 - defender_DEF_NFU) - ... + spd_check

Note it multiplies the GFU term only, so a Spd-based follow-up (added separately
by spd_check) is unaffected.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_defender


def test_def_nfu_cancels_foes_gfu():
    attacker = order_unit("A")
    attacker.active_statuses.append(seq_status("GFU"))
    defender = order_unit("D")
    defender.active_statuses.append(seq_status("DEF_NFU"))
    result = CombatEngine(attacker, defender).simulate()
    assert dealt_to_defender(result) == 20


def test_def_nfu_does_not_stop_a_natural_follow_up():
    """DEF_NFU only neutralises GFU; the Spd-based follow-up survives."""
    defender = order_unit("D", spd=20)
    defender.active_statuses.append(seq_status("DEF_NFU"))
    result = CombatEngine(order_unit("A", spd=25), defender).simulate()
    assert dealt_to_defender(result) == 40
