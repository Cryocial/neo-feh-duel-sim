"""
PHANTOM_STAT: a stat boost that stat comparisons can see but that never
decides follow-ups. It accumulates into CombatantState.phantom_bonus, read by
cbt_stat_with_phantom, which the `phantom_spd_diff` formula (Dodge) and the
`cbt_stat_check` condition use; the follow-up check reads combat_stats
directly and ignores it.

Setup: sword attacker at 40 Atk vs a 20 Def defender, 100 HP: 20 per hit.
Dodge is the real status from statuses.json (Spd diff x 4, max 40%).
"""

from backend.build import Unit, Skill, StatBlock, Status
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


def phantom_spd(amount):
    return Status(name="Phantom Spd", type="bonus", effects=[{
        "effect": "PHANTOM_STAT", "target": "self",
        "params": {"stats": ["spd"], "flat": amount}, "conditions": [],
    }])


def dealt(result):
    return 100 - result["defender_final_hp"]


def test_phantom_spd_feeds_dodge():
    """Equal 30 Spd gives Dodge nothing; +5 Phantom Spd on the defender makes
    the diff 5, so Dodge cuts the hit by 20%: ceil(20 x 0.8) = 16."""
    def defender(with_phantom):
        unit = make_unit("D", hp=100, spd=30)
        unit.active_statuses.append(BONUS_DATABASE["Dodge"])
        if with_phantom:
            unit.active_statuses.append(phantom_spd(5))
        return unit

    assert dealt(CombatEngine(make_unit("A", spd=30), defender(False)).simulate()) == 20
    assert dealt(CombatEngine(make_unit("A", spd=30), defender(True)).simulate()) == 16


def test_phantom_spd_never_decides_follow_ups():
    """The attacker is 5 faster and keeps its follow-up even though the
    defender's Phantom Spd would put it 5 ahead. Dodge still sees the phantom
    diff (40 vs 35 = 5, so 20% per hit): two hits of 16."""
    attacker = make_unit("A", spd=35)
    defender = make_unit("D", hp=100, atk=25, spd=30)
    defender.active_statuses.append(BONUS_DATABASE["Dodge"])
    defender.active_statuses.append(phantom_spd(10))

    result = CombatEngine(attacker, defender).simulate()

    assert dealt(result) == 32                      # follow-up happened
    assert result["attacker_final_hp"] == 50 - 5    # defender got no follow-up


def test_cbt_stat_check_includes_phantom_unless_told_not_to():
    """Defender's +6 true damage needs Spd >= the attacker's 32: 30 + 5
    Phantom passes, but with include_phantom false the bare 30 fails. The
    gated effect is on-strike, whose list is read after the condition pass."""
    def defender(include_phantom):
        unit = make_unit("D", hp=100, atk=25, spd=30)
        unit.active_statuses.append(phantom_spd(5))
        unit.a_slot = Skill(
            name="Gated", slot="passive_a", might=0, slaying=0, cooldown=0,
            visible_stats=StatBlock(), allowed_movement_types=[], allowed_weapon_types=[],
            effects=[{
                "effect": "FLAT_DAMAGE_STRIKE", "target": "self",
                "params": {"flat": 6, "strike": "every_strike"},
                "conditions": [{
                    "type": "cbt_stat_check",
                    "params": {"stat": "spd", "margin": 0, "include_phantom": include_phantom},
                }],
            }],
        )
        return unit

    with_phantom = CombatEngine(make_unit("A", spd=32), defender(True)).simulate()
    without = CombatEngine(make_unit("A", spd=32), defender(False)).simulate()

    assert with_phantom["attacker_final_hp"] == 50 - 11
    assert without["attacker_final_hp"] == 50 - 5
