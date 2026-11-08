# AI Language Creation Game (ALCG)

**An open-source, AI-first language-creation playground.** Begin with English-readable concepts and symbols, then grow toward wider semantic coverage and eventually reusable mesoscopic concept/function bundles.

> Status: **v0.17 cross-model finite causal robustness (experimental)** — not a finished language, cipher, natural-language translator or semantic proof system.

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

# v0.9: generate reader packets for three controlled disclosure conditions
python pattern_transfer.py check
python pattern_transfer.py report
python pattern_transfer.py prepare --task reconstruct --condition unaided \
  --packet .local/v09-reader.json --key .local/v09-private-key.json \
  --response-template .local/v09-responses.json
# See docs/PATTERN-TRANSFER-v0.9.md for distinct readers, grading and contrasts.

# v0.10: optional compact positional surface, pinned to the public pattern registry
python compact_surface.py check
python compact_surface.py report
python compact_surface.py encode 'P_STATE(subject=WATER,property=LIQUID)'
python compact_surface.py decode '@STATE[WATER|LIQUID]'
python compact_surface.py digest '@MAY_ACT2[SERVER|FAIL]'
# See docs/COMPACT-SURFACE-v0.10.md for registry costs, loss checks and limitations.

# v0.11: assistant-authored proposal examples; deterministic review-only gate
python pattern_evolution.py check
python pattern_evolution.py verify-report
python pattern_evolution.py report
python pattern_evolution.py export-preview --out .local/staged-v0.11.json
# Feed external proposals with --proposals .local/your-proposals.jsonl; never auto-merges.

# v0.12: mine reusable AST motifs from the 84 frozen English cases
python pattern_discovery.py check
python pattern_discovery.py report
python pattern_discovery.py export-proposals --out .local/discovered-v0.12.jsonl
# Patterns remain proposals; no public dictionary is automatically changed.

# v0.13: nontraining shape transfer, time/role/quantifier counterexamples
python transfer_lab.py check
python transfer_lab.py report
python transfer_lab.py match 'CAUSE(source=DROUGHT, effect=CHANGE(subject=SOIL, property=MOISTURE))'
# Historical matches may be foils: this is NOT an AI comprehension score.

# v0.14: deterministic self-generated structural challenges and mutation tests
python challenge_generator.py check
python challenge_generator.py report
python challenge_generator.py generate --out ../alcg-v0.14-generated.jsonl
# Uses human-curated English label banks; NOT independent semantic comprehension.

# v0.15: pin v0.14 generated contrasts and search toy finite-world witnesses
python counterexample_lab.py check
python counterexample_lab.py report
python counterexample_lab.py replay --case G14_EXISTS_01 --variant operator_or_coreference_change
# Reports replayable truth-value differences, NOT independent AI comprehension.

# v0.16: distinguish observational association from toy structural interventions
python causal_lab.py check
python causal_lab.py report

# v0.17: invariant or divergent do-effects across alternative mechanisms
python family_fixtures_v017.py check
python causal_robustness.py check
python causal_robustness.py summary
python causal_robustness.py replay --family F17_CONTEXT --context-index 0
python causal_lab.py replay --case G14_CAUSE_01 --variant lexical_slot_change
# Uses eight explicitly authored Boolean SCMs, NOT measured real-world causality.
```

Minimal examples:

```text
IS(subject=WATER, property=LIQUID)
DO(actor=AI, action=CREATE, object=LANGUAGE)
WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))
RAW(text="A meaning not yet expressed with structured concepts.")
```

These examples demonstrate a **parser**, not verified meaning or truth. See [syntax sketch](docs/GRAMMAR-v0.1.md) and the [v0.2 coverage protocol](docs/COVERAGE-v0.2.md), and the [v0.3 reconstruction protocol](docs/RECONSTRUCTION-v0.3.md), the [v0.4 scope/time/modality experiments](docs/SCOPE-TIME-MODAL-v0.4.md), and the [v0.5 semantic stability laboratory](docs/SEMANTIC-STABILITY-v0.5.md), the [v0.6 coverage and polysemy protocol](docs/SENSE-COVERAGE-v0.6.md), and the [v0.7 reader-transfer protocol](docs/READER-TRANSFER-v0.7.md), the [v0.8 composition pattern experiment](docs/COMPOSITION-PATTERNS-v0.8.md), and the [v0.9 pattern-transfer protocol](docs/PATTERN-TRANSFER-v0.9.md), and the [v0.10 compact surface experiment](docs/COMPACT-SURFACE-v0.10.md), and the [v0.11 pattern proposal gate](docs/PATTERN-EVOLUTION-v0.11.md) and [v0.12 deterministic discovery lab](docs/AUTOMATIC-DISCOVERY-v0.12.md), plus the [v0.13 nontraining transfer diagnostic](docs/HOLDOUT-TRANSFER-v0.13.md) and the [v0.14 generated challenge protocol](docs/AUTOMATIC-CHALLENGE-GENERATOR-v0.14.md), [v0.15 bounded counterexamples](docs/BOUNDED-COUNTEREXAMPLES-v0.15.md), and [v0.16 finite intervention experiments](docs/FINITE-CAUSAL-INTERVENTIONS-v0.16.md), plus [v0.17 cross-model causal invariance](docs/CROSS-MODEL-CAUSAL-INVARIANCE-v0.17.md), for current limits.

## Roadmap, kept intentionally small

1. **Seed (now):** a readable, recursive text syntax, examples, and a local audit that makes gaps visible.
2. **Coverage experiments (v0.2):** 36 annotated cases across six domains; `candidate`, `partial` and `raw` remain explicitly distinct. Blind reconstruction packets can be exported, but **no independent AI comprehension scores exist yet**.
3. **Blind-reading laboratory (v0.3):** 24 opaque reconstruction tasks and 12 semantic contrast pairs, with separate packet/key and scorer. No independent reader results are claimed.
4. **Scope, time and modality (v0.4):** add five provisional operators (`BEFORE`, `MAY`, `FORALL`, `EXISTS`, `REF`), hold the English benchmark fixed, and verify 20 distinctions in a synthetic finite-world model. v0.4 has 28 *authorial* structured candidates, not independent AI comprehension scores.
5. **Semantic stability (v0.5):** fix named-argument event identity and free-variable checking; compare 34 author-built same/different pairs over 192 finite toy models and 2 worlds each. These are bounded test outcomes, **not independently measured AI comprehension**.
6. **English concept/sense coverage (v0.6):** add 48 separately curated English meanings (84 across frozen v0.4 and new v0.6 files), reusing existing operators, with 17 distinct sense labels for eight polysemous English spellings. The blind-reader exporter excludes RAW and partial cases to prevent source-answer leaks. **No independent reader scores exist yet.**
7. **Paired reader-transfer laboratory (v0.7):** prepare 36 reconstruction tasks and 24 source-preserving contrast pairs, balance A/B options, pair the unaided and glossary conditions, and measure a deliberately simple **non-AI lexical control** (8 selected correct, 16 abstained). No independent AI responses have been recorded; the two conditions remain ready for a real reader trial.
8. **Transparent composition patterns (v0.8):** 16 optional published `P_` patterns expand back into existing v0.4 operators, with 24 exact canonical roundtrips across the same six domains. No new English cases, core operators, or independent AI reader scores; the original benchmark stays frozen.
9. **Three-condition pattern transfer (v0.9):** freeze the 24 v0.8 cases and create six reader packet types (24 free-reconstruction items or 12 contrast probes × `unaided` / `glossary` / `expanded`). Separate paraphrase choices from free reconstruction, with packet hashes, independent rating inputs and a descriptive cross-reader comparator. **This version has no observed independent AI comprehension scores.**
10. **Transparent compact surface (v0.10):** add optional `@NAME[slot|...]` abbreviations using the published, SHA-pinned v0.8 pattern dictionary. The 24 frozen examples expand to identical canonical structures; 10 negative probes distinguish invalid vs valid-but-changed shortenings. The 4,684-byte registry overhead is reported separately, so shorter payloads are not mislabeled as total compression. No new operators or independent AI reading results.
11. **Pattern evolution gate (v0.11):** accept third-party AI pattern proposals as UTF-8 JSONL, verify template structure/slot binding and authored reference roundtrips, flag duplicates and defective examples. The shipped 14 **assistant-authored** proposals produce four review-only staged records, two requiring more examples, and eight rejections. No active registry is updated. No independent model-comprehension or truth claims.
12. **Automated proposal discovery (v0.12):** deterministically mine repeated full-expression AST shapes from 64 candidate representations across the frozen 84 English cases. Four machine-induced, structurally roundtripping motifs enter human review; one redundant active shape is filtered out. The original examples are also the evidence, **not held-out testing**; estimated incremental dictionary cost exceeds payload savings for every two-sample batch. No automatic promotion or claim of AI comprehension.
13. **Nontraining structural transfer (v0.13):** examine 96 contrast expressions authored in earlier versions, removing 39 exact overlaps with the v0.12 mining set. Of 57 remaining canonical ASTs, three match the mined templates — **all three are deliberately incorrect foil answers** to their English targets. Add 16 post-discovery diagnostic pairs: all 16 positive structures roundtrip, eight foils fail the pattern while eight still match but alter the intended claim. This is syntax-level evidence, **not AI understanding or independent semantic generalization**; the active registry stays frozen.
14. **Automatic metamorphic challenges (v0.14):** generate 32 new synthetic ASTs and 104 variants from human-curated English label banks and the 4 non-active v0.12 candidate motifs. Check argument-order and alpha-renaming invariants, changed lexical slots that still match, and role/operator violations that do not. This is **deterministic synthetic structural testing**, not independent natural-language generalization or AI comprehension; no dictionary change.
15. **Bounded semantic counterexamples (v0.15):** revisit 104 frozen v0.14 variants with an intentionally limited finite oracle; generate 46 replayable toy separating models, retain 40 canonical equivalences, and distinguish 2 no-witness results from 16 unsupported causal contrasts. Old artifacts remain pinned.
16. **Opt-in causal interventions (v0.16):** add eight deliberately authored finite Boolean structural causal models with explicit `do`-style interventions. Test 24 CAUSE-root contrasts: 8 canonical matches, 7 conditional intervention separations, 1 non-separation, and 8 effects outside the typed `CHANGE` subset. Compare observational association against intervention sensitivity. This is **not empirical causal inference or independently measured AI comprehension**; no published dictionary change.
17. **Cross-model causal invariance (v0.17):** compare one typed `CAUSE` claim across 7 assistant-authored families and 21 finite SCMs, including 84 aligned model/background evaluations and 168 interventions. Distinguish exact output invariance, shared qualitative direction, background-restricted direction, and disagreement; preserve all earlier model files, reports and published patterns. No independent reader or real-world causal inference is claimed.
18. **Next:** preregister independent semantic readers and fresh out-of-sample meanings, including cases where observational evidence and intervention results conflict.
19. **Mesoscopic units (later):** explore actually usable functional/conceptual compositions without prematurely calling an unexecuted symbolic label a program.

GitHub Actions runs the unit tests, sample syntax check, vocabulary audit, and the v0.2–v0.17 laboratory validators on pushes and pull requests, using standard runners. All checks also work locally without Actions or external APIs. Contributions should include an example meaning, an expression, and a note about ambiguities or failures; not just a shorter spelling.

## 中文簡介

這是 **AI 語言創造遊戲** 的第一個開源試作。優先使用英文概念與現有符號，逐步擴大可表達的語義範圍，並保留 AI 可直接閱讀、依公開規格解析的可能性。目前提供**最小可解析結構與六領域合計 84 條人工英文語義樣本（v0.4 的 36 題保持原樣，v0.6 另增 48 題）**，明確區分候選結構、部分表達與原文保留；已具備 v0.3 與 v0.4 盲讀與概念辨別測試流程，v0.4 新增時間、可能性與量詞作用域及有限模型對照；v0.5 修正具名事件參數順序與自由變數檢查，新增 34 組語義一致／區別測試與有限反例搜尋；v0.6 增加 8 組英文多義詞的 17 個明確概念標籤、兩種盲讀條件及防止 RAW 原文洩漏的檢查；v0.7 新增 24 組語義對照與 36 題還原實驗，可輸出分離的題包／答案及測試非 AI 英文詞彙重疊基準（24 題中選答並答對 8 題、16 題棄答），並且在 v0.8 增加 16 個公開組合樣板，對 24 條既有跨領域題目驗證展開後結構不變；v0.9 再將這些樣板整理為不提供說明、提供樣板定義、完全展開三種獨立閱讀條件，另備 24 題自由還原與 12 題概念辨別的分離題包、校驗及評分流程；這不是新的關係算子、英文語義覆蓋率或中觀字元。 v0.10 增加公開樣板字典支持的 `@` 位置式簡寫：24 條舊題庫展開後標準化結構全數一致，原式字元合計由 1,459 降至 853；同時加入 10 個參數遺失／語義漂移的風險題。這是字串簡寫，不是直接量到 AI 理解率，且讀者仍必須取得 4,684 bytes 的公開規則字典。尚未取得獨立 AI 的實際測試紀錄，不宣稱 AI 已能無歧義理解，不處理發音、加密或中觀字元。後續中觀單元會優先考察實際可用的概念／函數組合。

v0.11 接著提供 AI 組合提案的**待審核關卡**：14 筆助手撰寫的示範提案中，4 筆完成結構自洽檢查而進入人工審核、2 筆需要更多樣本、8 筆被拒絕。既有 16 個公開樣板及 v0.10 的 24 個固定簡寫不會被自動修改。測試通過不代表跨 AI 理解成功，也不代表函數已經可以執行。詳見 [v0.11 研究規格](docs/PATTERN-EVOLUTION-v0.11.md)。

v0.12 新增**程式化組合候選發現器**：它從舊版 84 條人工英文案例中擷取 64 條已標記為結構候選的表達，按照算子／關係樹的重複形態，自動提出 4 個待審核樣板（1 個與既有公開形態重複者不列入）。四個提案都通過既有結構審核，但都還沒有獨立的跨 AI 理解驗證；同時把字典成本計入後，兩筆示例的淨節省皆為負。**這是確定性程式挖掘，不是模型自主發明詞義；無自動發布。** 詳見 [v0.12 實驗規格](docs/AUTOMATIC-DISCOVERY-v0.12.md)。

v0.13 開始針對候選樣板做**訓練集外的結構泛化診斷**：先從舊版 96 條概念對照表達中，扣除 39 條與 v0.12 挖掘輸入完全一致的結構，剩下 57 條只有 3 條符合樣板，且**三條全部是原問題的錯誤對照選項**。另加入 16 組事後設計的跨領域壓力測試，正例全部無損還原，對照中 8 條被拒絕，8 條仍符合結構卻改變了想要表達的意思。這個結果提醒我們：**可還原、可重用與「理解原意」必須分開驗證**。四個樣板仍在待審核區，公開字典沒有變動。詳見 [v0.13 規格](docs/HOLDOUT-TRANSFER-v0.13.md)。

v0.14 新增**程式產生的語言挑戰與變形測試**：由人工挑選的英文概念標籤池及既有四個待審核樣板，確定性生成 32 條新結構與 104 條對照；其中 40 條為標準化結構等價變形，32 條在樣板仍可匹配時改變概念內容，另 32 條改變算子或共用角色而不再匹配。這是可重現的**結構測試**，不是 AI 獨立創造了新的自然語義，也不是英文覆蓋率或理解率。仍未修改 16 個公開樣板。參見 [v0.14 生成實驗規格](docs/AUTOMATIC-CHALLENGE-GENERATOR-v0.14.md)。


v0.16 新增**有限布林結構因果模型（SCM）介入試驗**，以八組明確撰寫的假設性模型，檢查原本 v0.15 無法處理的部分 `CAUSE` 表達。系統比較「觀察到的相關性」與「固定背景條件、強制指定原因變數之後的結果」，可以展示有相關但無介入影響，或沒有整體相關卻存在條件介入影響的情況。24 組比較分為：8 組參數換序等價、7 組在指定模型中可區分、1 組在指定模型中無法區分，以及 8 組不符合限定的因果表達型別。**這些是人工設定的有限模型，不是現實因果發現，更不是 AI 理解率。** 既有的語法、已發布字典及 v0.15 報告保持不變。參見 [v0.16 試驗規格](docs/FINITE-CAUSAL-INTERVENTIONS-v0.16.md)。


v0.17 新增**跨模型有限因果穩定性試驗**：同一個 `CAUSE` 表達分別交給 7 組人工宣告的模型家族（21 個有限模型），比對 84 個模型背景組合及 168 次 `do` 介入結果。系統區分「介入結果完全一致」、「只有方向一致」、「只有特定背景方向一致」與「跨模型作用方向不一致」，並保存每個模型的可重播結果與不一致反例。這不是自然世界的因果推斷，也不是獨立 AI 的理解成績；既有的 v0.16 因果報告和公開字典保持原樣。詳見 [v0.17 研究規格](docs/CROSS-MODEL-CAUSAL-INVARIANCE-v0.17.md)。

## License

MIT — see [LICENSE](LICENSE).
