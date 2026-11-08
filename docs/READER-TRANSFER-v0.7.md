# ALCG v0.7 — Reader Transfer and Counterfactual Contrast Laboratory

**Date:** 2026-11-08  
**Status:** experimental, open-source, UTF-8 source-first  
**Repository:** <https://github.com/EveMissLab/AI-Language-Creation-Game>  
**Scope:** English-readable ALCG; no pronunciation, cryptography, new character system, or executable mesoscopic function bundles

## 1. Why this round exists

A syntax parser can establish whether an ALCG expression is well formed. A finite-world interpreter can establish whether selected expressions have different outcomes under its stipulated model. Neither demonstrates that **an unfamiliar AI reader** correctly interprets the expression.

There is a second trap: the English-derived symbols themselves provide clues. An AI may score well by recognizing the words `BANK_FINANCIAL`, `RIGHT_ENTITLEMENT`, or `MAY`, without correctly interpreting argument roles, the scope of a negation, the order of events, or the intended quantifier.

This version offers a falsifiable experiment that separates these effects. It does **not** claim that an independent AI has already been tested.

## 2. Frozen foundations

We reuse v0.6's existing 48 new curated English statements, 36 labeled `candidate`, and its 17 explicit sense labels (8 ambiguous English spellings). The v0.4 relation registry and the parser are unchanged. Source byte hashes are recorded in each private scoring key, and the v0.6 code validates its own earlier frozen benchmarks.

New `benchmarks/reader-contrast-v0.7.jsonl` contains **24 manually designed contrast pairs**: four per domain across daily life, science, mathematics, computing, society, and epistemic contexts. Each contrast has an English target, its existing v0.6 candidate expression, a different valid ALCG expression (the foil), a named contrast type and an explanation of the change. The new file does not change the original English sentences or add operators.

This enables **60 tasks per reader trial**:

| Task | Count | Input shown to reader | Measurement |
| --- | ---: | --- | --- |
| Reconstruction | 36 | ALCG expression only | Free-form English reconstruction; separately adjudicated |
| Forced-choice contrast | 24 | English target plus A/B expressions | Correct / incorrect / abstain / missing |

A and B answers are balanced at 12 each. Source case IDs and correct options are never included in the reader packet. Only the *local key* contains the reference English for reconstruction and correct option for the contrast.

The 24 foils test role direction, sense substitution, condition reversal, possible versus actual, quantifier choice, negation scope, time order, assertion polarity, and knowledge versus belief. They are *author-designed semantic contrasts*; passing the syntax validator does not prove the authored English-to-ALCG translation is a universal semantic ground truth.

## 3. The two reading conditions

- **Unaided:** A reader receives English-derived ALCG expressions without extra sense descriptions.
- **Glossary-assisted:** A reader receives the same expressions, same case IDs, and same A/B ordering, but also sees v0.6 sense glosses **only for labels present in that item**.

Use the same seed for two packets if you need paired item positions. **Do not give both conditions to the same model session**, which would leak the glossary condition into the unaided condition. Use distinct model instances or fully separated sessions with no carryover, and record the prompt, model and access conditions. Glossary assistance only affects tasks that actually contain a registered sense label; report that subgroup separately for future claims.

These packets are *operationally blinded* but **not secure held-out data**. The public GitHub repository contains the source English and the contrast gold. Any AI with repository browsing/retrieval access, or prior exposure to these public files, may discover the correct answers. To claim generalization, collect fresh unpublished cases and use an external blinded evaluator.

## 4. Generate the packets (Python 3.10+, no external dependencies)

From the repository root:

```bash
python reader_trial.py check
python reader_trial.py baseline-report

# Run these in separate experiments/sessions; keys remain under .local/.
python reader_trial.py prepare --condition unaided --seed 20261108 \
  --packet .local/reader-v0.7-unaided.json --key .local/reader-v0.7-unaided-key.json

python reader_trial.py prepare --condition glossary --seed 20261108 \
  --packet .local/reader-v0.7-glossary.json --key .local/reader-v0.7-glossary-key.json
```

The packet is the only file the reader should see. **Never give the reader the key, full repo, or original benchmark.** By default the command refuses to overwrite packet/key files, and keys created inside the public repository must be in a gitignored folder (`.local/`, `private/`, `.runs/`). Never commit keys or personal/private model-response metadata.

### Expected reader response format: UTF-8 JSONL

For a reconstruction task (`R####`):

```json
{"id":"R0001","reconstruction":"A possible English meaning stated by the reader.","uncertainty":"I may be missing the quantifier scope.","abstain":false}
```

To abstain, set `reconstruction` to an empty string and `abstain` to `true` (give a reason in `uncertainty`).

For a forced-choice task (`C####`):

```json
{"id":"C0001","choice":"ABSTAIN","rationale":"Both expressions share the same surface words, but their roles are unclear to me."}
```

The chosen option must be `A`, `B` or `ABSTAIN`. These JSON examples illustrate schema only; they are **not actual reader responses** and must not be submitted as evidence. Reader response files can be partial, but missing cases remain explicitly missing in the report.

### Grade a real response

```bash
python reader_trial.py grade \
  --packet .local/reader-v0.7-unaided.json \
  --key .local/reader-v0.7-unaided-key.json \
  --responses .local/actual-reader-responses.jsonl
```

Reconstruction scores are not automatically invented. If an independent evaluator has inspected the ordinary-English responses, it may create `ratings.jsonl` with items like:

```json
{"id":"R0001","rating":2,"notes":"Core relation preserved, but the modality is omitted."}
```

Then append `--ratings .local/ratings.jsonl` to the grade command. Ratings follow the earlier 0–3 rubric in `docs/COVERAGE-v0.2.md` and **must include explanatory notes**. A rating is invalid for a reconstruction that was missing or abstained. Report rated count, unrated count, abstentions and missing cases rather than presenting only a percentage.

Record reader identifier, exact model/version, system prompt, date/time, packet hash, tool/browsing access, session separation and adjudicator identity in your local experiment notes. These facts are self-reported and **not cryptographically proven by this tool**.

## 5. Non-AI lexical-overlap control

To establish what can be guessed from English surface words alone, `reader_trial.py` includes an intentionally weak, deterministic **non-AI** control. It tokenizes the visible English target, compares overlapping tokens to the labels in the A/B options, and **abstains on a tie**. It does not inspect the hidden gold, follow the argument roles, interpret nested operators, or use the glossary. Its contrast choices are ungraded until the local key is used by the scorer.

Run:

```bash
python reader_trial.py lexical-baseline \
  --packet .local/reader-v0.7-unaided.json \
  --out .local/lexical-v0.7.jsonl

python reader_trial.py grade \
  --packet .local/reader-v0.7-unaided.json \
  --key .local/reader-v0.7-unaided-key.json \
  --responses .local/lexical-v0.7.jsonl
```

In the frozen 2026-11-08 seed, this non-AI control yields:

- **8 correct choices out of 24 assigned**, 0 wrong, 16 abstentions, 0 missing;
- 8/8 correct among the selected cases only (selection is highly nonrandom), not 100% comprehension;
- **0 out of 36 reconstruction cases answered**, so no reconstruction score exists;
- the same numbers in glossary and unaided modes, because the rule deliberately ignores the glossary.

This is a diagnostic of **English-surface recoverability on an author-selected benchmark**, not an AI benchmark score, and not a legitimate comparison between independent models. The toy baseline could be replaced by better baselines in a later version, but changes must be versioned rather than rewriting this snapshot.

## 6. What is and is not demonstrated

**Mechanically established in v0.7:** the contrast source mapping remains frozen; all 24 foils parse and respect existing relation roles; 36+24 items are generated deterministically; the two conditions are paired; the correct A/B positions are balanced; packet/key integrity checks and response validation work; and the lexical baseline has measured, reproducible behavior.

**Not yet established:** that any independent AI can decode the notation accurately; that glossary assistance improves AI reconstruction; that these contrast questions generalize to unseen English meaning; or that any mesoscopic character/function is ready for use.

The next productive step is to obtain authentic reader responses, classify recurrent errors, and only then expand or modify the language rules. The governing principle is **measured comprehension rather than symbol-count inflation**.

## 繁體中文摘要

ALCG v0.7 建立 36 題語義還原與 24 題最小差異的語義辨別實驗（六領域各四題），在無詞義提示／有局部詞義提示兩種條件下產生分離的題包和答案檔。題庫仍使用既有英文與符號，不增加新算子。非 AI 的英文詞彙重疊演算法能從 24 題中選出 8 題並答對，其餘 16 題棄答；這只說明字面線索可以提供部分答案，並不證明 AI 理解。所有測試可在本地與 GitHub Actions 重現，真正的跨 AI 成績仍須實際讀者與獨立裁定後才能記錄。
