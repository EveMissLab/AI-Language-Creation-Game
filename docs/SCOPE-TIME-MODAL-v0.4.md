# ALCG v0.4 — Scope, Time, and Modality (Experimental)

**Date:** 2026-11-08  
**Project:** AI Language Creation Game (ALCG)  
**License:** MIT  
**Status:** Tested experimental extension; not a complete AI-native language or a verified English meaning translator.

## Why these operators?

ALCG prioritizes the *breadth and faithfulness of meaning* that a minimal English-readable symbolic language can express. The fixed v0.2 benchmark exposed several important mismatches:

- `AND(A, B)` does **not** say that A occurred before B.
- `CAUSE(A, B)` states a causal relation; it does **not** say the event might occur.
- `FORALL` and `EXISTS` require explicit scope and bound variables; English nouns alone are not quantifiers.

Version 0.4 adds exactly five provisional operators to the v0.2 role registry, without changing the v0.1 text grammar or requiring pronunciation, original glyphs, encryption, or executable program semantics.

| Operator | Required roles | Provisional reading | Caution |
| --- | --- | --- | --- |
| `BEFORE` | `earlier`, `later` | The first event/boundary precedes the second. | Does not establish event occurrence or physical time by itself. |
| `MAY` | `claim` | Claim holds in at least one accessible possible world. | Not probability, permission, future tense, or actual truth. |
| `FORALL` | `var`, `domain`, `claim` | For every member of a domain, a claim holds. | Domain and scope must be explicit. |
| `EXISTS` | `var`, `domain`, `claim` | There is at least one member satisfying the claim. | Empty domain makes this false. |
| `REF` | `var` | Reference a variable bound by a surrounding quantifier. | An unbound variable is rejected by the finite probe. |

Identifiers such as `SUNSET`, `INTEGER`, or `CLAIM` are still English-readable *labels*, not a formally completed ontology.

## Examples

Temporal ordering:

```text
BEFORE(
  earlier=DO(actor=PROGRAM, action=READ, object=FILE),
  later=DO(actor=PROGRAM, action=WRITE, object=OUTPUT)
)
```

Possibility rather than actual occurrence:

```text
MAY(claim=CAUSE(source=MEASUREMENT, effect=CHANGE(subject=SYSTEM, property=STATE)))
```

Bound-variable quantification:

```text
FORALL(
  var=N,
  domain=INTEGER,
  claim=EXISTS(
    var=M,
    domain=INTEGER,
    claim=COMPARE(left=REF(var=M), right=REF(var=N), by=GREATER_THAN)
  )
)
```

The third expression is intended to mean that *every integer has some larger integer*. It is true in the ordinary mathematical integers, but **false** when `INTEGER` is interpreted as the finite set `{ZERO, ONE, TWO}` in the toy model. This is deliberate: parsing a logical structure is not a proof of its assertion, and an explicitly finite model is not the infinite integers.

## Versioned fixed-English coverage bridge

`benchmarks/coverage-v0.2.jsonl` is frozen. `benchmarks/coverage-v0.4.jsonl` retains the **same 36 IDs, domains, and English target sentences**; only four proposed symbolic expressions and their *authorial hypothesis labels* change:

| ID | Targeted missing distinction | Old proposal | New proposal |
| --- | --- | --- | --- |
| `D05` | Arrival before sunset | partial | candidate |
| `S05` | A measurement **may** disturb an observed system | partial | candidate |
| `M06` | Every integer has a greater integer | raw | candidate |
| `C05` | Read before write | partial | candidate |

The balance changes from **24 candidate / 6 partial / 6 raw** to **28 candidate / 3 partial / 5 raw**. This is an *unverified authorial encoding proposal*, not a 11.1-point increase in real English concept coverage and **not** a measured AI-reader comprehension score.

The bridge validator (`coverage_bridge.py`) checks that no original English meaning or case ID was altered, that only these four rows changed, and that the original registry still validates v0.2.

`S05` includes an `IS(subject=SYSTEM, property=OBSERVED)` context beside the `MAY(...)` clause. It is still an interpretive proposal: whether the best reading is epistemic, physical, dispositional, or measurement-contextual remains open for independent reader evaluation.

## A limited executable interpretation

`finite_probe.py` provides a small, deterministic **stipulated-world evaluator** for the subset:

- Propositions: `IS`, `COMPARE(EQUAL|GREATER_THAN)`, `NOT`, `AND`, `BEFORE`, `MAY`, `FORALL`, `EXISTS`.
- Terms: `Name`, `REF`, and `DO(...)` **only as an event descriptor in `BEFORE`**.
- The finite world model lists object domains, present property facts, explicitly ordered event descriptors, an integer rank map, and possible-world accessibility edges.
- `REF(var=X)` resolves to the innermost binder for `X`; unresolved references error instead of silently becoming constants. Shadowing is lexical.
- `MAY` is existential over the specified accessible worlds, which may or may not include the current world.
- Empty-domain `FORALL` is vacuously true; empty-domain `EXISTS` is false.
- Unknown operators or invalid roles **fail closed**. The evaluator does not run DO commands, guess unknown domain membership, convert RAW English, or prove real-world propositions.

The toy example has an `actual` world and a `possible` world, two people `ALICE` and `BOB`, and three named finite integers `ZERO`, `ONE`, and `TWO`. In `actual`, `ALICE` is READY and `BOB` is not; `SYSTEM` is not DISTURBED, but it is DISTURBED in an accessible possible world. Consequently:

| Distinction | Evaluation in `actual` |
| --- | --- |
| `MAY(claim=IS(subject=SYSTEM, property=DISTURBED))` | `true` |
| `IS(subject=SYSTEM, property=DISTURBED)` | `false` |
| `EXISTS(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))` | `true` |
| `FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))` | `false` |
| `FORALL(var=X, domain=PERSON, claim=EXISTS(var=Y, domain=PERSON, claim=COMPARE(left=REF(var=X), right=REF(var=Y), by=EQUAL)))` | `true` |
| `EXISTS(var=Y, domain=PERSON, claim=FORALL(var=X, domain=PERSON, claim=COMPARE(left=REF(var=X), right=REF(var=Y), by=EQUAL)))` | `false` |

These countermodels expose **structural differences**, not whether an independent model understands ALCG.

## Independent AI reading — v0.4 packet

This version adds 12 semantic contrasts specifically testing time, modality, and scope. `reader_v04.py` reuses the well-defined v0.3 reconstruction/scoring protocol with 28 candidate reconstructions and 12 contrast pairs. The v0.2 and v0.3 fixture files remain unchanged; so do their historical results.

```bash
python reader_v04.py check
python reader_v04.py prepare --out .local/reader-v0.4.jsonl --key .local/key-v0.4.json --seed 20261108
# Send only the reader packet to an external reader.
# After obtaining its independent UTF-8 JSONL response:
python reader_v04.py grade --packet .local/reader-v0.4.jsonl --key .local/key-v0.4.json --responses .local/answers-v0.4.jsonl
```

**Do not send the key, source English benchmark, original contrast file, or grading reference to the reader.** These benchmark sources are public, so an external model that browses the repository can leak itself the answers. Never claim the published packet is a cryptographically secure holdout. Contrast scores are forced-choice. Free-form reconstruction requires independent adjudication, and scores are `null` until responses and ratings actually exist.

## Reproduce locally (Python 3.10+, no dependencies)

```bash
python coverage_lab.py check --benchmark benchmarks/coverage-v0.4.jsonl --relations data/relations-v0.4.json
python coverage_lab.py audit --benchmark benchmarks/coverage-v0.4.jsonl --relations data/relations-v0.4.json
python coverage_bridge.py check
python finite_probe.py check
python finite_probe.py eval --expression 'MAY(claim=IS(subject=SYSTEM, property=DISTURBED))'
python reader_v04.py check
python -m unittest discover -s tests -v
```

A fixed coverage comparison and finite-world oracle are **research tools**, not independent semantic evidence. The next empirical step is to gather actual reader responses under protocol-recorded conditions, ideally with new unpublished holdout meanings and blinded adjudicators.

## 中文研究界線

v0.4 是讓「時間先後、可能性、量詞作用域」開始具備可解析、可對照的結構；中觀字元和函數封裝仍留在之後的研究階段。有限世界對照可驗證新算子不是隨意換名，卻不能驗證人類語意、無限數學真值或跨 AI 的理解一致性。**來源、表徵候選、有限模型真假、獨立 AI 解讀成果，必須始終分開記錄。**
