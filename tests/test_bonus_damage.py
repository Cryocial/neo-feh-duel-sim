"""
Treachery (damage = unit's total visible bonuses) and Dominance (damage = foe's
total visible penalties), both status-only and both formula-driven.

They follow the same two rules as the doublers: a neutralized layer counts as
absent (the foe's Lull for Treachery, the foe's own Neutralize Penalties for
Dominance), while a buff or debuff the 99 cap made useless still counts in
full, because it exists even if the stat couldn't show it.

Setup: one strike each, 40 Atk vs 20 Def deals 20; anything above that is the
formula's true damage.
"""

from backend.build import Unit, StatBlock, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine
from backend.jsonbootupstuff import BONUS_DATABASE


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


def flag(effect):
    return Status(name=effect, type="bonus", effects=[{
        "effect": effect, "target": "self", "params": {}, "conditions": [],
    }])


def dealt(result):
    return 100 - result["defender_final_hp"]


# ── Treachery ────────────────────────────────────────────────────────────────


def treacherous(buff=6, atk=40):
    attacker = make_unit("A", atk=atk)
    attacker.visible_buffs = StatBlock(atk=buff)
    attacker.active_statuses.append(BONUS_DATABASE["Treachery"])
    return attacker


def test_treachery_adds_the_units_bonuses_as_true_damage():
    """+6 Atk visible (20 -> 26) and +6 true damage on top."""
    assert dealt(CombatEngine(treacherous(), make_unit("D", hp=100)).simulate()) == 32


def test_treachery_is_inert_under_the_foes_lull():
    foe = make_unit("D", hp=100)
    foe.active_statuses.append(flag("BONUS_NEUT"))

    assert dealt(CombatEngine(treacherous(), foe).simulate()) == 20


def test_treachery_still_counts_a_buff_the_cap_wasted():
    """99 + 6 shows 99, so the hit is 79, but the +6 still lands as true damage."""
    assert dealt(CombatEngine(treacherous(atk=99), make_unit("D", hp=100)).simulate()) == 85


# ── Dominance ────────────────────────────────────────────────────────────────


def dominant():
    attacker = make_unit("A")
    attacker.active_statuses.append(BONUS_DATABASE["Dominance"])
    return attacker


def debuffed_foe(atk=25, debuff=5):
    foe = make_unit("D", hp=100, atk=atk)
    foe.visible_debuffs = StatBlock(atk=debuff)
    return foe


def test_dominance_adds_the_foes_penalties_as_true_damage():
    assert dealt(CombatEngine(dominant(), debuffed_foe()).simulate()) == 25


def test_dominance_is_inert_when_the_foe_neutralizes_its_penalties():
    foe = debuffed_foe()
    foe.active_statuses.append(flag("PENALTY_NEUT"))

    assert dealt(CombatEngine(dominant(), foe).simulate()) == 20


def test_dominance_still_counts_a_debuff_the_cap_hid():
    """Foe at 99 with +6/-5 shows 99 and the debuff cost it nothing, but
    Dominance still reads the 5."""
    foe = debuffed_foe(atk=99)
    foe.visible_buffs = StatBlock(atk=6)

    assert dealt(CombatEngine(dominant(), foe).simulate()) == 25
