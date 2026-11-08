# ALCG Coverage Laboratory v0.2 — Experimental Protocol

**Date:** 2026-11-08  
**Language:** English-readable symbols, UTF-8 source  
**Status:** Open-source engineering experiment; not a validated semantic theory

## Purpose

ALCG starts from English-readable concepts and composes them as recursive expressions. The v0.1 parser only checked **syntax**. The v0.2 laboratory introduces a deliberately small, reproducible benchmark to separate three claims that must **not** be conflated:

1. **Parsing**: an expression can be represented as a structured syntax tree.
2. **Proposed expression**: a writer believes an expression captures an intended English meaning, subject to gaps.
3. **Reconstruction**: an independent reader or AI recovers the intended meaning from the expression **without seeing the source English**.

Only (1) is mechanically verified today. The dataset records (2) as human-authored hypotheses and leaves (3) unscored until independent blind trials occur.

## Data and the first experiment

- `benchmarks/coverage-v0.2.jsonl`: 36 authored English meanings; six each from daily situations, natural science, mathematics, computing, society, and epistemic concepts.
- `data/relations-v0.2.json`: 17 provisional operator signatures, with their required/optional role names and plain-English caveats.
- `coverage_lab.py`: deterministic validator, audit, blind challenge export, and **externally** adjudicated scoring interface.
- Existing `alcg.py` is unchanged. Core v0.1 grammar remains valid. This role layer is a **benchmark convention**, not a final universal syntax/ontology.

### Categories

| Label | Operational meaning | Interpretation |
|---|---|---|
| `candidate` | One expression; no `RAW`, no `PARTIAL`; registered operator/role signatures. | A **proposed** structured encoding, not yet a verified semantic match. |
| `partial` | `PARTIAL(core=..., missing=RAW(text="..."))` | Structured core exists, but known missing information prevents claiming full coverage. |
| `raw` | Top-level `RAW(text="...")` | No structured encoding is claimed. |

**Important:** English-readable `Name` identifiers such as `PLANET` or `GREATER_THAN` are **not a defined ontology**. A registered call name only checks the argument keys, not whether its words or claims are semantically correct. New relation labels require an explicit profile to pass the laboratory, but a profile alone cannot prove meaning.

### First seed audit (not a general-language coverage score)

| Domain | Candidate | Partial | Raw | Total |
|---|---:|---:|---:|---:|
| Daily | 4 | 1 | 1 | 6 |
| Natural science | 4 | 1 | 1 | 6 |
| Mathematics | 4 | 1 | 1 | 6 |
| Computing | 4 | 1 | 1 | 6 |
| Society | 4 | 1 | 1 | 6 |
| Epistemic concepts | 4 | 1 | 1 | 6 |
| **Total** | **24** | **6** | **6** | **36** |

The **24/36 candidate share (66.7%)** only describes **this manually curated seed**, deliberately balanced by category. It is *not* an estimate of the fraction of English meanings the language can express, nor of any AI's comprehension accuracy. No independent reconstruction has yet been graded.

## Reproduce the trial locally

Only Python 3.10+ and the standard library are needed:

```bash
python coverage_lab.py check
python coverage_lab.py audit
python coverage_lab.py blind --out blind-v0.2.jsonl
python -m unittest discover -s tests -v
```

### Blind reader protocol

1. The evaluator sees only records with `id` and `expression` from `blind-v0.2.jsonl`. They must **not** receive the benchmark's `english`, `hypothesis` or `gap` columns.
2. Ask the evaluator to describe each expression in ordinary English and report uncertainty. Use a different AI or a separately blinded evaluation procedure; do not claim independence without one.
3. An adjudicator separately checks reconstruction against the original `english` and notes known semantic loss. Give each case a **rating from 0 to 3**:
   - **0:** wrong, contradictory, or no useful reconstruction;
   - **1:** topic recovered but important proposition/roles missing;
   - **2:** central proposition mostly recovered but qualifiers, scope, or relations lost;
   - **3:** essential proposition and relations faithfully recovered with no critical omissions.
4. Store adjudications in a UTF-8 JSONL file, for example:

```jsonl
{"id":"D01","rating":3,"notes":"Example only: essential roles recovered; not a real evaluation result."}
{"id":"D02","rating":2,"notes":"Example only: possession/desire distinction partially recovered."}
```

The sample lines above are format documentation, **not observations**. No scored file ships with this repository. Only after independent ratings exist may you run:

```bash
python coverage_lab.py score --judgments your-blind-ratings.jsonl
```

Results explicitly report the number of rated and **unrated** cases; averages use rated cases only. Invalid or duplicated ratings are rejected.

## What the gaps currently reveal

- `D05`: "before sunset" requires temporal ordering/bounds.
- `S05`: "can disturb" requires possibility/modal qualification, not an unconditional event.
- `M06`: "for every ... there exists ..." requires bound variables and quantifier scopes.
- `C05`: `AND` is not "before"; conjunction cannot substitute for event ordering.
- `O05`: possibility and distinct beneficiary/harmed groups are not yet clearly bound.
- `E05`: predicting observations is not, on its own, proof that a model is true.

These are **specific targets for future operator experiments**, not a demand to implement a full programming language. We intentionally leave phonetics, custom glyphs, encryption, and mid-level function/character bundles out of v0.2.

## Next reproducibility conditions

Keep the original benchmark frozen when comparing iterations; put new samples in a **new versioned benchmark** and preserve old ratings with the exact evaluator identity and prompt. Report three metrics separately: (i) syntax/role validity, (ii) author-proposed structured share, and (iii) independent reconstruction scores. A language extension only counts as an empirical improvement if the third metric improves on a stable blind sample, rather than because more names or functions were introduced.
