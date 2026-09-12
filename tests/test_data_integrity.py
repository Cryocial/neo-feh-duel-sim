"""
Validates every JSON entry (skills, statuses, divine veins) against the engine
registries, so a malformed skill fails CI before anyone equips it.

Each entry is one parametrized case. The checks mirror build_effect exactly
(effect type, target, required params, strike and formula names) and add the
things build_effect can't see: condition types inside any_of / all_of, and a
Special slot that never declared its special_type.

KNOWN_BROKEN is a strict ledger of entries that fail today (audit bugs #7-11).
They are marked xfail(strict=True): the moment one of them validates cleanly
the test FAILS, telling you to delete it from the ledger. The ledger can only
shrink.
"""

import pytest

from backend.conditions import CONDITION_REGISTRY
from backend.constants import SpecialType
from backend.effects import validate_effect_desc
from backend.jsonbootupstuff import (
    BONUS_DATABASE,
    DIVINE_VEINS_DATABASE,
    PENALTY_DATABASE,
    SKILL_DATABASE,
)

KNOWN_BROKEN = {
    "Arcane Cake": "strike 'on_foe_special' is not a STRIKE_VALUES entry (audit #9)",
    "Chosen Sword": "effects [1]-[3] are nested {'effects': [...]} wrappers, "
                    "and strike 'on_foe_special' (audit #7, #9)",
    "Dragon Fang": "slot=special with no special_type, and strike "
                   "'on_unit_special' (audit #8, #9)",
    "Atk Liberate": "formula 'bonus_count_plus_4' does not exist (audit #10)",
    "Spd Liberate": "formula 'bonus_count_plus_4' does not exist (audit #10)",
    "Def Liberate": "formula 'bonus_count_plus_4' does not exist (audit #10)",
    "Res Liberate": "formula 'bonus_count_plus_4' does not exist (audit #10)",
    "Divine Nectar": "strike 'first_sequence', and effect "
                     "'NEUT_DEEP_WOUNDS_STRIKE' (audit #9, #11)",
    "Stone": "strike 'on_foe_special' (audit #9); its PERC_DR_AOE effect "
             "only exists once PR #36 lands",
    "Water": "DR_PIERCE written with the formula block (flat: 50) instead of "
             "value: 50, which is the key the engine reads; the pierce was "
             "silently 0% (found by REQUIRED_PARAMS, post-audit)",
}


def _entries():
    for name, skill in SKILL_DATABASE.items():
        yield "skills.json", name, skill
    for name, status in BONUS_DATABASE.items():
        yield "statuses.json", name, status
    for name, status in PENALTY_DATABASE.items():
        yield "statuses.json", name, status
    for name, vein in DIVINE_VEINS_DATABASE.items():
        yield "divine_veins.json", name, vein


ENTRIES = list(_entries())


def _condition_problems(conditions, path):
    problems = []
    for cond in conditions:
        if "any_of" in cond:
            problems += _condition_problems(cond["any_of"], path)
        elif "all_of" in cond:
            problems += _condition_problems(cond["all_of"], path)
        elif cond.get("type") not in CONDITION_REGISTRY:
            problems.append(f"{path}: unknown condition type {cond.get('type')!r}")
    return problems


def problems_for(name, entry):
    problems = []
    for i, desc in enumerate(entry.effects):
        path = f"{name}[{i}]"
        problems += [f"{path}: {p}" for p in validate_effect_desc(desc)]
        problems += _condition_problems(desc.get("conditions", []), path)

    slot = getattr(entry, "slot", None)
    special_type = getattr(entry, "special_type", SpecialType.NONE)
    if slot == "special" and special_type is SpecialType.NONE:
        problems.append(f"{name}: slot=special but no special_type, so it can never trigger")
    if slot not in (None, "special") and special_type is not SpecialType.NONE:
        problems.append(f"{name}: slot={slot!r} but special_type={special_type.name}")
    return problems


def _param(source, name, entry):
    marks = []
    if name in KNOWN_BROKEN:
        marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_BROKEN[name]))
    return pytest.param(name, entry, id=f"{source}:{name}", marks=marks)


@pytest.mark.parametrize("name,entry", [_param(*e) for e in ENTRIES])
def test_entry_is_well_formed(name, entry):
    problems = problems_for(name, entry)
    assert problems == [], "\n".join(problems)


def test_known_broken_ledger_only_names_real_entries():
    names = {name for _, name, _ in ENTRIES}
    assert set(KNOWN_BROKEN) <= names, sorted(set(KNOWN_BROKEN) - names)
