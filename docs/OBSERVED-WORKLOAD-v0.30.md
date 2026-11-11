# ALCG v0.30 — Prefix-Only Observed Workloads and Adaptive Cache Admission

**Status:** experimental, open-source. This specification is the canonical UTF-8 source artifact for the v0.30 module. It does not introduce new natural-language primitives, mesoscopic glyphs, or a cryptographic protocol.

## 1. Research question

v0.29 requires the caller to declare expected future reads and invalidation probability. Can a bounded event history replace those manually supplied values **without consulting future events**, while retaining v0.28's verified-once cache safety boundary?

The answer here is an **implemented demonstration for precisely defined synthetic events**, plus an opt-in single-process reader capable of recording its own real operations. It is not evidence that the predicted rates are accurate for a production workload.

## 2. Inputs and privacy

`data/workload-events-v0.30.json` stores four explicitly **synthetic** workloads (`stable`, `churn`, `sparse`, `drift`). Each contains 96 consecutively indexed *opportunities*. An opportunity is either an observed `read` or an explicitly reported `idle`; a tick is **not** a second, minute, or other wall-clock duration.

A successful read records only `tick`, `kind=read`, `revision_changed` (whether this one source stream differs from its last successful read), and `route` (`direct`, `cache`, or `not-executed`). An idle opportunity contains only `tick` and `kind=idle`. Failed reads are **not** counted as successful reads. The log does not export source expressions, source IDs, filenames, source hashes, session IDs, keys, inputs or output states. Event timing and patterns can still be privacy-relevant; logging and publication require deliberate consent and data review.

The `origin` field distinguishes `synthetic-fixture` from `instrumented-process`. The SHA-256 receipt checks accidental modifications under the published format; an actor who can rewrite the log and receipt can forge both. There is no remote authentication or proof of actual observation.

One explicit source stream is modeled per local reader. Automatic multi-tenant telemetry, clock-based sampling, disk persistence, and transport of private access events are not implemented.

## 3. Prefix-only estimator

At a selected `at_tick`, only events with smaller ticks are available. From the final **32** observed opportunities, the estimator counts successful reads and revision changes between consecutive reads *inside that window*. It ignores an unobserved gap before the first read in the window.

To prevent low-data guesses, predictions remain `direct` until there is a full 32-opportunity window with at least **8 reads and 7 read-to-read gaps**. The fallback also applies to unknown source encodings.

The next **64 opportunities** form the forecast horizon. An explicit, uncalibrated Beta(1,1) smoothing assumption estimates read intensity. An explicit, uncalibrated Beta(1,19) assumption estimates revision probability per observed read gap. Integer rates use deterministic half-up rounding; the latter is converted to invalidations per million. This is *not* a Bayesian guarantee about any actual workload.

For $r$ reads in a 32-opportunity window, $g$ eligible read gaps, and $c$ observed revisions:

$$
\widehat{N}=\operatorname{round}_{1/2\uparrow}\left(64\frac{r+1}{34}\right)
$$

$$
\widehat{p}=\frac{c+1}{g+20}
$$

The estimates are passed to the **unchanged** `adaptive_cache.estimate` routine, together with the previously captured v0.28 timing medians. The v0.29 cost terms for rebuild penalty and retention cost are fixed to zero in this specific v0.30 baseline, not assumed to be zero in general. The result is `cache` only when the modeled expected cache cost is strictly below the direct cost; a tie is `direct`.

The rolling window may adjust to shifts, but it can also overreact or lag. There are no confidence bounds, drift certificates, or accuracy guarantees. Comparing additional forecast methods belongs to a separate experiment.

## 4. Demonstrated synthetic cases

The committed report provides four cutoffs (`16`, `32`, `64`, `96`) for each of the four generated scenarios, totaling **16** prefix-only evaluations.

| Scenario | Prior observed pattern | Decision at tick 96 |
| --- | --- | --- |
| `stable` | read-heavy and stable in latest window | `cache` |
| `churn` | frequent revisions during latest read gaps | `direct` |
| `sparse` | very few reads | `direct` (insufficient data) |
| `drift` | stable until tick 64, then frequent revisions | `direct` (had been `cache` at tick 64) |

All four scenarios are deterministic and designed to exercise this mechanism; they are not an independent out-of-sample test, production telemetry, or an AI reader comprehension experiment.

## 5. Actual read-path demonstration

`ObservedCacheReader` uses the same pinned v0.28 timing source cases and the existing `VerifiedStateCache`. It decides from **events collected before the current read**. Unfamiliar expressions always use the full verification path. A newly seen exact source revision clears the cache before use. Model, decoder, timing-record or estimator source changes block the reader, and it must be reconstructed.

An admitted cache still performs its complete initial verification. A repeat hit checks source bytes, monitored dependencies and snapshot consistency. Only successful reads append events. The `idle()` method explicitly records an opportunity without a read. Unreported idle time is not inferred.

Thread access is serialized using a process-local lock. This is not safe against a malicious same-process actor, concurrent hostile filesystem mutation, or an independently supplied serialized cache. Log contents are never used to bypass verification.

## 6. Validation and replay

From repository root:

```bash
python workload_estimator.py check
python workload_estimator.py report
python workload_estimator.py predict --case stable --at 64 --mode selective
python workload_estimator.py predict --case drift --at 96 --mode selective
python -m unittest discover -s tests -p 'test_workload_estimator.py' -v
python tests/run_split_suite.py
```

The test suite checks strict event schema, sequence bounds, receipts, impossible first revision, privacy-oriented field restrictions, lack of future-event leakage, stable/churn/drift behavior, actual verified admission on repeated reads, safe revision invalidation, failed read non-recording, hostile file-environment detection, and deterministic report regeneration. CI uses fixed reports and tests, **not** volatile timing thresholds.

## 7. Evidence boundaries

1. The checked-in workload is synthetic; its percentages and decisions do **not** describe actual user behavior.
2. The timing values are reused from one v0.28 local experiment; they are not remeasured in v0.30 and cannot be generalized to another machine.
3. The forecast unit is an explicitly reported opportunity, not a wall-clock time interval. Failure to report idle opportunities biases the estimated read rate.
4. The prior distributions, rolling window and horizon are declared assumptions. They may be inappropriate for real workloads.
5. The event receipt ensures consistency, not authenticity, secrecy or resistance to a party who controls both source and receipt.
6. No changes are made to the base ALCG syntax, the published pattern registry, historical datasets, v0.29 policy profiles or any earlier report.
7. No independent AI reading/understanding result or actual production cost improvement is claimed.

## 8. Proposed v0.31 candidate, not part of this commit

Evaluate forecast calibration on *strictly separated future observations* with source-specific logging permissions and confidence-aware abstention. Do not use held-out future traffic as input to the predictor for the same cutoff.
