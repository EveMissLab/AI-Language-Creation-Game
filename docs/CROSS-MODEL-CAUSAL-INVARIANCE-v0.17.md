# ALCG v0.17 — 跨模型有限因果穩定性試驗

**Status:** Experimental, public, deterministic, Python standard library only. The findings concern **stipulated finite Boolean structural-causal-model families**. They are **not** evidence of causation in natural systems, a universal semantics for English `CAUSE`, independent AI understanding, or semantic truth of the original English labels.

## 1. Research question and scope

v0.16 implemented an optional, typed `CAUSE` probe in **one** explicitly specified model. This version asks a stronger, separate question:

> If the *same expression* and named background assignments are retained, which properties of an intervention remain invariant when the internal causal mechanism changes?

For example, the expression

```text
CAUSE(source=SIGNAL, effect=CHANGE(subject=ROBOTIC_ARM, property=CONTROL_SIGNAL))
```

is evaluated in three model mechanisms with identical source/outcome mappings but different structural equations. It is not assumed to hold simply because its symbolic expression parses. We compare outputs under `do(SIGNAL=false)` and `do(SIGNAL=true)` in every stipulated background.

**No core grammar changes, no new operators, no published dictionary additions.** The v0.16 model file and report, plus the published v0.8 dictionary, are checked against frozen SHA-256 values and left unchanged.

## 2. Restricted, falsifiable definitions

The toy SCM uses acyclic binary equations, each applying only `copy`, `not`, `and`, `or`, or `xor`. All families have a named endogenous `SIGNAL` initially assigned from exogenous `U`; a second exogenous condition `G`; and a declared Boolean indicator `Y` associated with the expression's named `CHANGE` outcome. Every model in a family agrees on the names of these input/output interfaces. The internal equation graph can vary.

The background domain in this release is the **four exhaustive pairs** of values for `U` and `G` — not data sampled from a population. Labels `U` and `G` are assumed to refer to aligned conditions across models; changing that assumption would invalidate direct comparisons.

For fixed model `M`, background `u`, source `X` and declared output `Y`, let:

$$
R_M(u)=\big(Y_{do(X=0)}(u),Y_{do(X=1)}(u)\big).
$$

Define the *signed response* as `positive` if the pair is `(0,1)`, `negative` if `(1,0)`, otherwise `unchanged`. These are differences in the **stipulated binary indicator**, not measured natural-world increases or decreases.

The system separately evaluates the following increasingly weaker concepts:

1. **Exact response invariant**: every model returns the identical ordered `(Y0,Y1)` pair for **every** background.
2. **Qualitative direction invariant**: every model returns the identical sign for **every** background, even if baseline values differ when influence is absent.
3. **Context-limited direction invariant**: at least one specified background has the same *nonzero* sign across all models; the sign may disagree elsewhere.
4. **Existential influence agreement**: each model does or does not have some influence somewhere. This is weaker than having the same sign or matching in the same background.
5. **No common nonzero direction**: no background has a shared positive or negative sign across all models; this does **not** imply there is no causal influence in any model.

In addition, the report records whether **every** model has nonzero influence in at least one background and whether **every** model has influence in all enumerated backgrounds. Negative results are relative to the enumerated models only.

## 3. Provenance, input isolation and reproduction

- Versioned declarations: `data/causal-families-v0.17.json`; seven manually selected model families with three explicitly stipulated mechanisms each.
- Deterministic fixture builder: `family_fixtures_v017.py` reproduces the exact fixture bytes. `emit` prints the declaration; `check` compares without overwriting files.
- Analyzer and counterexample receipt verifier: `causal_robustness.py`.
- Committed machine-readable result: `reports/cross-model-invariance-v0.17.json`.
- New regression and adversarial tests: `tests/test_causal_robustness.py`.
- Unchanged baselines: `data/causal-models-v0.16.json`, `reports/causal-intervention-v0.16.json`, `data/patterns-v0.8.json` (explicit SHA-256 locks).

The fixture cases were authored to demonstrate different logical possibilities. They are **not** randomly sampled, learned from empirical data, validated by external AI readers, or held-out from the design of this experiment. Counts are a *coverage of seven selected diagnostic categories*, not a population statistic or claim about naturally occurring causal mechanisms.

## 4. Results of this exact fixture

Seven families × three models × four backgrounds = **84 model-background evaluations** and **168 Boolean intervention evaluations**. The report also computes observational associations, but these descriptors are derived from the enumerated synthetic contexts.

| Family | Actual finding | Classification |
|---|---|---|
| `F17_DIRECT` | Direct, mediated and irrelevant-branch mechanisms all give the same `(false,true)` under either intervention at every background | Exact invariant |
| `F17_DIRECTION_ONLY` | When `G=true` all respond positively; when `G=false` all have zero sign, but some baselines are false and others true | Qualitative sign invariant only |
| `F17_CONTEXT` | All respond positively under `G=true`; under `G=false` the three responses are zero, positive and negative | Context-limited direction invariant |
| `F17_POLARITY` | Every model has an intervention effect, but mechanisms disagree on positive versus negative direction | No common nonzero direction |
| `F17_DISPUTED` | Direct/gated mechanisms have intervention effects; a common-driver model correlates observationally with the source but has zero intervention effect | No common nonzero direction |
| `F17_NO_EFFECT` | Every model has zero intervention effect, despite different observational patterns and output baselines | Qualitative sign invariant only (`unchanged`) |
| `F17_NEGATIVE` | Every mechanism inhibits the indicator when `G=true`; it has zero response when `G=false`, with differing suppressed baselines | Qualitative sign invariant only |

Counts: exact response invariant **1** family; qualitative direction invariant only **3**; context-limited **1**; no common nonzero direction **2**. The 7 categories were chosen before calculating these synthetic examples; the classifier did not discover that these phenomena occur in any outside population.

**Important distinction:** `F17_POLARITY` has existential intervention influence in all three models, yet no shared sign. A claim that survives the weak Boolean test *in all sampled model variants* can still fail under directional scrutiny.

### Finite-model counterexample: `F17_CONTEXT`

For `G=false` and any fixed `U`, the three mechanisms yield different intervention responses:

```text
F17_CONTEXT_M1: Y = SIGNAL AND G          -> do0=false, do1=false  (unchanged)
F17_CONTEXT_M2: Y = SIGNAL                -> do0=false, do1=true   (positive)
F17_CONTEXT_M3: Y = SIGNAL XOR (NOT G)    -> do0=true,  do1=false  (negative)
```

For `G=true`, all three become `do0=false, do1=true` (positive). The same ALCG expression therefore has a **context-restricted invariant**, not a globally identical interpretation across the stipulated mechanisms.

### Observational confounding versus intervention

In `F17_DISPUTED_M2`, `SIGNAL = U` and `Y = U`. Their observations coincide for all four backgrounds, but replacing the equation for `SIGNAL` does not alter `Y`. The observation is not evidence that an intervention on `SIGNAL` affects `Y`.

## 5. Runnable commands

```bash
# Reproduce and compare the synthetic declarations (no write by default)
python family_fixtures_v017.py check
python family_fixtures_v017.py emit

# Verify source locks, recompute the report and replay every model/background
python causal_robustness.py check

# Read concise summary or full machine-readable report
python causal_robustness.py summary
python causal_robustness.py report

# Replay all three mechanisms at the same background
python causal_robustness.py replay --family F17_CONTEXT --context-index 0
python causal_robustness.py replay --family F17_CONTEXT --context-index 1

# Validate every historical and new test case
python -m unittest discover -s tests -v
```

The checker rejects changed legacy baselines; a fixture that differs from the deterministic builder; duplicated, cyclic or forward-reference equations; missing source/outcome mappings; unmatched background variable names or ordering; duplicate model systems; inconsistent result receipts; and tampered committed report data. The actual interventions are recomputed in the replay path rather than trusting stored summaries.

`--context-index` refers to deterministic enumeration of the four `(U,G)` assignments, starting at zero. The returned receipt explicitly prints each model's outcome under both interventions, the common background, and whether directions agree. It never claims that the result applies to an actual engineering system.

## 6. Interpretation for the AI Language Creation Game

This experiment separates at least three representational tasks:

- **Expression identity:** two ALCG expressions with matching syntax and role names can be compared.
- **Model-relative executable meaning:** an explicitly declared mechanism fixes intervention responses within one finite world.
- **Robust cross-model meaning:** the response or its direction remains stable over a declared family of alternative mechanisms and aligned backgrounds.

The new results show why retaining a readable English concept name is not enough to identify a unique causal action. A future *functional* or mesoscopic representation would need to describe assumptions, interface variables, preconditions, intervention domain, output postconditions, and the evidence supporting its purported stability. The current release **does not define or promote mesoscopic units**; it only supplies a testable prerequisite.

## 7. Hard limitations

- Only **two exogenous Boolean variables**, three synthetic models per family, seven hand-picked families, and a restricted `CHANGE` indicator. Nothing here handles continuous values, feedback loops, real time, uncertainty, stochastic SCMs, interventions on exogenous variables, measurement error or counterfactual identification from data.
- The labels are convenient English identifiers. Their actual scientific meanings are **not** formalized or verified by the program.
- An invariant across the tested family is not invariant across all conceivable mechanisms. A different fourth model can invalidate the classification.
- Comparing contexts assumes semantic alignment of `U,G` across models. No transfer is justified when that fails.
- No independent AI readers were tested; comprehension score is `null`. No measured physical or social data were used; empirical causal evidence is `null`.
- Both observation and intervention calculations are fully synthetic. The uniform enumeration does **not** estimate real-world intervention probabilities.

**Concluding criterion:** The syntax tells us what is being claimed. A model tells us what that claim means under stated assumptions. Only a stated and tested family of models can tell us whether that meaning remains stable under changes in assumptions — and only *within that family*.
