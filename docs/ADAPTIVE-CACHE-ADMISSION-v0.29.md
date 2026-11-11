# ALCG v0.29 — Evidence-Gated Adaptive Cache Admission and Invalidation Economics

**Status:** experimental, bounded, open-source engineering study.  
**Canonical source:** UTF-8 Markdown; formulas use `$...$` and `$$...$$` only.  
**Compatibility:** no change to the ALCG grammar, published patterns, causal models, or v0.1–v0.28 receipts.

## Abstract

ALCG v0.28 introduced a *process-local* `VerifiedStateCache` that first replays and verifies the entire decision history and then serves immutable cached states. That version measured substantial first-admission cost and faster subsequent reads. v0.29 implements a bounded, evidence-gated admission policy and a reader that chooses, per requested workload, between **fresh verification on every read** and **verified-once caching**. It includes a hypothetical source-invalidation hazard and a per-read retention cost, to expose the conditions under which caching ceases to be worthwhile. The v0.28 measured samples are preserved and explicitly pinned, not treated as universally valid latency constants.

## 1. Scope

This release answers one engineering question: *When is it worth paying the initial verified-cache creation cost, given a forecast number of reads and a possible invalidation frequency?* It does not claim to infer a true source-change rate from observations. It does not optimize the ALCG symbolic grammar, define a new intermediate character, attest a local clock, prove semantic equivalence, or authenticate a process.

The analysis is restricted to three exact v0.28 representations of one fixed two-round synthetic session: `selective`, `hybrid_final`, and `full`. There are seven user-declared workloads in `data/adaptive-cache-profiles-v0.29.json`. They constitute 21 explicitly reproducible comparisons, not measurements of 21 independent deployments.

## 2. Source evidence and explicit assumptions

`reports/trusted-cache-v0.28.json` records five in-process samples per mode. Its SHA-256 bytes are pinned by the v0.29 workload file; its recorded medians and source fingerprints are re-verified by the existing v0.28 validator. The report was captured on one Linux/Python 3.13 environment and has no third-party performance attestation.

For a known exact source, define:

- $N$: forecast total reads, including the first read; integers $1$ through $4096$.
- $U$: recorded median time of one fully verified, uncached read.
- $C$: recorded elapsed time of the first cache admission and verified read.
- $H$: recorded median time of a warm cache hit.
- $p$: hypothetical probability of source invalidation in each *gap* between successive reads, expressed as integer parts per million.
- $R$: hypothetical extra recovery cost per invalidation, in nanoseconds.
- $M$: hypothetical cache retention charge per planned read, in nanosecond-equivalent units.

The forecast model assumes independently occurring reset events between reads, identical timing medians, and exactly one new cold admission after a reset. For the **expected count** equations, only the common marginal reset probability is necessary; independence is an added scenario assumption, not empirical evidence.

The expected number of admissions is

$$
A(N,p)=1+(N-1)p.
$$

The expected cache-hit count is

$$
K(N,p)=(N-1)(1-p).
$$

Expected total costs are

$$
D(N)=NU
$$

and

$$
C_{\mathrm{cache}}(N,p)=A(N,p)C+K(N,p)H+(N-1)pR+NM.
$$

The gate selects caching **only** when $C_{\mathrm{cache}}(N,p)<D(N)$. On a tie, it chooses fresh verification. Arithmetic is exact using Python `fractions.Fraction`, avoiding float rounding near a threshold. In the machine-readable report, values use integer numerator/denominator objects; no inferred seconds are substituted for the source nanosecond samples.

The `break_even_reads_with_same_hazard` field is the first integer $N$ in $1$–$4096$ at which the inequality holds with *the same* $p,R,M$. A missing break-even (`null`) means it was not found within this bounded forecast horizon, **not** that no break-even exists under every possible future workload.

## 3. Seven bounded scenarios

| Scenario | Forecast reads | Resets per million gaps | Modeled penalty | Interpretation |
|---|---:|---:|---:|---|
| `one_off` | 2 | 0 | 0 | Too few reads to amortize admission |
| `short_repeat` | 4 | 0 | 0 | A costly full representation may amortize earlier |
| `stable_repeat` | 64 | 0 | 0 | Repeated access to identical source and decoder |
| `medium_churn` | 64 | 50,000 | 0 | Source changes can defeat compact-source caching |
| `rapid_churn` | 64 | 800,000 | 1,000,000 ns/reset | Frequently invalidated cache is unattractive |
| `retention_cost` | 64 | 0 | 20,000,000 ns-equivalent/read | Memory holding cost can dominate |
| `steady_slow` | 32 | 10,000 | 2,000,000 ns/reset plus 100,000 ns-equivalent/read | Intermediate case |

All numbers are explicitly invented workloads. They should be replaced with credible telemetry before a deployment decision. This release does **not** estimate invalidation probability from the seven scenarios.

For `one_off`, all three modes use `direct`; for `stable_repeat`, all three modes use `cache`. Under `medium_churn`, the two compact modes choose `direct`, while the expensive full-history mode still chooses `cache`. Under `rapid_churn`, all choose `direct`. With zero invalidations and zero retention charge, the earliest modeled break-even points are **22**, **23**, and **3** reads respectively, but these thresholds are not hardware-independent constants.

## 4. Operational reader: no bypass of the trust boundary

`AdaptiveCacheReader` invokes the **actual** v0.26 full verifier on the `direct` path. Its `cache` path delegates to the unchanged v0.28 `VerifiedStateCache`: a miss always performs full model verification and materializes the complete immutable state list. Subsequent cache hits check source bytes, monitored code/model files, and cached snapshot hashes before serving a state.

The router uses the exact three **source expressions** in the pinned v0.28 report as known performance evidence. Any otherwise valid, unknown source is routed to `direct` regardless of workload. A caller's source `alias` is scoped to this process: changing its source expression conservatively clears all cached states, and the new source must be freshly verified. The reader monitors all v0.28 dependencies, its own code, the v0.29 policy, and the original benchmark report. Changing a monitored dependency permanently blocks the existing reader instance (a new controlled-process reader must be constructed).

Even when routing to `direct`, the policy does not skip dependency checking. After a read, the model/dependency manifest is checked again. Cache hits do not establish an external provenance claim: both content hashes and policies are local integrity checks only. This program assumes a non-hostile process and does not guarantee safety against hostile in-process mutation, a compromised kernel, or concurrent file changes engineered to evade checks.

**Important distinction:** an alias revision is a real, observed invalidation event; the $p$ supplied in a forecast is *not* observed. The planner's expected invalidation expenses must not be reported as actual costs incurred by a run.

## 5. Reproducibility

From a repository checkout, Python 3.10+ with the standard library is sufficient:

```bash
python adaptive_cache.py check
python adaptive_cache.py plan --profile one_off --mode selective
python adaptive_cache.py plan --profile stable_repeat --mode selective
python adaptive_cache.py plan --profile medium_churn --mode full
python adaptive_cache.py read --profile one_off --mode selective --state 2 --times 2
python adaptive_cache.py read --profile stable_repeat --mode selective --state 2 --times 3
python -m unittest discover -s tests -p test_adaptive_cache.py -v
python tests/run_split_suite.py
```

`check` recomputes the published 21 decisions from the pinned v0.28 timing source, checks its fingerprint and existing receipt, then performs a real direct read and a real cache admission/hit and compares the returned canonical state. It is not a new wall-clock benchmark. `plan` reports the workload assumption and exact modeled costs. `read` shows real counters from the two data paths; its `all_equal` result is structural identity, not semantic comprehension. Standard CI runs `check` and the tests, but does not require volatile timing thresholds.

To repeat the **physical timing experiment**, run the opt-in v0.28 command locally:

```bash
python trusted_cache.py bench --session R23_TWO_ROUNDS --repeats 5 --output .local/my-fresh-timing.json
```

New measured figures require a deliberate new policy/evidence version, not silent modification of the frozen v0.28 report.

## 6. Threats to validity and interpretation

1. **Tiny synthetic corpus:** five samples, one session, three serialization modes. No general workload distribution is measured.
2. **Model-based hazard:** reset probability, rebuild penalty and retention charge are invented; none is inferred from running GitHub Actions.
3. **Endogenous effects:** when source changes, future timing medians may differ; the forecast holds the old medians fixed.
4. **Resource competition:** actual memory usage, thread contention, eviction patterns and OS load are not priced directly. Retention is a hypothetical charge.
5. **Integrity versus authenticity:** SHA-256 receipts detect uncoordinated byte changes, not a malicious actor with write access to all artifacts.
6. **Unverified beyond the known formats:** unfamiliar expressions always require full verification, not unsafe admission based on a guessed cost.
7. **Not an AI reading study:** no independent AI reader, natural-language comprehension or semantic truth metrics have been obtained.
8. **No assumption that fewer bytes or fewer modeled units mean shorter runtime:** the old actual full verification remains the correctness anchor.

## Conclusion

The new contribution is not a universal performance ranking. It is a **reproducible decision rule that exposes when caching is worth paying for, and when repeated verification is safer or cheaper** under declared bounded assumptions. The symbolic decision and its assumptions are machine-readable; verified caching never replaces the first complete replay.
