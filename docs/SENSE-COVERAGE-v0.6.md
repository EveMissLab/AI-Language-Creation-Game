# ALCG v0.6 — Concept Coverage Extension and English Polysemy

**Date:** 2026-11-08  
**Repository:** [EveMissLab/AI-Language-Creation-Game](https://github.com/EveMissLab/AI-Language-Creation-Game)  
**Status:** experimental, source-first, not a verified general language or independent AI comprehension result  
**License:** MIT

## 1. Goal and design decision

Version 0.6 returns to the original language-creation game's practical goal: **increase the variety of English meanings that can be proposed using a stable, AI-readable combination language**. Instead of adding more operators, this release reuses exactly the **v0.4 registry of 22 relation operators** and the unchanged parser.

A major problem with using familiar English as concept labels is **polysemy**: `BANK` may refer to a financial institution or a riverbank. A language can remain English-readable while choosing explicit labels for distinct senses. A label such as `BANK_RIVER` is *a disambiguation proposal*, not a discovered semantic primitive or a proof of machine understanding.

The **mesoscopic character / executable function-bundle** work remains deliberately out of scope. Pronunciation, cryptography, custom glyphs and code-execution semantics are also out of scope.

## 2. Data and scope

The following v0.4 source files are byte-for-byte frozen (SHA-256 pinned in `sense_coverage.py`):

- `benchmarks/coverage-v0.4.jsonl`: 36 existing English meanings.
- `data/relations-v0.4.json`: the unchanged relation signatures and role constraints.

New files:

- `benchmarks/coverage-v0.6.jsonl`: **48 additional, hand-authored English meanings**, eight in each of six domains.
- `data/concept-senses-v0.6.json`: 17 explicit concept sense IDs associated with 8 ambiguous English surface words.
- `sense_coverage.py`: benchmark validation, source freeze checks, statistics and two blinded-reader export modes.
- `tests/test_sense_coverage.py`: regression tests including leakage detection.
- `reports/sense-coverage-v0.6.json`: deterministic analysis of the authored benchmark. No fabricated reader responses.

For the 48 *new, curated* meanings, the author's proposed status labels are:

| Domain | Candidate structure | Partial with declared gap | RAW / unresolved | New cases |
| --- | ---: | ---: | ---: | ---: |
| Daily | 6 | 1 | 1 | 8 |
| Science | 6 | 1 | 1 | 8 |
| Mathematics | 6 | 1 | 1 | 8 |
| Computing | 6 | 1 | 1 | 8 |
| Society | 6 | 1 | 1 | 8 |
| Epistemic | 6 | 1 | 1 | 8 |
| **Total** | **36** | **6** | **6** | **48** |

Combined with v0.4's 36 frozen cases, there are now **84 distinct English prompts** across both benchmark files. The new-case **36/48 candidate share (75%)** is deliberately authored and selected; it is **not an estimate of natural-language coverage, conceptual completeness, or independent AI comprehension**. Comparing 36/48 to the old 28/36 is not a meaningful improvement claim because the denominators contain different prompts.

## 3. English-readable sense distinctions

| English spelling | Distinct ALCG labels |
| --- | --- |
| bank | `BANK_FINANCIAL`, `BANK_RIVER` |
| light | `LIGHT_ILLUMINATION`, `LIGHT_WEIGHT` |
| cell | `CELL_BIOLOGICAL`, `CELL_ELECTRIC` |
| mouse | `MOUSE_ANIMAL`, `MOUSE_DEVICE` |
| model | `MODEL_STATISTICAL`, `MODEL_PHYSICAL` |
| right | `RIGHT_ENTITLEMENT`, `RIGHT_DIRECTION` |
| charge | `CHARGE_ELECTRIC`, `CHARGE_FEE` |
| key | `KEY_KEYBOARD`, `KEY_CREDENTIAL`, `KEY_LOCK` |

For example:

```text
HAS(owner=BANK_FINANCIAL, item=MONEY)
DO(actor=BOAT, action=REACH, object=BANK_RIVER)
DO(actor=DEVICE, action=CHARGE_ELECTRIC, object=CELL_ELECTRIC)
DO(actor=STORE, action=CHARGE_FEE, object=FEE)
```

The benchmark validator rejects bare ambiguous labels such as `BANK` in the new cases, ensures every registered sense ID occurs in an actual expression, rejects reused English prompts from the frozen benchmark, and checks all calls against the **existing** relation signatures.

**Limits:** Explicitly appending `_FINANCIAL` or `_RIVER` does not independently ground the intended sense. New concept names that have no glossary entry remain only English-readable placeholders. The v0.6 lexicon is therefore **not** a complete ontology. Even a syntactically valid candidate may omit important properties of the corresponding English sentence.

## 4. Why two reader conditions?

The central question is whether an AI reads expressions **directly**, using the English-derived identifiers alone, or benefits from a published explanation. Two packet variants enable a *future* independent reader comparison:

1. **Unaided:** each task contains only its ID and ALCG expression.
2. **Glossary-assisted:** each task adds the explanatory glosses for sense IDs actually used in that expression, *not* the source English sentence.

Only **36 candidate cases** are exported as reader challenges. We discovered during local testing that `RAW(text="...")` inside the six raw and six partial expressions includes the original English meaning; treating these as blind reader tasks would leak the target. The exporter now **excludes RAW/partial cases**, and regression tests explicitly check for that leak.

These files are safe for *procedural* blind reading when the evaluator sees only the exported packet. However, this project is public and the original benchmark is in the same public repository: a reader with access to GitHub, a prior copy, or training contamination might still know the gold sentences. **Packet separation is not cryptographic secrecy.** For valid independent evidence, prohibit browsing/retrieval of the repository during the trial, record model ID, environment and prompt, and preferably use unpublished held-out prompts and external adjudication.

Do not let the same reader see both packet conditions in one context when estimating glossary benefits. Randomize or balance assignment and record it; otherwise cross-contamination invalidates the comparison.

## 5. Reproduction (Python 3.10+, standard library)

```bash
# Structural, label, freeze and polysemy checks.
python sense_coverage.py check

# Full JSON report; reader score intentionally null.
python sense_coverage.py report

# Two candidate-only packets. These are NOT scores or completed trials.
python sense_coverage.py blind --condition unaided --out .local/reader-v0.6-unaided.jsonl
python sense_coverage.py blind --condition glossary --out .local/reader-v0.6-glossary.jsonl

# An external evaluator MAY submit adjudicated ratings (0 to 3), see v0.2 rubric.
# Never run this with fabricated evidence; nothing is graded by default.
python sense_coverage.py score --condition unaided --judgments .local/independent-human-ratings.jsonl

# Existing validations remain mandatory.
python -m unittest discover -s tests -v
python coverage_bridge.py check
python semantic_lab.py check
```

The `score` command only consumes supplied external ratings (`id`, `rating`, `notes`) for the 36 reader candidates and reports how many are still unrated. Use the 0–3 external adjudication scale defined in `docs/COVERAGE-v0.2.md`; even a 3/3 score reflects that adjudicator's case-specific judgment. Because results are not observed yet, `reports/sense-coverage-v0.6.json` contains **`independent_ai_reader_score: null`**.

## 6. Interpretation and next challenge

- **Mechanically established:** all new expressions parse, registered operator roles are syntactically legal, the same 22 operator signatures are reused, no frozen English prompt is replaced, and polysemous unqualified labels in the new cases are rejected.
- **Only proposed by the authors:** the 36 structured cases capture their corresponding English meanings; 17 disambiguated labels refer to the intended concepts; adding English-readable symbol strings makes expressions easier for AI to understand.
- **Not established:** general English semantic coverage, theoretical concept completeness, cross-model comprehension, or that the sense glossary improves reconstruction accuracy.

The next meaningful measurement is a reader trial that keeps **semantic reconstruction accuracy**, **unresolved gaps** and **structural parsability** separate. If independent readers confuse two senses or fail on a nested qualifier, that should drive the *next* language rule rather than just increase the symbol count.

## 繁體中文摘要

ALCG v0.6 在不新增語法或關係算子的前提下，擴充了 48 條跨領域英文語義樣本，並嘗試用 17 個英文衍生標籤區分 8 組多義單字，例如金融機構／河岸、光／輕、電池單元／生物細胞。連同凍結的 v0.4 基準，現共有 84 條人工選定的英文語句。

本版保留 36 條候選結構、6 條部分表達、6 條未結構化，並建立「不給詞義提示」及「提供局部詞義註解」兩種 AI 盲讀輸出。由於原始英文可能藏在 `RAW` 中，盲讀輸出只包含 36 條候選結構；這是實際發現並修正的測試資訊洩漏問題。

所有覆蓋與詞義標記仍屬研究假說，不能將語法驗證、人工候選比例或自動化測試通過率當作 AI 理解成功率。中觀字元、函數封裝、發音、密碼與自創字形繼續留到後續階段。
