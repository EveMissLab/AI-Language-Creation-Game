"""ALCG v0.5: finite-family semantic invariance and counterexample game.

Not an AI reader, NLP evaluation, or complete logical reasoner. Checks a
limited, explicitly specified finite-world subset of ALCG without network.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterator, Any

from alcg import Call, Name, ParseError, String, parse, render
from coverage_lab import BenchmarkError, inspect_calls, jsonl, relations
from finite_probe import FiniteModel, ProbeError, evaluate, check_scopes

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / 'benchmarks' / 'semantic-pairs-v0.5.jsonl'
RELATIONS_PATH = ROOT / 'data' / 'relations-v0.4.json'


class LabError(ValueError):
    """Invalid comparison, fixture, or expectation."""


def _name(expr: Name | String | Call, label: str) -> str:
    if not isinstance(expr, Name):
        raise LabError(f'{label} must be an identifier')
    return expr.value


def _canonical(expr: Name | String | Call, environment: dict[str, str], depth: int) -> Name | String | Call:
    """Normalize role ordering and alpha-rename *bound* variables only.

    `_BOUND0` is a canonical spelling, not a new ALCG primitive or ID.
    Regular concept names are not rewritten.
    """
    if not isinstance(expr, Call):
        return expr
    args = dict(expr.args)
    if expr.name == 'REF':
        if set(args) != {'var'}:
            raise LabError('REF requires var')
        variable = _name(args['var'], 'REF.var')
        if variable not in environment:
            raise LabError(f'unbound variable reference: {variable}')
        return Call('REF', (('var', Name(environment[variable])),))
    if expr.name in ('FORALL', 'EXISTS'):
        if set(args) != {'var', 'domain', 'claim'}:
            raise LabError(f'{expr.name} needs var, domain, claim')
        var = _name(args['var'], f'{expr.name}.var')
        domain = _name(args['domain'], f'{expr.name}.domain')
        canonical_var = f'_BOUND{depth}'
        new_env = dict(environment)
        new_env[var] = canonical_var
        claim = _canonical(args['claim'], new_env, depth + 1)
        return Call(expr.name, (('claim', claim), ('domain', Name(domain)), ('var', Name(canonical_var))))
    return Call(expr.name, tuple(sorted(
        (key, _canonical(value, environment, depth)) for key, value in expr.args
    )))


def normalize(expression: str | Name | String | Call) -> str:
    """Canonical text for structural invariance; NOT general semantic equivalence.

    Names of unrelated free constants never change. Logical equivalences
    such as double-negation elimination are intentionally not simplified.
    """
    try:
        node = parse(expression) if isinstance(expression, str) else expression
        inspect_calls(node, relations(RELATIONS_PATH))
        check_scopes(node)
        return render(_canonical(node, {}, 0))
    except (ParseError, ProbeError, BenchmarkError) as exc:
        raise LabError(str(exc)) from exc


@dataclass(frozen=True)
class Observation:
    fixture: str
    world: str
    left: bool
    right: bool

    def report(self) -> dict[str, Any]:
        return {'fixture': self.fixture, 'world': self.world,
                'left': self.left, 'right': self.right}


@dataclass(frozen=True)
class Comparison:
    relation: str
    observations: int
    first_witness: Observation | None
    canonical_same: bool

    def report(self) -> dict[str, Any]:
        return {
            'relation': self.relation,
            'observations_checked': self.observations,
            'first_counterexample': self.first_witness.report() if self.first_witness else None,
            'canonical_structures_equal': self.canonical_same,
            'scope': 'finite synthetic model suite only',
            'independent_ai_comprehension_score': None,
        }


def model_suite() -> Iterator[tuple[str, FiniteModel]]:
    """192 deterministic toy models, deliberately including empty domains.

    Four truth masks (people READY), three event-order arrangements, four
    accessibility choices and four domain sizes. Each has two evaluation
    worlds. No claim that this exhausts all possible ALCG interpretations.
    """
    people = ('ALICE', 'BOB', 'CHARLIE')
    orders = ('forward', 'reverse', 'none')
    accesses = ('self', 'other', 'both', 'none')
    domain_options = ((), ('ALICE',), ('ALICE', 'BOB'), people)
    read = 'DO(actor=PROGRAM, action=READ, object=FILE)'
    write = 'DO(actor=PROGRAM, action=WRITE, object=OUTPUT)'

    for mask in (0, 1, 3, 7):
        actual_ready = frozenset((name, 'READY') for i, name in enumerate(people) if mask & (1 << i))
        possible_ready = frozenset((name, 'READY') for i, name in enumerate(people) if not mask & (1 << i))
        actual_facts = actual_ready | (frozenset({('SYSTEM', 'DISTURBED')}) if mask & 1 else frozenset())
        possible_facts = possible_ready | (frozenset({('SYSTEM', 'DISTURBED')}) if not mask & 1 else frozenset())
        actual_facts = actual_facts | frozenset({('SYSTEM', 'STABLE')})
        for order in orders:
            first = frozenset({('READ_EVENT', 'WRITE_EVENT'), (read, write)})
            second = frozenset({('WRITE_EVENT', 'READ_EVENT'), (write, read)})
            before_actual = first if order == 'forward' else second if order == 'reverse' else frozenset()
            before_possible = second if order == 'forward' else first if order == 'reverse' else frozenset()
            for access in accesses:
                reachable = {'self': ('actual',), 'other': ('possible',),
                             'both': ('actual', 'possible'), 'none': ()}[access]
                for size, domain in enumerate(domain_options):
                    fixture_id = f'm{mask}-t{order}-a{access}-d{size}'
                    model = FiniteModel(
                        domains={'PERSON': tuple(domain), 'INTEGER': ('ZERO', 'ONE', 'TWO'), 'EMPTY': ()},
                        facts={'actual': actual_facts, 'possible': possible_facts},
                        before={'actual': before_actual, 'possible': before_possible},
                        accessible={'actual': reachable, 'possible': ('possible',)},
                        order={'ZERO': 0, 'ONE': 1, 'TWO': 2},
                    )
                    yield fixture_id, model


def compare(left: str, right: str) -> Comparison:
    """Compare two claims across the finite suite; return first witness.

    Recheck expression well-formedness even when none of the model branches
    are evaluated, so an unreachable invalid REF cannot pass unnoticed.
    """
    left_canonical = normalize(left)
    right_canonical = normalize(right)
    left_ast, right_ast = parse(left), parse(right)
    count = 0
    for fixture_id, model in model_suite():
        for world in ('actual', 'possible'):
            try:
                left_value = evaluate(left_ast, model, world=world)
                right_value = evaluate(right_ast, model, world=world)
            except ProbeError as exc:
                raise LabError(f'{fixture_id}/{world}: {exc}') from exc
            count += 1
            if left_value != right_value:
                return Comparison('distinguishable', count,
                                  Observation(fixture_id, world, left_value, right_value),
                                  left_canonical == right_canonical)
    return Comparison('indistinguishable_in_suite', count, None,
                      left_canonical == right_canonical)


def check_cases(path: Path = CASES_PATH) -> dict[str, Any]:
    rows = jsonl(path)
    if not rows:
        raise LabError('comparison corpus must not be empty')
    seen: set[str] = set()
    same = different = structural = 0
    witnesses: list[dict[str, Any]] = []
    for row in rows:
        if set(row) != {'id', 'focus', 'expected', 'left', 'right', 'explanation'}:
            raise LabError('comparison cases require id, focus, expected, left, right, explanation')
        case_id = row['id']
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise LabError(f'duplicate or empty comparison case id: {case_id!r}')
        seen.add(case_id)
        if not all(isinstance(row[k], str) and row[k].strip() for k in ('focus', 'expected', 'left', 'right', 'explanation')):
            raise LabError(f'{case_id}: invalid or empty comparison field')
        if row['expected'] not in {'same', 'different'}:
            raise LabError(f'{case_id}: expected must be same or different')
        result = compare(row['left'], row['right'])
        found = 'different' if result.first_witness else 'same'
        if found != row['expected']:
            raise LabError(f'{case_id}: expected {row["expected"]}, observed {found} (finite models only)')
        same += found == 'same'
        different += found == 'different'
        structural += result.canonical_same
        if result.first_witness:
            witnesses.append({'id': case_id, **result.first_witness.report()})
    return {
        'version': '0.5-semantic-stability-experiment',
        'pair_cases': len(rows),
        'same_in_suite': same,
        'distinguished_by_counterexample': different,
        'canonical_structure_identical': structural,
        'synthetic_models': sum(1 for _ in model_suite()),
        'worlds_per_model': 2,
        'first_witnesses': witnesses,
        'independent_ai_reading_score': None,
        'caution': 'This corpus was author-built. Same means not distinguished in this finite suite; no general language semantics, AI comprehension, or real-world truth is established.'
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.5 finite semantic stability game')
    cli.add_argument('command', choices=['check', 'compare', 'normalize'])
    cli.add_argument('--left', help='First ALCG claim for compare/normalize')
    cli.add_argument('--right', help='Second ALCG claim for compare')
    cli.add_argument('--cases', type=Path, default=CASES_PATH)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            result = check_cases(args.cases)
        elif args.command == 'normalize':
            if args.left is None:
                raise LabError('normalize requires --left')
            result = {'canonical': normalize(args.left), 'warning': 'Structural normal form is not a logical proof'}
        else:
            if args.left is None or args.right is None:
                raise LabError('compare requires --left and --right')
            result = compare(args.left, args.right).report()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (LabError, BenchmarkError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
