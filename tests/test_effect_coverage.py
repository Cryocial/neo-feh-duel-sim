"""
Every EffectType and condition type must be exercised by at least one test.

The engine can't prove that from the inside, so this scans the other test
files for each name. It is a coarse check (a name in a docstring counts), but
it guarantees a new effect type cannot land with zero tests.

UNTESTED_* are strict ledgers of the gaps. An entry
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

UNTESTED_EFFECT_TYPES: frozenset[str] = frozenset()

UNTESTED_CONDITION_TYPES: frozenset[str] = frozenset()


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
