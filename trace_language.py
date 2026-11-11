"""ALCG v0.22: auditable, English-readable computation-decision trace profile.

This adds no published-language operators. It encodes a single decision snapshot
with an ordered synthetic observation history, pinned v0.21 assumptions, exact
rational receipts and deterministic replay. Parsing is not semantic comprehension.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

from alcg import Call, Expr, Name, ParseError, String, parse, render
import correlated_design as v21
import noisy_design as v20

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / 'data' / 'trace-cases-v0.22.json'
SAMPLES_PATH = ROOT / 'samples' / 'decision-traces-v0.22.alcg'
REPORT_PATH = ROOT / 'reports' / 'trace-language-v0.22.json'
FORMAT = 'ALCG-v0.22-replayable-decision-trace'
PROFILE = 'V021_CORRELATED'
SOURCE = 'SYNTHETIC'
MAX_EXPRESSION_CHARS = 25000
MAX_OBSERVATIONS = v21.MAX_EVENTS
_HEX = re.compile(r'^[0-9a-f]{64}$')
_UINT = re.compile(r'^(0|[1-9][0-9]*)$')


class TraceError(ValueError):
    """Malformed, noncanonical, unauditable or inconsistent decision trace."""


def n(v: int) -> Call:
    if type(v) is not int or v < 0:
        raise TraceError('NAT expects a nonnegative integer')
    return Call('NAT', (('value', String(str(v))),))


def rat(v: Fraction) -> Call:
    if type(v) is not Fraction:
        raise TraceError('RAT expects an exact Fraction')
    return Call('RAT', (('n', String(str(v.numerator))), ('d', String(str(v.denominator)))))


def sha(v: str) -> Call:
    if not isinstance(v, str) or not _HEX.fullmatch(v):
        raise TraceError('SHA256 requires a lowercase 64-digit digest')
    return Call('SHA256', (('value', String(v)),))


def _profile_sha() -> str:
    return sha256(v21.SPEC_PATH.read_bytes()).hexdigest()


def _history_sha(family: str, observations: Sequence[dict], budget: int, loss: int, profile_sha: str) -> str:
    # Order-sensitive; a Bayesian posterior alone is not a complete event log.
    data = json.dumps({'format': FORMAT, 'family': family, 'observations': list(observations),
                       'budget': budget, 'loss': loss, 'profile_sha256': profile_sha},
                      ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return sha256(data.encode('utf-8')).hexdigest()


def _state_sha(state: tuple[Fraction, ...]) -> str:
    # Input to hash is exact normalized 32-cell rational representation.
    cells = [[v.numerator, v.denominator] for v in state]
    data = json.dumps({'profile': PROFILE, 'cells': cells}, separators=(',', ':'), sort_keys=True)
    return sha256(data.encode('utf-8')).hexdigest()


def _args(expr: Expr, name: str, expected: set[str] | None = None) -> dict[str, Expr]:
    if not isinstance(expr, Call) or expr.name != name:
        raise TraceError(f'expected {name} expression')
    d = dict(expr.args)
    if len(d) != len(expr.args):
        raise TraceError(f'duplicate fields in {name}')
    if expected is not None and set(d) != expected:
        raise TraceError(f'{name} fields must be {sorted(expected)}')
    return d


def _uint(expr: Expr, label: str) -> int:
    fields = _args(expr, 'NAT', {'value'})
    item = fields['value']
    if not isinstance(item, String) or not _UINT.fullmatch(item.value):
        raise TraceError(f'{label} must have canonical ASCII NAT representation')
    if len(item.value) > 6:
        raise TraceError(f'{label} exceeds supported numeric magnitude')
    return int(item.value)


def _name(expr: Expr, label: str) -> str:
    if not isinstance(expr, Name):
        raise TraceError(f'{label} must be a name')
    return expr.value


def _normal(expr: Expr) -> Any:
    """Normalize named field order; preserve indexed event names and values."""
    if isinstance(expr, Name):
        return ('NAME', expr.value)
    if isinstance(expr, String):
        return ('STRING', expr.value)
    if isinstance(expr, Call):
        args = _args(expr, expr.name)
        return ('CALL', expr.name, tuple(sorted((k, _normal(v)) for k, v in args.items())))
    raise TraceError('invalid AST node')


def _validate_input(family: str, observations: Sequence[dict], budget: int, loss: int) -> list[dict]:
    if type(family) is not str or not re.fullmatch(r'F17_[A-Z0-9_]{1,48}', family):
        raise TraceError('family must be a known v0.21 family ID')
    if not isinstance(observations, (list, tuple)) or len(observations) > MAX_OBSERVATIONS:
        raise TraceError('observation history length is out of bounds')
    if type(budget) is not int or not 0 <= budget <= v21.MAX_PLANNING_BUDGET:
        raise TraceError('budget is outside the bounded v0.21 policy')
    if type(loss) is not int or not 0 <= loss <= 10000:
        raise TraceError('loss is outside the bounded v0.21 policy')
    result = []
    for index, item in enumerate(observations, 1):
        if not isinstance(item, dict) or set(item) != {'action_id', 'observed_Y'}:
            raise TraceError(f'observation {index} has invalid fields')
        action, y = item['action_id'], item['observed_Y']
        if type(action) is not int or not 0 <= action <= 7 or type(y) is not bool:
            raise TraceError(f'observation {index} has invalid action/reading')
        result.append({'action_id': action, 'observed_Y': y})
    return result


@dataclass(frozen=True)
class Trace:
    family: str
    observations: tuple[tuple[int, bool], ...]
    budget: int
    loss: int
    decision: str
    next_action: int | None
    stop_risk: Fraction
    optimal_risk: Fraction
    max_mask_probability: Fraction
    session_fault_probability: Fraction
    state_sha256: str
    history_sha256: str
    spec_sha256: str

    def as_json(self) -> dict:
        def q(v: Fraction) -> dict:
            return {'n': str(v.numerator), 'd': str(v.denominator)}
        return {
            'format': FORMAT, 'family': self.family,
            'observations': [{'action_id': a, 'observed_Y': b} for a, b in self.observations],
            'budget': self.budget, 'loss': self.loss,
            'decision': self.decision, 'next_action': self.next_action,
            'stop_risk': q(self.stop_risk), 'optimal_risk': q(self.optimal_risk),
            'max_mask_probability': q(self.max_mask_probability),
            'session_fault_probability': q(self.session_fault_probability),
            'state_sha256': self.state_sha256, 'history_sha256': self.history_sha256,
            'spec_sha256': self.spec_sha256,
            'kind': SOURCE,
        }


def build(family: str, observations: Sequence[dict], budget: int, loss: int) -> Trace:
    obs = _validate_input(family, observations, budget, loss)
    try:
        rows = v21.pinned_rows()
        if family not in rows:
            raise TraceError('family is not present in pinned v0.21 models')
        row = rows[family]
        state = v21.posterior(row, obs)
        decision = v21.plan(row, state, budget, loss)
        return Trace(
            family=family, observations=tuple((e['action_id'], e['observed_Y']) for e in obs),
            budget=budget, loss=loss,
            decision=decision['decision'], next_action=decision['optimal_first_action'],
            stop_risk=v21.stop_loss(state, loss),
            optimal_risk=Fraction(decision['optimal_expected_future_total_loss']['numerator'],
                                  decision['optimal_expected_future_total_loss']['denominator']),
            max_mask_probability=max(v21.mask_posterior(state)),
            session_fault_probability=v21.fault_posterior(state),
            state_sha256=_state_sha(state),
            history_sha256=_history_sha(family, obs, budget, loss, _profile_sha()),
            spec_sha256=_profile_sha(),
        )
    except (v21.ChannelError, v20.NoisyDesignError, OSError, json.JSONDecodeError) as exc:
        raise TraceError(str(exc)) from exc


def encode(trace: Trace) -> str:
    if not isinstance(trace, Trace):
        raise TraceError('encode needs a Trace object')
    # Validate and recompute a receipt rather than trusting caller-created dataclass fields.
    expected = build(trace.family,
                     [{'action_id': a, 'observed_Y': y} for a, y in trace.observations],
                     trace.budget, trace.loss)
    if expected != trace:
        raise TraceError('trace fields are inconsistent with the pinned inference')
    obs = Call('OBSERVATIONS', tuple(
        (f'e{i:04d}', Call('OBS', (('action', n(act)), ('reading', Name('TRUE' if y else 'FALSE')))))
        for i, (act, y) in enumerate(trace.observations, 1)))
    policy = Call('POLICY', (
        ('budget', n(trace.budget)), ('loss', n(trace.loss)),
        ('decision', Name(trace.decision)),
        ('next', Name('NONE') if trace.next_action is None else n(trace.next_action)),
        ('stop_risk', rat(trace.stop_risk)), ('optimal_risk', rat(trace.optimal_risk)),
    ))
    receipt = Call('RECEIPT', (
        ('max_mask_p', rat(trace.max_mask_probability)),
        ('session_fault_p', rat(trace.session_fault_probability)),
        ('state_sha256', sha(trace.state_sha256)),
        ('history_sha256', sha(trace.history_sha256)),
    ))
    scenario = Call('SCENARIO', (
        ('family', Name(trace.family)), ('protocol', Name(PROFILE)),
        ('origin', Name(SOURCE)), ('spec_sha256', sha(trace.spec_sha256)),
    ))
    expression = Call('TRACE_V022', (
        ('scenario', scenario), ('evidence', obs), ('policy', policy), ('receipt', receipt),
    ))
    encoded = render(expression)
    if len(encoded) > MAX_EXPRESSION_CHARS:
        raise TraceError('encoded trace exceeds safe size bound')
    return encoded


def decode(source: str) -> Trace:
    if not isinstance(source, str) or not 0 < len(source) <= MAX_EXPRESSION_CHARS:
        raise TraceError('trace input must be a bounded nonempty UTF-8 string')
    try:
        tree = parse(source)
    except (ParseError, RecursionError, ValueError) as exc:
        raise TraceError(f'ALCG syntax error: {exc}') from exc
    top = _args(tree, 'TRACE_V022', {'scenario', 'evidence', 'policy', 'receipt'})
    scenario = _args(top['scenario'], 'SCENARIO', {'family', 'protocol', 'origin', 'spec_sha256'})
    family = _name(scenario['family'], 'family')
    if _name(scenario['protocol'], 'protocol') != PROFILE or _name(scenario['origin'], 'origin') != SOURCE:
        raise TraceError('unsupported protocol or observation origin')
    evidence_fields = _args(top['evidence'], 'OBSERVATIONS')
    if len(evidence_fields) > MAX_OBSERVATIONS:
        raise TraceError('observation history is too long')
    obs = []
    for i in range(1, len(evidence_fields)+1):
        key = f'e{i:04d}'
        if key not in evidence_fields:
            raise TraceError('observation indices must be contiguous, starting at e0001')
        item = _args(evidence_fields[key], 'OBS', {'action', 'reading'})
        flag = _name(item['reading'], 'reading')
        if flag not in {'TRUE', 'FALSE'}:
            raise TraceError('observation reading must be TRUE or FALSE')
        obs.append({'action_id': _uint(item['action'], 'action_id'), 'observed_Y': flag == 'TRUE'})
    policy = _args(top['policy'], 'POLICY',
                   {'budget', 'loss', 'decision', 'next', 'stop_risk', 'optimal_risk'})
    budget = _uint(policy['budget'], 'budget')
    loss = _uint(policy['loss'], 'loss')
    expected = build(family, obs, budget, loss)
    # Validity requires every output receipt, profile fingerprint, and decision
    # to equal the freshly recomputed canonical snapshot. Unknown slots fail too.
    expected_tree = parse(encode(expected))
    if _normal(tree) != _normal(expected_tree):
        raise TraceError('trace semantic receipt, schema, or decision does not match replay')
    return expected


def _cases() -> list[dict]:
    raw = json.loads(CASES_PATH.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or set(raw) != {'format', 'cases'} or raw['format'] != FORMAT:
        raise TraceError('invalid v0.22 case fixture format')
    cases = raw['cases']
    if not isinstance(cases, list) or not cases or len(cases) > 32:
        raise TraceError('invalid case fixture length')
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'id','family','observations','budget','loss'}:
            raise TraceError('invalid case fixture fields')
        if not isinstance(case['id'], str) or not re.fullmatch(r'T22_[A-Z0-9_]{1,40}', case['id']):
            raise TraceError('invalid fixture ID')
        if case['id'] in ids:
            raise TraceError('duplicate fixture ID')
        ids.add(case['id'])
        _validate_input(case['family'], case['observations'], case['budget'], case['loss'])
    return cases


def fixture_lines() -> list[str]:
    return [encode(build(case['family'], case['observations'], case['budget'], case['loss']))
            for case in _cases()]


def fixture_text() -> str:
    return ('# ALCG v0.22 synthetic decision snapshots; canonical UTF-8, one expression per line.\n'
            '# Not a measured history or independent AI comprehension result.\n'
            + '\n'.join(fixture_lines()) + '\n')


def report() -> dict:
    lines = fixture_lines()
    traces = [decode(x) for x in lines]
    counts = {'STOP': sum(t.decision == 'STOP' for t in traces),
              'CONTINUE': sum(t.decision == 'CONTINUE' for t in traces)}
    return {
        'format': FORMAT, 'source': 'assistant-authored, pinned v0.21 synthetic finite SCM and channel',
        'case_count': len(traces), 'observation_count': sum(len(t.observations) for t in traces),
        'decision_counts': counts, 'families': sorted({t.family for t in traces}),
        'cases': [dict(id=case['id'], decision=t.decision, action=t.next_action,
                       evidence_count=len(t.observations), state_sha256=t.state_sha256,
                       history_sha256=t.history_sha256,
                       stop_risk={'n':str(t.stop_risk.numerator),'d':str(t.stop_risk.denominator)},
                       optimal_risk={'n':str(t.optimal_risk.numerator),'d':str(t.optimal_risk.denominator)})
                  for case, t in zip(_cases(), traces)],
        'fixture_sha256': sha256(fixture_text().encode('utf-8')).hexdigest(),
        'profile_sha256': _profile_sha(),
        'no_empirical_evidence': True,
        'no_independent_ai_comprehension_scores': True,
        'published_language_dictionary_unchanged': True,
        'limitations': [
            'The document is an exact replayable snapshot of one decision, not a full experiment transcript.',
            'English-readable operator names do not establish understanding by another AI.',
            'All observations are authored synthetic cases, not empirical measurements.',
            'Hashes detect changed bytes relative to pinned artifacts; no signature or authenticity claim.',
            'The posterior and actions are only valid for the bounded v0.21 assumptions.',
        ],
    }


def report_text() -> str:
    return json.dumps(report(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def check() -> dict:
    if SAMPLES_PATH.read_bytes() != fixture_text().encode('utf-8'):
        raise TraceError('saved v0.22 .alcg fixture differs from recomputed canonical expressions')
    if REPORT_PATH.read_bytes() != report_text().encode('utf-8'):
        raise TraceError('saved v0.22 report differs from recomputed canonical report')
    entries = [x for x in SAMPLES_PATH.read_text(encoding='utf-8').splitlines() if x and not x.startswith('#')]
    assert len(entries) == len(_cases())
    for line in entries:
        assert encode(decode(line)) == line
    return report()


def _cli_observations(values: list[str]) -> list[dict]:
    out = []
    for v in values:
        if not re.fullmatch(r'[0-7]=[01]', v):
            raise TraceError('observe must be ACTION=0|1 where ACTION is 0..7')
        out.append({'action_id': int(v[0]), 'observed_Y': v[-1] == '1'})
    return out


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.22 replayable computation trace profile')
    cmd = cli.add_subparsers(dest='command', required=True)
    cmd.add_parser('check', help='verify pinned fixtures and every replay receipt')
    cmd.add_parser('report', help='recompute synthetic case report')
    cmd.add_parser('examples', help='print canonical sample expressions')
    make = cmd.add_parser('build', help='encode one single-decision ALCG snapshot to stdout')
    make.add_argument('--family', default='F17_DIRECT')
    make.add_argument('--budget', type=int, default=2)
    make.add_argument('--loss', type=int, default=64)
    make.add_argument('--observe', action='append', default=[])
    read = cmd.add_parser('decode', help='validate and decode one ALCG expression; input from a file')
    read.add_argument('file', type=Path)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            result = check()
            print(f"OK v0.22: {result['case_count']} replayable synthetic traces, "
                  f"{result['observation_count']} observations, public dictionary unchanged")
        elif args.command == 'report':
            print(report_text(), end='')
        elif args.command == 'examples':
            print(fixture_text(), end='')
        elif args.command == 'build':
            trace = build(args.family, _cli_observations(args.observe), args.budget, args.loss)
            print(encode(trace))
        elif args.command == 'decode':
            raw = args.file.read_text(encoding='utf-8')
            lines = [s for s in raw.splitlines() if s.strip() and not s.lstrip().startswith('#')]
            if len(lines) != 1:
                raise TraceError('decode input must contain exactly one expression')
            print(json.dumps(decode(lines[0]).as_json(), ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (TraceError, ParseError, OSError, json.JSONDecodeError, RecursionError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
