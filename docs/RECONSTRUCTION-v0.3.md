# ALCG v0.3 — AI Reader Reconstruction & Contrast Protocol

**Date:** 2026-11-08  
**Status:** reproducible open-source experiment, not an independently validated comprehension result  
**License:** MIT (same as repository)

## Question

When an AI sees an unfamiliar but English-readable symbol structure, how well does it recover the **roles, relationships, negation, causal direction, modality, and scope**, rather than simply recognize isolated English identifiers?

In v0.3, we intentionally test **readability of the existing v0.2 syntax**, not a newly invented alphabet or final AI-native language. We do not treat forced-choice agreement as proof of semantic understanding.

## Two tasks that must not be combined into one metric

| Task | Count | Visible to reader | Reader output | Scoring |
| --- | ---: | --- | --- | --- |
| `reconstruct` | 24 | `id`, `task`, ALCG `expression` | English reconstruction and uncertainty | Independent 0–3 adjudication; no automatic semantic grade |
| `choose` | 12 | `id`, `task`, English `target`, A/B symbol alternatives | A/B or ABSTAIN and rationale | Exact match to the curated answer key |

The reconstruction set uses only the 24 v0.2 **candidate** expressions. Excluding the six `RAW` and six `PARTIAL` records prevents the English text in their explicit fallback fields from trivializing the exercise. The candidate labels were written by the author; none is guaranteed semantically correct by the parser.

The new contrast set has two curated minimal contrasts in each of six domains: daily language, science, mathematics, computing, society, and epistemic discourse. Each contrast deliberately changes an important structural distinction: role assignment, desire versus assertion, direction, negation, the comparison relation, condition versus conjunction, or epistemic attribution.

## Create a reader packet locally

From the repository root, with Python 3.10+ and no dependencies:

```bash
python reconstruction_lab.py check
python reconstruction_lab.py prepare --out .local/reader-v0.3.jsonl --key .local/key-v0.3.json --seed 20261108
```

`prepare` writes exactly 36 lines of UTF-8 JSONL, with **opaque, shuffled IDs** (`R0001` or `C0001`). The `--key` JSON contains gold labels, the original English (reconstruction task), domain metadata and SHA-256 digests. The tool will **not overwrite** existing experiment files.

**Give only `reader-v0.3.jsonl` to the reader.** Keep the `key-v0.3.json` file with the evaluator. The repository `.gitignore` excludes `.local/` and private keys by convention; check staged files before pushing anything to a public repo.

Sample reader packet lines (*examples, not actual generated IDs*):

```jsonl
{"id":"R0001","task":"reconstruct","expression":"DO(actor=PERSON, action=HELP, object=COMMUNITY)"}
{"id":"C0001","task":"choose","target":"A child wants to have food.","options":{"A":"HAS(owner=CHILD, item=FOOD)","B":"WANT(agent=CHILD, goal=HAS(owner=CHILD, item=FOOD))"}}
```

The contrast task **does** show a target sentence, intentionally: it is a comprehension *discrimination* task, **not** a blind reconstruction task. Do not count its accuracy as free-form reconstruction.

## Reader conditions

Run separate, documented sessions. A reader should not receive the v0.2 benchmark, source English, answer key, or the v0.3 contrast benchmark's `correct`/`foil` labels.

1. **Zero-shot:** give only the task instructions below plus the packet. No operator glossary.
2. **Specification-assisted:** give the same packet and the publicly documented syntax and `data/relations-v0.2.json`. Report this condition separately from zero-shot.

**Instruction to the reader (copyable):**

> Read each record without consulting the source benchmark or any answer key. For `reconstruct`, express the complete meaning of the ALCG expression in ordinary English, without adding facts, and state any uncertainty. For `choose`, select A, B, or ABSTAIN as the representation that most faithfully matches the visible English target; briefly explain the distinction. Return one JSON object per input record, preserving its opaque `id`, using the formats specified below. Do not access the GitHub repository, search for the benchmark, or infer answer labels from source files.

Response formats (these are **schematic examples**, not test observations):

```jsonl
{"id":"R0001","reconstruction":"A person helps a community.","uncertainty":"No time or place is specified."}
{"id":"C0001","choice":"B","rationale":"The WANT wrapper states desire rather than current possession."}
```

Readers may submit incomplete files. `ABSTAIN` counts separately from a missing response. Keep the original response unmodified and log reader name/model, model version, date, instructions, prompt condition, parameters (if known), and whether the reader had access to the public repository.

## Score an actual response

```bash
python reconstruction_lab.py grade \
  --packet .local/reader-v0.3.jsonl \
  --key .local/key-v0.3.json \
  --responses .local/reader-answers.jsonl
```

The scorer verifies the packet's hash, IDs and schemas, reports contrast accuracy both over **all assigned** pairs and over **selected** pairs, and leaves reconstruction ratings as `null` until they are independently adjudicated. A constant choice of `A` scores 6/12 (50%) by construction; this is a trivial reference only, not a statistical null result.

For reconstruction ratings, have an independent adjudicator compare the saved reader response with the withheld original English. Supply a JSONL file containing only the rated case IDs:

```jsonl
{"id":"R0001","rating":2,"notes":"Format example only: the core roles were recovered, but scope was lost."}
```

Then append `--ratings .local/human-ratings.jsonl` to the scoring command. Scores must be 0, 1, 2, or 3:

- **0**: incorrect, contradictory, or no recoverable proposition;
- **1**: recognizable topic, but critical roles or relationships missing;
- **2**: central proposition mostly recovered, with a meaningful omission or addition;
- **3**: all essential roles, logical force, and scope preserved without critical additions.

Example ratings in documentation are **not actual observations**. Never pre-fill ratings by reading the key or take model self-ratings as independent adjudication.

## Limitations, leakage, and scientific interpretation

- **Public-source contamination:** The developmental v0.2 benchmark (including original English), the v0.3 contrast pairs and this generator are public. A reader with access to the source repository can retrieve answers. Packet-only presentation is useful operational blinding, **not** a secure unseen benchmark. Use genuinely held-out cases outside the repository when making generalization claims.
- **English is intentionally visible:** Decoding readable English identifiers is easier than deciphering a truly unfamiliar notation. High scores could reflect ordinary English fluency rather than a novel symbolic capacity.
- **Construction hypotheses are not truth:** Gold responses are authored expressions, not formal proofs that the expression fully matches a natural-language sentence.
- **Contrast is not reconstruction:** Even 12/12 forced-choice does not establish that a model can freely recover the intended meaning.
- **No independent reader was invoked to create v0.3:** Passing CI demonstrates parser/protocol correctness only. Actual AI-model comparisons require separately captured responses and preferably blinded adjudicators.
- **Sample size:** Twelve forced-choice pairs are a diagnostic seed, not a reliable model ranking. Report counts and conditions before interpreting a percentage.

## 下一步的研究判準（繁體中文）

本次目標不是讓語言突然變完整，而是建立可回溯的失敗測試。v0.3 把「無法理解」、「誤判角色」、「否定範圍錯置」、「因果反向」與「只因英文單字相近而猜對」分開觀察。即使 AI 全答對，也只能說它在這組公開、人工設計的題目上成功，不能直接推論其具備一般性的語義理解。

後續若加入時間先後、可能性與量詞等新算子，應保留這批固定題目作為回歸測試，再另外建立新題；不可只改寫題庫，卻宣稱覆蓋率進步。
