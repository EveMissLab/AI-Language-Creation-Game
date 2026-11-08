# ALCG v0.5 — Semantic Stability & Finite Counterexample Lab

**Date:** 2026-11-08  
**Project:** [AI Language Creation Game](https://github.com/EveMissLab/AI-Language-Creation-Game)  
**License:** MIT  
**Status:** reproducible, limited formal experiment; not an AI comprehension study, a theorem prover, or a complete language.

## 1. Why this version exists

Version 0.4 made temporal order, possibility and scoped quantifiers partially executable in a stipulated finite-world evaluator. Version 0.5 asks a narrower but foundational question:

> When an expression is rewritten without changing its intended roles or bindings, does the evaluator keep its meaning? And when a meaningful relationship or scope changes, can it show a counterexample?

This version **does not add a new ALCG primitive** or alter the v0.2 fixed-English 36-item benchmark. It tests the *stability of the representation system* so that future extensions are less likely to change meanings accidentally.

## 2. Two concrete defects found and addressed

### Event role-order dependence (regression)

The previous evaluator computed a structured `DO(...)` event descriptor by rendering its named roles in **input order**. Consequently, the following two descriptions were treated as different keys when compared with the `BEFORE` event table:

```text
DO(actor=PROGRAM, action=READ, object=FILE)
DO(object=FILE, action=READ, actor=PROGRAM)
```

Both give the same values for named roles `actor`, `action` and `object`. The v0.5 evaluator now constructs event keys in canonical role order (`actor`, `action`, `object`), making their values independent of input ordering. The fixed v0.4 finite-world file is **unchanged**.

### Free variable under an unexecuted branch

The v0.4 evaluator checked `REF(var=...)` only when evaluating a particular branch. Under `FORALL(var=X, domain=EMPTY, ...)`, the claim is never evaluated, so a stray `REF(var=Y)` could pass silently. Version 0.5 adds an **unconditional static scope check** before evaluation. Quantifier binding, including intentional shadowing, remains lexical.

This is a well-formedness rule, not a claim that all statements are meaningful or true.

## 3. Two independent diagnostic ideas

### Canonical structure (safe renaming and role permutation)

`normalize(...)` sorts *named* arguments of calls and renames bound variables consistently. For example:

```text
FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))
FORALL(claim=IS(property=READY, subject=REF(var=Z)), domain=PERSON, var=Z)
```

They receive the same structural normal form. Free concept constants (`ALICE`, `PERSON`, etc.) are **never renamed**. A normalization match establishes a limited structural identity; it is not a general proof that two arbitrary statements mean the same thing. The normalizer does not simplify `NOT(NOT(P))` or assume `MAY` means reality or probability.

### Finite model observations (possible counterexamples)

`compare(...)` evaluates two supported propositions against a **deterministic suite of 192 synthetic finite models**. Each is checked in two named worlds, giving up to **384 observations per pair**. Models vary across:

| Dimension | Choices |
| --- | --- |
| READY facts / disturbance | 4 explicitly chosen combinations of three named people, with complementary possible-world facts |
| Event ordering | forward, reverse, no `BEFORE` facts |
| Possible-world accessibility from `actual` | actual only, possible only, both, none |
| `PERSON` domain | empty, one person, two people, three people |
| Evaluation world | `actual`, `possible` |

Count: 4 × 3 × 4 × 4 = 192 models, times 2 evaluation worlds. This is **not exhaustive over all interpretations**. Each counterexample records a fixture ID, a world and the left/right stipulated truth values, so a discrepancy can be reproduced.

- `indistinguishable_in_suite`: both expressions agree at all 384 observations. **No universal equivalence claim.**
- `distinguishable`: at least one tested world yields a different truth value. **A concrete counterexample for this toy semantics**, not evidence about natural-language meanings or real-world facts.
- `canonical_structures_equal`: role order and consistently renamed bound variables reduce to the same representation; do not confuse this with all semantic equivalences.

For the full test corpus, all `same` pairs must survive every observation, while all `different` pairs must yield a counterexample. That is a deterministic *regression game*, not an independent AI reading outcome.

## 4. Key examples

**Role order is irrelevant:**

```text
BEFORE(earlier=DO(actor=PROGRAM, action=READ, object=FILE), later=DO(actor=PROGRAM, action=WRITE, object=OUTPUT))
BEFORE(later=DO(object=OUTPUT, actor=PROGRAM, action=WRITE), earlier=DO(object=FILE, action=READ, actor=PROGRAM))
```

**Scope can change truth:**

```text
NOT(claim=FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))
FORALL(var=X, domain=PERSON, claim=NOT(claim=IS(subject=REF(var=X), property=READY)))
```

The first means “not everyone is ready”; the second means “everyone is not ready”. When one person is ready and another is not, the first is true and the second false.

**Possible P and possible Q do not imply possible (P and Q):**

```text
MAY(claim=AND(left=IS(subject=ALICE, property=READY), right=IS(subject=BOB, property=READY)))
AND(left=MAY(claim=IS(subject=ALICE, property=READY)), right=MAY(claim=IS(subject=BOB, property=READY)))
```

These can differ when the two facts hold in different accessible worlds.

**Finite-domain warning:** Expanding `FORALL(var=X, domain=PERSON, ...)` into just two named people is unreliable when the domain is empty, one person or includes a third person. This is why the model suite varies domain sizes.

## 5. Reproduce (Python 3.10+, standard library)

```bash
# Validate the full 34-pair semantic regression corpus
python semantic_lab.py check

# Normalize structure (not a theorem prover)
python semantic_lab.py normalize --left 'FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))'

# Search toy finite worlds for a counterexample
python semantic_lab.py compare \
  --left 'MAY(claim=IS(subject=SYSTEM, property=DISTURBED))' \
  --right 'IS(subject=SYSTEM, property=DISTURBED)'

# Preserve all previous experiments
python finite_probe.py check
python coverage_bridge.py check
python reader_v04.py check
python -m unittest discover -s tests -v
```

`benchmarks/semantic-pairs-v0.5.jsonl` contains the explicit expectations and explanations. `reports/semantic-stability-v0.5.json` is generated from the public test source, and records the first counterexample per distinguishable pair. Neither includes independent model answers or private holdout data.

## 6. Results and boundary of interpretation

The frozen v0.5 author-built corpus contains **34 pairs**: 16 expected to agree across the suite, 18 expected to be distinguishable. The initial local run found matches for all 34 expectations. **This is an implementation and fixture consistency check only.**

Version 0.4's original **36 fixed English sentences, 28 authorial candidate representations and 20 toy-world probes remain unchanged**. The v0.3/v0.4 blind AI-reader protocol still has no independent reader responses. In particular, **34/34 is not an AI semantic comprehension score and cannot be used as evidence of general English coverage**.

## 7. 中文摘要

這次不是增加大量新字，也不是把 ALCG 改成以程式語言為目的的系統。v0.5 的用途是建立**可追查的語義一致性基準**：

- 同一個具名角色，交換書寫順序不得偷偷改變事件的意思。
- 同一個被綁定變數，安全改名後必須保持一致。
- `NOT`、`MAY`、`FORALL`、`EXISTS` 改變位置時，應能觀察到哪些差異真的存在。
- 找不到反例，只代表本次有限測試尚未區分；不能宣稱證明等價。
- 真正的跨 AI 直接理解，仍需要獨立 AI 在不取得答案時作答，再進行獨立評分。

長期方向仍是：**英文概念表徵 → 覆蓋率擴張 → 穩定組合 → 以實際函數組合作為後續中觀字元研究入口。**
