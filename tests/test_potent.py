"""
POTENT: an extra, reduced follow-up appended after the unit's other strikes.

`damage_pct` scales it (trunc), and `damage_pct_if_fu` replaces that when the
unit already makes a follow-up (or has Brave). The trigger lives in the
conditions: `potent_spd_check` lowers the usual 5-Spd follow-up requirement by
`spd_lower`, and `potent_patience` is the guaranteed variant for units whose
base Spd is 30 or more.

Setup: sword attacker at 40 Atk vs a 20 Def defender, 100 HP: 20 per hit,
so a Potent at 80% adds trunc(16) and at 40% adds trunc(8).
"""

import pytest

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=Color.RED,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def potent(condition, pct=80, pct_if_fu=None):
    params = {"damage_pct": pct}
    if pct_if_fu is not None:
        params["damage_pct_if_fu"] = pct_if_fu
    return Status(name="Potent", type="bonus", effects=[{
        "effect": "POTENT", "target": "self", "params": params, "conditions": [condition],
    }])


def spd_check(spd_lower):
    return {"type": "potent_spd_check", "params": {"spd_lower": spd_lower}}


def fight(attacker):
    return 100 - CombatEngine(attacker, make_unit("D", hp=100, spd=30)).simulate()["defender_final_hp"]


def test_potent_appends_a_reduced_strike():
    """Equal Spd, no natural follow-up: A1 (20), then Potent trunc(20 x 0.8)."""
    attacker = make_unit("A", spd=30)
    attacker.active_statuses.append(potent(spd_check(25)))

    assert fight(attacker) == 20 + 16


def test_potent_uses_its_follow_up_percent_when_the_unit_already_follows_up():
    attacker = make_unit("A", spd=40)
    attacker.active_statuses.append(potent(spd_check(25), pct=80, pct_if_fu=40))

    assert fight(attacker) == 20 + 20 + 8


def test_potent_spd_check_needs_spd_diff_of_five_minus_spd_lower():
    """spd_lower 0 is the plain follow-up requirement; at equal Spd it fails."""
    attacker = make_unit("A", spd=30)
    attacker.active_statuses.append(potent(spd_check(0)))

    assert fight(attacker) == 20


def test_potent_patience_reads_base_spd():
    patience = {"type": "potent_patience", "params": {}}

    fast = make_unit("A", spd=30)
    fast.active_statuses.append(potent(patience))
    slow = make_unit("A", spd=29)
    slow.active_statuses.append(potent(patience))

    assert fight(fast) == 36
    assert fight(slow) == 20


def test_potent_spd_check_needs_a_spd_lower():
    """potent_spd_check with no spd_lower is malformed and fails at load."""
    attacker = make_unit("A", spd=30)
    attacker.active_statuses.append(potent({"type": "potent_spd_check", "params": {}}))

    with pytest.raises(KeyError):
        CombatEngine(attacker, make_unit("D", hp=100)).simulate()
