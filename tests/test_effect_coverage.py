"""
Every EffectType and condition type must be exercised by at least one test.

The engine can't prove that from the inside, so this scans the other test
files for each name. It is a coarse check (a name in a docstring counts), but
it guarantees a new effect type cannot land with zero tests.

UNTESTED_* are strict ledgers of the gaps found in the 2026-09 audit. An entry
there is expected to have no test; the check FAILS if it gains one (delete it
from the ledger) or if a name outside the ledger has none (write the test).
The ledgers can only shrink.
"""

import re
from pathlib import Path

from backend.conditions import CONDITION_REGISTRY
from backend.constants import EffectType

TESTS_DIR = Path(__file__).resolve().parent
THIS_FILE = Path(__file__).resolve()

UNTESTED_EFFECT_TYPES = frozenset({
    "FLAT_DAMAGE_AOE",
    "FLAT_DR_AOE",
    "HEXBLADE_AOE",
    "PULSE_AOE",
    "PENALTY_NEUT",
    "PHANTOM_STAT",
    "FU_DENY",
    "OFF_NFU",
    "DEF_NFU",
    "GFU",
    "POTENT",
    "VANTAGE",
    "VANTAGE_NEUT",
    "DESPERATION",
    "DESPERATION_NEUT",
    "OFF_FROZEN",
    "DEF_FROZEN",
    "HEXBLADE_STRIKE",
    "EFFECTIVE",
    "NEUT_EFFECTIVE",
    "FLAT_DR_STRIKE",
    "PULSE_STRIKE",
    "SCOWL_STRIKE",
    "OFF_BREATH",
    "DEF_BREATH",
    "BREATH_NEUT",
    "OFF_GUARD",
    "DEF_GUARD",
    "GUARD_NEUT",
    "DR_FLOOR",
    "DEEP_WOUNDS_IN_CBT",
    "NEUT_DEEP_WOUNDS_IN_CBT",
    "REDUCE_DEEP_WOUNDS_IN_CBT",
    "STAFF_FULL_DAMAGE",
    "HEAL_POST_CBT",
    "DAMAGE_POST_CBT",
    "DEEP_WOUNDS_POST_CBT",
    "REDUCE_DEEP_WOUNDS_POST_CBT",
    "NEUT_DEEP_WOUNDS_POST_CBT",
})

UNTESTED_CONDITION_TYPES = frozenset({
    "first_combat_of_turn",
    "foe_weapon_type",
    "potent_patience",
    "bonus_penalty_total",
    "hp_above_pct",
    "cbt_stat_check",
    "cbt_stat_sum_check",
    "potent_spd_check",
    "triggers_brave",
})


def _test_corpus():
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(TESTS_DIR.glob("test_*.py"))
        if path.resolve() != THIS_FILE
    )


def _mentioned(name, corpus):
    return re.search(rf"\b{re.escape(name)}\b", corpus) is not None


def _check(names, ledger, label):
    corpus = _test_corpus()
    missing = sorted(n for n in names if n not in ledger and not _mentioned(n, corpus))
    assert missing == [], f"{label} with no test: {missing}"

    stale = sorted(n for n in ledger if _mentioned(n, corpus))
    assert stale == [], f"now tested, delete from the {label} ledger: {stale}"

    unknown = sorted(ledger - set(names))
    assert unknown == [], f"{label} ledger names things that don't exist: {unknown}"


def test_every_effect_type_has_a_test_or_is_on_the_ledger():
    _check({e.value for e in EffectType}, UNTESTED_EFFECT_TYPES, "effect types")


def test_every_condition_type_has_a_test_or_is_on_the_ledger():
    _check(set(CONDITION_REGISTRY), UNTESTED_CONDITION_TYPES, "condition types")
