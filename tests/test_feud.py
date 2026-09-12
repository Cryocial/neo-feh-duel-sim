"""
FEUD disables the skills of a unit's allies during combat. Blue Feud 3 reads:

    During combat, disables skills of all blue foes, excluding foe in combat.
    If in combat against a blue foe, disables skills of all foes, excluding
    foe in combat, and inflicts Atk/Spd/Def/Res-4 on foe during combat.

Ally skills enter through Unit.ally_supports, each tagged with the ally's
colour. A Drive (target "self") lands on the supported unit as "ally"; a Crux
(target "foe") lands on that unit's opponent as "enemy". FEUD sits on the unit
whose allies are disabled, the way FU_DENY sits on the unit that can't follow
up, so the data decides direction:

    Blue Feud 3 on me   {"effect": "FEUD", "target": "foe",  "params": {"colors": ["BLUE"]}}
    [Feud] debuff       {"effect": "FEUD", "target": "self", "params": {}}

With `colors`, an ally is disabled if its own colour is listed (first clause),
or every ally is if the unit it supports is of a listed colour (second
clause). Without `colors`, every ally. The -4 is not part of FEUD: it belongs
to the skill's JSON as a STAT_DAUNT gated on the `foe_color` condition.

Setup: one strike each. Units are colourless unless a test says otherwise, so
the weapon triangle never interferes. The 40 Atk attacker deals 20 to a 20 Def
foe; the 25 Atk foe counters for 5. Drives are +6 Atk and Cruxes -6 Atk, so
each live Drive on the foe adds 6 to what I take and each live Crux on me
takes 6 off what I deal.
"""

from backend.build import Unit, Skill, StatBlock, Status, AllySupport
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(name, color=Color.COLORLESS, hp=50, atk=40, spd=10, defense=20, res=20):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=WeaponType.SWORD,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def skill(name, effects):
    return Skill(
        name=name, slot="c", might=0, slaying=0, cooldown=0,
        visible_stats=StatBlock(), effects=effects,
        allowed_movement_types=[], allowed_weapon_types=[],
    )


def drive_atk():
    return skill("Drive Atk", [{
        "effect": "STAT_BOOST", "target": "self",
        "params": {"stats": ["atk"], "flat": 6}, "conditions": [],
    }])


def crux_atk():
    return skill("Atk Crux", [{
        "effect": "STAT_DAUNT", "target": "foe",
        "params": {"stats": ["atk"], "flat": 6}, "conditions": [],
    }])


def feud_skill(colors, conditions=()):
    """A Feud A-skill on its holder: the FEUD lands on the foe."""
    return skill("Feud", [{
        "effect": "FEUD", "target": "foe",
        "params": {"colors": colors}, "conditions": list(conditions),
    }])


def feud_debuff():
    """The [Feud] status on its victim: no colour filter."""
    return Status(name="Feud", type="penalty", effects=[{
        "effect": "FEUD", "target": "self", "params": {}, "conditions": [],
    }])


def supported(color, *allies):
    """A foe of `color` with one Drive per ally colour given."""
    unit = make_unit("D", color=color, hp=100, atk=25)
    unit.ally_supports.extend(AllySupport(drive_atk(), ally) for ally in allies)
    return unit


def with_feud(colors, conditions=()):
    attacker = make_unit("A")
    attacker.a_slot = feud_skill(colors, conditions)
    return attacker


def taken(result):
    return 50 - result["attacker_final_hp"]


def dealt(result):
    return 100 - result["defender_final_hp"]


# ── the two clauses ──────────────────────────────────────────────────────────


def test_a_drive_from_the_foes_ally_raises_its_counter():
    result = CombatEngine(make_unit("A"), supported(Color.COLORLESS, Color.BLUE)).simulate()

    assert taken(result) == 11


def test_feud_disables_listed_colour_allies_of_any_foe():
    """First clause. Green foe with a blue and a red ally: B Feud strips the
    blue one's Drive and leaves the red one's."""
    result = CombatEngine(
        with_feud(["BLUE"]), supported(Color.GREEN, Color.BLUE, Color.RED)
    ).simulate()

    assert taken(result) == 11               # only the red Drive survives


def test_feud_leaves_unlisted_allies_of_an_unlisted_foe_alone():
    result = CombatEngine(with_feud(["BLUE"]), supported(Color.GREEN, Color.RED)).simulate()

    assert taken(result) == 11


def test_feud_disables_every_ally_of_a_listed_colour_foe():
    """Second clause. Against a blue foe even the red ally's Drive is gone."""
    result = CombatEngine(with_feud(["BLUE"]), supported(Color.BLUE, Color.RED)).simulate()

    assert taken(result) == 5


def test_feud_leaves_the_foes_own_skills_alone():
    """'Excluding foe in combat': its own Drive is not an ally's."""
    defender = supported(Color.BLUE)
    defender.c_slot = drive_atk()

    result = CombatEngine(with_feud(["BLUE"]), defender).simulate()

    assert taken(result) == 11


def test_feud_disables_a_listed_allys_crux_on_me_but_not_an_unlisted_ones():
    def foe_with_crux(ally_color):
        unit = make_unit("D", color=Color.GREEN, hp=100, atk=25)
        unit.ally_supports.append(AllySupport(crux_atk(), ally_color))
        return unit

    no_feud = CombatEngine(make_unit("A"), foe_with_crux(Color.BLUE)).simulate()
    blue_crux = CombatEngine(with_feud(["BLUE"]), foe_with_crux(Color.BLUE)).simulate()
    red_crux = CombatEngine(with_feud(["BLUE"]), foe_with_crux(Color.RED)).simulate()

    assert dealt(no_feud) == 14
    assert dealt(blue_crux) == 20            # stripped
    assert dealt(red_crux) == 14             # kept


def test_feud_leaves_my_own_allies_alone():
    attacker = with_feud(["BLUE"])
    attacker.ally_supports.append(AllySupport(drive_atk(), Color.BLUE))

    result = CombatEngine(attacker, supported(Color.BLUE)).simulate()

    assert dealt(result) == 26


def test_feud_debuff_disables_allies_of_every_colour():
    defender = supported(Color.GREEN, Color.RED)
    defender.active_statuses.append(feud_debuff())

    result = CombatEngine(make_unit("A"), defender).simulate()

    assert taken(result) == 5


# ── the worked example: both sides carry Colorless Feud ──────────────────────


def test_worked_example_green_vs_colorless_with_feud_on_both_sides():
    """I am green with a blue and a colourless ally; the foe is colourless with
    a blue and a green ally; both of us have Colorless Feud.

    - The foe is colourless, so my Feud's second clause strips both its allies.
    - I am green, so the foe's Feud only reaches my colourless ally (first
      clause); my blue ally's Drive survives.
    """
    me = make_unit("A", color=Color.GREEN)
    me.a_slot = feud_skill(["COLORLESS"])
    me.ally_supports.extend([
        AllySupport(drive_atk(), Color.BLUE),
        AllySupport(drive_atk(), Color.COLORLESS),
    ])
    foe = supported(Color.COLORLESS, Color.BLUE, Color.GREEN)
    foe.a_slot = feud_skill(["COLORLESS"])

    result = CombatEngine(me, foe).simulate()

    assert dealt(result) == 26               # 40 + 6 (blue ally only) - 20
    assert taken(result) == 5                # 25, no Drives left


# ── conditions ───────────────────────────────────────────────────────────────


def test_feud_with_a_resolved_condition_applies():
    attacker = with_feud(["BLUE"], conditions=[{"type": "unit_initiates"}])

    result = CombatEngine(attacker, supported(Color.BLUE, Color.RED)).simulate()

    assert taken(result) == 5


def test_feud_gated_on_a_post_aoe_condition_still_applies():
    """The HP% check resolves in the post_aoe pass; Feud is re-applied right
    after it, so the Drive is stripped before combat stats are computed."""
    attacker = with_feud(
        ["BLUE"], conditions=[{"type": "hp_below_pct", "params": {"threshold": 100}}]
    )
    attacker.current_hp = 40                 # 80%, so hp_below_pct 100 holds

    result = CombatEngine(attacker, supported(Color.BLUE, Color.RED)).simulate()

    assert result["attacker_final_hp"] == 40 - 5


def test_foe_color_condition_matches_the_foes_colour():
    """The generic `foe_color` condition, which skill JSON uses for any
    "if in combat against a [colour] foe" clause. Here it gates a debuff: it
    lands on a blue foe and not on a green one."""
    def attacker_with_gated_debuff():
        unit = make_unit("A")
        unit.b_slot = skill("Gated debuff", [{
            "effect": "STAT_DAUNT", "target": "foe",
            "params": {"stats": ["atk"], "flat": 4},
            "conditions": [{"type": "foe_color", "params": {"colors": ["BLUE"]}}],
        }])
        return unit

    vs_blue = CombatEngine(attacker_with_gated_debuff(), supported(Color.BLUE)).simulate()
    vs_green = CombatEngine(attacker_with_gated_debuff(), supported(Color.GREEN)).simulate()

    assert taken(vs_blue) == 1
    assert taken(vs_green) == 5
