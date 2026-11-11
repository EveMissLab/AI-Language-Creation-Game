"""ALCG v0.26: bounded storage/checkpoint selection for replayable sessions.

This models *work units* for random state reads; it does NOT benchmark CPU time,
measure a real-world access distribution, or alter ALCG's core language.
All sources and snapshots are pinned to the frozen v0.23-v0.25 protocols.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from alcg import Call, Expr, parse, render, ParseError
import delta_language as v24
import selective_delta as v25
import session_language as v23
import trace_language as v22

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-v0.26-bounded-checkpoint-selection'
DATA_PATH = ROOT / 'data/checkpoint-profiles-v0.26.json'
SAMPLES_PATH = ROOT / 'samples/checkpoint-sessions-v0.26.alcg'
REPORT_PATH = ROOT / 'reports/checkpoint-planner-v0.26.json'
MAX_CHARS = 32000
# Old files must not change silently. The lower-level check also pins v0.23.
PINNED_V025 = {
    'selective_delta.py': 'befc10ee4b0d72f822bf7fa27f69b6a21f3011fbaafebca77a888121d9bbfe5a',
    'data/selective-profile-v0.25.json': '6a7ca226a4bd3125ea148deadce88cd80665466dbe83a883b8816ced1ca838d6',
    'samples/selective-sessions-v0.25.alcg': '762df7e57d8d39de93859913a5d2f63eddafc80e9cf32f310772cbff53e325a0',
    'reports/selective-delta-v0.25.json': 'b13f30352991264abb9da5730da262a6929da80c0e421a50f3e8da9f372ef428',
}


class CheckpointError(ValueError):
    """Invalid model assumptions, noncanonical data, or unreplayable receipt."""


def _check_pins() -> None:
    v25._check_pins()
    for path, expected in PINNED_V025.items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise CheckpointError('frozen v0.25 source changed: ' + path)


def _state(session: v23.Session, index: int) -> v22.Trace:
    if type(index) is not int or not 0 <= index <= len(session.rounds):
        raise CheckpointError('state index out of range')
    return session.initial if index == 0 else session.rounds[index - 1].after


def _check_indices(n: int, indices: Sequence[int]) -> tuple[int, ...]:
    if not isinstance(indices, (tuple, list)):
        raise CheckpointError('checkpoint indices must be a sequence')
    if any(type(i) is not int or not 0 <= i <= n for i in indices):
        raise CheckpointError('checkpoint index out of range')
    result = tuple(indices)
    if tuple(sorted(set(result))) != result:
        raise CheckpointError('checkpoint indices must be strictly increasing')
    return result


@lru_cache(maxsize=16)
def _source_parts(s: v23.Session) -> tuple[str, str, Expr, tuple[Expr, ...]]:
    """Replay and materialize each fixed state once per immutable session."""
    base = v25.encode(s)
    full = v23.encode(s)
    return (base, full, parse(base),
            tuple(parse(v22.encode(_state(s, i))) for i in range(len(s.rounds) + 1)))


def _hybrid_tree(s: v23.Session, indices: tuple[int, ...]) -> Call:
    _, _, base_ast, states = _source_parts(s)
    return Call('CHECKPOINT_RUN_V026', (
        ('base', base_ast),
        ('states', Call('STATES_V026', tuple(
            (f's{i:04d}', states[i]) for i in indices
        ))),
    ))


def encode_hybrid(s: v23.Session, indices: Sequence[int]) -> str:
    if not isinstance(s, v23.Session):
        raise CheckpointError('expected a verified v0.23 session')
    chosen = _check_indices(len(s.rounds), indices)
    if not chosen:
        raise CheckpointError('hybrid encoding requires at least one checkpoint')
    try:
        _check_pins()
        data = render(_hybrid_tree(s, chosen))
        if len(data) > MAX_CHARS:
            raise CheckpointError('checkpoint expression too long')
        return data
    except (v23.SessionError, v25.SelectionError, v22.TraceError, OSError) as exc:
        raise CheckpointError(str(exc)) from exc


def _decoded(source: str) -> tuple[v23.Session, str, tuple[int, ...]]:
    if not isinstance(source, str) or not 0 < len(source) <= MAX_CHARS:
        raise CheckpointError('expected bounded UTF-8 ALCG expression')
    try:
        _check_pins()
        root = parse(source)
        if render(root) != source:
            raise CheckpointError('noncanonical rendering is not a transport receipt')
        if not isinstance(root, Call):
            raise CheckpointError('root must be a named expression')
        if root.name == 'RUN_V023':
            session = v23.decode(source)
            return session, 'full', tuple(range(len(session.rounds) + 1))
        if root.name == 'SELECTIVE_RUN_V025':
            session = v25.decode(source)
            return session, 'selective', ()
        if root.name != 'CHECKPOINT_RUN_V026':
            raise CheckpointError('unsupported ALCG session representation')
        fields = v22._args(root, 'CHECKPOINT_RUN_V026', {'base', 'states'})
        base = render(fields['base'])
        session = v25.decode(base)
        snapshots = v22._args(fields['states'], 'STATES_V026')
        indices = []
        for key in snapshots:
            if (len(key) != 5 or key[0] != 's' or not key[1:].isdigit()):
                raise CheckpointError('invalid state checkpoint label')
            indices.append(int(key[1:]))
        checked = _check_indices(len(session.rounds), indices)
        if not checked:
            raise CheckpointError('hybrid must contain a checkpoint')
        # Full, exact re-rendering catches altered state receipts and ordering.
        expected = render(_hybrid_tree(session, checked))
        if source != expected:
            raise CheckpointError('checkpoint content, base, order or pin mismatch')
        return session, 'hybrid', checked
    except (ParseError, v25.SelectionError, v23.SessionError, v22.TraceError,
            ValueError, RecursionError, OSError) as exc:
        raise CheckpointError(f'nonreplayable v0.26 source: {exc}') from exc


def decode(source: str) -> v23.Session:
    return _decoded(source)[0]


def expand(source: str) -> str:
    """Recreate byte-identical v0.23 RUN from all three storage modes."""
    return v23.encode(decode(source))


def access_state(source: str, index: int) -> str:
    """Return exact TRACE_V022; this implementation validates whole chain first.

    It is *not* a low-latency lazy reader. The planner's work units model a
    possible trusted, post-validation cache, not measured performance here.
    """
    return v22.encode(_state(decode(source), index))


@dataclass(frozen=True)
class Workload:
    reads: tuple[int, ...]
    byte_weight: int = 1
    replay_weight: int = 1
    snapshot_write_weight: int = 0
    byte_budget: int | None = None
    max_lookup_units: int | None = None

    def validate(self, n: int) -> None:
        if not isinstance(self.reads, tuple) or len(self.reads) != n + 1:
            raise CheckpointError('reads must contain one integer per state, including initial')
        if any(type(x) is not int or x < 0 for x in self.reads):
            raise CheckpointError('read frequency must be a nonnegative integer')
        for name in ('byte_weight', 'replay_weight', 'snapshot_write_weight'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise CheckpointError(f'{name} must be a nonnegative integer')
        if self.byte_budget is not None and (type(self.byte_budget) is not int or self.byte_budget < 0):
            raise CheckpointError('byte_budget must be nonnegative integer or null')
        if self.max_lookup_units is not None and (
            type(self.max_lookup_units) is not int or self.max_lookup_units < 0
        ):
            raise CheckpointError('max_lookup_units must be nonnegative integer or null')


@dataclass(frozen=True)
class Plan:
    mode: str
    checkpoints: tuple[int, ...]
    expression: str
    byte_size: int
    read_work_units: int
    max_read_work_units: int
    snapshot_writes: int
    score: int

    def as_json(self) -> dict[str, Any]:
        return {
            'mode': self.mode, 'checkpoints': list(self.checkpoints),
            'utf8_bytes': self.byte_size,
            'weighted_replay_units': self.read_work_units,
            'max_replay_units_for_requested_states': self.max_read_work_units,
            'snapshot_write_units': self.snapshot_writes, 'objective_score': self.score,
            'expression_sha256': sha256(self.expression.encode('utf-8')).hexdigest(),
        }


def _read_units(n: int, checkpoints: tuple[int, ...], frequencies: tuple[int, ...]) -> tuple[int, int]:
    total = 0
    max_units = 0
    for i, count in enumerate(frequencies):
        before = [cp for cp in checkpoints if cp <= i]
        # A state at t=0 requires constructing the initial trace when uncached.
        units = i - before[-1] if before else i + 1
        total += units * count
        if count:
            max_units = max(max_units, units)
    return total, max_units


def _scored(mode: str, checkpoints: tuple[int, ...], body: str,
            config: Workload, n: int) -> Plan:
    bytes_count = len(body.encode('utf-8'))
    if mode == 'full':
        work, max_work = 0, 0
        writes = n + 1
    else:
        work, max_work = _read_units(n, checkpoints, config.reads)
        writes = len(checkpoints)
    return Plan(mode, checkpoints, body, bytes_count, work, max_work,
                writes, (config.byte_weight * bytes_count
                         + config.replay_weight * work
                         + config.snapshot_write_weight * writes))


@lru_cache(maxsize=256)
def candidates(s: v23.Session, config: Workload) -> tuple[Plan, ...]:
    """Exhaust all 2^(rounds+1) bounded checkpoint placements + a full source."""
    if not isinstance(s, v23.Session):
        raise CheckpointError('expected a v0.23 session')
    n = len(s.rounds)
    config.validate(n)
    _check_pins()
    base, full_source, _, _ = _source_parts(s)
    result = []
    for mask in range(1 << (n + 1)):
        indices = tuple(i for i in range(n + 1) if mask & (1 << i))
        mode = 'hybrid' if indices else 'selective'
        body = render(_hybrid_tree(s, indices)) if indices else base
        option = _scored(mode, indices, body, config, n)
        if config.byte_budget is not None and option.byte_size > config.byte_budget:
            continue
        if config.max_lookup_units is not None and option.max_read_work_units > config.max_lookup_units:
            continue
        result.append(option)
    full = _scored('full', tuple(range(n + 1)), full_source, config, n)
    if (config.byte_budget is None or full.byte_size <= config.byte_budget) and (
            config.max_lookup_units is None or full.max_read_work_units <= config.max_lookup_units):
        result.append(full)
    return tuple(result)


def choose(s: v23.Session, config: Workload) -> Plan:
    _check_pins()  # A warmed cache must not hide changes to frozen source files.
    feasible = candidates(s, config)
    if not feasible:
        raise CheckpointError('no representation satisfies declared byte/lookup constraints')
    # All choices have been exhaustively evaluated. Lexical tie is deterministic.
    return min(feasible, key=lambda x: (x.score, x.byte_size,
                                        x.read_work_units, x.mode, x.checkpoints))


def profiles(s: v23.Session) -> dict[str, Workload]:
    n = len(s.rounds)
    base_len = len(v25.encode(s).encode('utf-8'))
    reads_tail = (0,) * n + (80,)
    return {
        'cold_archive': Workload((0,) * (n + 1), 1, 50, 10),
        'hot_tail': Workload(reads_tail, 1, 20, 10),
        'mixed_reads': Workload(tuple(10 * (i + 1) for i in range(n + 1)), 1, 10, 15),
        'storage_limited': Workload(reads_tail, 1, 20, 10, byte_budget=base_len + 100),
        'bounded_latency': Workload(tuple(1 for _ in range(n + 1)), 1, 100, 10,
                                    max_lookup_units=1),
    }


@lru_cache(maxsize=1)
def _sessions() -> tuple[v23.Session, ...]:
    return tuple(v24._sessions())


def fixture_text() -> str:
    lines = [
        '# ALCG v0.26: bounded hybrid checkpoint selection, pinned to v0.23-v0.25.',
        '# One chosen storage expression for each frozen synthetic v0.23 session.',
        '# Scenario: hot_tail; these are not real workload frequencies.',
    ]
    for session in _sessions():
        lines.append(choose(session, profiles(session)['hot_tail']).expression)
    return '\n'.join(lines) + '\n'


def _profile_metadata(s: v23.Session) -> dict[str, Any]:
    return {k: {
        'reads_per_state': list(c.reads), 'byte_weight': c.byte_weight,
        'replay_weight': c.replay_weight, 'snapshot_write_weight': c.snapshot_write_weight,
        'byte_budget': c.byte_budget, 'max_lookup_units': c.max_lookup_units,
    } for k, c in profiles(s).items()}


def model_spec() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'public_registry_updated': False,
        'candidate_representations': ['v0.25 selective', 'v0.26 hybrid with any subset of 0..N state checkpoints', 'v0.23 full'],
        'maximum_rounds': v23.MAX_ROUNDS,
        'scoring': 'byte_weight*real_UTF8_bytes + replay_weight*weighted_abstract_replay_units + snapshot_write_weight*materialized_state_count',
        'replay_unit_model': 'no prior checkpoint -> state_index+1; prior checkpoint j -> state_index-j; stored state -> 0',
        'checkpoint_trust': 'all checkpoint traces and terminal receipts are verified against deterministic v0.23 replay before use',
        'measurement': 'actual source UTF-8 bytes; hypothetical replay work units; no wall-clock benchmarks',
        'full_trace': 'v0.23 RUN includes all states, so modeled read-replay units are 0',
        'initial_state': 'state index 0; round k -> state index k',
        'read_distribution': 'synthetic known integer counts, not a real-world estimate',
        'authentication': False,
        'dependency': 'requires pinned public v0.23-v0.25 sources and canonical ALCG parser',
        'limits': ['Not an online optimizer', 'No cache replacement/paging simulation',
                   'Does not avoid full replay during verification in current implementation',
                   'No proof of real CPU or network efficiency',
                   'Enumeration is bounded by MAX_ROUNDS; not scalable in general'],
    }


def report() -> dict[str, Any]:
    rows = []
    for s in _sessions():
        options = {}
        for name, config in profiles(s).items():
            plan = choose(s, config)
            # One authoritative replay per plan, not N repeated replays per state.
            if decode(plan.expression) != s:
                raise CheckpointError('planned session failed exact verified reconstruction')
            options[name] = {
                'assumptions': _profile_metadata(s)[name],
                'candidate_count': len(candidates(s, config)),
                'selected': plan.as_json(),
            }
        rows.append({
            'id': s.id, 'status': s.status, 'rounds': len(s.rounds),
            'baseline_v025_bytes': len(v25.encode(s).encode('utf-8')),
            'full_v023_bytes': len(v23.encode(s).encode('utf-8')),
            'profiles': options,
        })
    return {
        'format': FORMAT,
        'source_sessions': 'five fixed synthetic v0.23 examples',
        'sessions': len(rows), 'rounds': sum(r['rounds'] for r in rows),
        'profile_definitions': model_spec(),
        'cases': rows,
        'pinned_v025_sha256': PINNED_V025,
        'sample_sha256': sha256(fixture_text().encode('utf-8')).hexdigest(),
        'independent_ai_comprehension_measured': False,
        'real_cpu_time_measured': False,
        'distribution_and_reader_cost_included': False,
    }


def report_text() -> str:
    return json.dumps(report(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def check() -> dict[str, Any]:
    _check_pins()
    if DATA_PATH.read_bytes() != (json.dumps(model_spec(), ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'):
        raise CheckpointError('changed frozen v0.26 model specification')
    if SAMPLES_PATH.read_bytes() != fixture_text().encode('utf-8'):
        raise CheckpointError('changed frozen v0.26 samples')
    r = report()
    if REPORT_PATH.read_bytes() != (json.dumps(r, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'):
        raise CheckpointError('changed frozen v0.26 report')
    return r


def _one_line(path: Path) -> str:
    lines = [l.strip() for l in path.read_text(encoding='utf-8').splitlines()
             if l.strip() and not l.lstrip().startswith('#')]
    if len(lines) != 1:
        raise CheckpointError('file must contain one non-comment ALCG expression')
    return lines[0]


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.26 bounded checkpoint / delta planner')
    commands = cli.add_subparsers(dest='command', required=True)
    commands.add_parser('check')
    commands.add_parser('report')
    commands.add_parser('examples')
    p = commands.add_parser('plan')
    p.add_argument('--session', choices=[s.id for s in _sessions()], required=True)
    p.add_argument('--profile', choices=tuple(profiles(_sessions()[0])), default='hot_tail')
    p = commands.add_parser('expand')
    p.add_argument('file', type=Path)
    p = commands.add_parser('state')
    p.add_argument('file', type=Path)
    p.add_argument('--index', type=int, required=True)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            checked = check()
            print(f"OK v0.26: {checked['sessions']} sessions, {checked['rounds']} rounds")
        elif args.command == 'report':
            print(report_text(), end='')
        elif args.command == 'examples':
            print(fixture_text(), end='')
        elif args.command == 'plan':
            s = next(s for s in _sessions() if s.id == args.session)
            chosen = choose(s, profiles(s)[args.profile])
            print(json.dumps({'session': args.session, 'profile': args.profile,
                              'selected': chosen.as_json(), 'expression': chosen.expression},
                             ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == 'expand':
            print(expand(_one_line(args.file)))
        elif args.command == 'state':
            print(access_state(_one_line(args.file), args.index))
        return 0
    except (CheckpointError, ParseError, OSError, ValueError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
