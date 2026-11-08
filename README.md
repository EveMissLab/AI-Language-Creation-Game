# AI Language Creation Game (ALCG)

**An open-source, AI-first language-creation playground.** Begin with English-readable concepts and symbols, then grow toward wider semantic coverage and eventually reusable mesoscopic concept/function bundles.

> Status: **v0.8 transparent composition pattern laboratory (experimental)** — not a finished language, cipher, natural-language translator or semantic proof system.

## What is the game?

ALCG is an incremental experiment in **expressing meaning with readable, composable symbols**. The goal is to gradually cover more concepts while keeping structures inspectable by AI systems and humans. It is intended to become increasingly capable, not remain a toy.

We deliberately **do not** optimize for pronunciation, original writing systems, encryption, code execution, or maximal compression in this initial stage. Public GitHub research documents may eventually use a more mature form of this notation, but a reader should not need to reverse-engineer a secret code: rules and examples remain openly documented.

## Try it (Python 3.10+, standard library only)

```bash
python alcg.py check samples/seed.alcg
python alcg.py parse 'DO(actor=AI, action=CREATE, object=LANGUAGE)'
python alcg.py audit samples/seed.alcg
python -m unittest discover -s tests -v

# v0.2: annotated English-meaning coverage experiments
python coverage_lab.py check
python coverage_lab.py audit
python coverage_lab.py blind --out blind-v0.2.jsonl

# v0.3: AI reader reconstruction + semantic contrast probes
python reconstruction_lab.py check
python reconstruction_lab.py prepare --out .local/reader-v0.3.jsonl --key .local/key-v0.3.json
# After an independent AI responds: see docs/RECONSTRUCTION-v0.3.md for grade command.

# v0.4: scoped quantifiers, time ordering, and possibility
python coverage_lab.py check --benchmark benchmarks/coverage-v0.4.jsonl --relations data/relations-v0.4.json
python coverage_bridge.py report
python finite_probe.py check
python reader_v04.py check
# For a new independent reader packet: see docs/SCOPE-TIME-MODAL-v0.4.md

# v0.5: bounded semantic stability and counterexample search
python semantic_lab.py check
python semantic_lab.py normalize --left 'FORALL(var=X, domain=PERSON, claim=IS(subject=REF(var=X), property=READY))'
python semantic_lab.py compare --left 'MAY(claim=IS(subject=SYSTEM, property=DISTURBED))' --right 'IS(subject=SYSTEM, property=DISTURBED)'

# v0.6: more curated meanings without new operators; English polysemy
python sense_coverage.py check
python sense_coverage.py report
python sense_coverage.py blind --condition unaided --out .local/reader-v0.6-unaided.jsonl
python sense_coverage.py blind --condition glossary --out .local/reader-v0.6-glossary.jsonl

# v0.7: paired AI-reading protocol and transparent non-AI lexical baseline
python reader_trial.py check
python reader_trial.py baseline-report
python reader_trial.py prepare --condition unaided --packet .local/reader-v0.7.json --key .local/reader-v0.7-key.json
# See docs/READER-TRANSFER-v0.7.md for response schema and independent grading.

# v0.8: optional named English-symbol patterns; expand to existing ALCG
python pattern_lab.py check
python pattern_lab.py report
python pattern_lab.py expand 'P_MAY_ACT2(actor=SERVER, action=FAIL)'
python pattern_lab.py export --out .local/pattern-expanded-v0.8.jsonl
# Patterns are not new operators, AI understanding scores, or mesoscopic characters.
```

Minimal examples:

```text
IS(subject=WATER, property=LIQUID)
DO(actor=AI, action=CREATE, object=LANGUAGE)
WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))
RAW(text="A meaning not yet expressed with structured concepts.")
```

These examples demonstrate a **parser**, not verified meaning or truth. See [syntax sketch](docs/GRAMMAR-v0.1.md) and the [v0.2 coverage protocol](docs/COVERAGE-v0.2.md), and the [v0.3 reconstruction protocol](docs/RECONSTRUCTION-v0.3.md), the [v0.4 scope/time/modality experiments](docs/SCOPE-TIME-MODAL-v0.4.md), and the [v0.5 semantic stability laboratory](docs/SEMANTIC-STABILITY-v0.5.md), the [v0.6 coverage and polysemy protocol](docs/SENSE-COVERAGE-v0.6.md), and the [v0.7 reader-transfer protocol](docs/READER-TRANSFER-v0.7.md), and the [v0.8 composition pattern experiment](docs/COMPOSITION-PATTERNS-v0.8.md) for the current limits.

## Roadmap, kept intentionally small

1. **Seed (now):** a readable, recursive text syntax, examples, and a local audit that makes gaps visible.
2. **Coverage experiments (v0.2):** 36 annotated cases across six domains; `candidate`, `partial` and `raw` remain explicitly distinct. Blind reconstruction packets can be exported, but **no independent AI comprehension scores exist yet**.
3. **Blind-reading laboratory (v0.3):** 24 opaque reconstruction tasks and 12 semantic contrast pairs, with separate packet/key and scorer. No independent reader results are claimed.
4. **Scope, time and modality (v0.4):** add five provisional operators (`BEFORE`, `MAY`, `FORALL`, `EXISTS`, `REF`), hold the English benchmark fixed, and verify 20 distinctions in a synthetic finite-world model. v0.4 has 28 *authorial* structured candidates, not independent AI comprehension scores.
5. **Semantic stability (v0.5):** fix named-argument event identity and free-variable checking; compare 34 author-built same/different pairs over 192 finite toy models and 2 worlds each. These are bounded test outcomes, **not independently measured AI comprehension**.
6. **English concept/sense coverage (v0.6):** add 48 separately curated English meanings (84 across frozen v0.4 and new v0.6 files), reusing existing operators, with 17 distinct sense labels for eight polysemous English spellings. The blind-reader exporter excludes RAW and partial cases to prevent source-answer leaks. **No independent reader scores exist yet.**
7. **Paired reader-transfer laboratory (v0.7):** prepare 36 reconstruction tasks and 24 source-preserving contrast pairs, balance A/B options, pair the unaided and glossary conditions, and measure a deliberately simple **non-AI lexical control** (8 selected correct, 16 abstained). No independent AI responses have been recorded; the two conditions remain ready for a real reader trial.
8. **Transparent composition patterns (v0.8):** 16 optional published `P_` patterns expand back into existing v0.4 operators, with 24 exact canonical roundtrips across the same six domains. No new English cases, core operators, or independent AI reader scores; the original benchmark stays frozen.
9. **Next:** record actual independent reader responses, compare aided versus unaided interpretation of patterns, and modify language rules only when the evidence warrants it.
10. **Mesoscopic units (later):** explore functional composition and executable semantics as a separate future stage; v0.8 recipes are **not** this stage.

GitHub Actions runs the unit tests, sample syntax check, vocabulary audit, and the v0.2–v0.8 laboratory validators on pushes and pull requests, using standard runners. All checks also work locally without Actions or external APIs. Contributions should include an example meaning, an expression, and a note about ambiguities or failures; not just a shorter spelling.

## 中文簡介

這是 **AI 語言創造遊戲** 的第一個開源試作。優先使用英文概念與現有符號，逐步擴大可表達的語義範圍，並保留 AI 可直接閱讀、依公開規格解析的可能性。目前提供**最小可解析結構與六領域合計 84 條人工英文語義樣本（v0.4 的 36 題保持原樣，v0.6 另增 48 題）**，明確區分候選結構、部分表達與原文保留；已具備 v0.3 與 v0.4 盲讀與概念辨別測試流程，v0.4 新增時間、可能性與量詞作用域及有限模型對照；v0.5 修正具名事件參數順序與自由變數檢查，新增 34 組語義一致／區別測試與有限反例搜尋；v0.6 增加 8 組英文多義詞的 17 個明確概念標籤、兩種盲讀條件及防止 RAW 原文洩漏的檢查；v0.7 新增 24 組語義對照與 36 題還原實驗，可輸出分離的題包／答案及測試非 AI 英文詞彙重疊基準（24 題中選答並答對 8 題、16 題棄答），並且在 v0.8 增加 16 個公開組合樣板，對 24 條既有跨領域題目驗證展開後結構不變；這不是新的關係算子、英文語義覆蓋率或中觀字元。尚未取得獨立 AI 的實際測試紀錄，不宣稱 AI 已能無歧義理解，不處理發音、加密或中觀字元。後續中觀單元會優先考察實際可用的概念／函數組合。

## License

MIT — see [LICENSE](LICENSE).
