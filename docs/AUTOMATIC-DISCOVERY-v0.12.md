# ALCG v0.12 — Deterministic Pattern Discovery Laboratory

**Status:** experimental, review-only. **Output:** UTF-8 proposal JSONL and a machine-recomputable report. **No new core operators, active dictionary entries, model calls, or independent reader scores.**

## Purpose and scope

The v0.11 gate can inspect a candidate pattern supplied by a contributor. v0.12 adds an intentionally **non-AI deterministic control** that *finds* candidate recipes in the existing annotated English-symbol corpus, derives their parameters from repeated structures, and passes them through the unmodified v0.11 structural gate. It does not translate English into ALCG or demonstrate that any AI understood the resulting proposal.

**Data provenance:** 36 frozen v0.4 English meanings and 48 additional v0.6 meanings (84 total). Exactly 64 are annotated `candidate` structured expressions; `partial` and `raw` cases are excluded. This is a small, hand-curated research corpus, not a natural or random sample of the English language. Both source files have SHA-256 pins. No new English meaning is added or marked as covered.

## Reproduce (Python 3.10+, standard library)

```sh
python pattern_discovery.py check
python pattern_discovery.py report
python pattern_discovery.py export-proposals --out .local/discovered-v0.12.jsonl
python pattern_evolution.py report --proposals .local/discovered-v0.12.jsonl
python -m unittest discover -s tests -v
```

The exporter uses **exclusive file creation**: it will not overwrite existing exports. The v0.8 registry, v0.10 compact fixtures and v0.11 proposal fixtures remain unchanged; the output is *not installed*. The JSONL is ordered deterministically. `check` independently regenerates proposals and the report and compares them to the checked-in files. GitHub Actions runs these steps on standard Python runners.

## Deterministic mining rules

1. Parse the existing structured source expressions into ASTs. Keep only fully structured candidate cases. `RAW`, `PARTIAL`, strings, and unmodeled English are not mined.
2. Group **whole expressions** by operator tree and **named argument roles**, ignoring leaf English identifiers for grouping. A group requires at least **two distinct expressions** and **two operator calls**; single-operator wrappers are not considered novel composition.
3. Align name-leaf positions by their argument paths, independent of source argument order. A shared parameter is inferred **only** if the two positions have the same identifier in *every* example in the group. Distinct actor/object or earlier/later roles are not merged on one accidental match.
4. Replace name leaves with explicit `HOLE(slot=...)` placeholders. The `P_DISC_...` name is based on the SHA-256 digest of the tree and inferred equality partition. This creates a candidate recipe, not a semantic primitive.
5. Compare the candidate's structural identity with the **active** 16-pattern registry and the **already staged** v0.11 candidates to avoid obvious duplicate claims. This is not an exhaustive check for semantic redundancy or logical equivalence.
6. Send the resulting proposals and their original annotated examples through `pattern_evolution.evaluate_one`. The gate validates syntax, explicit slot use, scopes, structural roundtrips and compact encoding. A successful output is `staged_for_human_review`, never `published` or `semantically_verified`.
7. Report structural support and a **transparent** byte ledger. Estimated registry overhead is the compact UTF-8 JSON serialization size of one new definition, not the cost of distributing the entire registry, indexing, version negotiation, or runtime. The break-even reuse estimate assumes the sample's average per-use savings repeat; it is a rough *conditional* estimate, not measured deployment performance.

### Why name equality matters

For the two existing computer examples involving `BEFORE`, the actor is `PROGRAM` on both sides of each expression, so one slot may be reused for that actor. The earlier object and later object **are not consistently identical** across both examples, so they must remain distinct slots. For existential comparison examples, the quantified variable and `REF(var=...)` stay aligned. These are directly testable **syntactic correlations**, not proof of intended meaning.

## Pinned results

| Scope | Observed |
|---|---:|
| Author-curated meanings in v0.4 + v0.6 | 84 |
| Fully structured candidate expressions | 64 |
| Root AST shape groups | 31 |
| Low-support groups (less than two examples) | 21 |
| Single-operator supported groups excluded | 5 |
| Already active structural identity groups excluded | 1 |
| Newly generated proposals | 4 |
| Pass v0.11 structural gate to *human review* | 4 |
| Promoted to live registry | 0 |
| Held-out AI / human reader measurements | 0 |

| Generated composition (illustrative label) | Source IDs | Domains | Sample bytes saved (excludes dictionary) | Estimated standalone definition bytes | Net on one sample batch |
|---|---|---|---:|---:|---:|
| CAUSE → CHANGE | `C04`, `S02` | computing, science | 48 | 314 | -266 |
| BEFORE → DO + DO | `C05`, `C105` | computing | 116 | 419 | -303 |
| EXISTS → COMPARE, REF | `M102`, `M104` | mathematics | 76 | 376 | -300 |
| NOT → COMPARE | `M03`, `M04` | mathematics | 28 | 300 | -272 |

The table uses **UTF-8 bytes**, not language tokens. A positive payload saving does **not** imply net compression after dictionary transfer. The program supplies conditional reuse estimates for each definition; none of the four is cost-effective for the two original sample uses once the estimated standalone definition is included.

## Evaluation boundaries

- The **same examples** determine the discovered patterns and supply their roundtrip checks. These are *in-sample*, not held-out generalization, and are not independent evidence of novel semantic understanding.
- Name co-occurrence and AST equality do not establish logical equivalence across possible worlds, correct English interpretation, truth, ontology membership, or executable function semantics.
- A `staged_for_human_review` decision validates structural conformance, **not** actual AI comprehension or correctness of a newly created concept.
- A structural fingerprint can fail to recognize more abstract redundancies (for example, logical equivalences not expressed as identical ASTs). More frequent does not necessarily mean more useful.
- A shared string in two examples may be accidental; proposed variable-sharing constraints must be reviewed on new data before publishing a language rule.
- The next meaningful evaluation needs genuinely unseen examples and independent reader responses. Do **not** use the pinned source items as a hidden test set for these four induced patterns.

## Output contracts

- `benchmarks/discovered-proposals-v0.12.jsonl`: machine-induced, **non-active** proposals compatible with the v0.11 gate; every example includes a historical source expression. These are public evidence, **not** a blind-reader question packet.
- `reports/pattern-discovery-v0.12.json`: reproducible discovery metrics, deduplication counts, per-pattern evidence, and incremental-definition cost estimates. `independent_ai_participants=0`, `heldout_transfer_results=null`.
- `pattern_discovery.py`: deterministic generator, gate adapter and CLI.
- `tests/test_pattern_discovery.py`: fixtures, role co-reference, scope binding, rejection of wrong expected output, corpus pinning, deterministic order, non-promotion and cost-accounting checks.

**Design rule:** *Detect a repeated form → propose a reversible structure → account for its costs → ask for independent semantic evidence.* The language evolves by explicit review, not by silently changing the meaning of previously published expressions.
