# ALCG v0.24 — Reversible Incremental Decision Sessions

**Status:** finite, experimental and replayable; an open source transport profile for existing v0.23 decisions, **not** a new published language primitive, a universal AI representation, secure authentication or empirical causal inference.

## 1. Problem and invariants

ALCG v0.23 saves the full `TRACE_V022` posterior/policy snapshot after every synthetic observation. Those snapshots are valuable for offline inspection, but the ordered history is already sufficient to recompute their exact contents under fixed v0.21 rules. This version creates a smaller representation without dropping the ability to recover v0.23's canonical UTF-8 expression.

A v0.24 record is valid only if all of the following hold:

1. The publicly pinned v0.21, v0.22 and v0.23 model and source rules match exactly.
2. The source is a synthetic, bounded v0.23 `Session`. New observational facts or off-policy actions cannot be silently inserted.
3. Each step records the *actual* action chosen by the immediately preceding v0.21 decision policy and its one Boolean observation.
4. Costs, next-step policies, exact rational Bayesian posteriors, and the v0.22 state/history digests can all be recalculated from the initial parameters and the ordered step sequence.
5. The stored per-step link digests and final receipt agree with the replayed v0.23 chain, including the session identifier and order.
6. `STOP` denotes an actual policy stop; `OPEN` explicitly means the saved computation is an unfinished prefix.

The result is a reversible **delta transport**, not a lossless archive of arbitrary external content or a proof that the synthetic model is true.

## 2. Profile schema

The runnable example file is `samples/delta-sessions-v0.24.alcg`. This *non-executable sketch* illustrates field names and nesting:

```text
DELTA_RUN_V024(
  id=R23_EXAMPLE,
  start=START_V024(
    family=F17_DIRECT, budget=NAT(value="2"), loss=NAT(value="64"),
    origin=SYNTHETIC, protocol=V021_CORRELATED,
    profile_sha256=SHA256(value="<64 lowercase hex>"),
    seed_sha256=SHA256(value="<64 lowercase hex>")
  ),
  steps=STEPS_V024(
    r0001=STEP_V024(
      action=NAT(value="3"), reading=TRUE,
      link_sha256=SHA256(value="<64 lowercase hex>")
    )
  ),
  end=END_V024(
    rounds=NAT(value="1"), spent=NAT(value="1"),
    remaining=NAT(value="1"), status=OPEN,
    history_sha256=SHA256(value="<64 lowercase hex>"),
    state_sha256=SHA256(value="<64 lowercase hex>"),
    chain_sha256=SHA256(value="<64 lowercase hex>")
  )
)
```

| Component | Carried information | Reconstructed information |
| --- | --- | --- |
| `START_V024` | Session ID (root), family, original budget, original loss, model/version and session seed digests | Original full `TRACE_V022`, initial posterior and policy |
| `STEP_V024` | Index-keyed action, Boolean reading and v0.23 round link digest | Action cost, updated evidence history, posterior, decision and after-snapshot receipt |
| `END_V024` | Step count, total spent, remaining budget, actual STOP/OPEN, separate history/state/final-chain digests | Canonical `END_V023` and complete v0.23 record |

Names are English-readable ASCII identifiers using the pre-existing ALCG named-argument syntax. `NAT`, `SHA256` and the parser are unchanged. No new primitive operator, glyph, audio or encryption is involved. Keys `r0001`, `r0002`, ... must be contiguous; the maximum number of actions is four in this fixed-cost budgeted model.

## 3. Exact replay and delta extension

Given the header, the decoder first recomputes the full initial v0.22 snapshot. For each step, it checks the previous policy recommends the recorded action and that the action fits the remaining budget; it appends the reading, recomputes the exact posterior and decision, then verifies the saved v0.23 link digest. Finally it checks spent/remaining budget, stop status, and distinct ordered-history and posterior-state receipts.

- `expand(delta)` yields the **complete byte-canonical** `RUN_V023` expression.
- `pack(full)` parses and verifies a full v0.23 record before producing an equivalent delta expression.
- `append(delta, reading)` accepts a `TRUE/FALSE` observation only when the verified prefix is `OPEN`. The next action is *selected by the existing policy*, not chosen by the caller. Previously recorded step digests must not change.
- A legitimate `OPEN` prefix is replayable even if it later extends. A `STOP` record is not extendable.

This is **not** a generic event sourcing mechanism, a model-independent proof of correctness or a treatment of real-world missing data. Round links are the existing unkeyed v0.23 SHA-256 chain, not a digital signature. Someone who completely rewrites the synthetic session and recomputes all digests can make another internally consistent record; an independent trusted anchor would be needed for stronger provenance.

## 4. Measured bytes on the frozen five-case corpus

The following comparisons use UTF-8 lengths of each expression on one non-comment line and exclude a newline, filesystems, source-code/model distribution and ZIP overhead. The same five original v0.23 sessions, with a total of eight recorded rounds, were used without altering the synthetic readings.

| Frozen case | v0.23 full bytes | v0.24 delta bytes | Saved bytes |
| --- | ---: | ---: | ---: |
| R23_TWO_ROUNDS | 3,171 | 1,050 | 2,121 |
| R23_THREE_ROUNDS | 4,254 | 1,201 | 3,053 |
| R23_START_STOP | 1,172 | 754 | 418 |
| R23_OPEN_PREFIX | 2,169 | 902 | 1,267 |
| R23_CONTEXT_FAMILY | 3,174 | 1,055 | 2,119 |
| **Total** | **13,940** | **4,962** | **8,978** |

**Reduction on this frozen sample: 64.405%.** All five delta expressions re-expand to the exact corresponding original `RUN_V023` bytes, with the *same* final v0.23 chain, history digest, state digest and STOP/OPEN semantics. This is an expression transport size result, **not** a measured reduction in computational time, total deployment size or AI token usage. Recomputing snapshots can use more CPU; the public model and decoder must still be distributed. No reader-comprehension scores were collected.

## 5. Repeat locally (Python 3.10+, standard library only)

```bash
python delta_language.py check
python delta_language.py report
python delta_language.py examples
python delta_language.py replay --id R23_TWO_ROUNDS
python -m unittest discover -s tests -p test_delta_language.py -v
python tests/run_split_suite.py
```

To convert a full v0.23 record into a shorter record, save exactly one verified `RUN_V023` expression in a UTF-8 file and run:

```bash
python delta_language.py pack old-session.alcg > small-session.alcg
python delta_language.py expand small-session.alcg > restored-v023.alcg
python delta_language.py decode small-session.alcg
```

To append one synthetic observation to a verified unfinished prefix (one expression per file):

```bash
python delta_language.py append open-prefix.alcg --reading 0 > extended-session.alcg
```

`check` regenerates the exact fixed-sample and JSON-report bytes, then checks bidirectional transformations. The unit tests additionally reject changed action IDs, observations, receipts, model fingerprints, cost totals, malformed indices, invalid origins and attempts to append after policy STOP. GitHub Actions runs this check on three Python versions, without external APIs.

## 6. Limitations and next concept

A smaller textual record is useful only when readers know the pinned interpretation rules. Because we deliberately retain the v0.23 chain and re-execute the original optimizer, consistency is conditional on that frozen model and its cost assumptions. Different policies, actual sensors, concurrency, external origin signatures and cross-model AI comprehension are outside this release. **A parser's acceptance of `DELTA_RUN_V024` is not evidence that an unfamiliar AI understands its intended semantics.**

The design principle is to transmit the smallest *replay sufficient change*, while retaining the ability to reconstruct exactly what was omitted. Future mesoscopic representation may make some function and concept bundles executable, but v0.24 neither defines such units nor claims they already exist.
