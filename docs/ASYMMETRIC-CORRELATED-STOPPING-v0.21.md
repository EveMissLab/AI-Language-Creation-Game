# ALCG v0.21 — Asymmetric Observation, Persistent Session Noise, and Stop/Continue Decisions

**Project:** AI Language Creation Game (ALCG), EveMissLab  
**Status:** deterministic, bounded synthetic experiment; **not** a natural-language semantics proof or empirical causal finding.  
**Interface:** `correlated_design.py`, Python 3.10+, standard library only.  
**Upstream:** v0.19 Boolean mechanism family and v0.20 noisy-cost planner, byte-pinned as frozen dependencies.

## 1. Question and scope

ALCG v0.19 demonstrated exact finite identification with four noiseless interventions, and v0.20 modeled independent symmetric observation flips with unequal costs. v0.21 tests two limitations: a sensor can have **different false-positive and false-negative rates**, and successive readings can share a persistent error source. Under these conditions, repeated readings are not independent after the shared error source is marginalized out.

**No changes** are made to ALCG syntax, published concept registry, v0.19 or v0.20 reports. This is an experiment over existing **assistant-authored Boolean mechanisms**, not a claim of a newly discovered causal law. A human/AI reader comprehension benchmark is a separate task.

## 2. Finite model and channel

There are 16 hypothesis masks $m\in\{0,\ldots,15\}$ and one binary session fault $z\in\{0,1\}$. Both are constant for one session. The initial assumptions are $P(M=m)=1/16$, $P(Z=1)=1/8$ and independence of $M$ and $Z$ at the start of a session.

For an action $a$, let $Y_m(a)$ denote the deterministic Boolean output of the **frozen** v0.19 mechanism. First the base sensor produces $B$ with context-dependent error probabilities:

$$
P(B=1\mid Y_m(a)=0)=\mathrm{FPR}_{c(a)},\qquad
P(B=0\mid Y_m(a)=1)=\mathrm{FNR}_{c(a)}.
$$

The reported reading is $R=B\oplus Z$. The base sensor draws are conditionally independent **given** the mechanism, session fault, and selected actions; the fault $Z$ is drawn once and remains fixed throughout the session. Consequently, marginalizing $Z$ creates correlation between readings of the same underlying signal.

| Context | False positive | False negative | Action cost |
|---|---:|---:|---:|
| 0 | 1/32 | 1/16 | 4 |
| 1 | 1/16 | 3/16 | 1 |
| 2 | 3/16 | 1/8 | 1 |
| 3 | 1/8 | 1/4 | 3 |

All four contexts are **hypothetical settings**, not field measurements. The cost is measured in arbitrary integer units. Both natural-value and off-natural interventions are available; the former may calibrate the shared sensor fault even if they do not directly distinguish mechanisms.

## 3. Exact posterior and correlation control

The program retains a 32-cell joint distribution $P(M=m,Z=z\mid D)$ with rational weights. For the recorded history $D$ of action/reading pairs, each update is

$$
P(m,z\mid D)\propto P(m)P(z)\prod_{(a,r)\in D}P(r\mid m,z,a).
$$

The displayed mechanism posterior is $P(m\mid D)=\sum_z P(m,z\mid D)$. This retains the session fault instead of multiplying separately marginalized single-reading likelihoods.

A deliberately different *control model* redraws $Z$ independently on **every** reading. It has the same one-reading marginal channel but no across-reading correlation due to the fault. This control is a mathematical contrast, **not** another source of observed data. The module tests that the two models agree after a single reading and can diverge after repeated readings.

### Frozen sample receipt

With the `F17_DIRECT` family and three `true` readings of action `3` (no actual random samples taken), the maximum mechanism posterior is:

| Model | Maximum posterior over masks |
|---|---:|
| Fixed shared session fault | approximately **0.102498935** |
| Fresh independent fault each reading | approximately **0.123417797** |

The exact rational results and the complete receipt are in `reports/correlated-design-v0.21.json`. This comparison does **not** imply correlated noise always reduces the most likely hypothesis probability for every history. The intended conclusion is that assuming independence can change the inference.

## 4. Stopping as a decision, not a certainty claim

Stopping immediately produces MAP classification of the full mechanism mask. With chosen penalty $L$ for an incorrect mask, the expected loss is

$$
C_{\mathrm{stop}}(s)=L\bigl(1-\max_m P(M=m\mid s)\bigr).
$$

A future action costs its predefined integer amount. An exact finite-horizon dynamic program chooses **STOP** or an experiment according to total expected loss (future action costs plus the eventual classification penalty):

$$
V(s,b)=\min\left\{ C_{\mathrm{stop}}(s),\;\min_{a:\,c(a)\leq b}\left[c(a)+\sum_{r\in\{0,1\}}P(r\mid s,a)V(s_{a,r},b-c(a))\right]\right\}.
$$

The source enumerates each possible binary outcome, updates the **joint** posterior with exact `Fraction` arithmetic, and caches solved subproblems. On ties it prefers STOP; otherwise it chooses the smaller action ID. The maximum allowed future budget is **4** cost units, and all eight frozen v0.19 action IDs are permitted. This is exact **only** for the specified model class, costs, budget, and loss; it is not a universally optimal experimental-design algorithm.

For the initial equal prior, a budget of 2, and the `F17_DIRECT` family:

| Incorrect-classification penalty $L$ | Exact first decision |
|---:|---|
| 8 | STOP |
| 64 | CONTINUE with action 3 |

With $L=64$ and budget 1, the prior stop loss is 60, and the optimal expected total loss (including the action cost) is exactly **235/4 = 58.75**. When remaining budget is 0, STOP is mandatory regardless of confidence.

Positive sensor error rates mean that finite observations do not guarantee a posterior probability of 1 for any of the 16 masks. STOP expresses an *economic decision under a declared loss*, **not** proof of the true mechanism.

## 5. Reproduction

```bash
python correlated_design.py check
python correlated_design.py summary
python correlated_design.py plan --family F17_DIRECT --budget 2 --loss 64
python correlated_design.py plan --family F17_DIRECT --budget 2 --loss 64 --observe 3=1 --observe 2=0
python correlated_design.py replay --family F17_DIRECT --mask 5 --fault 1 --action 3
python -m unittest discover -s tests -p 'test_correlated_design.py' -v
python tests/run_split_suite.py
```

`replay` shows the **exact probability distribution of possible synthetic readings**, not a falsely claimed realized trial. `summary` prints pinned deterministic receipts. `check` rejects changes to v0.20's scenario/report and to the v0.21 canonical specification or report.

## 6. Validation and interpretation boundaries

The new tests include probability normalization, non-symmetric error channels, correlated-vs-independent likelihoods, calibration, zero-fault consistency, finite non-certainty, malformed evidence, frozen-version guards, STOP/CONTINUE thresholds, and an independent explicit two-step enumeration to cross-check the policy value. Legacy tests are preserved unchanged. GitHub CI runs the same checks under Python 3.10, 3.12 and 3.13.

A numerical pass establishes internal consistency of this **specified mathematical toy system**; it does not validate the rates, selected loss, AI semantic understanding, or causality in the external world. The experiment does not establish that new words should be added to ALCG. Its contribution is to distinguish known assumptions and to make their consequences computable and reproducible.
