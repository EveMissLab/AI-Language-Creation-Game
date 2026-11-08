# ALCG v0.10 — Transparent Compact Surface and Meaning-Retention Guards

**Status:** experimental, MIT licensed, Python 3.10+ (standard library).  
**Target:** open-source AI Language Creation Game, based on recognizable English concepts and symbols.  
**This is not:** encryption, a new natural-language dictionary, semantic theorem proving, an executable language, or the future mesoscopic functional-unit system.

## 1. Why this experiment exists

In v0.8, 16 public named patterns could reproduce 24 existing expressions exactly after expansion. However, the chosen named patterns totaled **1,457 characters** while their base expressions totaled **1,459**. They improved reuse but not surface brevity.

v0.10 tests a narrower question: **Can the author omit repeated role labels from familiar English-symbol compositions without losing the source's complete ALCG abstract syntax tree (AST)?** The public registry supplies the role labels and their order. The structural expansion must reproduce each archived reference expression after v0.5 canonicalization (argument order and bound-variable names are normalized).

**Example:**

```text
@MAY_ACT2[SERVER|FAIL]
```

expands to:

```text
MAY(claim=DO(actor=SERVER, action=FAIL))
```

The special prefix `@` and separators `[` `|` `]` are plain visible text. This is not a cipher. The shorthand is an **optional surface layer**; the native v0.1 ALCG parser is untouched.

## 2. Precise semantics of the abbreviation

The v0.8 registry contains entries like:

```json
{
  "name": "P_STATE",
  "slots": ["subject", "property"],
  "template": "IS(subject=HOLE(slot=subject), property=HOLE(slot=property))",
  "gloss": "..."
}
```

The surface text `@STATE[WATER|LIQUID]` expands by **fixed public slot order** to `P_STATE(subject=WATER, property=LIQUID)`, which in turn expands to `IS(subject=WATER, property=LIQUID)`. For all aliases, name `@FOO` maps to registry entry `P_FOO`.

The registry bytes are pinned at SHA-256:

```text
5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6
```

v0.10 refuses to run against silently changed v0.8 definitions, source cases, or benchmark examples. A future registry edit requires an explicit version update and new tests. **Reader access to this public registry is required for guaranteed slot interpretation.** Unaided AI inference has not been evaluated.

### Compact syntax

Informal EBNF (the implementation enforces recursion, input-size, slot-count and validity limits):

```ebnf
compact_expression = name | native_call | alias_call ;
alias_call         = "@", registered_pattern_suffix, "[", compact_expression,
                     { "|", compact_expression }, "]" ;
native_call        = name, "(", [ name, "=", compact_expression,
                     { ",", name, "=", compact_expression } ], ")" ;
name               = ASCII_identifier ;
```

`native_call` means an already supported ALCG call with named roles. Positional fields are accepted **only for registered `@` aliases**. Only expressions whose expanded form passes the existing v0.8/v0.4 validation are valid. No `RAW`, `PARTIAL`, quoted text or hidden `HOLE` is permitted in this compact experiment.

Nested example:

```text
@NOT[@ALL[X|PERSON|@STATE[REF(var=X)|READY]]]
```

is structurally equivalent to:

```text
NOT(claim=FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY)))
```

Do not confuse exact AST reconstruction with proof that the English interpretation is true, unambiguous, or correct in any physical world.

## 3. Experiment: frozen six-domain examples

The v0.6 source and v0.8 roundtrip cases are unchanged: four examples per domain, 24 in total. The new `benchmarks/compact-roundtrips-v0.10.jsonl` adds exactly one generated compact spelling for each archived example and keeps its source ID and note.

| Measured quantity | This 24-case public corpus |
|---|---:|
| Core expanded ALCG characters | 1,459 |
| v0.8 named-pattern characters | 1,457 |
| v0.10 compact characters | 853 |
| Saving over full expanded text | 606 characters |
| Exact canonical expanded AST roundtrips | 24 / 24 |
| New source sentences or operators | 0 |

These are ASCII message-character counts in a **selected, nonrandom, authored** dataset. This is not a measured improvement in independent AI comprehension, coding efficiency, token cost, storage compression or English semantic coverage.

### Dictionary overhead

The registry file is **4,684 bytes**. Transmitting it just once with these 24 compact examples costs **5,537 bytes (4,684 + 853)** versus **1,459 ASCII bytes** for their fully expanded expressions. On this identical corpus repeated with a shared cached registry, the shorthand savings of 606 bytes per batch need **8 complete repetitions** to exceed the one-time registry transfer cost. This ignores protocol headers, caching behavior, tokenizer costs and compression algorithms; it is a conditional accounting exercise, not a global efficiency claim.

## 4. Why unlabelled positions are risky

v0.10 has 10 deliberately authored adversarial probes:

- **4 invalid forms** (missing slot, extra slot, unregistered alias, free variable) must be rejected.
- **6 valid-but-different forms** (modality removal, time inversion, negation removal, quantifier change, role swap, attribution removal) must produce different canonical ASTs.
- **2 of the six** also have explicit **finite synthetic model** truth-value counterexamples (negation and universal/existential quantification).

**Important:** A swapped actor and object can still be a valid positional expression. The parser cannot divine the author's intended meaning. Version-pinned public slot order, optional structure digests and independent human/AI review are the available safeguards. Failure detection is not universal or a formal correctness proof.

## 5. SHA-256 structural digest

`structure_digest()` computes SHA-256 on the UTF-8 bytes of the expanded, v0.5-canonicalized ALCG expression. This fingerprints an **AST interpretation under this software version**, not natural-language meaning. The `decode` CLI can fail closed if the expected digest differs:

```bash
python compact_surface.py digest '@MAY_ACT2[SERVER|FAIL]'
python compact_surface.py decode '@MAY_ACT2[SERVER|FAIL]'
python compact_surface.py decode '@MAY_ACT2[SERVER|FAIL]' --expect-sha256 EXPECTED_DIGEST_HERE
```

The digest does not authenticate an untrusted original publisher. Trust still depends on obtaining the expected hash through an independent trusted channel. It also does not make role-swaps impossible; it can *detect changes relative to an already-known structure*.

## 6. Commands and reproducibility

```bash
python -m unittest discover -s tests -v
python compact_surface.py check
python compact_surface.py report
python compact_surface.py encode 'P_STATE(subject=WATER,property=LIQUID)'
python compact_surface.py decode '@STATE[WATER|LIQUID]'
python compact_surface.py export --out .local/v010-nonblind-examples.jsonl
```

The exported data include both compact expression and full expansion. **They are nonblind** and should not be handed to a reader during a comprehension evaluation. Previous v0.9 independent-reader results remain uncollected. No external APIs or private answers are needed to reproduce the checks. GitHub Actions executes them on three standard Python versions.

Source artifacts are UTF-8. The complete repository snapshot and source SHA-256 manifest are available in the versioned ZIP download.

## 7. 中文補充：這一輪究竟得到什麼？

這次並沒有創造新字元，也沒有提前設計中觀函數語言。研究對象只有一個：**把已有英文概念組合改寫成更簡短的公開符號表示，能否仍然逐字典規則還原到同一個結構？**

24 題的測試結果是「可以」，但這是**標準化 AST 還原**，不是「24 題英文意思已被 AI 理解」。

而且簡寫的弱點也明顯：只靠位置，順序交換就可能改變主詞、受詞、時間或作用域。因此，公開字典、固定版本、反例測試與可選擇的結構雜湊，都是實驗必要部分。少量資料還不一定比完整表達便宜，因為讀者還得先有字典。

這更像是在試玩「語言的表面壓縮與結構保真」；後續若要把組合升級成真正有計算作用的中觀單元，必須另行定義輸入輸出、函數效果、錯誤行為、作用域以及可驗證條件，不能直接把這套 `@` 簡寫當成已經完成的計算語言。
