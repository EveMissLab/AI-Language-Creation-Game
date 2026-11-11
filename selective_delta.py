"""ALCG v0.25: cost-aware, reversible selection of redundant per-round receipts.

This is a bounded, pinned, synthetic transport experiment, not a new public
language operator. An observation is never inferred; selected actions and
intermediate chain hashes MAY be recomputed from pinned v0.23 policy rules.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from alcg import Call, Expr, Name, ParseError, parse, render
import delta_language as v24
import session_language as v23
import trace_language as v22

ROOT = Path(__file__).resolve().parent
PROFILE_PATH = ROOT / 'data/selective-profile-v0.25.json'
SAMPLE_PATH = ROOT / 'samples/selective-sessions-v0.25.alcg'
REPORT_PATH = ROOT / 'reports/selective-delta-v0.25.json'
FORMAT = 'ALCG-v0.25-selective-derivable-receipts'
MAX_SOURCE_CHARS = 16000
MAX_GAP = v23.MAX_ROUNDS + 1


class SelectionError(ValueError):
    """Invalid constraints, unsupported field, or nonreplayable receipt."""


def _check_pins() -> None:
    v24._check_pins()


def _validate_constraints(n: int, max_gap: int, min_actions: int) -> None:
    if type(max_gap) is not int or not 1 <= max_gap <= MAX_GAP:
        raise SelectionError(f'max_gap must be an integer in [1,{MAX_GAP}]')
    if type(min_actions) is not int or not 0 <= min_actions <= n:
        raise SelectionError('min_actions must be an integer in [0,round count]')


def _valid_masks(n: int, max_gap: int, min_actions: int, actions: int, links: int) -> bool:
    """Final end.chain_sha256 acts as an obligatory anchor at index n."""
    if actions.bit_count() < min_actions:
        return False
    # A step-n link duplicates the mandatory terminal end-chain receipt.
    if n and links & (1 << (n - 1)):
        return False
    anchored = [0] + [i + 1 for i in range(n - 1) if links & (1 << i)] + [n]
    return all(b - a <= max_gap for a, b in zip(anchored, anchored[1:]))


def _tree(s: v23.Session, max_gap: int, min_actions: int,
          actions: int, links: int) -> Call:
    # Reuse the existing, version-pinned start/end receipts byte-for-byte.
    src = dict(v24._session_tree(s).args)
    steps = []
    for i, r in enumerate(s.rounds):
        fields: list[tuple[str, Expr]] = [
            ('reading', Name('TRUE' if r.reading else 'FALSE')),
        ]
        if actions & (1 << i):
            fields.append(('action', v22.n(r.action)))
        if links & (1 << i):
            fields.append(('link_sha256', v22.sha(r.chain_sha256)))
        steps.append((f'r{i + 1:04d}', Call('STEP_V025', tuple(fields))))
    return Call('SELECTIVE_RUN_V025', (
        ('id', src['id']),
        ('rules', Call('RULES_V025', (
            ('max_gap', v22.n(max_gap)),
            ('min_actions', v22.n(min_actions)),
        ))),
        ('start', src['start']),
        ('steps', Call('STEPS_V025', tuple(steps))),
        ('end', src['end']),
    ))


@lru_cache(maxsize=256)
def _best(s: v23.Session, max_gap: int, min_actions: int) -> tuple[int, int, str]:
    """Exact smallest UTF-8 expression among this bounded 2-bit-per-round family.

    The result is *not* asserted optimal among other languages or encodings.
    """
    n = len(s.rounds)
    _validate_constraints(n, max_gap, min_actions)
    best: tuple[int, str, int, int] | None = None
    for actions in range(1 << n):
        for links in range(1 << n):
            if not _valid_masks(n, max_gap, min_actions, actions, links):
                continue
            body = render(_tree(s, max_gap, min_actions, actions, links))
            # Explicit byte length and lexicographic deterministic tie break.
            candidate = (len(body.encode('utf-8')), body, actions, links)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        raise SelectionError('no feasible selection plan')
    return best[2], best[3], best[1]


def encode(s: v23.Session, max_gap: int = MAX_GAP, min_actions: int = 0,
           byte_budget: int | None = None) -> str:
    if not isinstance(s, v23.Session):
        raise SelectionError('encode requires a validated v0.23 Session')
    _validate_constraints(len(s.rounds), max_gap, min_actions)
    _check_pins()
    try:
        v23.encode(s)  # Replay and verify the supplied complete session.
        text = _best(s, max_gap, min_actions)[2]
        if not 0 < len(text) <= MAX_SOURCE_CHARS:
            raise SelectionError('expression exceeds bounded source length')
        if byte_budget is not None:
            if type(byte_budget) is not int or byte_budget < 0:
                raise SelectionError('byte_budget must be a nonnegative integer')
            if len(text.encode('utf-8')) > byte_budget:
                raise SelectionError('no feasible encoding within the byte budget')
        return text
    except (v23.SessionError, v24.DeltaError, v22.TraceError, OSError) as exc:
        raise SelectionError(str(exc)) from exc


def _read(source: str) -> tuple[v23.Session, int, int, Expr]:
    root = parse(source)
    fields = v22._args(root, 'SELECTIVE_RUN_V025',
                       {'id', 'rules', 'start', 'steps', 'end'})
    rule = v22._args(fields['rules'], 'RULES_V025', {'max_gap', 'min_actions'})
    gap = v22._uint(rule['max_gap'], 'max_gap')
    min_actions = v22._uint(rule['min_actions'], 'min_actions')
    run_id = v22._name(fields['id'], 'id')
    start = v22._args(fields['start'], 'START_V024',
                      {'family','budget','loss','origin','protocol',
                       'profile_sha256','seed_sha256'})
    family = v22._name(start['family'], 'family')
    budget = v22._uint(start['budget'], 'budget')
    loss = v22._uint(start['loss'], 'loss')
    rounds = v22._args(fields['steps'], 'STEPS_V025')
    if len(rounds) > v23.MAX_ROUNDS:
        raise SelectionError('too many rounds')
    _validate_constraints(len(rounds), gap, min_actions)
    readings: list[bool] = []
    for i in range(1, len(rounds) + 1):
        key = f'r{i:04d}'
        if key not in rounds:
            raise SelectionError('non-contiguous round identifiers')
        one = v22._args(rounds[key], 'STEP_V025')
        if not {'reading'} <= set(one) <= {'reading','action','link_sha256'}:
            raise SelectionError('unsupported step keys')
        tag = v22._name(one['reading'], f'reading {i}')
        if tag not in ('TRUE', 'FALSE'):
            raise SelectionError('reading must be TRUE or FALSE')
        readings.append(tag == 'TRUE')
    # Exact replay is the authority for all omitted fields and frozen pins.
    s = v23.build(run_id, family, budget, loss, readings)
    return s, gap, min_actions, root


def decode(source: str) -> v23.Session:
    if not isinstance(source, str) or not 0 < len(source) <= MAX_SOURCE_CHARS:
        raise SelectionError('expected one bounded ALCG selective expression')
    try:
        _check_pins()
        s, gap, min_actions, root = _read(source)
        selected = _best(s, gap, min_actions)[2]
        if v22._normal(parse(selected)) != v22._normal(root):
            raise SelectionError('changed receipt, noncanonical plan or stale replay')
        return s
    except (ParseError, v23.SessionError, v24.DeltaError, v22.TraceError,
            RecursionError, ValueError, OSError) as exc:
        raise SelectionError(f'invalid v0.25 expression: {exc}') from exc


def expand(source: str) -> str:
    """Recreate byte-identical canonical RUN_V023 with all intermediate states."""
    return v23.encode(decode(source))


def pack(full_source: str, max_gap: int = MAX_GAP,
         min_actions: int = 0, byte_budget: int | None = None) -> str:
    try:
        return encode(v23.decode(full_source), max_gap, min_actions, byte_budget)
    except (v23.SessionError, v22.TraceError) as exc:
        raise SelectionError(str(exc)) from exc


def append(source: str, reading: bool) -> str:
    """Extend one OPEN prefix without weakening its recorded audit constraints."""
    if type(reading) is not bool:
        raise SelectionError('reading must be an explicit Boolean')
    prior = decode(source)
    if prior.status != 'OPEN':
        raise SelectionError('cannot append after STOP')
    _, gap, min_actions, _ = _read(source)
    try:
        later = v23.build(prior.id, prior.initial.family, prior.initial.budget,
                          prior.initial.loss,
                          [r.reading for r in prior.rounds] + [reading])
        if later.rounds[:len(prior.rounds)] != prior.rounds:
            raise SelectionError('existing prefix changed during append')
        return encode(later, gap, min_actions)
    except (v23.SessionError, v22.TraceError) as exc:
        raise SelectionError(str(exc)) from exc


def policy_cases() -> list[tuple[str, int, int]]:
    """The profiles are *constraints*, never unverified claims of optimality."""
    return [('lean', MAX_GAP, 0),
            ('review', 2, 1),
            ('audit', 1, -1)]  # audit's -1 means every round has visible action


def _profiles(s: v23.Session) -> list[tuple[str, int, int]]:
    return [(name, gap, len(s.rounds) if acts == -1 else min(acts, len(s.rounds)))
            for name, gap, acts in policy_cases()]


def profile_spec() -> dict[str, Any]:
    return {
        'format': FORMAT,
        'public_registry_updated': False,
        'source_sessions': 'data/linked-sessions-v0.23.json',
        'constraints': {
            'lean': {'max_gap': MAX_GAP, 'min_visible_actions': 0},
            'review': {'max_gap': 2, 'min_visible_actions': 'min(1, round count)'},
            'audit': {'max_gap': 1, 'min_visible_actions': 'all rounds'},
        },
        'fields_never_removed': ['reading', 'initial model/policy pins',
                                  'budget/loss', 'final chain/state/history receipts'],
        'optional_per_step_fields': ['policy-selected action', 'intermediate v0.23 chain SHA-256'],
        'selection_method': 'exhaustively minimize UTF-8 length within this bounded candidate family',
        'authentication': False,
        'requires_frozen_public_v023_rules': True,
    }


def profile_text() -> str:
    return json.dumps(profile_spec(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def fixture_text() -> str:
    lines = [
        '# v0.25 selected-derivation representation for frozen synthetic v0.23 sessions.',
        '# Review profile: max_gap=2, at least one visible action if rounds exist.',
    ]
    for s in v24._sessions():
        _, gap, ma = _profiles(s)[1]
        lines.append(encode(s, gap, ma))
    return '\n'.join(lines) + '\n'


def report() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for s in v24._sessions():
        legacy = v24.encode(s)
        full = v23.encode(s)
        trial = {}
        for name, gap, ma in _profiles(s):
            a, h, expr = _best(s, gap, ma)
            # Ensure every candidate can be expanded to frozen v0.23 bytes.
            if expand(expr) != full:
                raise SelectionError('selected profile failed byte-exact expansion')
            trial[name] = {
                'max_gap': gap, 'min_actions': ma,
                'utf8_bytes': len(expr.encode('utf-8')),
                'stored_readings': len(s.rounds),
                'stored_action_receipts': a.bit_count(),
                'stored_step_chain_receipts': h.bit_count(),
                'derived_actions': len(s.rounds) - a.bit_count(),
                'derived_step_chain_receipts': len(s.rounds) - h.bit_count(),
                'source_sha256': sha256(expr.encode('utf-8')).hexdigest(),
                'exact_v023_expansion': True,
            }
        cases.append({'id': s.id, 'status': s.status, 'rounds': len(s.rounds),
                      'full_v023_bytes': len(full.encode('utf-8')),
                      'legacy_v024_bytes': len(legacy.encode('utf-8')),
                      'profiles': trial})
    total = lambda key: sum(x['profiles'][key]['utf8_bytes'] for x in cases)
    return {
        'format': FORMAT,
        'source': 'five frozen synthetic v0.23 sessions, not general language statistics',
        'cases': len(cases),
        'rounds': sum(x['rounds'] for x in cases),
        'full_v023_bytes': sum(x['full_v023_bytes'] for x in cases),
        'legacy_v024_bytes': sum(x['legacy_v024_bytes'] for x in cases),
        'profile_totals': {p[0]: total(p[0]) for p in policy_cases()},
        'profile_savings_vs_v024': {
            p[0]: sum(x['legacy_v024_bytes'] for x in cases) - total(p[0])
            for p in policy_cases()
        },
        'per_case': cases,
        'pinned_v023_sha256': dict(v24.PINNED_V023),
        'fixture_sha256': sha256(fixture_text().encode('utf-8')).hexdigest(),
        'finite_exhaustive_search_over_optional_action_and_step_hash_fields': True,
        'mandatory': ['each new observed Boolean', 'source model/policy pins',
                      'initial budget/loss', 'final history/state/chain receipts'],
        'derivable_under_pins': ['chosen action', 'intermediate chain hash',
                                 'Bayesian state, cost debit and policy recommendation'],
        'real_world_or_independent_ai_test': False,
        'measured_replay_time': False,
        'fully_self_contained_without_public_rules': False,
        'cryptographic_authentication_or_tamper_proof': False,
        'distribution_cost_included': False,
        'limits': [
            'Shortest among four optional action/hash flags per round under declared constraints, not globally optimal compression.',
            'All profiles require the same deterministic pinned v0.23 replay; saved bytes do not prove saved CPU time.',
            'Per-step action/hash copies support direct inspection or fault localization but are not secure signatures.',
            'The terminal chain digest remains mandatory in all profiles; it is not a trusted external signature.',
            'The synthetic corpus contains only five sessions (0 to 3 rounds), not a representative workload.',
        ],
    }


def report_text() -> str:
    return json.dumps(report(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def check() -> dict[str, Any]:
    _check_pins()
    if PROFILE_PATH.read_bytes() != profile_text().encode('utf-8'):
        raise SelectionError('stored profile registry differs from canonical constraints')
    if SAMPLE_PATH.read_bytes() != fixture_text().encode('utf-8'):
        raise SelectionError('frozen samples differ from reproducible source')
    r = report()
    if REPORT_PATH.read_bytes() != (json.dumps(r, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode('utf-8'):
        raise SelectionError('stored report differs from reproducible source')
    for line in SAMPLE_PATH.read_text('utf-8').splitlines():
        if line and not line.startswith('#'):
            if encode(decode(line), 2, min(1, len(decode(line).rounds))) != line:
                raise SelectionError('sample is not canonical')
    return r


def _one_line(path: Path) -> str:
    lines = [line.strip() for line in path.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1:
        raise SelectionError('expected exactly one expression in file')
    return lines[0]


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.25 selective storage of derived receipts')
    cmd = cli.add_subparsers(dest='command', required=True)
    cmd.add_parser('check')
    cmd.add_parser('report')
    cmd.add_parser('examples')
    pack_cmd = cmd.add_parser('pack', help='pack one RUN_V023 expression')
    pack_cmd.add_argument('file', type=Path)
    pack_cmd.add_argument('--max-gap', type=int, default=MAX_GAP)
    pack_cmd.add_argument('--min-actions', type=int, default=0)
    pack_cmd.add_argument('--byte-budget', type=int)
    expanded = cmd.add_parser('expand', help='exactly restore one RUN_V023')
    expanded.add_argument('file', type=Path)
    look = cmd.add_parser('inspect', help='validate and show full session JSON')
    look.add_argument('file', type=Path)
    add = cmd.add_parser('append', help='append one observation to an OPEN prefix')
    add.add_argument('file', type=Path)
    add.add_argument('--reading', choices=('0', '1'), required=True)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            r = check()
            print(f"OK v0.25: {r['cases']} frozen sessions; "
                  f"lean={r['profile_totals']['lean']} bytes; "
                  f"v0.24={r['legacy_v024_bytes']} bytes")
        elif args.command == 'report':
            print(report_text(), end='')
        elif args.command == 'examples':
            print(fixture_text(), end='')
        elif args.command == 'pack':
            print(pack(_one_line(args.file), args.max_gap, args.min_actions, args.byte_budget))
        elif args.command == 'expand':
            print(expand(_one_line(args.file)))
        elif args.command == 'inspect':
            print(json.dumps(decode(_one_line(args.file)).as_json(), ensure_ascii=False, sort_keys=True, indent=2))
        elif args.command == 'append':
            print(append(_one_line(args.file), args.reading == '1'))
        return 0
    except (SelectionError, OSError, ValueError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
