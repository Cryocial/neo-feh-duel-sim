## Description

<!-- What does this PR change? -->

## Type of change

- [ ] New skill/status 

- [ ] Bug fix

- [ ] Refactor

- [ ] Other

## Checklist

- [ ] Every new effect type or condition has a test that asserts **final HP**, not just an intermediate value
- [ ] New JSON entries pass `uv run pytest tests/test_data_integrity.py`
- [ ] New effect / strike / formula / condition names are added to the matching Appendix table in `doc/ARCHITECTURE.md`
- [ ] If a fix removes an entry from a `KNOWN_BROKEN` / `UNTESTED_*` ledger in `tests/`, that entry is deleted from the ledger

## Related issue

<!-- Closes #__ if applicable -->
