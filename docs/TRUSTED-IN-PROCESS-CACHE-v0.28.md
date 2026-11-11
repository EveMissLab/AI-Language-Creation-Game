# ALCG v0.28 — Verified-once, in-process cache for replayable decision states

**Research status:** bounded, experimental implementation. This is an **execution/replay optimization**, not a new core ALCG language operator, not an independently tested AI reader, and not a cryptographic authentication layer.

## Problem inherited from v0.27

The v0.26 `checkpoint_planner.access_state` method replays and verifies the full session **on every request**, regardless of whether the representation contains a materialized checkpoint. The v0.27 measurements revealed why additional stored state does not automatically produce a faster implementation.

The v0.28 `trusted_cache.VerifiedStateCache` makes a narrower, testable change:

1. On first request for an exact canonical source expression, run the existing v0.26 full decoder and its pinned-model checks.
2. Materialize **all** canonical v0.22 state strings and the byte-exact v0.23 full session string; keep them in an immutable private in-process entry.
3. For a repeated read, check the exact input source digest, the hashes of monitored model/decoder files, and the returned state digest, then serve the already-verified snapshot **without rerunning the causal model**.
4. Reject invalid expressions and out-of-range states. Changed watched files clear the cache and raise an explicit exception; a fresh full replay is required after restoring a valid environment.
5. Enforce a bounded least-recently-used (LRU) capacity. A process restart, eviction, or manual `clear()` discards the existing admission.

The monitoring is based on `WATCH_FILES` (v0.22–v0.26 model/decoder source and referenced public parameters). It is not an operating-system security boundary or an atomic filesystem snapshot. A hostile process with the ability to modify live Python objects or modules is outside this threat model.

### Trust boundary, explicitly limited

- **Verified** means replayed and checked under the *installed, monitored synthetic model*; it does not establish truth about real sensors or the world.
- A SHA-256 hash detects changes relative to a local source or receipt. It provides **no proof of authorship, signature, remote identity, or resistance to an attacker who can recompute the entire record**.
- Cached state is never deserialized from disk or accepted from another process. Each process must perform its own first full verification.
- If a watched model/source file changes while the process is running, it invalidates cached entries and refuses that access. After correcting the files, the next request requires fresh validation. A code restart is recommended if loaded modules have changed.
- Reads and admissions are serialized under a lock within one cache instance. No cross-process synchronization is provided.
- Model file checks cannot guarantee atomicity against a hostile concurrent file rewrite; deployment must control that access separately.

## Exact, reproducible commands

```bash
# Functional validation; no timing threshold and no write to source files
python trusted_cache.py check

# Two accesses: first admission, then one verified cache hit
python trusted_cache.py read --session R23_TWO_ROUNDS --mode selective --state 2 --times 2

# Run an environment-specific local timing experiment. Result stays under .local
python trusted_cache.py bench --session R23_TWO_ROUNDS --repeats 5 --output .local/cache-run.json

# All regression tests (the CI runs them by modules)
python tests/run_split_suite.py
```

The frozen artifact `reports/trusted-cache-v0.28.json` contains raw nanosecond observations, input SHA-256 identities, first-admission time, and medians. `check` verifies its internal consistency and replays canonical source records; it **cannot independently confirm that recorded wall-clock timings were actually measured**. No fixed performance minimum is asserted in CI.

## One captured local environment (5 repeated reads per mode)

| Encoding | UTF-8 bytes | First cache admission (ms) | Full replay per read, median (ms) | Repeated cache hit, median (ms) |
|---|---:|---:|---:|---:|
| `selective` | 890 | 111.312 | 5.505 | 0.323 |
| `hybrid_final` | 1,688 | 120.963 | 5.663 | 0.334 |
| `full` | 3,171 | 163.868 | 63.670 | 0.364 |

These values are rounded from a **single local captured run** with a small synthetic two-round history. The environment, interpreter, cache state, and system load affect them. The first admission cost includes full verification **and building every canonical state and full session string**, not just fetching the requested state. Repeated hits still read and hash monitored model/source files. For an application that reads once, cache admission can cost far more than the original single replay.

From these median values alone, the approximate warm-process break-even number of reads is 22 (`selective`), 23 (`hybrid_final`), and 3 (`full`) under a simple first-admission-plus-hit scenario. These are **illustrative arithmetic estimates, not stable operational thresholds**.

## Tests and historical compatibility

The v0.28 test module verifies all three representations and every state against the unchanged v0.26 reader; it checks fresh verification only on miss, input tampering, changed policy/model input detection, fake digest collision, source encoding bounds, cache entry corruption, manual invalidation, LRU eviction, concurrent same-source calls, source-pinned reports, and output-path restrictions.

**No existing grammar, ALCG concept dictionary, published pattern registry, finite model definition, or v0.1–v0.27 report is modified.** The cache only acts after the trusted baseline parser/decoder has established validity. The synthetic decision records do not demonstrate independent AI comprehension.

## Interpretation

Version 0.28 establishes a narrow execution-level claim: a fully verified computation history can be reused for further reads in the **same trusted process**, provided it is matched to the same canonical source and the monitored decoder/model bytes remain unchanged. This is separate from source compression, computational correctness of hypothetical assumptions, and external identity authentication.
