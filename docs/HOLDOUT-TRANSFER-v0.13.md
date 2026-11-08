# ALCG v0.13 — Nontraining Structural Transfer and Negative Controls

**Status:** deterministic structural transfer diagnostic; **not** a semantic-generalization study, an independent AI reader result, a new language operator, or an approved pattern registry revision.

## Question

The v0.12 miner inferred four non-active whole-expression AST templates from 64 author-curated candidate representations. Each candidate originally used two examples to derive its named argument roles and equalities. Can these structures be *reapplied* without alteration to new expressions, and can the same method detect harmful changes?

The critical distinction is:

1. **Shape compatibility:** does the AST match a candidate pattern, including shared named leaves and binder-reference equality?
2. **Lossless structural reconstruction:** does substituting the inferred slots and expanding the candidate yield exactly the original **canonical ALCG AST**?
3. **Faithfulness to the intended English meaning:** does the expression correspond to what the writer intended?

The first two are tested here. The third is **not proved** by them. A contrast `foil` can pass the first two while remaining the incorrect answer for the English target.

## Reproduce without network calls

```sh
python transfer_lab.py check
python transfer_lab.py report
python transfer_lab.py match 'CAUSE(source=DROUGHT, effect=CHANGE(subject=SOIL, property=MOISTURE))'
python -m unittest discover -s tests -v
```

`match` is a **read-only** local candidate-preview command. It prints the inferred slots, optional shorthand and reconstructed AST hash when a proposal matches; a mismatch prints `matched=false`. It never mutates the published dictionary or supplies semantic judgments.

`check` recreates the entire machine-readable report and compares it with the committed JSON. The test suite also verifies that the v0.8 active registry, v0.10 shorthand roundtrips, and v0.12 mined proposal artifacts remain unchanged. No optional AI service, GPU, external package or GitHub Action is required. GitHub CI runs the same checks on Python 3.10, 3.12 and 3.13.

## The data splits are intentionally NOT the same

| Source | Origin and role | What is valid to infer |
|---|---|---|
| v0.4/v0.6 author-curated coverage cases | 84 meanings, of which 64 fully structured candidate ASTs were inputs to the v0.12 miner | **Training / pattern induction**, not an independent evaluation |
| v0.3, v0.4, v0.7 contrast datasets | Written before the v0.12 miner; their `correct` and `foil` ALCG expressions were **not supplied** to its discovery function | A historical *nontraining* syntactic diagnostic after excluding exact canonical matches to the 64 training ASTs; not independently sampled English |
| v0.13 targeted transfer pairs | Authored **after seeing** the four candidate patterns: 16 positive/foil pairs across new contextual domains | Adversarial unit-test controls for matching, co-reference and role/scope changes; **not an unseen natural sample or independent AI trial** |

All historical input files are individually SHA-256 pinned. Training is re-derived from the exact frozen corpus inputs used by v0.12; duplicates are compared by **canonical AST**, not by raw text. The v0.13 posthoc positives and valid foils are checked against training expressions and against previous probes; an unbound reference is explicitly a rejected scope probe. The four v0.12 candidate definitions are loaded in memory for checks; none is written into `data/patterns-v0.8.json`.

## Historical, genuinely outside the miner's input list (but not independent authorship)

The historical contrast files contain **96** total expressions: 48 `correct` and 48 deliberately contrasting `foil` expressions. Of these, **39** are identical to one of the 64 source-corpus candidate ASTs and are excluded. The remaining **57** distinct nontraining ASTs contain **3** matches to the new candidate shapes, and all **three are foils**:

- `K403`, v0.4: removing `MAY` from a possible change leaves a structurally matchable `CAUSE → CHANGE`, but is not the intended *possible* claim.
- `K407`, v0.4: reversing two `DO` events still fits the `BEFORE → DO + DO` outline, but the English target fixes their temporal order.
- `V715`, v0.7: a different reversed event order likewise fits the shared-actor `BEFORE` candidate, although the choice was constructed to be wrong for the source meaning.

**3/57 is not a translation accuracy, a generalization success rate or a meaningful sample of all English.** It is the number of these particular historical nontraining ASTs that the four narrow syntactic candidate templates happen to match. The observation is useful precisely because it challenges any conflation of valid pattern expansion with correct intended meaning.

## Newly authored adversarial probes

There are four pairs for each of the four v0.12 proposals (16 pairs total). Each pair has one **positive** expression using new English concept identifiers, and one different **foil**. In the targeted probe set:

- **16/16 positives** fit their intended candidate, expand to identical canonical ASTs, and survive compact encode/decode roundtrips.
- **8/16 foils** change the operator, break co-reference/binding, or otherwise leave the inferred template and are rejected by the candidate matcher.
- **8/16 foils** deliberately preserve the template shape while changing temporal direction, argument roles or comparison relations. They **still match**; the author-provided English/contrast notes identify a different intended claim.

These scores are *diagnostic invariants designed into the probe construction*, **not statistical evidence** for wider comprehension. In particular, the matcher must **not** reject valid-but-different meanings simply because the human considers them the wrong answer to a different question. That semantic check belongs to a separately specified reader/evaluator.

### A concrete limitation

```text
BEFORE(earlier=DO(actor=DRONE, action=LOAD, object=PACKAGE),
       later=DO(actor=DRONE, action=DELIVER, object=PACKAGE))
```

and

```text
BEFORE(earlier=DO(actor=DRONE, action=DELIVER, object=PACKAGE),
       later=DO(actor=DRONE, action=LOAD, object=PACKAGE))
```

both match the same candidate AST outline. They are reversible and have the same shared `DRONE` actor — but they describe opposite sequences. The normalized AST hashes are different; neither is rewritten into the other. **Template recognition and correctness of a response to an English target are different tasks.**

Another case breaks `EXISTS(var=S, ...)` by using `REF(var=T)` without a binding for `T`. The matcher rejects it; the v0.5 scope guard separately diagnoses the unbound variable. This is a structural/scope error, not a semantic opinion.

## Conditional UTF-8 payload ledger

For four posthoc *positive* uses of each candidate, the bytes in the full canonical expression, optional compact expression, and the candidate's one-definition JSON cost are:

| Candidate | Full expression bytes (4 uses) | Compact bytes (4 uses) | Payload saved | One definition, estimated bytes | Net after definition |
|---|---:|---:|---:|---:|---:|
| `CAUSE → CHANGE` | 285 | 189 | 96 | 314 | -218 |
| `BEFORE → DO + DO` | 460 | 234 | 226 | 419 | -193 |
| `EXISTS → COMPARE, REF` | 368 | 216 | 152 | 376 | -224 |
| `NOT → COMPARE` | 230 | 174 | 56 | 300 | -244 |

These calculations use UTF-8 bytes of Python's ALCG renderer and positional shorthand; the definition estimate is the compact JSON serialization of the proposal's pattern definition. They do not include all possible version negotiation, transport, metadata, parser CPU, or distribution costs. At four uses each, none achieves net savings from publishing its definition once. That observation does **not** mean a pattern has no value for clarity, debugging, or substantially more future uses.

## Integrity and safety boundaries

- The original two mining source files and three historical contrast files are SHA-256 pinned. Modifying either group fails verification.
- The pre-v0.12 historical AST set is **not** fed back to the v0.12 miner. The v0.13 diagnostic measures matches with its *frozen* four proposals.
- A candidate matches by exact operator and named-role tree, not by surface token overlap or guessed English translations. Name leaves bound to the same `HOLE` slot must stay equal. Positional shorthand is expanded and checked against the original normalized AST.
- A matching shape does not supply a truth condition or a calibrated confidence in a statement's intended meaning. Real independent readers have **not** participated.
- The public 16-entry dictionary remains SHA-256 identical. **Zero new patterns are promoted automatically.** The v0.11 human review barrier remains in force.

## Future experiment boundary

The next scientifically meaningful step is to preregister a truly independent test set *before* pattern discovery, use new contributors/agents who cannot see the reference interpretations, and score **English-to-structure** and **structure-to-English** separately. Natural-language paraphrase fidelity, operator-argument accuracy and explicit abstention must be recorded, not inferred from parsing success. A valid structural reconstruction can be a prerequisite for trustworthy communication; it is not a substitute for communication evidence.

**Finding:** Reusability of a format can be demonstrated mechanically; correctness of its meaning requires a separate, independent referential test.
