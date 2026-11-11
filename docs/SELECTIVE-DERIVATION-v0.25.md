# ALCG v0.25 — Selective Storage of Derivable Computation Receipts

**Status:** experimental, bounded synthetic transport profile; not a published core language operator, a compression theorem, or a cryptographic provenance system.

## 1. Problem

v0.23 `RUN_V023` stores full `TRACE_V022` snapshots after every synthetic observation. v0.24 `DELTA_RUN_V024` removes the snapshots but still keeps the selected **action** and the full **per-round chain SHA-256** along with each new Boolean observation. Given the frozen v0.21 policy and v0.23 replay rules, these action and chain values are themselves reproducible. This raises a more precise question:

> Which *redundant* per-round fields can be omitted while satisfying an explicit, checkable audit policy and preserving **byte-identical v0.23 reconstruction**?

The present laboratory does **not** solve general data compression, decide which information is philosophically indispensable, or prove that an AI understands the resulting text. It enumerates a small, specified field-selection space for five fixed synthetic sessions.

## 2. What may and may not be omitted

**Always retained:** session ID, source/protocol pins, initial model family, budget, classification loss, every new synthetic observed Boolean, final spent/remaining/status and the final history/state/chain receipts. `OPEN` means an unfinished prefix and is never silently transformed into `STOP`.

**Optional by round:** (a) the policy-selected action ID, (b) the intermediate v0.23 chain SHA-256 receipt. Both are precisely recomputable from the pinned rule set plus the ordered readings. An action receipt makes the chosen experiment directly visible; a saved intermediate hash provides a comparison point for locating divergence after replay. Neither is required for complete reconstruction, and neither constitutes authentication.

**Derived at replay:** posterior state, expected risk, next decision, per-action cost, omitted actions, and omitted intermediate hash receipts. These are **computed** rather than ignored.

## 3. New ALCG surface

The existing ASCII identifiers, named arguments and recursive-call syntax from v0.1 remain unchanged. A readable example:

```text
SELECTIVE_RUN_V025(
  id=R23_TWO_ROUNDS,
  rules=RULES_V025(max_gap=NAT(value="5"), min_actions=NAT(value="0")),
  start=START_V024(...),
  steps=STEPS_V025(
    r0001=STEP_V025(reading=TRUE),
    r0002=STEP_V025(reading=FALSE)
  ),
  end=END_V024(...)
)
```

Ellipses above are explanatory only; actual `samples/selective-sessions-v0.25.alcg` contains five *complete*, single-line, fully parseable expressions. Every emitted expression can be used to recreate the exact canonical v0.23 UTF-8 source, including all full intermediate computation snapshots.

The `RULES_V025` fields encode a **publicly inspectable selection contract**, not new math operators:

- `min_actions`: at least this many per-round policy actions must remain directly visible.
- `max_gap`: maximum number of rounds between stored intermediate chain receipts, counting the mandatory final chain receipt as an anchor. Round zero represents the initial state. The terminal receipt itself is not stored twice.

A candidate violating either constraint is rejected. The decoder enforces a *canonical minimum-length* solution under the declared constraints, not just any structurally legal answer.

## 4. Exact bounded selection algorithm

There are `n` observed rounds, with `0 <= n <= 4`. For every round, the implementation evaluates two optional bits: keep `action`, keep `link_sha256`. All `2^(2n)` combinations are enumerable (at most 256). For every candidate, it:

1. checks `min_actions` and `max_gap`, disallowing a duplicated final step-chain receipt;
2. constructs the canonical ALCG syntax tree and measures **actual UTF-8 bytes**;
3. chooses the smallest encoded byte length, with a deterministic text-order tie break;
4. replays through the frozen v0.23 rules, and verifies that the actual stored input equals the canonical selected expression, including every fixed initial and final receipt;
5. recreates `RUN_V023` and requires **byte-identical** equality with the original validated full record.

`--byte-budget` rejects the request if the smallest feasible expression exceeds the supplied threshold; the program never silently drops a required field or weakens an audit constraint to fit.

The optimization is exact **only within this bounded per-round optional-field family**. It does not compare alternative syntaxes, compression algorithms, external dictionaries, checkpoints or other code systems.

## 5. Fixed outcomes and negative results

Five immutable author-selected synthetic v0.23 cases contain 8 total rounds (lengths 2, 3, 0, 1, 2). The frozen 0.23 complete source totals 13,940 UTF-8 bytes and v0.24 delta source totals **4,962 bytes**. The v0.25 profiles are:

| Named selection constraints | Total UTF-8 bytes | Change vs. v0.24 |
|---|---:|---:|
| `lean`: `max_gap=5`, `min_actions=0` | 4,396 | -566 bytes (-11.41%) |
| `review`: `max_gap=2`, `min_actions=min(1, round count)` | 4,582 | -380 bytes (-7.66%) |
| `audit`: `max_gap=1`, `min_actions=round count` | 4,956 | -6 bytes (-0.12%) |

The **zero-round** case is a deliberate counterexample to universal improvement: v0.24 uses **754 bytes** while all v0.25 profiles use **828 bytes**. The extra rules envelope costs more than it saves when there are no repeated fields. Overall reductions are properties of exactly these five examples, not expected savings over arbitrary histories.

All profiles reconstruct identical full v0.23 bytes and preserve `OPEN` versus `STOP`. This costs additional deterministic replay, and **no replay-time or CPU savings have been measured**. A more stringent audit policy may increase transmission length while improving immediately available inspection fields; it does not make data cryptographically trustworthy.

## 6. Reproduction

Python 3.10+ and only the standard library are required:

```bash
python selective_delta.py check
python selective_delta.py report
python selective_delta.py examples
python -m unittest discover -s tests -p 'test_selective_delta.py' -v
```

For one full `RUN_V023` expression in a UTF-8 file:

```bash
python selective_delta.py pack path/to/full-run.alcg --max-gap 2 --min-actions 1
```

Store the resulting single-line `SELECTIVE_RUN_V025` in a UTF-8 file, then:

```bash
python selective_delta.py expand path/to/selected-run.alcg
python selective_delta.py inspect path/to/selected-run.alcg
python selective_delta.py append path/to/open-prefix.alcg --reading 0
```

`append` is allowed only on valid `OPEN` prefixes. It preserves the original recorded `max_gap` and `min_actions`, but new rounds may change which optional receipts are selected. It cannot append to `STOP`.

All five outputs, metadata, SHA-256 digests, and derivation counts are in `reports/selective-delta-v0.25.json`. The exact published constraints are in `data/selective-profile-v0.25.json`.

## 7. Trust boundaries

- A hash in the record does not give authenticated authorship. Someone who can rewrite the entire synthetic session can recompute all its hashes. External trusted checkpoints or signatures would be additional mechanisms.
- The decoder requires the same public v0.21/v0.22/v0.23 rules and pinned source contents. Omitted fields are **not** understandable without those rules. It is incorrect to describe this version as self-contained.
- Exact byte reconstruction demonstrates implementation fidelity under pinned assumptions, not that the claimed event happened, that an independent AI understood the symbols, or that the policy is good in the real world.
- Corpus selection is small and authored. A realistic benefit requires held-out long sessions, measured compute cost, storage accounting including model distribution, and external reader trials.
- The ALCG public concept dictionary and all earlier experimental results remain unchanged.

**Research boundary:** v0.25 asks what can safely be *derived under a frozen rule set*, not which information can be removed from the underlying epistemic process.
