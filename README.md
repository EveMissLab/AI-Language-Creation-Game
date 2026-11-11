# AI Language Creation Game (ALCG)

**An open-source, AI-first language-creation playground.** Begin with English-readable concepts and symbols, then grow toward wider semantic coverage and eventually reusable mesoscopic concept/function bundles.

> Status: **v0.28 verified-once, in-process decision-state cache (experimental implementation)** — not a finished language, cipher, natural-language translator or semantic proof system.

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

# v0.18: exhaust 16 observation-equivalent synthetic mechanisms per family
python mechanism_search.py check
python mechanism_search.py summary

# v0.19: choose interventions to distinguish still-compatible mechanisms
python active_design.py check
python active_design.py summary

# v0.20: Bayesian noisy readings and cost-aware finite experiment selection
python noisy_design.py check
python noisy_design.py report
python noisy_design.py plan --family F17_DIRECT --budget 2
python noisy_design.py plan --family F17_DIRECT --budget 1 --observe 3=1 --observe 3=0
python noisy_design.py replay --family F17_DIRECT --mask 5 --action 3 --flip
python active_design.py recommend --family F17_DIRECT --objective identify
python active_design.py simulate --family F17_DIRECT --mask 9 --objective anchor
# The oracle is a bounded synthetic SCM, NOT a real intervention or AI comprehension score.
```

Minimal examples:

```text
IS(subject=WATER, property=LIQUID)
DO(actor=AI, action=CREATE, object=LANGUAGE)
WANT(agent=PERSON, goal=DO(actor=AI, action=HELP, object=PERSON))
RAW(text="A meaning not yet expressed with structured concepts.")
```

These examples demonstrate a **parser**, not verified meaning or truth. See [syntax sketch](docs/GRAMMAR-v0.1.md) and the [v0.2 coverage protocol](docs/COVERAGE-v0.2.md), and the [v0.3 reconstruction protocol](docs/RECONSTRUCTION-v0.3.md), the [v0.4 scope/time/modality experiments](docs/SCOPE-TIME-MODAL-v0.4.md), and the [v0.5 semantic stability laboratory](docs/SEMANTIC-STABILITY-v0.5.md), the [v0.6 coverage and polysemy protocol](docs/SENSE-COVERAGE-v0.6.md), and the [v0.7 reader-transfer protocol](docs/READER-TRANSFER-v0.7.md), the [v0.8 composition pattern experiment](docs/COMPOSITION-PATTERNS-v0.8.md), and the [v0.9 pattern-transfer protocol](docs/PATTERN-TRANSFER-v0.9.md), and the [v0.10 compact surface experiment](docs/COMPACT-SURFACE-v0.10.md), and the [v0.11 pattern proposal gate](docs/PATTERN-EVOLUTION-v0.11.md) and [v0.12 deterministic discovery lab](docs/AUTOMATIC-DISCOVERY-v0.12.md), plus the [v0.13 nontraining transfer diagnostic](docs/HOLDOUT-TRANSFER-v0.13.md) and the [v0.14 generated challenge protocol](docs/AUTOMATIC-CHALLENGE-GENERATOR-v0.14.md), [v0.15 bounded counterexamples](docs/BOUNDED-COUNTEREXAMPLES-v0.15.md), and [v0.16 finite intervention experiments](docs/FINITE-CAUSAL-INTERVENTIONS-v0.16.md), plus [v0.17 cross-model causal invariance](docs/CROSS-MODEL-CAUSAL-INVARIANCE-v0.17.md), for current limits.

```bash
# v0.21: asymmetric observations, persistent session fault, stopping under risk
python correlated_design.py check
python correlated_design.py summary
python correlated_design.py plan --family F17_DIRECT --budget 2 --loss 64
python correlated_design.py plan --family F17_DIRECT --budget 2 --loss 64 --observe 3=1 --observe 2=0
# Causal mechanisms and sensor parameters are synthetic, not empirical data.
```

```bash
# v0.22: experimental English-readable decision snapshots, no registry update
python trace_language.py check
python trace_language.py report
python trace_language.py build --family F17_DIRECT --budget 2 --loss 64 --observe 3=1 --observe 3=0
# Each snapshot is one typed, replayable ALCG expression with an order-sensitive history receipt.
# See docs/REPLAYABLE-DECISION-TRACES-v0.22.md for exact schema and limitations.
```

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
18. **Bounded mechanism search (v0.18):** exhaustively enumerate 16 synthetic observationally anchor-equivalent Boolean completions per v0.17 family (112 candidate SCMs total). All match the designated first model at four natural backgrounds, but new candidates weaken the previously true finite-family stability claim in all five applicable families. The other two families already lacked a nonzero common direction. This is bounded *model-family sensitivity*, not a falsification of earlier calculations, not all causal models and not empirical inference. [Detailed scope and replayable witnesses](docs/OBSERVATION-EQUIVALENT-MECHANISM-SEARCH-v0.18.md).
19. **Active intervention design (v0.19):** use the 16 v0.18 observation-equivalent completions per family as a fixed, noiseless hypothesis class. Four informative off-natural interventions are necessary and sufficient for exact identification; a weaker anchor-agreement test can stop at the first mismatch (uniform-prior mean 1.875, worst 4). Supports partial-information recommendations under restricted access, and 896 independent SCM response replays. **No real experiments, independent AI-reader data or dictionary update.** [Full specification](docs/ACTIVE-INTERVENTION-DESIGN-v0.19.md).
20. **Noisy, cost-aware active experiments (v0.20):** keep the v0.19 exact finite benchmark fixed and instead assume independent symmetric binary measurement errors and unequal intervention costs. Repeated readings update a rational Bayesian posterior rather than deleting candidates. Compare greedy information gain per cost with exact budget-limited MAP mechanism classification; the objectives can select different next interventions. These are hypothetical synthetic channel/cost parameters, **not measured sensor error, real-world causal discovery or AI comprehension**. [Specification](docs/NOISY-COST-AWARE-ACTIVE-DESIGN-v0.20.md).
21. **Asymmetric and session-correlated sensors (v0.21):** retain the v0.19/v0.20 frozen finite cases, but now use distinct false-positive / false-negative probabilities plus a persistent shared session fault. Maintain an exact joint posterior over 16 masks and two fault states, compare against an independent-per-reading control, and solve a finite four-unit-cost STOP/CONTINUE policy based on assumed misclassification loss. This is synthetic decision analysis, **not** measured sensor performance, AI comprehension or a new published language operator. [Specification](docs/ASYMMETRIC-CORRELATED-STOPPING-v0.21.md).
22. **Replayable experimental decision traces (v0.22):** reuse the published ALCG grammar to encode eight bounded synthetic decision snapshots in `TRACE_V022` with named `SCENARIO`, ordered `OBSERVATIONS`, exact `POLICY`, and independently checkable `RECEIPT`. The serializer/decoder rejects altered action histories, out-of-range inputs, changed policy decisions and stale model fingerprints. These are **profile-specific executable expressions**, not new public core language operators, encryption, independent AI semantic understanding, or real-world sensor evidence. [Specification](docs/REPLAYABLE-DECISION-TRACES-v0.22.md).
23. **Linked multi-round decision sessions (v0.23):** chain full v0.22 snapshots as `RUN_V023`, replaying each previous STOP/CONTINUE selection, cost debit, ordered synthetic reading, updated exact posterior and policy decision. Each round binds its predecessor and successor to a domain-separated SHA-256 content link; unlike v0.22, the record can verify *which prior policy led to each later action*. Five synthetic sessions record eight rounds: four end with actual STOP decisions; one is explicitly an unfinished OPEN prefix. These are not real measurements, tamper-proof signatures, independent AI understanding results, or general-purpose program semantics. Old grammar, data and public dictionary stay frozen. [Specification](docs/LINKED-DECISION-SESSIONS-v0.23.md).
24. **Reversible incremental session transport (v0.24):** encode the same five frozen v0.23 sessions as `DELTA_RUN_V024`, retaining initial model/budget/loss, action/reading pairs, inherited per-round v0.23 chain hashes and final receipts, but omitting recomputable full `TRACE_V022` snapshots. The 13,940 UTF-8 bytes of full expressions become 4,962 bytes of delta expressions (64.405% smaller on this fixed corpus), and expanding each delta yields byte-identical `RUN_V023` text. Supports policy-following append to an explicitly `OPEN` prefix, not after `STOP`. **Decoder requires frozen public rules; no real sensor evidence, independent AI comprehension, authenticated provenance or new published language operator.** [Full specification](docs/INCREMENTAL-DECISION-SESSIONS-v0.24.md).
25. **Selective, constraint-aware derived receipts (v0.25):** start from v0.24 and enumerate the bounded choices to retain or derive each round's policy action and intermediate chain receipt. Every Boolean observation, initial model pin and final state/chain receipt remains mandatory. In five frozen synthetic sessions, `lean` is **4,396 UTF-8 bytes** versus **4,962** for v0.24, while `review` is **4,582** and `audit` **4,956**. The **zero-round case gets larger** (828 versus 754 bytes), and CPU/replay cost has **not** been measured. All three profiles reproduce byte-identical v0.23 source, preserve `OPEN`/`STOP`, and do not update the published language dictionary. [Full scope and negative results](docs/SELECTIVE-DERIVATION-v0.25.md).
26. **Bounded checkpoint/delta storage planning (v0.26):** enumerate v0.25 selective deltas, every subset of full materialized v0.22 state checkpoints, and complete v0.23 histories. Choose using actual UTF-8 byte size plus **hypothetical** state-read frequencies, abstract reconstruction steps and materialization work, optionally enforcing storage and per-request work limits. Five frozen synthetic sessions yield different choices: cold archive selects pure deltas, frequent final-state reads usually favor an extra checkpoint, and one zero-round case favors the complete original. Every representation is verified against byte-identical v0.23 replay; the decoder still fully validates history and **no real CPU-time or AI understanding gains are claimed**. [Specification](docs/CHECKPOINT-REPLAY-PLANNING-v0.26.md).
27. **Measured fully verified replay (v0.27):** measure actual warm-process `checkpoint_planner.access_state` times for the same v0.23 session in v0.25 selective, v0.26 final-checkpoint and v0.23 full representations. Compare per-state medians and actual UTF-8 bytes under explicitly declared read frequencies and a synthetic storage weight; keep v0.26's abstract replay-work model separate. The committed illustrative run (one warm-up, three measured blocks) selects selective rather than the abstract planner's hybrid, but small samples cannot establish a portable performance ranking. The reader **still fully validates every access**, so this is not a lazy-checkpoint speedup. [Experiment and limitations](docs/MEASURED-REPLAY-v0.27.md).
28. **Non-implemented challenge:** collect independent reader data without conflating it with synthetic mechanism experiments.
29. **Mesoscopic units (later):** explore actually usable functional/conceptual compositions without prematurely calling an unexecuted symbolic label a program.

GitHub Actions runs the unit tests, sample syntax check, vocabulary audit, and the v0.2–v0.27 laboratory validators on pushes and pull requests, using standard runners. All checks also work locally without Actions or external APIs. Contributions should include an example meaning, an expression, and a note about ambiguities or failures; not just a shorter spelling.

## 中文簡介

這是 **AI 語言創造遊戲** 的第一個開源試作。優先使用英文概念與現有符號，逐步擴大可表達的語義範圍，並保留 AI 可直接閱讀、依公開規格解析的可能性。目前提供**最小可解析結構與六領域合計 84 條人工英文語義樣本（v0.4 的 36 題保持原樣，v0.6 另增 48 題）**，明確區分候選結構、部分表達與原文保留；已具備 v0.3 與 v0.4 盲讀與概念辨別測試流程，v0.4 新增時間、可能性與量詞作用域及有限模型對照；v0.5 修正具名事件參數順序與自由變數檢查，新增 34 組語義一致／區別測試與有限反例搜尋；v0.6 增加 8 組英文多義詞的 17 個明確概念標籤、兩種盲讀條件及防止 RAW 原文洩漏的檢查；v0.7 新增 24 組語義對照與 36 題還原實驗，可輸出分離的題包／答案及測試非 AI 英文詞彙重疊基準（24 題中選答並答對 8 題、16 題棄答），並且在 v0.8 增加 16 個公開組合樣板，對 24 條既有跨領域題目驗證展開後結構不變；v0.9 再將這些樣板整理為不提供說明、提供樣板定義、完全展開三種獨立閱讀條件，另備 24 題自由還原與 12 題概念辨別的分離題包、校驗及評分流程；這不是新的關係算子、英文語義覆蓋率或中觀字元。 v0.10 增加公開樣板字典支持的 `@` 位置式簡寫：24 條舊題庫展開後標準化結構全數一致，原式字元合計由 1,459 降至 853；同時加入 10 個參數遺失／語義漂移的風險題。這是字串簡寫，不是直接量到 AI 理解率，且讀者仍必須取得 4,684 bytes 的公開規則字典。尚未取得獨立 AI 的實際測試紀錄，不宣稱 AI 已能無歧義理解，不處理發音、加密或中觀字元。後續中觀單元會優先考察實際可用的概念／函數組合。

v0.11 接著提供 AI 組合提案的**待審核關卡**：14 筆助手撰寫的示範提案中，4 筆完成結構自洽檢查而進入人工審核、2 筆需要更多樣本、8 筆被拒絕。既有 16 個公開樣板及 v0.10 的 24 個固定簡寫不會被自動修改。測試通過不代表跨 AI 理解成功，也不代表函數已經可以執行。詳見 [v0.11 研究規格](docs/PATTERN-EVOLUTION-v0.11.md)。

v0.12 新增**程式化組合候選發現器**：它從舊版 84 條人工英文案例中擷取 64 條已標記為結構候選的表達，按照算子／關係樹的重複形態，自動提出 4 個待審核樣板（1 個與既有公開形態重複者不列入）。四個提案都通過既有結構審核，但都還沒有獨立的跨 AI 理解驗證；同時把字典成本計入後，兩筆示例的淨節省皆為負。**這是確定性程式挖掘，不是模型自主發明詞義；無自動發布。** 詳見 [v0.12 實驗規格](docs/AUTOMATIC-DISCOVERY-v0.12.md)。

v0.13 開始針對候選樣板做**訓練集外的結構泛化診斷**：先從舊版 96 條概念對照表達中，扣除 39 條與 v0.12 挖掘輸入完全一致的結構，剩下 57 條只有 3 條符合樣板，且**三條全部是原問題的錯誤對照選項**。另加入 16 組事後設計的跨領域壓力測試，正例全部無損還原，對照中 8 條被拒絕，8 條仍符合結構卻改變了想要表達的意思。這個結果提醒我們：**可還原、可重用與「理解原意」必須分開驗證**。四個樣板仍在待審核區，公開字典沒有變動。詳見 [v0.13 規格](docs/HOLDOUT-TRANSFER-v0.13.md)。

v0.14 新增**程式產生的語言挑戰與變形測試**：由人工挑選的英文概念標籤池及既有四個待審核樣板，確定性生成 32 條新結構與 104 條對照；其中 40 條為標準化結構等價變形，32 條在樣板仍可匹配時改變概念內容，另 32 條改變算子或共用角色而不再匹配。這是可重現的**結構測試**，不是 AI 獨立創造了新的自然語義，也不是英文覆蓋率或理解率。仍未修改 16 個公開樣板。參見 [v0.14 生成實驗規格](docs/AUTOMATIC-CHALLENGE-GENERATOR-v0.14.md)。


v0.16 新增**有限布林結構因果模型（SCM）介入試驗**，以八組明確撰寫的假設性模型，檢查原本 v0.15 無法處理的部分 `CAUSE` 表達。系統比較「觀察到的相關性」與「固定背景條件、強制指定原因變數之後的結果」，可以展示有相關但無介入影響，或沒有整體相關卻存在條件介入影響的情況。24 組比較分為：8 組參數換序等價、7 組在指定模型中可區分、1 組在指定模型中無法區分，以及 8 組不符合限定的因果表達型別。**這些是人工設定的有限模型，不是現實因果發現，更不是 AI 理解率。** 既有的語法、已發布字典及 v0.15 報告保持不變。參見 [v0.16 試驗規格](docs/FINITE-CAUSAL-INTERVENTIONS-v0.16.md)。


v0.17 新增**跨模型有限因果穩定性試驗**：同一個 `CAUSE` 表達分別交給 7 組人工宣告的模型家族（21 個有限模型），比對 84 個模型背景組合及 168 次 `do` 介入結果。系統區分「介入結果完全一致」、「只有方向一致」、「只有特定背景方向一致」與「跨模型作用方向不一致」，並保存每個模型的可重播結果與不一致反例。這不是自然世界的因果推斷，也不是獨立 AI 的理解成績；既有的 v0.16 因果報告和公開字典保持原樣。詳見 [v0.17 研究規格](docs/CROSS-MODEL-CAUSAL-INVARIANCE-v0.17.md)。

v0.18 加入**觀察等價的有限機制探索**：在既有 7 組 v0.17 家族上，以每組第一個模型為觀察錨點，枚舉 16 種不改變自然觀察輸出、但可能改變 `do(SIGNAL)` 結果的有限布林機制（共 112 個新模型）。五組原本具非空穩定性結論的家族都找到加入新模型後不再維持原結論的反例；兩組本來就沒有共同非零方向，不能被虛報成「再度推翻」。這不修改既有 v0.17 計算結論，而是測量**擴張假設模型家族時的敏感性**，也不是現實因果發現或獨立 AI 理解測試。詳見 [v0.18 研究規格](docs/OBSERVATION-EQUIVALENT-MECHANISM-SEARCH-v0.18.md)。

v0.19 新增**主動有限介入辨識**：在 v0.18 已知的七組家族、每組 16 個觀察等價機制中，系統能按照條件選擇下一個可分辨機制的 `do(SIGNAL)` 測試，並將結果回饋至剩餘候選清單。四個有效介入是完整辨識的必要且充分條件；若只是判斷是否與錨點相同，均勻候選假設下平均 1.875 次，最壞四次。總共重新執行 896 次合成模型介入來核對保存的真值表；這些**不是現實中的實驗、AI 語義理解測試，也不代表一般因果系統必須四次介入**。不更動既有公開字典。詳見 [v0.19 研究規格](docs/ACTIVE-INTERVENTION-DESIGN-v0.19.md)。

v0.20 新增**假設性雜訊與不同介入成本的主動實驗設計**：以 v0.19 七組家族、每組 16 個既有機制為固定基礎，設定四種不同成本及非零對稱觀測翻轉機率。即使遇到矛盾讀數，也會以有理數貝葉斯後驗保留所有候選，不再假裝已能零錯誤辨識。比較每單位成本的預期資訊收益與固定預算內最終全機制 MAP 成功率；兩者在某些情況會選不同的下一步。本版沒有新增語言算子、沒有更新公開字典，也沒有現實感測或獨立 AI 理解率的測量。詳見 [v0.20 研究規格](docs/NOISY-COST-AWARE-ACTIVE-DESIGN-v0.20.md)。


v0.21 加入**非對稱觀測誤差、整個實驗階段共用的隱藏感測偏差，以及有限預算下的停止決策**。使用 v0.19 的 16 種觀察等價機制，另增一個二元的固定階段偏差，形成 32 個聯合狀態。系統以精確有理數計算後驗，並對比每次重新抽取誤差的控制模型。在兩單位成本預算下，錯誤分類代價為 8 時決策停止，代價為 64 時則建議繼續。這是**明確限定的合成決策實驗**，非現實量測、非 AI 語義理解成績，也沒有變更任何正式字典。參見 [v0.21 完整規格](docs/ASYMMETRIC-CORRELATED-STOPPING-v0.21.md)。

v0.22 首次提供一套**可還原的英文符號計算決策紀錄**：將 v0.21 的假設性觀測歷程、成本預算、停止／繼續決策與精確計算收據寫成 `TRACE_V022` 表達式。八個合成案例均可由公開模型重算並核對 SHA-256 來源指紋及歷史順序指紋，任何更動讀數、作用對象、模型版本或最佳決策而未重新計算者都會被拒絕。這是**有限模型的專用實驗表徵**，不是已驗證的 AI 跨模型理解能力，也不是新的加密系統、正式中觀字元或真實量測。參見 [v0.22 規格](docs/REPLAYABLE-DECISION-TRACES-v0.22.md)。

v0.23 新增**多回合的可重播決策歷程**：`RUN_V023` 以 v0.22 的完整決策快照為節點，依序保存前一步選擇的介入、後續合成讀數、剩餘預算、重新計算的後驗，以及每回合與前一回合相連的 SHA-256 內容指紋。五筆合成歷程共有八回合，四筆以實際 `STOP` 結束，一筆只保留 `OPEN` 前綴；不能把中途截斷說成模型已停止。這仍是**有限合成模型下的結構與計算驗證**，不是實際 AI 讀者理解、真實感測、密碼學認證或已實作的中觀函數。參見 [v0.23 規格](docs/LINKED-DECISION-SESSIONS-v0.23.md)。

v0.24 新增**可逆增量式多回合歷程表達**：保留原本 v0.23 的模型來源、初始預算／損失、各回合動作與合成讀數、SHA-256 鏈及最終狀態，將可從公開固定規則重新計算的完整後驗／決策快照從傳輸內容中省略。固定五筆歷程的 UTF-8 字串由 13,940 bytes 減為 4,962 bytes（減少 64.405%），五筆都能逐位元組還原成舊版完整原稿，且 `OPEN` 前綴可以繼續追加，但 `STOP` 不可冒充未完成歷程。**這是限定實驗中的編碼長度改善，不是整體儲存成本、AI 理解率或安全認證。** 詳見 [v0.24 增量式語言規格](docs/INCREMENTAL-DECISION-SESSIONS-v0.24.md)。

v0.25 新增**具可檢查約束的增量欄位自動選擇**：在不改變既有計算歷程或公開概念字典的條件下，程式枚舉每回合是否保留可推導的動作和中間鏈指紋。每筆新觀測、初始模型／規則指紋以及最終歷程憑證仍強制保留。固定五筆合成案例中，最精簡模式合計 4,396 bytes，相對 v0.24 的 4,962 bytes 少 11.41%；審查模式 4,582 bytes，強化逐步稽核模式 4,956 bytes。**零回合案例反而變大**，且沒有測量 CPU 節省或獨立 AI 理解成績。所有案例都能逐位元組還原 v0.23 原始碼。見 [v0.25 完整規格](docs/SELECTIVE-DERIVATION-v0.25.md)。

## License

MIT — see [LICENSE](LICENSE).

### v0.26 — checkpoint selection by declared access costs

```bash
python checkpoint_planner.py check
python checkpoint_planner.py report
python checkpoint_planner.py plan --session R23_THREE_ROUNDS --profile mixed_reads
python checkpoint_planner.py plan --session R23_START_STOP --profile hot_tail
```

`CHECKPOINT_RUN_V026` is an optional, verifiable materialized-state overlay on the canonical v0.25 delta. The planner also considers plain v0.25 and full v0.23 records. **The work estimates are synthetic replay units, not measured latency**; a state is returned only after full deterministic verification. Original grammar, published dictionary and historical data remain unchanged.

中文補充：v0.26 在五筆既有合成決策歷程上，按預期讀取次數、真實 UTF-8 儲存位元組數與假設性的重建步數，在完整快照與增量紀錄之間窮舉選擇。冷存檔適合只留增量，常讀取末端狀態可能值得另存完整狀態；但**沒有實測 CPU 加速、獨立 AI 理解率，也沒有發明新的正式語言字典**。

### v0.27 — measured full-replay timing, not hypothetical checkpoint latency

```bash
python measured_replay.py check
python measured_replay.py recommend --profile hot_tail --byte-price-ns 1000
python measured_replay.py bench --session R23_TWO_ROUNDS --repeats 5 --warmups 2 --output .local/own-timing.json
```

The captured Linux/Python 3.13 sample shows ~6.08 ms (selective), ~6.17 ms (hybrid final checkpoint), and ~54.26 ms (full) for a final-state read **with full-history verification on every access**. This is one environment and a tiny synthetic corpus, **not** a stable hardware benchmark, a causal/AI understanding result, or a working lazy-cache performance improvement. CI checks the sample receipts and score arithmetic, **not** volatile clock values. [Specification and raw-sample interpretation](docs/MEASURED-REPLAY-v0.27.md).

中文補充：v0.27 開始直接量測現有解碼器的 CPU 執行時間，區分「理論重建成本」與「真正讀取時包含完整驗證的時間」。目前只是有限樣本與單一環境的示範，不能以此宣稱檢查點無用或某種格式在所有硬體上都最快。既有正式語言字典及歷史資料不變。

### v0.28 — verified-once process-local replay cache

```bash
python trusted_cache.py check
python trusted_cache.py read --session R23_TWO_ROUNDS --mode selective --state 2 --times 2
python trusted_cache.py bench --session R23_TWO_ROUNDS --repeats 5 --output .local/cache-run.json
```

`VerifiedStateCache` fully verifies a **canonical source on first admission**, materializes the v0.22 states, then serves repeated reads from a bounded in-process LRU while checking the source and monitored model/decoder byte fingerprints. Changed inputs cause invalidation; eviction and restart require fresh replay. The sample records faster repeat-hit reads but substantial first-admission cost. **No signatures, cross-process trust, hostile concurrent-file guarantees, or independent AI understanding are implied.** The original v0.1–v0.27 language, models and reports are not changed. See [v0.28 research specification and measured limitations](docs/TRUSTED-IN-PROCESS-CACHE-v0.28.md).

中文補充：v0.28 先做完整可重播驗證，再讓同一個受控 Python 程序重複使用已驗證的計算狀態。首次建立快取成本較高，重複讀取才可能攤平；來源、模型或解碼器檔案發生變動時，必須清除快取並重新驗證。雜湊檢查不等於密碼學身分認證，亦不是獨立 AI 語義理解測試。
