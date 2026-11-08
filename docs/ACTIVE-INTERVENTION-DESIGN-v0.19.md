# ALCG v0.19 — Bounded Active Intervention Design and Mechanism Identification

**Status:** verified synthetic experiment; UTF-8 canonical Markdown source. 2026-11-09.

## 1. Goal and inheritance

ALCG v0.18 enumerated 16 observationally equivalent Boolean structural causal mechanisms per family. v0.19 asks a narrower operational question:

> If all 16 candidates agree with existing observations, which intervention should be performed next, and what is the smallest number needed to distinguish a candidate from the alternatives?

The experiment operates on seven frozen v0.17 model families, 112 total v0.18 completion models. It **does not** claim general causal identifiability, AI comprehension, empirical discovery, or physical experiment selection.

The v0.18 search-space and complete report are SHA-256 pinned. Earlier artifacts, language syntax, 16 published `P_` patterns, and the public dictionary remain untouched. This version adds a separate planner, tests, and an audit report.

## 2. Fixed model class

There are two Boolean backgrounds $U,G$, one endogenous intervention source `SIGNAL`, and a Boolean outcome $Y$. The natural mechanism is `SIGNAL=U`. Four background contexts occur in the order

$$
(0,0),\ (0,1),\ (1,0),\ (1,1).
$$

The first v0.17 model in each family specifies the observational anchor $B(U,G)$. The v0.18 candidate family is

$$
Y = B(U,G) \oplus \left[(SIGNAL\oplus U)\land H(U,G)\right],
$$

where $H$ can take any of the $2^4=16$ Boolean truth tables on those four contexts. The $i$th bit of integer `mask` records $H$ at context $i$.

Under the natural condition `SIGNAL=U`, all 16 completions agree on $Y=B$. Consequently, collecting additional *identical natural-condition observations inside this model* does not identify $H$.

Interventions are restricted to setting `SIGNAL` to `false` or `true` in one specified context. Each has unit cost. In particular, setting `SIGNAL` to its *non-natural* value $1-U$ yields

$$
Y_{\mathrm{off}}(U,G)=B(U,G)\oplus H(U,G).
$$

This reveals precisely one bit of $H$ if the observation is noiseless and the model class is correct. Setting `SIGNAL` to its natural value reveals zero new bits. These are mathematical properties of the chosen synthetic circuit, not assumptions about actual interventions.

## 3. Eight possible actions and four informative actions

Action IDs use `2 * context_index + do_SIGNAL`. Thus the informative set is exactly `[1, 3, 4, 6]`.

| Context index | $U$ | $G$ | Natural-value control | Informative intervention |
|---|---:|---:|---|---|
| 0 | 0 | 0 | action 0: do(0) | action 1: do(1) |
| 1 | 0 | 1 | action 2: do(0) | action 3: do(1) |
| 2 | 1 | 0 | action 5: do(1) | action 4: do(0) |
| 3 | 1 | 1 | action 7: do(1) | action 6: do(0) |

An action's answer is always Boolean $Y$; a program cannot infer information merely from seeing the action syntax. Outcomes are obtained from the saved model signatures and cross-checked by re-executing the original `BooleanSCM` evaluator.

## 4. Two different identification objectives

### 4.1 Identify the entire mechanism mask

For complete discrimination among all 16 independent four-bit masks, **four informative interventions are necessary and sufficient**. After $k$ distinct informative actions, there can be at most $2^k$ outcome patterns, so fewer than four cannot separate all 16 candidates. Four experiments, one per background, directly recover each bit.

| Intervention budget | Maximum distinct equivalence classes | Candidates remaining in each class |
|---:|---:|---:|
| 0 | 1 | 16 |
| 1 | 2 | 8 |
| 2 | 4 | 4 |
| 3 | 8 | 2 |
| 4 | 16 | 1 |

An exact finite dynamic program independently computes the worst-case and uniform-prior expected number of measurements. Both are four for full identification. **Adaptivity offers no worst-case or average advantage in this particular unrestricted, independent-bit class.** This is a negative result worth retaining.

### 4.2 Decide whether a candidate agrees with the first v0.17 model

A weaker question asks whether the intervention signature is *the same as* the first v0.17 model in the family. This original anchor has exactly one corresponding four-bit mask in the v0.18 completion class.

If an observed response differs from the anchor at any checked background, the answer is already **different**; further interventions are unnecessary. If all tested bits agree, further testing is necessary until all four are checked.

Under a uniform prior over 16 completion masks, the dynamic program and exhaustive replay obtain the exact query-cost distribution:

| Number of interventions | Number of candidate masks |
|---:|---:|
| 1 | 8 |
| 2 | 4 |
| 3 | 2 |
| 4 | 2 |

The expected interventions are

$$
\frac{8\cdot1+4\cdot2+2\cdot3+2\cdot4}{16}=\frac{15}{8}=1.875.
$$

The worst case remains four. This is not the expected cost of actual science: it assumes uniform prior, accurate Boolean outcomes, these exact 16 hypotheses, and identical unit costs.

## 5. Optimal planning, adaptive stopping, and partial identifiability

`active_design.py` implements a finite minimax decision tree. At each candidate set it evaluates all allowed experiments, partitions hypotheses by `true/false` outcomes, and minimizes:

1. the worst remaining number of interventions;
2. the conditional mean under a uniform prior;
3. the deterministic action ID for ties.

Because each selected query partitions the compatible candidates into strictly smaller nonempty subsets, the recursion terminates. The planner is exhaustively optimized for this **bounded** action and hypothesis class.

When an experiment returns an outcome, the tool removes incompatible candidates and recomputes its next suggestion. The displayed information gain is descriptive Shannon entropy reduction under a uniform conditional prior.

If a context cannot be intervened upon, exact identification may become impossible. The API then reports `identifiability_under_allowed_actions: false`, with null worst-case and expected completion costs. It may still suggest a useful *partial-information-only* experiment. It never claims that limited access resolves all 16 mechanisms.

Likewise, an intervention result incompatible with all 16 candidates raises an error rather than inventing a seventeenth model or silently suppressing the result. That failure is informative about the limitations of the hypothesis class, not a proof of the true outside model.

## 6. Reproducible commands

From the repository root, with Python 3.10+ and no external packages:

```bash
python active_design.py check
python active_design.py summary
python active_design.py report
python active_design.py emit-spec

# Which action should be measured next for exact identification?
python active_design.py recommend --family F17_DIRECT --objective identify

# Retain the outcome of an earlier action and choose the next one.
python active_design.py recommend --family F17_DIRECT --objective identify --evidence 1=true

# Decide whether the anchor's entire intervention signature is shared.
python active_design.py recommend --family F17_DIRECT --objective anchor

# Limit accessible backgrounds; the planner explicitly reports non-identifiability.
python active_design.py recommend --family F17_DIRECT --forbid-context 2

# Run a full simulation, choosing and executing interventions until stopping.
python active_design.py simulate --family F17_DIRECT --mask 9 --objective identify
python active_design.py simulate --family F17_DIRECT --mask 14 --objective anchor

# Run dedicated tests.
python -m unittest tests.test_active_design -v
```

`--evidence ACTION=true|false` means an observed *Boolean outcome*, not a desired mask bit. Because some baselines are `true`, the two quantities are not interchangeable. The tool will reject a response that no enumerated model can explain.

The report includes a replay of every signature against `BooleanSCM`: 7 families × 16 masks × 8 intervention actions = **896 synthetic model outcomes**, plus all 16 simulated paths for both decision objectives within each family. Recomputed results must exactly match `reports/active-design-v0.19.json`.

## 7. Threat model, provenance, and limitations

- **Finite conditional result only:** only four backgrounds, 16 completion masks, eight actions, unit cost, deterministic Boolean outcomes.
- **No statistical sample noise:** a noisy intervention or imperfect measurement would invalidate the exact one-bit-per-query result.
- **No assumption of unique real-world mechanism:** observational equivalence may remain when the hypothesis class is expanded.
- **No cost of discovering or implementing intervention is modeled:** unit cost abstracts away engineering, resource and ethical constraints.
- **No independent AI reader scores:** the language comprehension benchmark is separate from these synthetic causal calculations.
- **No automatic publication of semantic units:** the v0.8 public pattern registry stays unchanged and v0.11/v0.12 proposals remain staged.
- **Deterministic revalidation:** frozen v0.17/v0.18 artifacts are pinned by SHA-256; changed inputs and mismatched stored reports are rejected.
- **Interventions are computations, not actions on a real system:** all `do(SIGNAL=...)` evaluations happen inside a local Boolean SCM evaluator.

**Result in one sentence:** when observationally equivalent descriptions remain, the amount of additional experimental information required depends on the hypothesis class, the measurement action set, and the exact decision one wants to make; a syntactically shared `CAUSE` expression alone does not fix those conditions.
