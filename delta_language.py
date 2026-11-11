"""ALCG v0.24: replayable delta transport for frozen v0.23 synthetic sessions.

An incremental *representation* profile, not a new public core operator.
Each step stores only the action, observation and preserved v0.23 chain digest;
all exact Bayesian states, costs and policy decisions are recomputed from pins.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from alcg import Call, Name, ParseError, Expr, parse, render
import session_language as v23
import trace_language as v22

ROOT = Path(__file__).resolve().parent
SAMPLES_PATH = ROOT / 'samples' / 'delta-sessions-v0.24.alcg'
REPORT_PATH = ROOT / 'reports' / 'delta-sessions-v0.24.json'
FORMAT = 'ALCG-v0.24-replayable-delta-session'
MAX_SOURCE_CHARS = 16000
MAX_ROUNDS = v23.MAX_ROUNDS
# Frozen source versions: v0.24 is a transport for v0.23, not a rewrite.
PINNED_V023 = {
    'session_language.py': '08e4ffb15fd301aa1897e803dd893f1e05c9f524481a98ef3bb081c45a6742f2',
    'data/linked-sessions-v0.23.json': '227e60504d707c4073e3ada2924b38a93c77f9fde49dfa979432623c682191ed',
    'samples/linked-sessions-v0.23.alcg': '190e7f2a6b2efd045e635c6496f8e10da0522962263bf0b1752671561ad68098',
    'reports/linked-sessions-v0.23.json': '881acf9b453d87c7390c877d4fe774c47ef0dc2f4bd84d67099c04c0c397c6c5',
}


class DeltaError(ValueError):
    """Invalid incremental transport, divergent replay or changed pinned source."""


def _check_pins() -> None:
    for name, expected in PINNED_V023.items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise DeltaError('frozen v0.23 source changed: ' + name)
    v23._check_pins()


def _session_tree(s: v23.Session) -> Call:
    start = Call('START_V024', (
        ('family', Name(s.initial.family)),
        ('budget', v22.n(s.initial.budget)),
        ('loss', v22.n(s.initial.loss)),
        ('origin', Name('SYNTHETIC')),
        ('protocol', Name(v22.PROFILE)),
        ('profile_sha256', v22.sha(s.initial.spec_sha256)),
        ('seed_sha256', v22.sha(s.seed_sha256)),
    ))
    steps = Call('STEPS_V024', tuple((f'r{r.index:04d}',
                                    Call('STEP_V024', (
                                        ('action', v22.n(r.action)),
                                        ('reading', Name('TRUE' if r.reading else 'FALSE')),
                                        ('link_sha256', v22.sha(r.chain_sha256)),
                                    ))) for r in s.rounds))
    end = Call('END_V024', (
        ('rounds', v22.n(len(s.rounds))),
        ('spent', v22.n(s.total_spent)),
        ('remaining', v22.n(s.remaining)),
        ('status', Name(s.status)),
        ('history_sha256', v22.sha(s.final_history_sha256)),
        ('state_sha256', v22.sha(s.final_state_sha256)),
        ('chain_sha256', v22.sha(s.final_chain_sha256)),
    ))
    return Call('DELTA_RUN_V024', (
        ('id', Name(s.id)), ('start', start), ('steps', steps), ('end', end),
    ))


def encode(session: v23.Session) -> str:
    """Encode only if the complete v0.23 session can be recomputed exactly."""
    if not isinstance(session, v23.Session):
        raise DeltaError('expected one v0.23 Session')
    _check_pins()
    try:
        # v0.23 encode rejects forged receipts, incorrect cost or invalid chains.
        v23.encode(session)
        output = render(_session_tree(session))
        if not 0 < len(output) <= MAX_SOURCE_CHARS:
            raise DeltaError('delta expression exceeds bounded length')
        return output
    except (v23.SessionError, v22.TraceError, OSError) as exc:
        raise DeltaError(str(exc)) from exc


def _inputs(tree: Expr) -> tuple[str, str, int, int, list[bool]]:
    root = v22._args(tree, 'DELTA_RUN_V024', {'id','start','steps','end'})
    run_id = v22._name(root['id'], 'id')
    start = v22._args(root['start'], 'START_V024',
                      {'family','budget','loss','origin','protocol',
                       'profile_sha256','seed_sha256'})
    if v22._name(start['origin'], 'origin') != 'SYNTHETIC':
        raise DeltaError('non-synthetic source unsupported')
    if v22._name(start['protocol'], 'protocol') != v22.PROFILE:
        raise DeltaError('wrong or unsupported inference protocol')
    family = v22._name(start['family'], 'family')
    budget = v22._uint(start['budget'], 'initial budget')
    loss = v22._uint(start['loss'], 'classification loss')
    steps = v22._args(root['steps'], 'STEPS_V024')
    if len(steps) > MAX_ROUNDS:
        raise DeltaError('too many steps')
    readings = []
    for i in range(1, len(steps) + 1):
        key = f'r{i:04d}'
        if key not in steps:
            raise DeltaError('steps must be contiguous, starting at r0001')
        one = v22._args(steps[key], 'STEP_V024',
                         {'action','reading','link_sha256'})
        v22._uint(one['action'], f'action {i}')
        y = v22._name(one['reading'], f'reading {i}')
        if y not in ('TRUE', 'FALSE'):
            raise DeltaError('readings must be TRUE or FALSE')
        readings.append(y == 'TRUE')
    # The exact receipts are checked after rebuilding the session below.
    v22._args(root['end'], 'END_V024',
               {'rounds','spent','remaining','status',
                'history_sha256','state_sha256','chain_sha256'})
    return run_id, family, budget, loss, readings


def decode(source: str) -> v23.Session:
    """Strictly validate fields, replay all decisions and verify each step hash."""
    if not isinstance(source, str) or not 0 < len(source) <= MAX_SOURCE_CHARS:
        raise DeltaError('expected one bounded ALCG delta expression')
    try:
        _check_pins()
        tree = parse(source)
        run_id, family, budget, loss, readings = _inputs(tree)
        expected = v23.build(run_id, family, budget, loss, readings)
        if v22._normal(tree) != v22._normal(_session_tree(expected)):
            raise DeltaError('delta, pinned protocol, policy, hashes or final state do not replay')
        return expected
    except (ParseError, v23.SessionError, v22.TraceError,
            RecursionError, OSError, ValueError) as exc:
        raise DeltaError(f'invalid v0.24 delta: {exc}') from exc


def expand(source: str) -> str:
    """Return complete byte-canonical RUN_V023, not an approximate summary."""
    return v23.encode(decode(source))


def pack(full_source: str) -> str:
    """Convert one validated full RUN_V023 expression to equivalent delta."""
    try:
        return encode(v23.decode(full_source))
    except (v23.SessionError, v22.TraceError) as exc:
        raise DeltaError(str(exc)) from exc


def append(source: str, reading: bool) -> str:
    """Append exactly one policy-selected action; forbid append after STOP."""
    if type(reading) is not bool:
        raise DeltaError('new observation must be an explicit Boolean')
    prefix = decode(source)
    if prefix.status != 'OPEN':
        raise DeltaError('cannot append after a STOP decision')
    new = v23.build(prefix.id, prefix.initial.family,
                    prefix.initial.budget, prefix.initial.loss,
                    [r.reading for r in prefix.rounds] + [reading])
    if (new.seed_sha256 != prefix.seed_sha256 or
            new.rounds[:len(prefix.rounds)] != prefix.rounds):
        raise DeltaError('previous prefix changed during append')
    return encode(new)


@lru_cache(maxsize=1)
def _sessions() -> tuple[v23.Session, ...]:
    return tuple(v23._build_case(case) for case in v23._cases())


def fixture_text() -> str:
    _check_pins()
    lines = [
        '# ALCG v0.24 delta transport for the frozen v0.23 synthetic sessions.',
        '# Each non-comment line is a standalone DELTA_RUN_V024 expression.',
    ]
    lines.extend(encode(s) for s in _sessions())
    return '\n'.join(lines) + '\n'


def report() -> dict[str, Any]:
    _check_pins()
    records = []
    for session in _sessions():
        full = v23.encode(session)
        short = encode(session)
        replayed = expand(short)
        if full != replayed:
            raise DeltaError('expanded delta does not equal frozen full record')
        records.append({
            'id': session.id, 'rounds': len(session.rounds),
            'status': session.status,
            'full_v023_utf8_bytes': len(full.encode('utf-8')),
            'delta_v024_utf8_bytes': len(short.encode('utf-8')),
            'saved_utf8_bytes': len(full.encode('utf-8')) - len(short.encode('utf-8')),
            'final_state_sha256': session.final_state_sha256,
            'final_history_sha256': session.final_history_sha256,
            'v023_and_v024_final_chain_sha256': session.final_chain_sha256,
            'byte_exact_expansion': True,
        })
    raw = sum(row['full_v023_utf8_bytes'] for row in records)
    compact = sum(row['delta_v024_utf8_bytes'] for row in records)
    return {
        'format': FORMAT,
        'source': 'five frozen author-selected synthetic v0.23 sessions',
        'cases': len(records),
        'rounds': sum(row['rounds'] for row in records),
        'stop_sessions': sum(row['status'] == 'STOP' for row in records),
        'open_prefixes': sum(row['status'] == 'OPEN' for row in records),
        'total_full_utf8_bytes': raw,
        'total_delta_utf8_bytes': compact,
        'saved_utf8_bytes': raw - compact,
        'reduction_percent': round(100 * (raw - compact) / raw, 3),
        'per_case': records,
        'pinned_v023_sha256': dict(PINNED_V023),
        'fixture_sha256': sha256(fixture_text().encode('utf-8')).hexdigest(),
        'same_v023_end_chain': True,
        'portable_without_pinned_rules': False,
        'dictionary_distribution_cost_included': False,
        'independent_ai_comprehension_measured': False,
        'real_sensor_data': False,
        'authenticated_against_rewritten_full_chain': False,
        'limits': [
            'Delta decoding requires the exact public v0.21 model and v0.22/v0.23 replay rules.',
            'An OPEN prefix is a valid partial record but does not assert STOP.',
            'All examples use fixed synthetic observations and bounded policy-following actions.',
            'Hashes show internal consistency, not real-world provenance or secure authentication.',
            'Byte comparisons count per-record UTF-8 text, excluding code/rule distribution.',
        ],
    }


def report_text() -> str:
    return json.dumps(report(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def check() -> dict[str, Any]:
    _check_pins()
    fixture = fixture_text().encode('utf-8')
    if SAMPLES_PATH.read_bytes() != fixture:
        raise DeltaError('delta sample bytes differ from canonical replay')
    expected = report_text().encode('utf-8')
    if REPORT_PATH.read_bytes() != expected:
        raise DeltaError('delta report bytes differ from canonical replay')
    for line in SAMPLES_PATH.read_text('utf-8').splitlines():
        if line and not line.startswith('#'):
            if encode(decode(line)) != line or pack(expand(line)) != line:
                raise DeltaError('sample delta does not roundtrip byte exactly')
    return report()


def _single_line(path: Path) -> str:
    lines = [line for line in path.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1:
        raise DeltaError('expected exactly one non-comment expression in file')
    return lines[0]


def main(argv: list[str] | None = None) -> int:
    cmd = argparse.ArgumentParser(description='ALCG v0.24 replayable delta session transport')
    sub = cmd.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    sub.add_parser('report')
    sub.add_parser('examples')
    one = sub.add_parser('replay', help='return full verified v0.23 JSON state for a saved case')
    one.add_argument('--id', required=True)
    for op in ('expand', 'pack', 'decode'):
        p = sub.add_parser(op)
        p.add_argument('file', type=Path)
    a = sub.add_parser('append')
    a.add_argument('file', type=Path)
    a.add_argument('--reading', choices=('0', '1'), required=True)
    args = cmd.parse_args(argv)
    try:
        if args.command == 'check':
            x = check()
            print(f"OK v0.24: {x['cases']} cases, {x['rounds']} rounds, "
                  f"{x['saved_utf8_bytes']} UTF-8 bytes saved in frozen corpus")
        elif args.command == 'report':
            print(report_text(), end='')
        elif args.command == 'examples':
            print(fixture_text(), end='')
        elif args.command == 'replay':
            x = [s for s in _sessions() if s.id == args.id]
            if len(x) != 1:
                raise DeltaError('unknown example case ID')
            print(json.dumps(x[0].as_json(), ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == 'pack':
            print(pack(_single_line(args.file)))
        elif args.command == 'expand':
            print(expand(_single_line(args.file)))
        elif args.command == 'decode':
            print(json.dumps(decode(_single_line(args.file)).as_json(),
                             ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(append(_single_line(args.file), args.reading == '1'))
        return 0
    except (DeltaError, v23.SessionError, v22.TraceError, OSError, ValueError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
