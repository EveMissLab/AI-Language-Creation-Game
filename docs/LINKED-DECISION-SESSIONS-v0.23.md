# ALCG v0.23 — Linked, Replayable Multi-Round Decision Sessions

**Status:** experimental, executable, profile-specific source specification. **Date:** 2026-11-11. **License:** MIT (repository license).

## Abstract

ALCG v0.22 introduced a single replayable computational *snapshot* but could not verify which prior policies produced a sequence of actions. This v0.23 experiment addresses the narrower problem of connecting ordered decision snapshots into a replayable finite session. The `RUN_V023` profile embeds an initial `TRACE_V022`, followed by index-addressed `ROUND_V023` records. Each round must use the action selected by the previous optimal bounded policy and contains its updated `TRACE_V022`, cumulative evidence, cost and a content-based hash link. The final status explicitly distinguishes a genuine policy `STOP` from an unfinished `OPEN` prefix.

The profile expresses one possible execution path under the already public v0.21 synthetic Bayesian model. It does not change the basic ALCG grammar, published registry, decision algorithm, sensor channel, English vocabulary, or causal model. It is not a new encryption method, a cryptographic authentication scheme, a semantic understanding score, a generic workflow engine, or empirical evidence for any causal law.

## 1. Fixed assumptions and provenance

All calculations are from the frozen v0.21 *asymmetric, session-correlated* synthetic channel, whose prior contains 16 candidate Boolean mechanisms and one persistent session-fault bit (32 joint hypothesis states). Its Boolean observations are deliberately authored. At every step, the planner recomputes exact rational posterior and the bounded STOP/CONTINUE policy using the **remaining future experimental budget** and the original fixed misclassification penalty. Costs are sunk once an action occurs.

Inputs of each session:

- A unique bounded ASCII identifier starting with `R23_`.
- One existing v0.21 family identifier (e.g. `F17_DIRECT`).
- Initial available cost budget 0–4 and loss penalty 0–10,000.
- A bounded, ordered sequence of synthetic `TRUE` / `FALSE` readings. The **action IDs are not arbitrary**: the v0.21 policy selects each next action.
- A frozen v0.22 snapshot format and v0.21 model specification, each reproducible through public artifacts.

Maximum number of recorded actions: **4**, because the initial budget is at most four units and the cheapest supported action costs one. Every session may have fewer actions, either because the decision is `STOP` or because the author saved an `OPEN` prefix.

## 2. Profile schema

The fully executable examples are in `samples/linked-sessions-v0.23.alcg`. The following *non-executable sketch* only shows the shape:

```text
RUN_V023(
  id=R23_EXAMPLE,
  initial=TRACE_V022(...),
  seed_sha256=SHA256(value="<64 lowercase hex>"),
  rounds=ROUNDS_V023(
    r0001=ROUND_V023(
      before=SHA256(value="<64 lowercase hex>"),
      action=NAT(value="3"), reading=TRUE, cost=NAT(value="1"),
      after=TRACE_V022(...),
      chain_sha256=SHA256(value="<64 lowercase hex>")
    )
  ),
  end=END_V023(
    rounds=NAT(value="1"), spent=NAT(value="1"),
    remaining=NAT(value="1"), status=OPEN,
    history_sha256=SHA256(value="<64 lowercase hex>"),
    state_sha256=SHA256(value="<64 lowercase hex>"),
    chain_sha256=SHA256(value="<64 lowercase hex>")
  )
)
```

| Named structure | Required properties |
| --- | --- |
| `RUN_V023` | Exactly `id`, `initial`, `seed_sha256`, `rounds`, `end` |
| `initial` | Valid `TRACE_V022` with no previous observations; pinned v0.21 source and valid initial decision |
| `ROUNDS_V023` | Zero through four `r0001`, `r0002`, ... entries, without gaps or duplicate keys |
| `ROUND_V023` | Previous trace digest, action, Boolean reading, paid action cost, complete `after=TRACE_V022`, and chained digest |
| `END_V023` | Exact number of rounds, spent cost, remaining budget, `STOP` or `OPEN`, and exact final-state, observation-history and chained digests |
| `STOP` | The v0.21 policy has selected `STOP`, not merely that the author ended the file |
| `OPEN` | The v0.21 policy still selects `CONTINUE`; the saved sequence is an explicitly unfinished prefix |

`NAT`, `SHA256`, `TRACE_V022` and the existing named-argument ALCG parser are inherited. `RUN_V023`, `ROUND_V023`, etc. are **new profile labels**, not new basic published language operators. Independent readers who do not implement this profile must not silently pretend to have validated it.

## 3. Exact budget accounting and policy-following constraints

For round $i$ let $b_i$ be the remaining budget, $a_i$ the action the prior snapshot selected and $c(a_i)$ its public integer cost. The next snapshot is valid only when $b_{i+1}=b_i-c(a_i)$ and its evidence equals all previous evidence followed by exactly $(a_i,y_i)$. Its loss penalty, family, synthetic provenance and model fingerprint must remain unchanged.

The updated posterior is recomputed from the full ordered observation sequence using the persistent-fault v0.21 channel; costs are **not charged twice**. The decoder checks all v0.22 rational policy receipts for the initial and every successive snapshot by recomputing canonical expressions from the immutable public rules. It checks cumulative spending and ensures there is no action following a `STOP`.

Important distinction: a valid `OPEN` prefix is **not a completed record**. It is valid to save a partial computation; it is invalid to label it `STOP` if the policy still says `CONTINUE`. The profile does not claim that every possible real-world action obeys the toy optimizer; only policy-following sessions are in scope.

## 4. Content-linked receipts

This profile defines domain-separated SHA-256 digests over canonical UTF-8 JSON with sorted keys and compact separators. The root digest binds the `RUN_V023` session ID and the canonical initial `TRACE_V022` bytes. The digest for round $i$ binds:

1. The `RUN_V023` session ID and a version-specific domain label.
2. The previous chain digest and prior `TRACE_V022` digest.
3. The one-indexed round number, action ID, observed Boolean value and charged cost.
4. The canonical updated `TRACE_V022` digest.

The last round digest becomes the end-of-session chain digest; a zero-round session uses the root digest. This links costs, observations, decisions and the order of state changes. The individual snapshots retain their v0.22 **history digests** and separate **posterior state digests**; neither is interchangeable with the v0.23 link digest.

**Security boundary:** these are unkeyed SHA-256 checksums only. A person who rewrites the entire synthetic history, recalculates all outputs and hashes and replaces any unanchored copy can produce a different internally consistent record. There is no trusted timestamp, signed identity, immutable ledger service, consensus layer, anti-replay guarantee or secrecy. Exact structural replay verifies **internal consistency against pinned rules**, not external authenticity or empirical correctness.

## 5. Reproducibility

No network, external API, secret token, custom font or third-party Python dependency is required. From the repository root, with Python 3.10+:

```bash
python session_language.py check
python session_language.py report
python session_language.py examples
python session_language.py replay --id R23_TWO_ROUNDS
python session_language.py build --id R23_CUSTOM --budget 2 --loss 64 --reading 1 --reading 0
python -m unittest discover -s tests -p test_session_language.py -v
python tests/run_split_suite.py
```

`check` recomputes every saved session and report; `replay` returns the exact per-round state as JSON; `build` encodes a new **synthetic, policy-following** sequence. For independent whole-expression decoding, save one generated line to a UTF-8 file, then use `python session_language.py decode <file>`. Source files and documents remain canonical UTF-8, not copies of chat-rendered output.

## 6. Fixed examples and current findings

Five assistant-authored examples use one of two pinned model families. They contain eight recorded rounds and eight charged synthetic cost units. Four end in `STOP`; one is an `OPEN` prefix. The examples include a two-step `3 → 4` action path, a three-step `3 → 3 → 4` path, a zero-step STOP, and a still-continuing prefix. These are demonstrations of **structured consistency**, not samples of an AI-agent population or independent reader judgments.

The new test suite explicitly modifies actions, observations, intermediate policy results, cumulative costs, previous hashes, end labels, round indexes and model fingerprint references. Any isolated edit without appropriate recalculation is rejected. Independent code paths check exact budget conservation, re-evaluate each stored v0.22 snapshot and compare the expected chain digest at every round.

## 7. Boundaries and interpretation

- There are no empirical sensor measurements, external causal discoveries, or independent AI comprehension results in this release.
- Session IDs and hashes are identifiers and integrity hints, not secure authentication or identity verification.
- The entire chain is intentionally verbose: each complete `TRACE_V022` snapshot is repeated to make self-contained verification easy. Reducing duplication without losing semantics is a later engineering decision.
- The bounded optimizer assumes exact knowledge of its finite model class and hand-authored observation distribution. The real world is not assumed to obey it.
- Even with consistent calculation receipts, identical posterior states can arise from differently ordered observations. Keep separate event history, current state and chain identity.
- Off-policy decisions, mixed model versions, concurrent observers, partial sensor failure not represented by v0.21, and external data provenance are beyond v0.23.

**Conclusion.** A language intended for AI computation must be able to express not just a state or a function name, but *which action was selected from which state, what evidence followed, how the state changed, what the process cost, and why the record stopped.* ALCG v0.23 demonstrates a tiny, deterministic, falsifiable implementation of that requirement without claiming universal AI understanding.
