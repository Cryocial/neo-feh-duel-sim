"""
Special cooldown charge: Breath, Guard, Pulse and Scowl.

Every strike moves both units' Special cooldowns. A unit whose Special did NOT
trigger on that strike charges by:

    charge = 1 + int(breath and not breath_neut) - int(guard and not guard_neut)
    current_cooldown = max(0, current_cooldown - charge)

with the effects read from the charging unit's OWN effects_on_strike list:

  striker side   OFF_BREATH (+1 when attacking), DEF_GUARD (-1)
  target side    DEF_BREATH (+1 when struck),    OFF_GUARD (-1)

The Guard types are named for who INFLICTS them, so they sit in the victim's
own list: DEF_GUARD slows the unit while it attacks, OFF_GUARD slows it while it
is being attacked. BREATH_NEUT and GUARD_NEUT cancel their family, also from the
holder's own list.

Breath and Guard are presence flags, not sums - `int(any(...))` - so two Breath
sources still give +1 ("only the highest value is applied; does not stack").

Separately, before the ready-check, PULSE_STRIKE subtracts from the cooldown and
SCOWL_STRIKE adds to it, both resolved through _resolve_formula so they carry a
magnitude.

Setup: same colour, both melee, equal Spd, so exactly one strike each and no
follow-ups to muddy the count. Specials carry a large max_cooldown and never
trigger, so the assertions read the cooldown directly after a single exchange.
"""

from backend.build import Unit, Skill, Status, StatBlock
from backend.constants import MovementType, WeaponType, SpecialType, Color
from backend.combatcalculator import CombatEngine


START_CD = 5


def make_unit(name, color=Color.RED, hp=200, atk=40, spd=20, defense=20, res=20):
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


def give_special(unit, max_cooldown=START_CD, effects=None):
    """An OFF Special with a cooldown high enough that it never reaches 0 in a
    single exchange, so the tests observe charging rather than triggering."""
    unit.special = Skill(
        name="Test Special", slot="special", might=0, slaying=0,
        cooldown=max_cooldown, visible_stats=StatBlock(),
        effects=effects or [], allowed_movement_types=[], allowed_weapon_types=[],
        special_type=SpecialType.OFF,
    )
    unit.max_cooldown = max_cooldown
    return unit


def status(effect, params=None):
    return Status(
        name=f"Test {effect}",
        type="bonus",
        effects=[{
            "effect": effect,
            "target": "self",
            "params": params or {},
            "conditions": [],
        }],
    )


def run(attacker, defender):
    engine = CombatEngine(attacker, defender)
    engine.simulate()
    return engine


def attacker_cd(engine):
    return engine.combatant_states["attacker"].current_cooldown


def defender_cd(engine):
    return engine.combatant_states["defender"].current_cooldown


# ── baseline: one charge per strike, on both sides ───────────────────────────

def test_baseline_charges_once_per_strike():
    """One exchange: the attacker charges 1 for attacking, the defender charges
    1 for being attacked (and 1 more for its own counter)."""
    attacker = give_special(make_unit("A"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    # attacker: -1 for its strike, -1 for being hit by the counter
    assert attacker_cd(engine) == START_CD - 2
    assert defender_cd(engine) == START_CD - 2


# ── OFF_BREATH: +1 while attacking ───────────────────────────────────────────

def test_off_breath_adds_a_charge_when_attacking():
    """OFF_BREATH gives +1 on the strike the unit makes, so 2 instead of 1
    there; being hit by the counter still charges the usual 1."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 3   # 2 attacking + 1 struck


def test_off_breath_does_not_help_while_being_struck():
    """OFF_BREATH is the attacking-side bonus only. Give it to the defender and
    its charge is unchanged on the strike it receives; it only benefits on its
    own counter."""
    attacker = give_special(make_unit("A"))
    defender = give_special(make_unit("D"))
    defender.active_statuses.append(status("OFF_BREATH"))

    engine = run(attacker, defender)

    # defender: 1 struck + 2 on its own counter
    assert defender_cd(engine) == START_CD - 3


def test_off_breath_does_not_stack():
    """Presence flag, not a sum: two sources still give +1."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 3   # not -4


# ── DEF_BREATH: +1 while being struck ────────────────────────────────────────

def test_def_breath_adds_a_charge_when_struck():
    """DEF_BREATH gives +1 on the strike the unit receives."""
    attacker = give_special(make_unit("A"))
    defender = give_special(make_unit("D"))
    defender.active_statuses.append(status("DEF_BREATH"))

    engine = run(attacker, defender)

    assert defender_cd(engine) == START_CD - 3   # 2 struck + 1 countering


def test_both_breaths_apply_in_their_own_roles():
    """A unit with both charges 2 attacking and 2 being struck."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    attacker.active_statuses.append(status("DEF_BREATH"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 4   # 2 + 2


# ── BREATH_NEUT ──────────────────────────────────────────────────────────────

def test_breath_neut_cancels_off_breath():
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    attacker.active_statuses.append(status("BREATH_NEUT"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 2   # back to baseline


def test_breath_neut_cancels_def_breath():
    attacker = give_special(make_unit("A"))
    defender = give_special(make_unit("D"))
    defender.active_statuses.append(status("DEF_BREATH"))
    defender.active_statuses.append(status("BREATH_NEUT"))

    engine = run(attacker, defender)

    assert defender_cd(engine) == START_CD - 2


# ── Guard: -1 charge ─────────────────────────────────────────────────────────

def test_def_guard_slows_the_unit_while_it_attacks():
    """DEF_GUARD sits in the victim's own list and removes the charge from the
    strike it makes: 0 there, still 1 for being struck."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("DEF_GUARD"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 1   # 0 attacking + 1 struck


def test_off_guard_slows_the_unit_while_it_is_struck():
    """OFF_GUARD removes the charge from the strike the unit receives."""
    attacker = give_special(make_unit("A"))
    defender = give_special(make_unit("D"))
    defender.active_statuses.append(status("OFF_GUARD"))

    engine = run(attacker, defender)

    assert defender_cd(engine) == START_CD - 1   # 0 struck + 1 countering


def test_guard_neut_cancels_guard():
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("DEF_GUARD"))
    attacker.active_statuses.append(status("GUARD_NEUT"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 2   # back to baseline


def test_breath_and_guard_cancel_each_other():
    """+1 and -1 on the same strike net to the usual 1."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(status("OFF_BREATH"))
    attacker.active_statuses.append(status("DEF_GUARD"))
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 2


def test_charge_never_pushes_cooldown_below_zero():
    """max(0, ...) floors the cooldown; a Guarded unit at 0 cannot go negative."""
    attacker = give_special(make_unit("A"), max_cooldown=1)
    defender = give_special(make_unit("D"), max_cooldown=1)

    engine = run(attacker, defender)

    assert attacker_cd(engine) >= 0
    assert defender_cd(engine) >= 0


# ── PULSE_STRIKE / SCOWL_STRIKE ──────────────────────────────────────────────

def test_pulse_strike_reduces_cooldown_further():
    """Pulse is applied before the ready-check, on top of the normal charge.

    The pulse/scowl loop runs for BOTH roles on every strike, so a
    "first_strike" pulse resolves twice across the exchange: once while its
    holder strikes, once while its holder is struck. 2 normal charges + 2 x 2
    pulse = 6."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(
        status("PULSE_STRIKE", {"flat": 2, "strike": "first_strike"})
    )
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == max(0, START_CD - 6)  # 2 normal + 2x2 pulse


def test_scowl_strike_increases_cooldown():
    """Scowl is the inverse of Pulse: it adds to the cooldown. Like pulse it
    resolves once per role per strike, so 2 x 2 scowled back against 2 normal
    charges leaves the cooldown 2 ABOVE where it started."""
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(
        status("SCOWL_STRIKE", {"flat": 2, "strike": "first_strike"})
    )
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD + 2   # 2 charged, 4 scowled back


def test_pulse_and_scowl_cancel():
    attacker = give_special(make_unit("A"))
    attacker.active_statuses.append(
        status("PULSE_STRIKE", {"flat": 2, "strike": "first_strike"})
    )
    attacker.active_statuses.append(
        status("SCOWL_STRIKE", {"flat": 2, "strike": "first_strike"})
    )
    defender = give_special(make_unit("D"))

    engine = run(attacker, defender)

    assert attacker_cd(engine) == START_CD - 2   # baseline
