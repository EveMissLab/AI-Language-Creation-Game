# ALCG v0.18 — Observation-Equivalent Mechanism Search

**Status:** bounded experimental mechanism exploration, 2026-11-09. This is an **AI Language Creation Game** research component, not a discovery of empirical causation, not a formal theorem about all causal models, and not a measurement of independent AI understanding.

## 1. Research question

v0.17 tested the same typed `CAUSE(source=SIGNAL, effect=CHANGE(...))` claim in seven families of three manually specified Boolean structural causal models (SCMs). Those classifications are **correct for those exact families**. But what happens when the family expands to include a mechanism that agrees with existing observations yet behaves differently under `do(SIGNAL=x)`?

v0.18 addresses this *model-family sensitivity* with a **finite exhaustive completion experiment**, without changing a single v0.17 input or published pattern.

The distinction is:

1. **Observational equivalence to a designated anchor:** new and anchor models output identical `(SIGNAL, Y)` for each enumerated exogenous background with no intervention.
2. **Interventional equivalence:** for every background, the model also agrees under both `do(SIGNAL=false)` and `do(SIGNAL=true)`.
3. **Family stability:** the originally true invariant across the three old models survives addition of the candidate as a fourth.

The first **does not imply** the second or third.

## 2. Bounded universe, declared before measuring the outcomes

The frozen space in `data/mechanism-search-space-v0.18.json` specifies:

- Two binary exogenous variables, `U` and `G`, with exactly four backgrounds in ordered `(U,G)` order: `(0,0)`, `(0,1)`, `(1,0)`, `(1,1)`.
- The endogenous source `SIGNAL` naturally copies `U`, so all observational rows lie on the restricted support `SIGNAL = U`.
- A binary endogenous output `Y`, explicitly mapped to each family's existing `CHANGE(subject=..., property=...)` indicator.
- The baseline observation function `B(U,G)` is the first original family model's **observed** value of `Y` in each background.
- An arbitrary Boolean completion function `H(U,G)` has four output bits. There are exactly `2^4 = 16` such completions, numbered `0..15`.

Every candidate implements the following original mathematical source expression (canonical LaTeX delimiters):

$$
Y=B(U,G)\oplus\left((SIGNAL\oplus U)\land H(U,G)\right).
$$

When `SIGNAL = U` without intervention, the second term is zero and the expression collapses to `B(U,G)` regardless of `H`. When an intervention sets `SIGNAL` to the opposite value of `U`, the term is `H(U,G)`; changing one mask bit changes exactly that off-support response.

Thus, **relative to this fixed anchor and this finite domain, 16 different full interventional response tables are exhaustively covered**. This does **not** enumerate all possible SCMs, inputs, outcomes, physics, or human meanings. All candidate circuits use only `copy`, `not`, `and`, `or`, and `xor` within the v0.16 limit of 24 acyclic equations.

All families share the *same label names and background ordering* in this experiment. The code rejects a source which does not naturally copy `U`. It does not assign statistical probabilities to backgrounds.

## 3. Frozen evidence / no retrospective rewriting

Pinned inputs:

| Artifact | SHA-256 |
|---|---|
| `data/causal-families-v0.17.json` | `8e56da78a59fae8a3c7c65940b2a44b2d351d8a155cded02308f75b3173e0589` |
| `reports/cross-model-invariance-v0.17.json` | `e10073f903a77017ebae9c8571359f02028fa79276f6523f1da25aa6972838b3` |

The older v0.16 and published `data/patterns-v0.8.json` records remain frozen through the existing v0.17 guard. Search space, classifier, selection rule, source-alignment requirements and all 16 masks are committed independently of test scores.

## 4. Search and witness logic

For each of the seven families:

1. Load its original three pinned SCMs and original category.
2. Read the **first** model's four natural observational outputs. Do **not** claim observation equality to every original member; they need not have identical observational functions.
3. Compile 16 models with identical observations to the selected anchor but differing possible off-support responses.
4. Check each compiled model and verify observational equivalence in all four backgrounds.
5. Compare the new intervention pairs `(Y_do0, Y_do1)` with the original three models for every background, for a total of 16 distinct response signatures per family.
6. Add **one candidate at a time** to the original three and recompute the v0.17 classification.
7. Select the first mask in ascending order that invalidates a **previously true** nonvacuous invariance claim:
   - **Exact response invariant:** a model has a different intervention pair in any context.
   - **Qualitative direction invariant:** a model has a different sign category (`positive`, `negative`, `unchanged`) in any context.
   - **Context-limited robust direction:** a model violates an originally agreed nonzero direction in any previously robust context.
   - **No common nonzero direction:** no such invariant existed; adding a model **cannot refute its absence**. Record it as nonapplicable, not a false success.
8. Preserve the first witness including exact `U,G` values, all three old model responses and the new model response; expose a `replay` command.

A family that loses only one previously robust context is classified as **weakened**, not automatically as having no stable contexts whatsoever. `first_refuting_mask` means *first counterexample to the old claim*, never a universal impossibility theorem.

## 5. Results from this pinned synthetic space

| Measure | v0.18 result |
|---|---:|
| Original families / models | 7 / 21 |
| Candidate masks per anchor | 16 |
| Generated candidate models | 112 |
| Distinct response signatures within each anchored search | 16 |
| Candidate × natural-background slots | 448 |
| Candidate × background × intervention-value slots | 896 |
| Families with initially nonvacuous invariants | 5 |
| Families with an additional counterexample | 5 |
| Families already lacking a common nonzero direction | 2 |
| Independent AI readers / empirical cause data | 0 / 0 |

The slot counts describe the unique comparisons reported; internal validation and recomputation may execute the same model more than once.

| Family | v0.17 class | First violating completion |
|---|---|---:|
| `F17_DIRECT` | exact intervention response | mask `0` |
| `F17_DIRECTION_ONLY` | qualitative direction only | mask `0` |
| `F17_CONTEXT` | context-restricted direction | mask `0` |
| `F17_POLARITY` | no shared nonzero direction | not applicable |
| `F17_DISPUTED` | no shared nonzero direction | not applicable |
| `F17_NO_EFFECT` | qualitative direction (`unchanged`) | mask `1` |
| `F17_NEGATIVE` | qualitative direction only | mask `0` |

### Specific counterexample: same observations, different causal claims

`F17_DIRECT` originally contains three models whose intervention outcomes are always `(false, true)`, i.e. `SIGNAL` has a positive effect on `Y` in every background. The new mask `0` candidate uses `H=0`, so its output is just `B(U,G)=U`; consequently the candidate's outcome is independent of intervening on `SIGNAL`.

Both the original first model (`Y=SIGNAL`) and this new model (`Y=U`) yield **identical observed `(SIGNAL, Y)` at all four backgrounds**, because `SIGNAL=U` in nature. But they differ under intervention, e.g. at `U=0,G=0`, where the original has `(Y_do0=false, Y_do1=true)` and the candidate has `(false,false)`.

This refutes a stronger assertion, *"the exact response is stable across every model compatible with those observations in the bounded completion class"*, **not** the true assertion that the original three specified models agree.

`F17_NO_EFFECT` yields the complementary example: the first three models have no nonzero source influence; completion mask `1` creates a positive effect in `U=0,G=0` while preserving the anchor's observed output in all four contexts.

## 6. Reproduction (standard-library Python 3.10+)

```bash
python mechanism_search.py check
python mechanism_search.py summary
python mechanism_search.py replay --family F17_DIRECT --mask 0 --context-index 0
python mechanism_search.py replay --family F17_NO_EFFECT --mask 1 --context-index 0
python -m unittest discover -s tests -v
```

`check` recomputes all candidates, checks the complete machine-readable receipt against `reports/mechanism-search-v0.18.json`, and replays each selected counterexample. `emit-space` prints the canonical deterministic search specification. No external APIs, random model sampling, paid runners, or independent AI calls are required.

The report stores every candidate's mask, count of compiled equations, full four-background intervention signature, matches to old members, changed family classification, and first violation witness where applicable.

## 7. Interpretation and boundaries

- This is **programmatically generated Boolean mechanism exploration** over an explicitly finite hypothesis class. It is not an LLM independently inventing valid human concepts or real-world mechanisms.
- Matching observed outputs only to the first model of each family deliberately isolates *underidentification*; these candidates are **not** asserted to fit all observations from all three historical family members.
- Synthetic Boolean `Y` represents a named indicator, not an observed physical quantity, event time series, or proof of a linguistic proposition.
- Because the source `SIGNAL` is fixed by `U` in the natural data, the unseen intervention surface is large. A real experimental design with interventions could constrain this ambiguity. This laboratory intentionally does not have such data.
- Exhaustive coverage of 16 completions does not imply all theoretical mechanisms are exhausted. No unobserved continuous state, stochastic processes, counterfactual cross-world assumptions, measurement error, or physical realizability is modeled.
- A negative claim about an existing lack of shared sign is not something that can be "refuted" by merely adding another member. The system explicitly preserves this monotonicity.
- The v0.8 public pattern dictionary, v0.17 classification report and all earlier artifacts are unchanged; no new ALCG syntax, mesoscopic character, or callable executable semantics is published by this experiment.

**Takeaway:** In an AI-readable language, a cause-effect relation must eventually carry its *model assumptions and intervention scope*, or else apparently identical observational descriptions may hide incompatible causal actions.
