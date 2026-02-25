---
description: Run the full test suite and verify all tests pass
---
// turbo-all

# Run Full Test Suite

This workflow runs the complete test suite to ensure nothing is broken.
**All tests MUST pass before any task can be considered complete.**

## Steps

1. Run backend unit tests (excludes emulator-only tests):
```bash
python -m pytest tests/ -v --ignore=tests/test_emulator_compat.py --ignore=tests/test_emulator_race.py --ignore=tests/test_unified_integration.py
```

2. Run the unified integration tests (requires emulator + OpenRouter):
```bash
python -m pytest tests/test_unified_integration.py -v -s
```

3. Run emulator compatibility tests (requires emulator Docker):
```bash
python -m pytest tests/test_emulator_compat.py tests/test_emulator_race.py -v -m docker
```

4. **Verify 100% pass rate.** If ANY test fails:
   - DO NOT proceed to other tasks
   - Fix the failure immediately
   - Re-run the full suite
   - Only proceed when all tests pass

## Quick Single Command (All Tests)
```bash
python -m pytest tests/ -v -s
```
