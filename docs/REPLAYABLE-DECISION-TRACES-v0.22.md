# ALCG v0.22 — Replayable English-Symbol Computation Decision Traces

**Status:** experimental, profile-specific, executable and auditable. **Date:** 2026-11-11. **License:** MIT (repository license).

## Abstract

ALCG v0.22 introduces a *typed expression profile* representing a single decision snapshot with its ordered observation history, model provenance, bounded cost/loss policy and exact Bayesian calculation receipt. It uses the existing ALCG recursive, English-readable syntax. It does **not** revise the published ALCG grammar, registry, v0.21 probability model or meaning inventory. This first profile deliberately targets one executable problem family instead of pretending to encode every English thought.

The question is not whether the textual expression is short. It is whether a third party possessing the public model, source and rules can (i) parse the same information, (ii) check whether all fields are well-typed, (iii) recompute the exact result, and (iv) notice modification of the observation history or claimed output relative to its receipt.

## 1. Scope and provenance

The profile reuses v0.21's seven assistant-authored Boolean causal families, 16 candidate completion masks per family, and one persistent binary sensor-fault variable. The posterior has 32 joint cells. Sensor false-positive / false-negative rates, prior, permitted actions (0–7), costs, and decision loss are the hypothetical v0.21 assumptions.

- Source identification is **`SYNTHETIC`**, not `OBSERVED_REAL_WORLD`.
- A trace contains **one decision snapshot**, not a record of every earlier decision or the grounds on which historical actions were selected.
- `budget` is the **remaining future experimental cost budget**, not the sum spent acquiring the earlier observations. Previous costs are sunk.
- `loss` is the assumed misclassification penalty. `STOP` is an optimal *bounded decision* under that penalty, not knowledge of the correct mechanism.
- The model and channel specification is pinned with the exact SHA-256 of `data/correlated-design-space-v0.21.json`. The v0.21 code and all earlier data must be available to replay.
- Calculations use `fractions.Fraction`: the receipt is exact under this finite toy model, not a rounded decimal approximation.

## 2. Typed representation

The top-level expression is:

```text
TRACE_V022(
    scenario=SCENARIO(family=F17_DIRECT, protocol=V021_CORRELATED, origin=SYNTHETIC, spec_sha256=SHA256(value="...64 lowercase hex...")),
    evidence=OBSERVATIONS(e0001=OBS(action=NAT(value="3"), reading=TRUE)),
    policy=POLICY(budget=NAT(value="2"), loss=NAT(value="64"), decision=CONTINUE, next=NAT(value="4"), stop_risk=RAT(n="...", d="..."), optimal_risk=RAT(n="...", d="...")),
    receipt=RECEIPT(max_mask_p=RAT(n="...", d="..."), session_fault_p=RAT(n="...", d="..."), state_sha256=SHA256(value="..."), history_sha256=SHA256(value="..."))
)
```

The example shows *the shape* of the expression, not a complete executable source: literal ellipses must be replaced with the generated values. A fully valid, single-line example is available at `samples/decision-traces-v0.22.alcg` (one expression per non-comment line).

### Profile primitives and their meaning

| Construct | Meaning and required constraints |
|---|---|
| `TRACE_V022` | Exactly the four fields `scenario`, `evidence`, `policy`, `receipt` |
| `SCENARIO` | Known family ID, exact `V021_CORRELATED` version, `SYNTHETIC` origin, pinned model-specification digest |
| `OBSERVATIONS` | Ordered history, zero through 32 `e0001`, `e0002`, ... entries with no gaps |
| `OBS` | `action=NAT(value="0".."7")` and `reading=TRUE` or `FALSE` |
| `POLICY` | Remaining cost budget 0..4, penalty 0..10,000, `STOP` or `CONTINUE`, `next=NONE` or action ID, exact present and future optimal expected losses |
| `RECEIPT` | Exact maximum marginal mask probability, session-fault posterior, joint-state digest, order-sensitive history digest |
| `NAT`, `RAT` | Decimal ASCII number **strings** because v0.1 grammar intentionally has no numeric literal. Negative numbers are allowed only as canonical signed numerators for exact rational results; values are reduced by Python `Fraction` and denominators are positive |
| `SHA256` | Lowercase 64-character digest string; a change detector relative to the versioned public source, not a security signature |

`TRACE_V022`, `NAT`, `RAT`, `SHA256`, etc. are **profile labels** with machine-checked semantics, not additions to the public general-purpose language operator registry. They may be treated as optional domain-specific extensions by readers that recognize this profile. Readers that do not recognize this profile should not silently pretend to know its meaning.

### Named fields and event order

ALCG calls use named arguments. The order of *named fields* inside a call can vary without changing their declared role; the serializer returns one canonical layout. Event order is carried by the **indexed names** `e0001`, `e0002`, ... . A permutation of readings produces a different event history even if the joint posterior remains equal under the particular exchangeable likelihood model. That is why the receipt includes both a posterior-state digest and a separate **history digest**.

## 3. Replay and verification

To build a new synthetic example using the same pinned profile:

```bash
python trace_language.py build --family F17_DIRECT --budget 2 --loss 64 --observe 3=1 --observe 3=0
```

To validate every saved ALCG expression and the stored report:

```bash
python trace_language.py check
python trace_language.py report
```

To decode one expression saved by the author to a single-line UTF-8 file:

```bash
python trace_language.py decode my-single-trace.alcg
```

The validator performs four distinct operations:

1. Verify expression grammar and rigid profile-specific field names and types. Reject missing, extra, duplicated, out-of-range, or malformed fields.
2. Verify the pinned v0.21 model inputs, family ID, channel version and synthetic-data declaration.
3. **Recompute** the 32-cell posterior and the bounded exact STOP/CONTINUE policy; compare every claimed probability, risk, action and checksum with computed values.
4. Reject changed observations, switched action IDs, altered output fractions or mismatched version fingerprints. A saved public report is checked byte-for-byte against the recomputed canonical UTF-8 output.

The posterior-state SHA-256 hashes the ordered 32 exact rational cells. The history SHA-256 hashes the version identifier, family, ordered event list, remaining budget, penalty and pinned specification digest. These fingerprints make accidental/stale edits detectable, but **they do not authenticate an author** and are not encryption. Someone controlling both data and its recalculated digest can forge a new, internally consistent synthetic trace.

## 4. Frozen synthetic test cases

There are **eight** deliberately assistant-authored snapshots, split across `F17_DIRECT` and `F17_CONTEXT`: no evidence and budget 0; no evidence and budget 2; one reading; contradictory repeated readings; calibration plus a targeted reading; three repeated readings; low-penalty STOP after evidence; and an alternate causal family. Total ordered reading entries: **11**. On the fixed assumptions there are **two STOP** and **six CONTINUE** decisions.

These are not independently collected AI behavior or sensor measurements. The numbers merely show that the language is capable of preserving and replaying distinct computation states and recommendations. They do not estimate external semantic coverage.

## 5. Explicit failure modes and open boundaries

- The v0.21 policy assumes known model structure and a fixed list of 16 mechanisms; absent real-world unknown mechanisms it may make overconfident claims if treated as universal.
- Reading order is represented, but **the original policies that produced earlier actions are not**. For a true multi-step provenance chain, each decision must be separately recorded and linked under a future protocol.
- The profile cannot express arbitrary arithmetic, quantification over infinite domains, or natural-language pragmatics. Those require other profiles or extensions.
- A well-formed `TRACE_V022` is a **claim plus a reproducible computation receipt**, not proof of a real-world fact or AI interpretation.
- Hashes are integrity references to a publicly reproducible computation, not secret signatures, encryption or evidence of the author's identity.
- Full validation depends on the pinned public v0.21 model and executable code. The text alone is only partially interpretable without that public specification.
- Structural/canonical checks do not amount to a successful independent cross-model AI comprehension experiment. No such comprehension result is claimed for this release.

## 6. Design implication

This version does not maximize symbol compression. Instead, it demonstrates an intermediate capability: an AI-oriented language can name a calculation, preserve its input history, identify the assumptions that made it meaningful, provide its outcome, and require a recipient to verify rather than merely infer. It moves the ALCG game toward reusable executable semantic profiles, while leaving mesoscopic functional units for a subsequent stage.

**Nothing was automatically promoted to the published pattern dictionary.** The earlier 84 English meaning cases, 16 public pattern templates and v0.21 report remain frozen.
