# ALCG v0.9 — Three-condition pattern-transfer reader laboratory

**Status:** public, reproducible *protocol*, NOT an AI-understanding result. 2026-11-08. UTF-8 Markdown canonical source.

## 1. Research question

Does an AI reader understand an optional ALCG `P_*` composition directly, and how does its reading change when supplied with the relevant pattern definitions or the original expanded ALCG expression?

The three **input conditions** are:

| Condition | Reader input | Important boundary |
| --- | --- | --- |
| `unaided` | `P_*` composition only | No external pattern registry inside the packet; the English-oriented symbol names themselves may be informative. |
| `glossary` | Same expression, plus only the used pattern definitions and their dependency closure | The templates are supplied; English source sentences and expected readings are not. |
| `expanded` | Same meaning, expressed without `P_*` patterns | This uses the existing v0.4 native ALCG operators; it is **not** the English answer. |

The **two tasks** are administered in *separate reader sessions*:

- `reconstruct`: 24 source-preserving, free-response interpretations, four selected examples in each of six v0.6 domains. Do **not** include multiple-choice answers in the reader's context.
- `contrast`: 12 manually curated, three-choice probes (two in each domain). These have multiple-choice paraphrases by design and thus **must not** precede reconstruction in the same context.

Total configurations: **3 conditions × 2 tasks = 6 packet types**, built deterministically from the same frozen 24 v0.8 pattern roundtrips and 12 new probes. The 12 probes are a subset of the 24 cases; they are **not** 12 new English coverage examples.

## 2. Preparation and administration

Run locally at the repository root with Python 3.10+, standard library only:

```bash
python pattern_transfer.py check
python pattern_transfer.py report

# Example: one independent reader, unaided reconstruction task.
python pattern_transfer.py prepare \
  --task reconstruct --condition unaided --seed 20261108 \
  --reader-id reader-alpha \
  --packet .local/v09-reader-packet.json \
  --key .local/v09-private-key.json \
  --response-template .local/v09-reader-response.json
```

Deliver **only** the reader packet (and the response schema or blank response template) to the reader. The key contains the original English, reference expression and, for contrasts, the correct answer. Store key files outside reader context; `.local/` is ignored by Git. `prepare` refuses to overwrite files or alias any output paths.

For other arms, use `--condition glossary` or `--condition expanded` with **different filenames and a fresh reader context**. For the alternate task, use `--task contrast` and a different reader session. Keep `--seed` identical for across-condition comparisons of the same task. Item order and contrast option shuffle are deterministic and **identical across conditions** for a fixed seed. Use different pseudonyms for different readers.

**Reader instruction:** explain what each expression says in plain English, including agency, role, quantity, negation, conditional direction, time, and possibility; abstain explicitly when uncertain. For `contrast`, choose A/B/C or null for abstention. The respondent's model name, model version, settings, prompt, decoding options, whether they could browse the public repo, and test time must be recorded separately by the experiment operator. The tool does not authenticate these facts.

### Public-benchmark limitation

All benchmarks and pattern definitions are open source. Publishing a benchmark means it is **not a securely held-out set**: a reader with GitHub access could inspect the answers. To claim a *genuinely blinded* experiment, isolate the reader from the repository, deliver only the packet, use independent raters, and declare any contamination. Public files are sufficient for a reproducible protocol, not for guaranteeing reader ignorance. No external AI readers have been measured in the v0.9 checked-in report.

## 3. Response schemas

`--response-template` writes an intentionally **all-abstain placeholder**. Fill it with **actual** reader output; never call its zero scores an AI result. The shape is:

```json
{
  "format": "ALCG-pattern-transfer-response-v0.9",
  "packet_hash": "<the exact SHA-256 from the generated template>",
  "reader_id": "reader-alpha",
  "items": [
    {"id": "R01", "reconstruction": "Plain English answer", "abstain": false}
  ]
}
```

The example above is an abbreviated schema. A real file must contain every packet item exactly once (24 for reconstruction; 12 for contrast). For abstention, set `abstain: true` and an empty reconstruction string. A contrast response has `{"id":"Q01", "choice":"B"}`; set `choice: null` to abstain. Omit ratings at this stage.

## 4. Scoring and adjudication

```bash
# Objective multiple-choice grading:
python pattern_transfer.py grade \
  --packet .local/v09-contrast-packet.json \
  --key .local/v09-contrast-key.json \
  --responses .local/v09-contrast-responses.json \
  --out .local/v09-contrast-report.json

# Free reconstruction: returns answered/abstained, but NO comprehension score without human ratings:
python pattern_transfer.py grade \
  --packet .local/v09-reader-packet.json \
  --key .local/v09-private-key.json \
  --responses .local/v09-reader-response.json

# With an independent rater's judgments:
python pattern_transfer.py grade \
  --packet .local/v09-reader-packet.json \
  --key .local/v09-private-key.json \
  --responses .local/v09-reader-response.json \
  --ratings .local/v09-independent-ratings.json \
  --out .local/v09-reconstruction-report.json
```

For reconstruction, the external rater reviews the independent answer against the key's original English *and* structured reference. The rater supplies **one item for each non-abstained response**:

```json
{
  "format": "ALCG-pattern-transfer-rating-v0.9",
  "packet_hash": "<the exact packet SHA-256>",
  "rater_id": "adjudicator-beta",
  "items": [
    {"id": "R01", "fidelity": 3, "critical_structure": true, "note": "Preserved event agent, object, and scope."}
  ]
}
```

Editorial fidelity rubric: **3** = preserves meaning and all critical relations; **2** = broadly correct with minor non-critical omissions; **1** = partial match but a materially important aspect is missing; **0** = contradicts central roles/scope or is not faithful. `critical_structure` separately records whether the case's critical role/scope/modality distinction was preserved. An all-abstain trial has *no independent comprehension observations*. Abstentions count as zero only in the across-all-items average **after** the rater has supplied a complete rating set for all answered items. If there are no external ratings, all fidelity results are `null`.

Contrast scoring computes accuracy over *all* 12 items (abstentions contribute zero), and separately over answered items. Responses and ratings are strictly validated: mismatched packet hash, repeated or missing IDs, invalid choice labels, reader self-adjudication, missing ratings and tampered packet/key are rejected.

## 5. Comparing conditions

```bash
python pattern_transfer.py compare \
  .local/v09-unaided-report.json \
  .local/v09-glossary-report.json \
  .local/v09-expanded-report.json
```

The comparison tool requires distinct reader pseudonyms, the same seed, matching source digests and task, and different conditions. Its output is **descriptive**. Differences between readers may reflect reader/model ability, task familiarity, contextual memory, answer contamination or chance. A causal or statistically significant inference would require controlled assignment and additional sampling not provided by v0.9.

## 6. Conservation principles

- No changes to the v0.1 syntax or v0.4 native relation registry.
- No change to the 36 v0.4 or 48 v0.6 source English items, and no change to v0.8 pattern templates or its 24 examples.
- No pronunciation, cryptography, secure cipher, machine-executable mesoscopic units, automated remote AI calls, or claimed external-comprehension scores.
- New 12-probe content is editorial and must be validated independently if used for high-stakes cross-model claims.
- The v0.9 report describes protocol validation only, not any measured AI reading success.

> A combination being fully expandable is evidence about structural reversibility, not evidence that its meaning was successfully communicated.
