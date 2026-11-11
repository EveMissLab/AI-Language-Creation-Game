"""ALCG v0.23: linked, replayable multi-round synthetic decision sessions.

Profile extension only: no new published core language operator, no empirical
sensor evidence, no cryptographic authentication, no independent AI reading test.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from functools import lru_cache
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from alcg import Call, Name, Expr, ParseError, parse, render
import trace_language as t22
import correlated_design as v21

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / 'data' / 'linked-sessions-v0.23.json'
SAMPLES_PATH = ROOT / 'samples' / 'linked-sessions-v0.23.alcg'
REPORT_PATH = ROOT / 'reports' / 'linked-sessions-v0.23.json'
FORMAT = 'ALCG-v0.23-linked-decision-session'
MAX_ROUNDS = v21.MAX_PLANNING_BUDGET
MAX_CHARS = 100000
_ID = re.compile(r'^R23_[A-Z0-9_]{1,36}$')
PINNED_V022_SAMPLE_SHA256 = 'a19e3a6a6c2af32630abaed6f7db75f7cac2442c19ce55e07ca6f8de40acf640'
PINNED_V022_REPORT_SHA256 = 'e9ee27dd9c1c8635489554af2bb04672a1de161dc7f42144e98c883690d79dfd'
PINNED_V022_CASES_SHA256 = '5c53caec985932773a477123d37edee664a58f69a282a38502ce0d3ad37645b2'


class SessionError(ValueError):
    """Invalid chained session, changed receipt or incoherent experiment history."""


def _check_pins() -> None:
    for path, expected in ((t22.SAMPLES_PATH, PINNED_V022_SAMPLE_SHA256),
                           (t22.REPORT_PATH, PINNED_V022_REPORT_SHA256),
                           (t22.CASES_PATH, PINNED_V022_CASES_SHA256)):
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise SessionError(f'pinned v0.22 source changed: {path.name}')


def _sha(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest()


def _hash_json(document: dict) -> str:
    return _sha(json.dumps(document, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':')))


@lru_cache(maxsize=2048)
def _trace_hash(trace: t22.Trace) -> str:
    return _sha(t22.encode(trace))


@lru_cache(maxsize=512)
def _cached_snapshot(family: str, evidence: tuple[tuple[int,bool], ...], budget: int, loss: int) -> t22.Trace:
    obs = [{'action_id': act, 'observed_Y': y} for act, y in evidence]
    return t22.build(family, obs, budget, loss)


def _snapshot(family: str, evidence: list[dict], budget: int, loss: int) -> t22.Trace:
    return _cached_snapshot(family, tuple((x['action_id'], x['observed_Y']) for x in evidence), budget, loss)


def _seed(run_id: str, initial: t22.Trace) -> str:
    return _hash_json({'domain': FORMAT + '/seed', 'id': run_id,
                       'initial_sha256': _trace_hash(initial)})


def _link(run_id: str, previous_chain: str, before: t22.Trace,
          index: int, action: int, reading: bool, cost: int,
          after: t22.Trace) -> str:
    return _hash_json({'domain': FORMAT + '/round', 'id': run_id,
                       'previous_chain_sha256': previous_chain,
                       'before_trace_sha256': _trace_hash(before),
                       'round': index, 'action': action, 'observed_Y': reading,
                       'cost': cost, 'after_trace_sha256': _trace_hash(after)})


@dataclass(frozen=True)
class Round:
    index: int
    before_trace_sha256: str
    action: int
    reading: bool
    cost: int
    after: t22.Trace
    chain_sha256: str


@dataclass(frozen=True)
class Session:
    id: str
    initial: t22.Trace
    seed_sha256: str
    rounds: tuple[Round, ...]
    total_spent: int
    remaining: int
    status: str
    final_history_sha256: str
    final_state_sha256: str
    final_chain_sha256: str

    def as_json(self) -> dict:
        return {
            'format': FORMAT, 'id': self.id, 'source': 'SYNTHETIC',
            'family': self.initial.family,
            'initial_budget': self.initial.budget, 'loss': self.initial.loss,
            'profile_sha256': self.initial.spec_sha256,
            'seed_sha256': self.seed_sha256,
            'initial_trace_sha256': _trace_hash(self.initial),
            'rounds': [
                {'index': r.index, 'before_trace_sha256': r.before_trace_sha256,
                 'action': r.action, 'observed_Y': r.reading, 'cost': r.cost,
                 'after_trace_sha256': _trace_hash(r.after),
                 'after': r.after.as_json(), 'chain_sha256': r.chain_sha256}
                for r in self.rounds],
            'total_spent': self.total_spent, 'remaining_budget': self.remaining,
            'status': self.status, 'final_history_sha256': self.final_history_sha256,
            'final_state_sha256': self.final_state_sha256,
            'final_chain_sha256': self.final_chain_sha256,
        }


def build(run_id: str, family: str, budget: int, loss: int,
          readings: Sequence[bool]) -> Session:
    """Replay actual v0.21 policy at each round; actions are *not* user chosen."""
    if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
        raise SessionError('session ID must have R23_ prefix and bounded ASCII form')
    if not isinstance(readings, (list, tuple)) or len(readings) > MAX_ROUNDS:
        raise SessionError('round count exceeds supported bounded budget')
    if any(type(y) is not bool for y in readings):
        raise SessionError('readings must be explicit Boolean values')
    try:
        _check_pins()
        # Always check pinned inputs even when a prior snapshot is cached.
        v21.pinned_rows()
        initial = _snapshot(family, [], budget, loss)
        current = initial
        obs = []
        spent = 0
        link = _seed(run_id, initial)
        rounds = []
        for i, y in enumerate(readings, 1):
            if current.decision != 'CONTINUE' or current.next_action is None:
                raise SessionError(f'cannot append round {i} after a STOP decision')
            action = current.next_action
            cost = v21.action_cost(action)
            if cost > current.budget:
                raise SessionError('policy selected an action beyond remaining budget')
            obs.append({'action_id': action, 'observed_Y': y})
            after = _snapshot(family, obs, current.budget-cost, loss)
            next_link = _link(run_id, link, current, i, action, y, cost, after)
            rounds.append(Round(i, _trace_hash(current), action, y, cost, after, next_link))
            current = after
            link = next_link
            spent += cost
        if spent + current.budget != initial.budget:
            raise SessionError('budget conservation violated')
        return Session(run_id, initial, _seed(run_id, initial), tuple(rounds),
                       spent, current.budget,
                       'STOP' if current.decision == 'STOP' else 'OPEN',
                       current.history_sha256, current.state_sha256, link)
    except (t22.TraceError, v21.ChannelError, OSError, json.JSONDecodeError) as exc:
        raise SessionError(str(exc)) from exc


def _tree(s: Session) -> Call:
    rounds = Call('ROUNDS_V023', tuple(
        (f'r{r.index:04d}', Call('ROUND_V023', (
            ('before', t22.sha(r.before_trace_sha256)),
            ('action', t22.n(r.action)),
            ('reading', Name('TRUE' if r.reading else 'FALSE')),
            ('cost', t22.n(r.cost)),
            ('after', parse(t22.encode(r.after))),
            ('chain_sha256', t22.sha(r.chain_sha256)),
        ))) for r in s.rounds))
    final = Call('END_V023', (
        ('rounds', t22.n(len(s.rounds))),
        ('spent', t22.n(s.total_spent)),
        ('remaining', t22.n(s.remaining)),
        ('status', Name(s.status)),
        ('history_sha256', t22.sha(s.final_history_sha256)),
        ('state_sha256', t22.sha(s.final_state_sha256)),
        ('chain_sha256', t22.sha(s.final_chain_sha256)),
    ))
    return Call('RUN_V023', (
        ('id', Name(s.id)),
        ('initial', parse(t22.encode(s.initial))),
        ('seed_sha256', t22.sha(s.seed_sha256)),
        ('rounds', rounds),
        ('end', final),
    ))


def encode(session: Session) -> str:
    if not isinstance(session, Session):
        raise SessionError('encode requires a Session')
    expected = build(session.id, session.initial.family, session.initial.budget,
                     session.initial.loss, [r.reading for r in session.rounds])
    if expected != session:
        raise SessionError('session cannot be replayed or is inconsistent')
    result = render(_tree(session))
    if len(result) > MAX_CHARS:
        raise SessionError('session payload too long')
    return result


def decode(source: str) -> Session:
    if not isinstance(source, str) or not 0 < len(source) <= MAX_CHARS:
        raise SessionError('expected one bounded ALCG session expression')
    try:
        tree = parse(source)
        fields = t22._args(tree, 'RUN_V023',
                           {'id','initial','seed_sha256','rounds','end'})
        run_id = t22._name(fields['id'], 'id')
        start_fields = t22._args(fields['initial'], 'TRACE_V022',
                                 {'scenario','evidence','policy','receipt'})
        scenario = t22._args(start_fields['scenario'], 'SCENARIO',
                              {'family','protocol','origin','spec_sha256'})
        policy = t22._args(start_fields['policy'], 'POLICY',
                            {'budget','loss','decision','next','stop_risk','optimal_risk'})
        initial_family = t22._name(scenario['family'], 'family')
        initial_budget = t22._uint(policy['budget'], 'initial budget')
        initial_loss = t22._uint(policy['loss'], 'initial loss')
        round_fields = t22._args(fields['rounds'], 'ROUNDS_V023')
        if len(round_fields) > MAX_ROUNDS:
            raise SessionError('too many rounds')
        readings = []
        for i in range(1, len(round_fields)+1):
            key = f'r{i:04d}'
            if key not in round_fields:
                raise SessionError('round indexes must be contiguous and begin at r0001')
            entry = t22._args(round_fields[key], 'ROUND_V023',
                               {'before','action','reading','cost','after','chain_sha256'})
            reading = t22._name(entry['reading'], 'reading')
            if reading not in ('TRUE','FALSE'):
                raise SessionError('reading must be TRUE or FALSE')
            readings.append(reading == 'TRUE')
        rebuilt = build(run_id, initial_family, initial_budget, initial_loss, readings)
        if t22._normal(tree) != t22._normal(_tree(rebuilt)):
            raise SessionError('rounds, policy snapshots, provenance or receipts do not replay')
        return rebuilt
    except (ParseError, t22.TraceError, RecursionError, ValueError) as exc:
        raise SessionError(f'invalid ALCG session: {exc}') from exc


def _cases() -> list[dict]:
    data = json.loads(CASES_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != {'format','cases'} or data['format'] != FORMAT:
        raise SessionError('invalid cases file header')
    cases = data['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= 24:
        raise SessionError('invalid number of session cases')
    ids = set()
    for item in cases:
        if not isinstance(item, dict) or set(item) != {'id','family','budget','loss','readings'}:
            raise SessionError('case contains unknown or missing fields')
        if item['id'] in ids:
            raise SessionError('duplicate session id')
        ids.add(item['id'])
        build(item['id'], item['family'], item['budget'], item['loss'], item['readings'])
    return cases


def _build_case(case: dict) -> Session:
    return build(case['id'], case['family'], case['budget'], case['loss'], case['readings'])


def fixture_text() -> str:
    out = ['# ALCG v0.23: synthetic, ordered, linked policy decisions; not real observations.',
           '# One complete RUN_V023 expression per non-comment line.']
    for case in _cases():
        out.append(encode(_build_case(case)))
    return '\n'.join(out) + '\n'


def report() -> dict:
    sessions = [_build_case(case) for case in _cases()]
    return {
        'format': FORMAT, 'source': 'assistant-authored hypothetical Boolean observation sequences',
        'sessions': len(sessions), 'rounds': sum(len(s.rounds) for s in sessions),
        'terminal_stops': sum(s.status == 'STOP' for s in sessions),
        'open_prefixes': sum(s.status == 'OPEN' for s in sessions),
        'spent_units': sum(s.total_spent for s in sessions),
        'case_summaries': [
            {'id': s.id, 'family':s.initial.family, 'budget':s.initial.budget,
             'loss':s.initial.loss, 'actions':[r.action for r in s.rounds],
             'readings':[r.reading for r in s.rounds], 'rounds':len(s.rounds),
             'spent':s.total_spent, 'remaining':s.remaining, 'status':s.status,
             'final_state_sha256':s.final_state_sha256,
             'final_chain_sha256':s.final_chain_sha256}
            for s in sessions],
        'v022_sample_sha256': PINNED_V022_SAMPLE_SHA256,
        'v022_report_sha256': PINNED_V022_REPORT_SHA256,
        'fixture_sha256': _sha(fixture_text()),
        'published_dictionary_unchanged': True,
        'empirical_sensor_measurements': False,
        'independent_ai_comprehension_scores': False,
        'limitations': [
            'Each session is a finite-horizon policy-following path in the fixed synthetic v0.21 model.',
            'An OPEN prefix is intentionally truncated and is not equivalent to a STOP action.',
            'Link digests are unkeyed and are not signatures; rewriting an entire chain remains possible.',
            'The parser verifies computations under pinned public assumptions, not real-world truth.',
            'All observations are synthetic and were selected by the author, not measured.',
            'The profile encodes policy-following decisions, not externally chosen or off-policy actions.',
        ],
    }


def report_text() -> str:
    return json.dumps(report(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def check() -> dict:
    _check_pins()
    if SAMPLES_PATH.read_bytes() != fixture_text().encode('utf-8'):
        raise SessionError('v0.23 sample expressions differ from replayed canonical bytes')
    if REPORT_PATH.read_bytes() != report_text().encode('utf-8'):
        raise SessionError('v0.23 report differs from replayed canonical bytes')
    lines = [line for line in SAMPLES_PATH.read_text('utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    for line in lines:
        if encode(decode(line)) != line:
            raise SessionError('roundtrip mismatch')
    return report()


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.23 linked policy decision sessions')
    commands = cli.add_subparsers(dest='cmd', required=True)
    commands.add_parser('check')
    commands.add_parser('report')
    commands.add_parser('examples')
    make = commands.add_parser('build')
    make.add_argument('--id', default='R23_CLI_EXAMPLE')
    make.add_argument('--family', default='F17_DIRECT')
    make.add_argument('--budget', type=int, default=2)
    make.add_argument('--loss', type=int, default=64)
    make.add_argument('--reading', choices=('0','1'), action='append', default=[])
    replay = commands.add_parser('replay')
    replay.add_argument('--id', required=True)
    inspect = commands.add_parser('decode')
    inspect.add_argument('file', type=Path)
    args = cli.parse_args(argv)
    try:
        if args.cmd == 'check':
            result = check()
            print(f"OK v0.23: {result['sessions']} sessions, {result['rounds']} rounds, "
                  f"{result['terminal_stops']} STOP and {result['open_prefixes']} OPEN")
        elif args.cmd == 'report':
            print(report_text(), end='')
        elif args.cmd == 'examples':
            print(fixture_text(), end='')
        elif args.cmd == 'build':
            print(encode(build(args.id, args.family, args.budget, args.loss,
                               [s == '1' for s in args.reading])))
        elif args.cmd == 'replay':
            matches = [c for c in _cases() if c['id'] == args.id]
            if len(matches) != 1:
                raise SessionError('unknown session fixture ID')
            print(json.dumps(_build_case(matches[0]).as_json(), ensure_ascii=False, indent=2, sort_keys=True))
        else:
            raw = args.file.read_text(encoding='utf-8')
            lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            if len(lines) != 1:
                raise SessionError('decode requires exactly one session expression')
            print(json.dumps(decode(lines[0]).as_json(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (SessionError, OSError, json.JSONDecodeError, RecursionError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
