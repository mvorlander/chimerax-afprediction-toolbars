# Smoke Tests

Run the discovery smoke test from the repository root:

```bash
python3 tests/smoke_test_discovery.py
```

The test builds temporary AF2 and AF3-like prediction folders and checks that the
bundle discovers top-hit and all-hit model/data pairs without requiring a
ChimeraX installation. Full toolbar and rendering tests still need ChimeraX
because they exercise UCSF ChimeraX APIs and Qt tools.
