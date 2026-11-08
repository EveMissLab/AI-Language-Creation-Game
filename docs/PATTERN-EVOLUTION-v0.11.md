# ALCG v0.11 — Pattern Evolution Gate / 樣板提案演化關卡

**Status:** Experimental, review-only, open source (2026-11-08).  **No automated installation of new patterns.**

## Purpose

ALCG has a pinned published pattern registry (v0.8), an exact compact syntax (v0.10), and a set of frozen old tests. v0.11 lets an AI agent or other contributor **propose** a reusable, English-readable composition without modifying this registry. A deterministic gate checks structural integrity, sample roundtrips, duplication, and explicit provenance. The output is a review queue, **not** a new standardized dictionary.

This is a language-creation *game* with actual constraints and cumulative, reproducible research. It is neither encryption nor a spoken-language project. Mesoscopic function bundles and executable semantics remain separate later investigations.

## Commands

Requires only Python 3.10+ standard library:

```bash
python pattern_evolution.py check
python pattern_evolution.py verify-report
python pattern_evolution.py report
python pattern_evolution.py export-preview --out .local/new-staging-preview.json
python pattern_evolution.py report --proposals .local/your-ai-proposals.jsonl
python -m unittest discover -s tests -v
```

`check` compares each included demonstration's **expected status** with the gate's computed status; those expectations are NOT the evidence used in the decision. `verify-report` recomputes the pinned sample report **and** the preview, failing if either committed artifact differs. `report --proposals` supports third-party AI or user proposals in the same UTF-8 JSONL format. It never calls an external model or connects to an API.

## Proposal format

One JSON object per line in `benchmarks/pattern-proposals-v0.11.jsonl`:

```json
{
  "id": "EV011-01",
  "origin": "assistant-authored-v0.11-example",
  "note": "Preserve the temporal order of CHECK and DELETE.",
  "pattern": {
    "name": "P_BEFORE_CHECK_DELETE",
    "slots": ["actor", "object"],
    "template": "BEFORE(earlier=DO(actor=HOLE(slot=actor), action=CHECK, object=HOLE(slot=object)), later=DO(actor=HOLE(slot=actor), action=DELETE, object=HOLE(slot=object)))",
    "gloss": "Expose the shared actor and ordered check-then-delete action."
  },
  "examples": [
    {
      "input": "P_BEFORE_CHECK_DELETE(actor=PROGRAM, object=FILE)",
      "expected": "BEFORE(earlier=DO(actor=PROGRAM, action=CHECK, object=FILE), later=DO(actor=PROGRAM, action=DELETE, object=FILE))"
    },
    {
      "input": "P_BEFORE_CHECK_DELETE(actor=SERVICE, object=ARCHIVE)",
      "expected": "BEFORE(earlier=DO(actor=SERVICE, action=CHECK, object=ARCHIVE), later=DO(actor=SERVICE, action=DELETE, object=ARCHIVE))"
    }
  ]
}
```

`expected_status` is an optional **fixture expectation**, not a decision override. Live inputs do not need it. `origin` must declare where the proposal came from; the 14 shipped fixtures are assistant-authored examples, **not independently measured external AI output**. Published benchmarks must not silently rewrite that provenance.

## Gate sequence (deterministic)

1. Confirm pinned v0.10 registry and all 24 frozen compact cases remain intact.
2. Parse one proposal as UTF-8 JSONL, reject duplicate IDs, oversized input, missing provenance or malformed schema. Limit file size to 256,000 bytes, 48 proposals, six examples per proposal, and 5,000 characters per template.
3. Ensure a proposed pattern cannot overwrite an existing `P_` ID. Append it only to a **temporary** copy of the registry in order to reuse the v0.8 validator. The validator checks declared `HOLE` slots, required roles, explicit caller-supplied quantified binders, cycles, unknown operations and prohibited `RAW`/`PARTIAL` escapes.
4. Expand a candidate with indexed slot placeholders; reject an identical expanded structural signature already published or already staged in this batch. This does not recognize arbitrary mathematical equivalences.
5. Compare each provided sample expansion against its purported full structural reference under v0.5 canonical role-ordering and alpha-renaming. Reject a mismatch, a duplicate reference example, an incorrectly named pattern call, or failed compact roundtrip.
6. Require at least **two distinct** successful examples before `staged_for_human_review`. One or zero examples means `needs_more_evidence`; a structural defect means `rejected`.
7. Generate `reports/staged-patterns-v0.11.json` with an intentionally **non-active** schema. It is not a valid v0.8 registry and cannot be mistaken for one by the registry loader.

A proposal being staged does **not** imply correct informal English meaning, physical truth, executable behavior, full logical equivalence or AI reading comprehension. The example author also wrote the expected result, so this is a self-consistency demonstration, not independent evidence of intended semantics.

## Frozen demonstration outcome

| Decision | Count | Meaning |
| --- | ---: | --- |
| `staged_for_human_review` | 4 | Structural evidence is self-consistent, pending semantic review |
| `needs_more_evidence` | 2 | Fewer than two distinct supporting examples |
| `rejected` | 8 | Duplicate, broken reference, unsafe binding, unused slot, RAW, existing ID or cycle |
| **Total** | **14** | Curated assistant-authored fixtures |

All 16 original patterns and 24 v0.10 frozen compact examples remain unchanged. The **four staged patterns** are `P_BEFORE_CHECK_DELETE`, `P_SAY_NOT_STATE`, `P_MAY_NOT_STATE`, `P_NOT_MAY_ACT2`. Each has two demonstrations. The **examples only** total 590 UTF-8 bytes fully expanded versus 245 bytes in positional shorthand, **excluding the registry and its transmission cost**. These illustrative samples are not an unbiased corpus, and the shorthand cannot be used by the old locked reader until an explicit future registry release.

The eight rejected fixtures include two structural duplicates, a fixed quantifier binder, an unused declared slot, a RAW tunneling attempt, an incorrect negative reference, an existing registry name collision, and a cycle. The two incomplete proposals await additional evidence.

## Threat model, audit boundaries and release discipline

- **Do not auto-merge candidate definitions**: repo `data/patterns-v0.8.json` and compact surface locks remain byte-for-byte frozen. Review records have a separate format.
- **Reject source reference leakage**: in this gate, authored examples openly contain the expected expansion. Thus it is intentionally NOT an AI blind-reading benchmark. Reader trials are defined in v0.3/v0.7/v0.9.
- **Prevent false novelty**: identical canonical expansions are rejected, but other redundancies or logical equivalences may remain undetected.
- **Preserve role ordering**: all proposed slots are explicitly named, and tests include swapped role counterexamples. Positional `@` notation depends on a pinned, versioned dictionary.
- **Scope boundaries**: the imported scope checker rejects unbound variables. The gate does not implement a general model checker or prove that every sentence means what the proposer intended.
- **Human review required**: an eventual v0.12+ promotion must separately version the active registry, publish a manifest and update consumers intentionally; v0.11 performs none of these operations.
- **No GitHub Actions tokens are needed**: the included CI only reads files and validates them. It does not promote, commit, execute submitted expressions as Python, download models or call an AI service.

## 中文結論

這一版正式允許 AI 提出新的英文符號組合，但將「提案」、「結構驗證」與「正式語言規格」分離。四個候選只是待審核，不能聲稱已經被證明語義正確；八個被退回的案例則使語言在演化時保留可追溯的錯誤紀錄。**我們讓 AI 有提案自由，卻不讓它任意改寫已發布的概念規則。**
