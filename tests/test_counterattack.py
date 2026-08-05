"""
Tests for range-based counter eligibility (defender_counterattack) in
CombatEngine._determine_strike_sequence.

Rules verified:
  - The defender counters if combat_range matches their own base weapon
    range, or if they've been granted EffectType.COUNTERATTACK
  - A range mismatch without COUNTERATTACK blocks the counter, independently
    of Flash / Flash Neutralization
  - Flash still blocks the counter (and Flash Neutralization still cancels
    that block) when the range matches
  - A style-driven RANGE_EXTENSION feeds into this the same way a plain
    weapon-range mismatch does, whether it blocks or enables a counter
"""

from backend.build import Unit, Status
from backend.constants import MovementType, WeaponType, Color
from backend.combatcalculator import CombatEngine


def make_unit(
    name, color=Color.RED, hp=50, atk=40, spd=10, defense=20, res=20,
    weapon_type=WeaponType.SWORD,
):
    return Unit(
        name=name,
        movement_type=MovementType.INFANTRY,
        weapon_type=weapon_type,
        color=color,
        hp=hp,
        atk=atk,
        spd=spd,
        defense=defense,
        res=res,
    )


def counterattack_status():
    """Grants EffectType.COUNTERATTACK to whoever holds it, unconditionally."""
    return Status(
        name="Test Counterattack",
        type="bonus",
        effects=[
            {"effect": "COUNTERATTACK", "target": "self", "params": {}, "conditions": []}
        ],
    )


def flash_status():
    return Status(
        name="Test Flash",
        type="penalty",
        effects=[
            {"effect": "FLASH", "target": "self", "params": {}, "conditions": []}
        ],
    )


def flash_neut_status():
    return Status(
        name="Test Flash Neut",
        type="bonus",
        effects=[
            {"effect": "FLASH_NEUT", "target": "self", "params": {}, "conditions": []}
        ],
    )


def style_range_status(min_range, max_range):
    """A bonus status granting a RANGE_EXTENSION, gated on style_enabled."""
    return Status(
        name="Test Style Range",
        type="bonus",
        grants_style=True,
        effects=[
            {
                "effect": "RANGE_EXTENSION",
                "target": "self",
                "params": {"min": min_range, "max": max_range},
                "conditions": [{"type": "style_enabled", "params": {}}],
            }
        ],
    )


def test_defender_counters_when_range_matches():
    """Melee attacker vs melee defender: combat_range (1) matches the
    defender's own base range, so the counter proceeds normally."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)

    result = CombatEngine(attacker, defender).simulate()

    # Defender's counter: 30 atk - 20 def = 10 damage to the attacker.
    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 20


def test_defender_cannot_counter_on_range_mismatch():
    """Ranged (Tome) attacker vs melee defender: combat_range (2) doesn't
    match the defender's base range (1), and no COUNTERATTACK effect is
    present, so the defender cannot counter."""
    attacker = make_unit("A", weapon_type=WeaponType.TOME, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)

    result = CombatEngine(attacker, defender).simulate()

    # No counter -> attacker takes no damage.
    assert result["attacker_final_hp"] == 50
    assert result["defender_final_hp"] == 50 - 30


def test_counterattack_effect_overrides_range_mismatch():
    """Same range mismatch as above, but the defender has been granted
    EffectType.COUNTERATTACK -> the counter proceeds despite the mismatch."""
    attacker = make_unit("A", weapon_type=WeaponType.TOME, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)
    defender.active_statuses.append(counterattack_status())

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 30


def test_flash_still_blocks_counter_when_range_matches():
    """Range matches (melee vs melee), but Flash without Flash Neutralization
    still blocks the counter -- the range fix must not break this."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)
    defender.active_statuses.append(flash_status())

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50
    assert result["defender_final_hp"] == 50 - 20


def test_flash_neutralization_restores_counter_when_range_matches():
    """Range matches, Flash is present but neutralized -> counter proceeds."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)
    defender.active_statuses.append(flash_status())
    defender.active_statuses.append(flash_neut_status())

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 20


def test_flash_neutralization_does_not_override_range_mismatch():
    """Range mismatch, no COUNTERATTACK effect, but Flash Neutralization is
    present anyway -> still cannot counter. Flash Neut only cancels Flash,
    it doesn't grant a range bypass -- the two gates must stay independent."""
    attacker = make_unit("A", weapon_type=WeaponType.TOME, atk=40, defense=20)
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)
    defender.active_statuses.append(flash_neut_status())

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50
    assert result["defender_final_hp"] == 50 - 30


def test_style_range_extension_blocks_counter_on_mismatch():
    """A melee attacker whose style forces combat_range to 2 creates the same
    kind of mismatch as a Tome attacker would -- the melee defender (base
    range 1) cannot counter."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD, atk=40, defense=20)
    attacker.active_statuses.append(style_range_status(2, 2))
    attacker.style_enabled = True
    defender = make_unit("D", weapon_type=WeaponType.SWORD, atk=30, defense=20, res=10)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50
    assert result["defender_final_hp"] == 50 - 20


def test_style_range_extension_enables_counter_on_match():
    """A melee attacker's style forces combat_range to 2, which now matches a
    ranged (Bow) defender's own base range -- a counter that would NOT happen
    without the style (attacker's base range is 1) now proceeds."""
    attacker = make_unit("A", weapon_type=WeaponType.SWORD, atk=40, defense=20)
    attacker.active_statuses.append(style_range_status(2, 2))
    attacker.style_enabled = True
    defender = make_unit("D", weapon_type=WeaponType.BOW, atk=30, defense=20, res=10)

    result = CombatEngine(attacker, defender).simulate()

    assert result["attacker_final_hp"] == 50 - 10
    assert result["defender_final_hp"] == 50 - 20
