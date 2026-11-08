# ALCG v0.15 — Replayable Bounded Semantic Counterexamples

**Status:** deterministic, pair-directed finite interpretation and countermodel search. **NOT** a complete semantic theory, a truth engine for English, an independent AI comprehension experiment, or a causal discovery system.

## Research question

v0.14 generated 32 synthetic ALCG expressions and 104 controlled variants. A changed canonical abstract syntax tree does *not* entail a changed truth value in every interpretation. Can we find and publish small, executable **separating finite models** for some of those contrasts, while keeping unsupported cases explicitly unverified?

v0.15 keeps the frozen v0.14 challenge suite (SHA-256 `0d40a9effbf8c3f559269d5a300a6160e5ed3ef251b0bd2b2ad18651c60f8802`) and the official 16-pattern v0.8 dictionary unchanged. No promotion or alteration of v0.12 candidate patterns occurs.

## Executable interpretation (narrow on purpose)

We reuse `finite_probe.py` from v0.4, which interprets only specific operations in a **stipulated toy world**. v0.15 extends its already-existing ordinal comparison to support `LESS_THAN` alongside `GREATER_THAN` and `EQUAL`. This changes the finite evaluator, **not** the language's syntax or the published dictionary.

- `BEFORE`: a ground pair of named `DO` event descriptors appears in the world's before relation. Event descriptors are not executable functions, and no general causal or transitivity rule is asserted.
- `EXISTS` and `FORALL`: evaluate a `COMPARE` predicate over a small explicitly listed domain. `REF` is lexically bound to a domain member. `EQUAL` in this particular evaluator means **literal identifier equality**; it does *not* implement an arbitrary ontology of co-referent names.
- `NOT` and `MAY`: evaluate negation and possibility. For the constructed witnesses `MAY` can see the designated `actual` world. No probability or permission claim is implied.
- `LESS_THAN` and `GREATER_THAN`: evaluate strict inequalities over supplied integer ranks; those ranks are modeling choices, not measurements.
- `CAUSE` and `CHANGE`: may be syntactically well-formed, but **there is no causal truth oracle** in `finite_probe.py`. All 16 non-equivalent causal variants are marked unsupported. Eight argument-reordering controls involving `CAUSE` are *structurally* equivalent but have not been truth-evaluated.

The witness constructor sees both expressions. It deliberately selects small domains, event pairs, or ranks that might separate them; `finite_probe.evaluate` then independently recomputes the truth values under those constructed assumptions. This is not held-out prediction. A finite countermodel establishes a difference **in that stipulated interpretation**; failure to find one within this bounded strategy does not establish general equivalence.

## Reproducible results

| Category | v0.14 variants | Interpretation |
| --- | ---: | --- |
| Canonical structures equivalent | 40 | Normalization preserves order-independent roles and correctly bound alpha-renaming. 32 have additional finite spot checks; eight causal reorderings remain structural-only. |
| Finite counterexample found | 46 | A replayable model makes one expression true and its paired variant false (or vice versa). |
| No counterexample in this bounded search | 2 | `EQUAL` lexical substitutions with distinct literal names can produce the same truth result under all 27 checked rank assignments. This is **inconclusive**, not proof of equivalence. |
| Unsupported causal semantics | 16 | Contrasts using `CAUSE` receive no invented oracle. |
| **Total** | **104** | The categories are disjoint. |

The search evaluated **111** constructed models across the 48 supported non-equivalent pairs. This is the count of pair-directed candidate evaluations, not a statistical sample or a number of independent AI readers. The official English benchmark, original v0.14 challenges, and public pattern registry were not altered.

### Concrete countermodel

The following existing generated example has two structurally different readings:

```text
EXISTS(claim=COMPARE(by=EQUAL, left=REF(var=T), right=SAFETY_MARGIN), domain=MEASUREMENTS, var=T)
FORALL(claim=COMPARE(by=EQUAL, left=REF(var=T), right=SAFETY_MARGIN), domain=MEASUREMENTS, var=T)
```

Under the explicitly constructed domain `MEASUREMENTS = {SAFETY_MARGIN, V15_UNEQUAL}` with literal-identity equality, the first expression is **true** and the second **false**. The actual domain members are included in the machine-readable witness receipt; anyone can replay the same evaluation. No assertion is made about actual measurements or safety margins in the real world.

## Run the experiment (Python 3.10+, standard library only)

```bash
python challenge_generator.py check
python counterexample_lab.py check
python counterexample_lab.py report
python counterexample_lab.py replay --case G14_EXISTS_01 --variant operator_or_coreference_change
python -m unittest discover -s tests -v
```

`counterexample_lab.py check` recomputes the pinned v0.14 suite, regenerates and compares every finding against `reports/bounded-counterexamples-v0.15.json`, and **replays every reported finite counterexample** using only the serialized world stored with the result. The report is deterministic UTF-8 JSON. Its `ai_comprehension_score` and `real_world_semantic_accuracy` are `null` because no such outcomes were tested.

## Failure modes retained as first-class results

1. **Syntactic difference without a found semantic witness:** the two `NOT(COMPARE(...,by=EQUAL))` variants differ as structures but, under literal-name equality here, the relevant values remain unequal in every checked assignment.
2. **Structurally equivalent, not causally validated:** changing the order of named arguments in `CAUSE` preserves canonical text but does not justify a causal oracle.
3. **Pair-directed construction:** picking an informative witness from the pair itself makes the result a constructive diagnostic, not an unbiased generalization score.
4. **Interpretation incompleteness:** unknown operators and malformed model receipts fail closed; they are not silently treated as false.
5. **No external AI readers:** the language's actual readability by models, scientific correctness, and broader English concept coverage remain unmeasured by this version.

## 中文說明

v0.15 把「符號結構不同」進一步區分為「在指定有限世界中，能構造出真假不同的反例」、「在有限搜尋中還找不到反例」與「目前沒有可執行語義可判定」三類。104 條變形對照中有 46 條可重播反例、40 條標準化結構等價、2 條有限模型未分離、16 條因果語義未支援。有限世界是為了測試構造而人工指定，不是現實因果、客觀真值或獨立 AI 理解率。這輪不修改正式樣板字典，也不涉及加密、發音或中觀字元設計。
