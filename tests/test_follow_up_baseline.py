"""
Baseline follow-up behaviour with no effects involved.

Establishes the two reference points every other combat-order test is measured
against: equal Spd means one strike each, and a 5+ Spd advantage is the natural
follow-up (spd_check). If these break, the failures in the GFU / FU_DENY / NFU
files are not about those effects.
"""

from backend.combatcalculator import CombatEngine
from conftest import order_unit, dealt_to_attacker, dealt_to_defender


def test_baseline_one_strike_each():
    """Equal Spd, no effects: one strike each, 40-20=20 damage apiece."""
    result = CombatEngine(order_unit("A"), order_unit("D")).simulate()
    assert dealt_to_defender(result) == 20
    assert dealt_to_attacker(result) == 20


def test_spd_gap_gives_natural_follow_up():
    """A 5+ Spd advantage is the natural follow-up, no effects involved."""
    result = CombatEngine(order_unit("A", spd=25), order_unit("D", spd=20)).simulate()
    assert dealt_to_defender(result) == 40
    assert dealt_to_attacker(result) == 20
