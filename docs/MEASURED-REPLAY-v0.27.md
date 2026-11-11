# ALCG v0.27 — Observed Replay Latency Versus Hypothetical Checkpoint Value

**Date:** 2026-11-11. **Status:** reproducible *method*, environment-specific sample; experimental and synthetic. **Dependencies:** existing v0.23–v0.26 frozen models and MIT-licensed standard-library-only Python 3.10+ code. This version does not introduce a core ALCG operator, update the public concept registry, or assert independent AI semantic understanding.

## 1. The question

In v0.26 a checkpoint stored at the final state has zero **modeled** reconstruction distance. But the actual `checkpoint_planner.access_state(...)` calls `decode(...)` and **validates the entire stored session before returning a state**, even when a checkpoint is present. The engineering question is not whether extra snapshots *might* be useful for some future reader. It is whether the **current, published reader** actually runs faster on a given workload.

This experiment tests the difference between the data-layout model and the running program. It explicitly does *not* model the work of a hypothetical lazy reader as if it already existed.

## 2. Study design and controls

The pinned example is `R23_TWO_ROUNDS` from the frozen v0.23 synthetic session corpus. Its accessible states have indices 0, 1, 2. Three alternative encodings represent **the exact same session**:

| Mode | Encoding | UTF-8 bytes |
|---|---|---:|
| `selective` | v0.25 selective delta | 890 |
| `hybrid_final` | v0.26 delta + full final-state checkpoint | 1,688 |
| `full` | v0.23 complete session | 3,171 |

Every encoding is checked by `checkpoint_planner.decode`, and all measured calls to `checkpoint_planner.access_state` are compared to the same byte-identical canonical `TRACE_V022`. A result that differs from the reference aborts the benchmark. Neither published dictionaries nor historical sessions are mutated.

The sample records **one warm-up block, followed by three measured balanced blocks**; each block reads each of the three states from each of the three encodings exactly once. The order within each block is shuffled with a fixed pseudorandom seed, but the timing data are not deterministic. Each read is timed with `time.perf_counter_ns()`; the recorded duration includes the actual full-chain decoding and trace access, but excludes the subsequent comparison to the reference. The process is warm, with Python caching, OS scheduling and CPU frequency effects; no process-isolation or dedicated-hardware benchmark is claimed.

## 3. Concrete captured observation

The committed illustrative fixture was produced in a Linux x86_64 container under Python 3.13.5, on 2026-11-11 (UTC timestamp retained in the JSON report). Its *final-state read* sample medians were:

| Mode | Median fully verified read | Minimum of three samples | Maximum of three samples |
|---|---:|---:|---:|
| `selective` | 6.079 ms | 5.164 ms | 6.397 ms |
| `hybrid_final` | 6.173 ms | 5.565 ms | 6.604 ms |
| `full` | 54.265 ms | 54.027 ms | 54.974 ms |

On this one process, with a **synthetic** `hot_tail` read-frequency vector (0, 0, 80) and an assumed storage weight of 1,000 nanosecond-*equivalent* score units per UTF-8 byte, the observed-median scoring chooses `selective`. The old v0.26 *abstract-replay-unit* model chooses `hybrid` for the same hot-tail label. This difference is not a contradiction: the two models price different operations.

The observed-weighted scores are approximately 487.178 million, 495.514 million and 4,344.363 million ns-equivalent units respectively. Those are **80×median extrapolations plus declared byte penalties, not measurements of eighty sequential real requests**. The assumed byte penalty is illustrative and is not a measured economic or storage cost. The sample size is too small to support a stable ranking of `selective` versus `hybrid` (their median times are close and sampling ranges overlap).

**Important negative result:** a stored checkpoint does not automatically accelerate a reader that still validates and regenerates the entire chain. Nothing in these observations establishes that delta is always faster or full storage is always slower on a different platform, Python runtime, access distribution or implementation.

## 4. Measured-choice calculation

For encoding `P` and state `i`, let `t(P,i)` denote the **lower median** of its positive monotonic measured durations in nanoseconds. Let `f_i` be declared integer state-read frequencies, `B(P)` its actual UTF-8 source bytes and `lambda_B` a declared nonnegative price in *ns-equivalent* score units per byte. The score is

$$
J_{\mathrm{observed}}(P)=\sum_{i=0}^n f_i\,t(P,i)+\lambda_B B(P).
$$

The selector evaluates the three recorded encoding modes, breaks ties deterministically by score, bytes, and mode, and does not label the result universally optimal. It can re-score **the same recorded per-state samples** for another declared read distribution or byte price without pretending the timer would return the same samples again. A zero-read cold-archive profile selects the smallest recorded encoding when the storage price is positive.

The v0.26 alternative remains available and unchanged. Its replay-unit estimates are explicitly identified as hypothetical. This version does **not** replace those abstract units with an automatically fitted clock on every machine, nor does it add a trusted lazy-reader or deploy a new cache to production.

## 5. Reproduction

Run the deterministic **data/structure validation**, which does *not* rerun benchmarks or assert matching times:

```bash
python measured_replay.py check
python measured_replay.py recommend --profile cold_archive --byte-price-ns 1000
python -m unittest discover -s tests -p 'test_measured_replay.py' -v
```

To generate your **own** fresh local sample:

```bash
python measured_replay.py bench --session R23_TWO_ROUNDS --profile hot_tail \
  --repeats 5 --warmups 2 --byte-price-ns 1000 \
  --output .local/measured-replay-my-machine.json
python measured_replay.py recommend .local/measured-replay-my-machine.json \
  --profile mixed_reads --byte-price-ns 1000
```

The benchmark CLI writes only under `.local/`, so an experiment cannot accidentally overwrite old pinned reports or source data. To write elsewhere, redirect stdout explicitly or make an intentional source change via normal repository review. CI runs **only** the deterministic fixture integrity and rescore checks: volatile timings are not expected to be bit-for-bit reproduced in GitHub-hosted environments.

## 6. Reproducibility and integrity boundaries

The committed JSON includes all timing samples, per-state medians, CPU/OS/Python descriptors, full-source SHA-256 fingerprints, the source expression digests, recorded score components and a content-consistency SHA-256 digest. These fields help audit that reported numbers match the stored inputs and the same source version. The receipt is **not a signature**: someone who alters all fields and recomputes the digest can create another internally consistent report. Benchmark output cannot authenticate an experimenter's measurements by itself.

Unit tests intentionally refuse to enforce a timing threshold, a fixed ordering of the encodings or identical sample results between machines. They enforce timing-array shape, positive duration, exact medians, pinned source identities, score arithmetic, deterministic ranking, and byte-exact semantic-state reconstruction, including deliberately corrupted samples.

## 7. What is, and is not, established

- Established for this fixture: all three encodings reconstruct the same original synthetic states; the current published reader fully verifies each read; the recorded process-local timing medians, byte counts and cost scenario are internally consistent; the measured selector can make a different choice from the v0.26 abstract planner.
- Not established: general speedup on other hardware; a stable advantage of `selective` over `hybrid`; a working lazy-checkpoint reader; reduced end-to-end energy, token cost, network cost, or human/AI semantic comprehension; real-world sensor or causal measurements.
- Logical next engineering step: implement a **separately specified post-validation trusted index**, account for its one-time validation cost, amortize repeated accesses, and explicitly invalidate it when pinned source/version changes. Do not silently assume its benefits already exist.

**Conclusion:** an encoding can *contain* a useful-looking checkpoint without the reader *using* it as a shortcut. This ALCG experiment makes that distinction executable, measured and open to replication rather than burying it inside an assumed cost coefficient.
