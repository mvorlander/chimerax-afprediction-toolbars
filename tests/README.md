# Smoke Tests

Run the discovery smoke test from the repository root:

```bash
python3 tests/smoke_test_discovery.py
```

The test builds temporary AF2 and AF3-like prediction folders and checks that the
bundle discovers top-hit and all-hit model/data pairs without requiring a
ChimeraX installation. Full toolbar and rendering tests still need ChimeraX
because they exercise UCSF ChimeraX APIs and Qt tools.

Run the native UI regression test in a **fresh** GUI ChimeraX process:

```bash
ChimeraX --exit --script tests/smoke_test_ui.py
```

The script loads synthetic two-chain predictions into two runs and checks toolbar
singleton reuse, all pages at narrow widths, expanded controls without horizontal
clipping, model/PAE synchronization, separate/embedded plot placement, debounced
selection triggers, and run cleanup. It writes
screenshots and `result.txt` under `/tmp/af-ui-test` (override with
`AF_UI_TEST_OUTPUT`). Check that the report ends in `PASS`; GUI script errors do
not necessarily produce a nonzero ChimeraX exit code. Do not run it in a session
containing your own work.

For confidence-mask and overlay equivalence, including asymmetric PAE, invalid
rows, missing chains, NaNs, and cutoff boundaries:

```bash
python3 tests/smoke_test_performance.py
```

Run the same script in a fresh GUI ChimeraX process for native atom/bond display,
selection, label, and coloring checks with 3,000 residues / 15,000 atoms:

```bash
ChimeraX --exit --script tests/smoke_test_performance.py
```

Results go to `/tmp/af-performance-results.json` (override with `AF_PERF_OUTPUT`).
Set `AF_PERF_BASELINE` to a copy of the previous `src/workflow.py` to compare its
outputs and timings. Check `status: PASS`; timings cover operations, not complete
GPU frame rendering, network fetches, or initial domain clustering.
