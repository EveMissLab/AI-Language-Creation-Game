# ALCG v0.16 — 有限布林結構因果介入實驗

**Status:** Experimental, opt-in, assistant-authored toy-model semantics. **Not** empirical causation, a universal meaning of `CAUSE`, a general program-execution language, or an AI comprehension benchmark.

## 1. Why this release exists

The frozen v0.15 report has **16 non-equivalent CAUSE-root contrasts without executable causality semantics**. The old report remains unmodified. v0.16 defines an explicitly separate, narrow demonstration of intervention on a *predeclared finite structural causal model (SCM)*.

There are two experimentally different questions:

- **Observation:** when a named source is observed as true or false, does an outcome indicator co-vary?
- **Intervention:** holding the background variables fixed, would replacing the source's structural equation by an assigned value change the outcome indicator?

A high observational association alone does not answer the intervention question. This is the central point of this release.

## 2. Supported ALCG subset

The new oracle accepts only this tree shape:

```text
CAUSE(source=NAME, effect=CHANGE(subject=NAME, property=NAME))
```

Argument order does not matter; typed roles do. The expression identifies a *source variable* and a *Boolean outcome indicator* mapped by the fixture. The model-specific interpretation is whether toggling that source changes the indicator in **at least one** enumerated background context.

**Important scope limitation:** `CHANGE` in this oracle is an explicitly declared Boolean indicator. It is **not** a measured difference between two time-indexed physical states. An `IS(...)` outcome cannot be silently substituted for `CHANGE(...)`: this version reports it as **outside the typed causal subset**, not as a false causal proposition. Nothing here changes v0.4's `finite_probe.py` interpreter or the 16 published v0.8 patterns.

## 3. Toy-SCM definition

Let $U$ denote a finite vector of exogenous Boolean context variables. Each named endogenous variable  $X_i$ is defined by an equation using an earlier variable, with operations restricted to `copy`, `not`, `and`, `or`, or `xor`. Dependencies must be acyclic. The system enumerates every possible assignment to `$U$` (in the shipped models, **4 contexts per scenario**).

An intervention `do(X=x)` replaces only the named structural equation for `X`, without modifying other equations or the held exogenous context. If the declared output indicator is `Y`, the opt-in interpretation of the causal candidate is:

$$
I_M(X,Y)=1 \iff \exists u:\ Y_{do(X=0)}(u) \ne Y_{do(X=1)}(u).
$$

**This is a chosen finite-model criterion of contextual influence, not the general definition of causation in nature.** It is symmetric with respect to the magnitude of source activation (it detects inhibitory effects as well). It does not infer when an event happens, nor measure probabilities of real-world interventions.

An observational comparison uses the fraction of fixture contexts where `Y=true` among contexts where `X=true` versus those where `X=false`. The contexts are enumerated **uniformly by design**, not sampled from a population; the fractions are toy-model descriptors, not empirical probabilities.

### Example A: association without causal influence

```text
U -> X (copy)
U -> Z (copy)
U -> Y (copy)
```

Here observations show `X=Y` for every listed context, so they are perfectly associated. But `do(X=0)` and `do(X=1)` leave `Y` unchanged while `U` is held fixed. This is the confounding scenario `G14_CAUSE_06`.

### Example B: contextual causal influence without marginal association

```text
X = U
Z = U
Y = xor(X, G)
```

With `U` and `G` independently taking both values in the four toy contexts, the observed fraction of `Y=true` is **1/2 for either value of X**. However, under a fixed `G`, intervening on X changes Y. This is `G14_CAUSE_07`. The implication is limited to this declared circuit.

## 4. Exact dataset and provenance

- **Original input:** the already frozen `benchmarks/generated-challenges-v0.14.jsonl`, identified by SHA-256 `0d40a9effbf8c3f559269d5a300a6160e5ed3ef251b0bd2b2ad18651c60f8802`.
- **Toy models:** `data/causal-models-v0.16.json`: **eight manually specified, assistant-authored** finite SCMs matched to the eight v0.14 CAUSE-root cases. Mechanisms include direct, mediated, gated, inhibitory, spurious-confounding, interactive and foil-caused indicators. **They were not learned from independently observed data.**
- **Baseline preserved:** `reports/bounded-counterexamples-v0.15.json` and `data/patterns-v0.8.json` remain byte-identical to pinned baselines. The new interpretation is opt-in and does not replace older statuses.
- **Computed report:** `reports/causal-intervention-v0.16.json`, directly regenerated and verified by `causal_lab.py`.

Each case has three comparisons: a canonically equivalent argument reorder, a changed-source variant, and a changed-effect-operator variant. **24 comparisons in 8 deliberately constructed contexts of interpretation**, not a random English sample or an independent test of language generality.

## 5. Results of this particular, stipulated fixture

| Category | Count | Exact interpretation |
|---|---:|---|
| Canonical equivalent under same SCM | 8 | Named argument order changes without changing the expression |
| Source contrast differs under the stipulated SCM | 7 | One source has contextual intervention influence on the mapped indicator and the other does not |
| Source contrast not separated by this SCM | 1 | Both sources lack contextual influence here; does **not** prove semantic equivalence outside this toy model |
| Effect replaced with `IS(...)` | 8 | Expression outside the v0.16 typed subset; **not** scored true or false |

The seven separating contrasts deliberately include **one case where the foil is causally influential and the original is not**. The report cannot be used to assert that the original expressions are true descriptions of those real-world devices or processes. The circuits were *authored* to illustrate possible behaviors, and no independent AI reader was tested.

Among the eight originals, six have toy contextual influence, two do not. Seven have marginal observational association and one has none; the no-association case still has intervention influence. These are fixed-model counts, not measured rates in the world.

## 6. Running and verifying

Standard library Python 3.10+ is sufficient:

```bash
python causal_lab.py check
python causal_lab.py report
python causal_lab.py replay --case G14_CAUSE_01 --variant lexical_slot_change
python causal_lab.py replay --case G14_CAUSE_08 --variant lexical_slot_change --side alternate
python -m unittest discover -s tests -v
```

The `check` command recomputes the report, checks frozen input hashes, verifies the committed report against fresh output, and independently replays all positive intervention receipts. The `replay` command exposes one held background context, the observed source/outcome values, and the outcomes under the two counterfactual interventions.

The checker refuses unknown, cyclic or forward-reference equations; unknown output mappings; invalid Boolean values; untyped `CAUSE` structures; arbitrary operators; altered baselines; and modified witness receipts. There is **no `eval`, user code execution, network dependency, GitHub secret or API requirement**.

## 7. What this version does not establish

1. It does **not** discover real causal structure from observations. The structural equations are externally stipulated, not inferred.
2. It does **not** justify saying “cause” whenever two symbols or measurements correlate. Conditional intervention and observational association are tracked separately.
3. A missing witness under a particular SCM is **not** a model-independent equivalence theorem. A found witness is only a counterexample **under the authored finite SCM**.
4. `CHANGE` here is an outcome-marker convention; it is not a time-series dynamics semantics, engineering control law or physical causal measure.
5. The prototype does **not** prove cross-AI semantic understanding, and is not a substitute for fresh, independently scored reader experiments.
6. It does **not** promote any v0.11/v0.12 generated proposal into the published ALCG dictionary.

## 8. Research interpretation

The useful v0.16 distinction is not how often an authored fixture produces `true`, but that **language syntax, structural truth in an explicitly specified model, observational association, and intervention sensitivity have separate evidence requirements**.

That separation lets AI language creation grow toward usable concept/function composition without prematurely treating readable English labels as real executable physics or inferring meaning from string matching alone.
