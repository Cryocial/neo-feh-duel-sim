"""
OFF_FROZEN / DEF_FROZEN - shift the Spd threshold for the natural follow-up.

The requirement becomes:

    spd_diff >= 5 - off_frozen + def_frozen

Both are read from the unit's OWN strike-sequence list (OFF_FROZEN granted
there makes its follow-up easier, DEF_FROZEN inflicted there makes it harder),
and both are resolved through _resolve_formula, so they carry a magnitude
rather than being presence flags.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, seq_status, dealt_to_defender


def test_off_frozen_lowers_the_follow_up_threshold():
    """OFF_FROZEN 5 makes the requirement `spd_diff >= 5 - 5 = 0`, so equal Spd
    is now enough for a natural follow-up."""
    attacker = order_unit("A", spd=20)
    attacker.active_statuses.append(seq_status("OFF_FROZEN", {"flat": 5}))
    result = CombatEngine(attacker, order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 40


def test_def_frozen_raises_the_follow_up_threshold():
    """DEF_FROZEN 5 makes the requirement `spd_diff >= 5 + 5 = 10`, so a +5 Spd
    lead is no longer enough."""
    attacker = order_unit("A", spd=25)
    attacker.active_statuses.append(seq_status("DEF_FROZEN", {"flat": 5}))
    result = CombatEngine(attacker, order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 20


def test_frozen_effects_cancel_each_other():
    """`5 - off + def` with both at 5 returns the threshold to the usual 5."""
    attacker = order_unit("A", spd=25)
    attacker.active_statuses.append(seq_status("OFF_FROZEN", {"flat": 5}))
    attacker.active_statuses.append(seq_status("DEF_FROZEN", {"flat": 5}))
    result = CombatEngine(attacker, order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 40
