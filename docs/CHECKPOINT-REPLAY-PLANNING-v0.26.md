# ALCG v0.26 — Bounded Checkpoint / Delta Storage Planning

**Status:** experimental, synthetic, standard-library-only, replayable, not a new public core-language operator. Date: 2026-11-11. License: inherited project MIT.

## Research question

When a verified ALCG computation session may be read repeatedly, under what declared workload and storage constraints should a reader persist complete materialized states rather than relying entirely on deterministic reconstruction from a compact decision history?

This version is deliberately restricted to the five frozen synthetic `RUN_V023` sessions. It does not measure latency on real hardware, the runtime of another AI, network transfer overhead, or semantic comprehension. No existing data file, dictionary, grammar or historical report is changed.

## Three compatible transport alternatives

1. **`selective`** — the complete canonical v0.25 selective delta expression. It stores mandatory observations, model pins and final receipts and derives intermediate states.
2. **`hybrid`** — `CHECKPOINT_RUN_V026(base=SELECTIVE_RUN_V025(...), states=STATES_V026(s0002=TRACE_V022(...), ...))`. The base always retains the full canonical delta information; a checkpoint is an **additional** complete materialized snapshot. It can be placed at state 0 (before any round) or at any later state.
3. **`full`** — the existing v0.23 `RUN_V023` representation, containing initial and every subsequent state. No repackaging into the new root is required.

All modes expand to exactly the same UTF-8 `RUN_V023` bytes. The hybrid decoder requires an exact canonical v0.25 base and checks every embedded `TRACE_V022` against the corresponding recomputed v0.23 state. A final chained receipt remains mandatory. This is content consistency, **not authentication**; a malicious actor who regenerates an entire internally consistent history is not stopped by hashes alone.

## Finite optimization problem

For a session with $n$ experimental rounds, the accessible states are numbered from $0$ through $n$. The planner exhaustively considers all subsets of these $n+1$ checkpoint locations, plus the full v0.23 record. Therefore at most $2^{n+1}+1$ candidate representations are considered. The project limits $n$ to the existing bounded session limit; this is **not** a scalable global compression algorithm.

Given a plan $P$, let $B(P)$ be its actual UTF-8 bytes and $K(P)$ the number of materialized states written. For requested state $i$, the *abstract* reconstruction distance is

$$
d_P(i)=\begin{cases}
0, & \text{if state }i\text{ is materialized},\\
i-j, & \text{if }j\le i\text{ is the latest checkpoint},\\
i+1, & \text{if no earlier checkpoint exists}.
\end{cases}
$$

The initial-state term of one is an explicitly declared unit convention. It is **not** a timing measurement. The full v0.23 representation has $d_P(i)=0$ for each stored state *after verification*.

If $f_i$ is the assumed number of reads of state $i$, the bounded planner minimizes

$$
J(P)=w_B B(P)+w_R\sum_{i=0}^{n}f_i d_P(i)+w_K K(P).
$$

All weights and frequencies are nonnegative integers. The planner may additionally enforce a maximum byte budget and a maximum modeled reconstruction distance for every **requested** state. It exhaustively enumerates feasible plans and breaks ties deterministically. The numerical weights are specified by the chosen synthetic profile, not fitted to measured workloads.

The actual decoder in this version intentionally **validates by replaying the entire history before returning any snapshot**. It does not implement a trusted lazy cache. Thus the `replay_units` above are a hypothetical post-validation access-cost proxy. They must not be reported as verified CPU-time improvements. Full distribution/reader implementation overhead is also not included.

## Fixed synthetic profiles

| Profile | Assumption | Typical result |
|---|---|---|
| `cold_archive` | No requested state reads, storage bytes still matter | Pure v0.25 selective delta |
| `hot_tail` | Repeated reads of the final state, relatively expensive model replay | Hybrid checkpoint at final state; zero-round case chooses full |
| `mixed_reads` | Repeated requests to different intermediate states | Checkpoint at a useful interior state, or pure delta for a short run |
| `storage_limited` | High final-state read count but byte budget only 100 above baseline | Pure selective delta |
| `bounded_latency` | Every state requested; maximum abstract reconstruction distance one | Intermediate checkpoint(s) where needed |

No general workload distribution is inferred from these profiles.

## Fixed-sample results

The five original sessions have eight rounds in total. Each v0.26 profile expands exactly to its original v0.23 source and verifies all v0.25 data pins.

| Session | v0.25 selective bytes | v0.23 full bytes | `hot_tail` selected | Hot-tail bytes | `mixed_reads` selected |
|---|---:|---:|---|---:|---|
| `R23_TWO_ROUNDS` | 890 | 3171 | hybrid checkpoint 2 | 1688 | hybrid checkpoint 1 |
| `R23_THREE_ROUNDS` | 924 | 4254 | hybrid checkpoint 3 | 1774 | hybrid checkpoint 2 |
| `R23_START_STOP` | 828 | 1172 | full v0.23 | 1172 | selective |
| `R23_OPEN_PREFIX` | 859 | 2169 | hybrid checkpoint 1 | 1621 | selective |
| `R23_CONTEXT_FAMILY` | 895 | 3174 | hybrid checkpoint 2 | 1691 | hybrid checkpoint 1 |

In the cold archive profile, all five choose pure selective encoding; in the tight-budget profile all five do too. This is an explicit counterexample to any claim that storing additional snapshots is always preferable. Conversely, a frequently accessed final state may warrant higher storage cost under the selected **hypothetical** work model. There is no claim of real-world throughput, energy, memory or CPU savings.

## Reproduce and inspect

```bash
python checkpoint_planner.py check
python checkpoint_planner.py report
python checkpoint_planner.py plan --session R23_THREE_ROUNDS --profile mixed_reads
python checkpoint_planner.py plan --session R23_START_STOP --profile hot_tail
python checkpoint_planner.py examples
python -m unittest discover -s tests -p 'test_checkpoint_planner.py' -v
```

To expand one saved line, put a canonical v0.25, v0.23, or hybrid expression into one UTF-8 file, then:

```bash
python checkpoint_planner.py expand .local/one-v026.alcg
python checkpoint_planner.py state .local/one-v026.alcg --index 1
```

`expand` regenerates the complete canonical v0.23 history. `state` returns one exact v0.22 trace, **after** full replay verification. This is not an unverified shortcut for random access.

## Validation and failure cases

- Reject missing or modified baseline model pins; reject changed embedded state receipts, unknown checkpoint labels, duplicate or unsorted checkpoint indices, impossible byte budgets and unsupported roots.
- Reject noncanonical transport renderings and any history whose final receipt fails replay.
- Confirm zero-round `STOP` and unfinished `OPEN` sessions retain their original status.
- Compare optimizer results with an independently written brute-force objective calculation for a small case.
- Preserve v0.23–v0.25 historical source bytes and all previous ALCG conformance tests.

## Limitations

The working corpus is small and author-generated; read frequencies, byte weights and work costs are hypothetical; the source and decoder cost are excluded; verification still involves full historical replay; there is no runtime benchmark, cache algorithm, real-world experiment, independent AI language reader, or secure signature protocol. The output is a **bounded transport/storage-planning experiment**, not an optimal policy for arbitrary AI systems.

**Interpretation:** saving enough to reconstruct a state and saving the state itself are different storage decisions. Choosing between them requires both the retrieval demand and the cost of recomputation — not just the minimum number of characters.
