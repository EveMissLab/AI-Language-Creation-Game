# ALCG v0.8 — Transparent Composition Pattern Laboratory

**Date:** 2026-11-08  
**Status:** Experimental / Open source / UTF-8 source-first  
**Repository:** https://github.com/EveMissLab/AI-Language-Creation-Game

## 1. Why pattern composition now?

After v0.7, the existing ALCG notation can express some useful relations, but many examples repeat `DO(actor=..., action=..., object=...)`, `MAY(claim=DO(...))`, and longer quantifier constructions. If users invent each abbreviation informally, two readers may interpret the same shortened expression differently.

v0.8 introduces **optional, publicly defined, lossless structural patterns**, written entirely with the existing English/ASCII ALCG syntax. The goal is reproducible composition, not a new writing system, pronunciation, encryption, executable function language, or completed mesoscopic character system. No new core relation operator is added.

A *pattern* is a recipe that expands into an ordinary, already recognized ALCG expression. It has an identifier starting `P_`, explicitly named slots and a fully visible expansion template. `HOLE(slot=...)` appears **only inside the published template**, never in an expanded statement.

## 2. Example of transparent reuse

```text
P_MAY_ACT2(actor=SERVER, action=FAIL)
```

Expands deterministically to:

```text
MAY(claim=DO(actor=SERVER, action=FAIL))
```

The syntax **still says possible failure**, not that a failure occurred. It also does not establish a probability, permission, or certainty. These meanings are inherited from the provisional v0.4 registry and must not be silently broadened.

Nested patterns are allowed:

```text
P_NOT(claim=P_ALL(var=X, domain=PERSON, claim=P_STATE(subject=REF(var=X), property=READY)))
```

Expands to:

```text
NOT(claim=FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))
```

The scope of `NOT` stays **outside** `FORALL`. `NOT(FORALL(...))` is not automatically exchanged with `FORALL(NOT(...))`.

## 3. Files

- `data/patterns-v0.8.json`: 16 public, named pattern recipes (and their intended readings).
- `pattern_lab.py`: deterministic validator, expander, report, and export CLI; Python 3.10+ standard library only.
- `benchmarks/pattern-roundtrips-v0.8.jsonl`: **24 curated** instances, four per domain, referencing unchanged v0.6 IDs.
- `reports/pattern-roundtrip-v0.8.json`: derived machine-readable results.
- `tests/test_pattern_lab.py`: roundtrip, malformed registry, cycle, unsafe placeholder and scope regression tests.

## 4. Run locally

```bash
python pattern_lab.py check
python pattern_lab.py report
python pattern_lab.py expand 'P_MAY_ACT2(actor=SERVER, action=FAIL)'
python pattern_lab.py export --out .local/pattern-expanded-v0.8.jsonl
python -m unittest discover -s tests -v
```

The export is **not a blinded AI-reader packet**. It contains both the patterned form and the original reference form for transparent inspection. It refuses to overwrite existing files. If a future AI-reader evaluation uses patterns, prepare a separate, genuinely blinded packet and do not expose the expansion or scoring key to its reader.

## 5. What the validator guarantees (and does not)

Validation establishes that:

1. Pattern names, slots and relation roles are explicit and internally consistent.
2. All nested patterns refer to known recipes; circular dependencies are rejected.
3. A caller cannot insert an unresolved `HOLE(...)` as an argument.
4. Quantifier binder names **must be supplied** through a public slot. Fixed hidden binder names and fixed hidden `REF` names are rejected. After expansion, unbound `REF` is rejected.
5. Expansion is limited by a node and depth budget, and final ALCG relations are checked using the unchanged v0.4 registry.
6. Every curated v0.8 case expands into the same **canonical syntax tree** as its frozen v0.6 reference, accounting for named role ordering and legal renaming of bound variables.

This does **not** establish that the original v0.6 English translation was semantically complete, that patterns apply safely to every imaginable context, or that a reader unfamiliar with the registry will infer every abbreviated expression correctly. In particular, `P_` names are **not automatically understandable** by a new AI; an unaided reader may require the published pattern glossary. A pattern expansion is a structural guarantee, not a theorem about natural-language truth.

## 6. Measurements and limits

The selected 24 public author-curated patterns span six domains and are drawn exclusively from the original **36 v0.6 structured candidates**. Source English sentences, raw fallbacks, and existing benchmark files remain untouched.

The counts are **24/24 canonical roundtrips on the selected examples**, *not* 24/24 English meaning coverage, accuracy on an independent model, or semantic inference. No fresh independent reader evaluation occurred. Pattern lengths may be longer or shorter; simple compression is deliberately not the principal target.

To avoid the appearance of an artificially rising score, `new_english_coverage_claims` and `new_relation_operators` are both recorded as zero. The existing 84 English cases from the earlier frozen corpora are unchanged.

## 7. Next experimental question

A useful future trial compares a reader given only `P_*` expressions to a reader given the same expressions **plus the explicit public expansion glossary**, then measures independently adjudicated reconstruction errors and abstentions. Until such readers produce real responses, there is no AI comprehension score to report.

---

## 繁體中文摘要

v0.8 不創造新字形，也不提前宣稱完成中觀字元。這輪先讓常見英文概念結構能用公開、可驗證的樣板重複組合；`P_` 標籤只是實驗性可讀別名，經工具展開後完全回到既有 ALCG 表達。16 個樣板在六領域選取的 24 條既有案例都通過結構回復測試，沒有修改原始英文題庫，也沒有增加新算子。對量詞變數、作用域、循環參照與未展開佔位符設置錯誤檢查。這證明的是有限樣本上的結構一致性，不等於獨立 AI 已經理解，也不等於自然語言語義全域等價。
