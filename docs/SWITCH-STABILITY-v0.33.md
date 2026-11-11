# ALCG v0.33 — Prefix-Only Switch Stability, Evidence Gating and Regime-Shift Cost

**Status:** experimental, reproducible, fully synthetic  
**Date:** 2026-11-11  
**Project:** AI Language Creation Game (ALCG)  
**Source:** canonical UTF-8 Markdown

## Abstract

This experiment extends the v0.32 three-expert prequential model selector with a finite, auditable *switch gate*. Rather than switching whenever a competitor's short-run mean loss is marginally better, the gate requires repeated wins on **previously closed** windows, a declared minimum expected advantage, an explicit Beta-Bernoulli win score, and a one-window cooldown. It then projects each decision into a parseable `GATE_V033(...)` expression with an exact source-prefix receipt. The scheme does not update the v0.32 expert definitions, cached observations, historical reports, language dictionaries, or core parser.

The primary finding is a **tradeoff, not a universal improvement**. On the frozen v0.32 synthetic corpus, switches decline from five to four, but mean combined Brier loss increases from approximately 0.208214 to 0.213635. On a deliberately alternating adversarial loss track, the gated policy avoids ten naive one-window switches; on a sustained shift, it responds later and accumulates additional loss. These are bounded computational observations, not real-world generalization or AI comprehension measurements.

## 1. Inputs and temporal coordinates

The immutable v0.32 sources contain four synthetic event streams: `stable`, `churn`, `sparse`, and `drift`. Each stream has 192 time opportunities. The evaluated forecast cuts are 32, 64, 96, 128 and 160; each holdout covers 32 future opportunities.

At cut $t$, the input is **exactly** the prefix ending at $t$. Expert predictions at earlier cuts $u$ may be scored only if their holdout is completely closed:

$$
u(u)=u+32\leq t.$$

Every recorded paired loss is associated with its old cut, its completed-outcome digest and an exact rational loss per expert. Future holdouts never participate in issuance; they are examined separately only for post-hoc evaluation.

The three frozen candidate models are `RAW`, `LAGGED`, and `HEDGE`. When a supported forecast cannot be issued, the publicly visible selection is `DEFER`, with the safe direct-verification route.

## 2. Gate and finite evidence score

Let $L_{m,i}$ be the previously measured combined Brier loss for candidate $m$ on closed historical window $i$. For incumbent $b$ and challenger $m$ define the signed advantage over up to three most recent closed and supported windows $I_t$:

$$
A_{m,b}(t)=\frac{1}{|I_t|}\sum_{i\in I_t}(L_{b,i}-L_{m,i}).
$$

A win is a strict lower loss. Exact ties are counted separately and are not silently assigned as wins. The gate uses the **declared assumption** of a uniform Beta(1,1) prior and a Bernoulli likelihood for a hypothetical repeated win process. With $w$ wins and $\ell$ losses, its score is:

$$
S(w,\ell)=\Pr(p>1/2\mid w,\ell)
=\frac{1}{2^{w+\ell+1}}\sum_{k=0}^{w}\binom{w+\ell+1}{k}.
$$

Exact fractions are used throughout, without floating-point decisions. A challenger may be selected only if:

1. At least two closed supported windows exist and at least two are strict wins;
2. $S(w,\ell)\geq 7/8$;
3. $A_{m,b}> 1/10000+1/1000$ (switch penalty plus additional margin);
4. No switch occurred during the preceding one decision window.

Among qualifying challengers, the lower mean loss wins, with `RAW`, `LAGGED`, `HEDGE` as a deterministic tie breaker. Otherwise the incumbent remains. A true switch updates the cooldown state.

**Interpretation limit:** $S$ is a reproducible **model-assumption score**. Its Bernoulli independence assumption can be false for overlapping, regime-correlated or adversarial observations. It is NOT a calibrated confidence interval, probability that the selected model is objectively correct, or proof of stationarity.

## 3. Frozen-case evidence and negative result

| Metric | v0.32 | v0.33 |
|---|---:|---:|
| Synthetic issuance windows | 20 | 20 |
| Supported and scored windows | 15 | 15 |
| Deferred `sparse` windows | 5 | 5 |
| Model switches | 5 | 4 |
| Mean combined Brier loss | 0.208214 | 0.213635 |

In the v0.33 fixture the selected inventory is 10 `RAW`, 2 `LAGGED`, 3 `HEDGE`, and 5 `DEFER`. Model switches occur once in `stable`, twice in `churn`, once in `drift`, and never in `sparse`.

This is a **negative comparison for predictive loss**: fewer switches did not make the score better. The old report stays published and unchanged; a new report contains both results, sourced from the same completed holdouts.

## 4. Adversarial diagnostic tracks

Four additionally authored **loss trajectories** are not part of the v0.32 event streams. They use a 12-step sequence of exact bounded losses for each expert and compare v0.33 to a distinct *one-previous-window winner* heuristic. This latter policy is NOT identical to v0.32, and must not be labeled as such.

| Track | Gated switches | One-window heuristic switches | Result |
|---|---:|---:|---|
| `alternating` | 0 | 10 | Gate avoids repeated back-and-forth changes |
| `single_spike` | 0 | 2 | Gate ignores an isolated challenger win |
| `sustained_shift` | 1 | 1 | Gate first leaves `RAW` at step 9, three steps after the change at step 6 |
| `flat` | 0 | 0 | Both remain stable |

On `sustained_shift` the gate incurs a greater synthetic realized loss than the one-window heuristic. The delay is the cost of requiring persistence, and is an essential finding rather than an implementation mistake. Neither strategy is claimed optimal for unknown conditions.

## 5. Language representation

A decision is exposed as English-readable ALCG syntax, without adding a new core-parser rule:

```text
GATE_V033(scenario=DRIFT, at="128", selected=RAW, reason=NO_QUALIFYING_ADVANTAGE, prior="3", policy=DIRECT, prefix_sha256="...", receipt_sha256="...")
```

The displayed hashes above are schematic. The checked-in `.alcg` file contains actual full digests and all twenty exact decisions. A `GATE_V033` expression is **not self-authenticating**. To verify a receipt, load the pinned public model and exact original prefix, recompute the decision and compare the entire issuance, including its hash. A forged receipt with a recomputed hash still fails if its decision differs from the canonical recomputation.

## 6. Reproduction

Requirements: Python 3.10+, standard library only, no API keys or network access.

```bash
python switch_stability.py check
python switch_stability.py report
python switch_stability.py issue --case drift --at 128
python switch_stability.py stress --case alternating
python switch_stability.py stress --case sustained_shift
python alcg.py check samples/switch-decisions-v0.33.alcg
python -m unittest discover -s tests -p 'test_switch_stability.py' -v
python tests/run_split_suite.py
```

All published data is synthetic and intended as a reusable language-game benchmark. GitHub Actions checks each supported Python version separately, including the frozen report and language projections; it does not impose CPU-time thresholds.

## 7. Scope and epistemic boundaries

- The fixed candidate models, Beta prior, threshold, evidence window, minimum margin and cooldown were authored. They were not learned from a representative sample of production workloads.
- The stress tracks are deliberately constructed diagnostics and should not be treated as independent predictive performance evidence.
- No conclusion is asserted about actual AI understanding of `GATE_V033` or any other ALCG expression. Structural parse success and exact receipt replay are not independent AI comprehension.
- There is no new cryptographic authentication; SHA-256 is used for integrity and cross-version replay only.
- The old v0.32 report is pinned by its byte hash. Its separate unchanged CI test verifies that report from its historical canonical sources.
- A different lookback, cost ratio, workload distribution or noise regime can reverse the result. There is no general optimal-switching theorem here.

**Core conclusion:** A policy that resists spurious short-run variation can also resist useful change. ALCG must record both the evidence that justified a model change and the evidence-cost of waiting to change it.
