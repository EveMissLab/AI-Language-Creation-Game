"""ALCG v0.4: intentionally limited finite-world semantics probe.

A deterministic test oracle for a few structured operators, not a natural
language interpreter, an unrestricted theorem prover, or an AI reader.
Python >=3.10, standard library only.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from alcg import Call, Name, ParseError, String, parse, render
from coverage_lab import BenchmarkError, inspect_calls, jsonl, relations

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / 'data' / 'finite-world-v0.4.json'
DEFAULT_CASES = ROOT / 'benchmarks' / 'finite-probes-v0.4.jsonl'
DEFAULT_REGISTRY = ROOT / 'data' / 'relations-v0.4.json'


class ProbeError(ValueError):
    """Invalid finite model, expression, or probe case."""


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _pairs(value: Any, label: str) -> frozenset[tuple[str, str]]:
    if not isinstance(value, list):
        raise ProbeError(f'{label} must be a list')
    pairs: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, list) or len(item) != 2 or not all(_nonblank(x) for x in item):
            raise ProbeError(f'{label} entries must be pairs of non-empty strings')
        entry = (item[0], item[1])
        if entry in pairs:
            raise ProbeError(f'{label}: duplicate pair {entry!r}')
        pairs.add(entry)
    return frozenset(pairs)


@dataclass(frozen=True)
class FiniteModel:
    domains: dict[str, tuple[str, ...]]
    facts: dict[str, frozenset[tuple[str, str]]]
    before: dict[str, frozenset[tuple[str, str]]]
    accessible: dict[str, tuple[str, ...]]
    order: dict[str, int]

    @classmethod
    def load(cls, path: Path) -> 'FiniteModel':
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise ProbeError(f'could not load finite model: {exc}') from exc
        if not isinstance(doc, dict) or set(doc) != {'version', 'domains', 'worlds', 'accessibility', 'order'}:
            raise ProbeError('model requires version, domains, worlds, accessibility, order')
        if doc['version'] != '0.4-finite-demo':
            raise ProbeError('unknown model format version')
        domains, worlds, access, order = (doc[k] for k in ('domains', 'worlds', 'accessibility', 'order'))
        if not isinstance(domains, dict) or not isinstance(worlds, dict) or not worlds or not isinstance(access, dict) or not isinstance(order, dict):
            raise ProbeError('model maps are invalid')
        checked_domains: dict[str, tuple[str, ...]] = {}
        for name, values in domains.items():
            if not _nonblank(name) or not isinstance(values, list) or not all(_nonblank(x) for x in values) or len(set(values)) != len(values):
                raise ProbeError(f'invalid domain: {name!r}')
            checked_domains[name] = tuple(values)
        fact_maps: dict[str, frozenset[tuple[str, str]]] = {}
        before_maps: dict[str, frozenset[tuple[str, str]]] = {}
        for world, info in worlds.items():
            if not _nonblank(world) or not isinstance(info, dict) or set(info) != {'facts', 'before'}:
                raise ProbeError(f'invalid world: {world!r}')
            fact_maps[world] = _pairs(info['facts'], f'{world}.facts')
            before_maps[world] = _pairs(info['before'], f'{world}.before')
        if set(access) != set(worlds):
            raise ProbeError('accessibility must be specified for every world')
        checked_access: dict[str, tuple[str, ...]] = {}
        for world, targets in access.items():
            if not isinstance(targets, list) or len(set(targets)) != len(targets) or not set(targets).issubset(worlds):
                raise ProbeError(f'invalid accessibility list for {world}')
            checked_access[world] = tuple(targets)
        if not all(_nonblank(k) and type(v) is int for k, v in order.items()):
            raise ProbeError('order must map identifiers to integer ranks')
        return cls(checked_domains, fact_maps, before_maps, checked_access, dict(order))


@dataclass
class _Budget:
    left: int

    def tick(self) -> None:
        self.left -= 1
        if self.left < 0:
            raise ProbeError('evaluation budget exceeded')


def _roles(node: Call, names: tuple[str, ...]) -> dict[str, Name | String | Call]:
    args = dict(node.args)
    if set(args) != set(names):
        raise ProbeError(f'{node.name} expects roles {names!r}')
    return args


def _as_name(node: Name | String | Call, label: str) -> str:
    if not isinstance(node, Name):
        raise ProbeError(f'{label} must be an identifier')
    return node.value


def _term(node: Name | String | Call, env: dict[str, str], budget: _Budget, *, event: bool = False) -> str:
    budget.tick()
    if isinstance(node, Name):
        return node.value
    if not isinstance(node, Call):
        raise ProbeError('literal quoted strings are not evaluated')
    if node.name == 'REF':
        name = _as_name(_roles(node, ('var',))['var'], 'REF.var')
        if name not in env:
            raise ProbeError(f'unbound variable reference: {name}')
        return env[name]
    if event and node.name == 'DO':
        args = dict(node.args)
        if not {'actor', 'action'}.issubset(args) or not set(args).issubset({'actor', 'action', 'object'}):
            raise ProbeError('event DO requires actor, action, optionally object')
        # Render event terms in original role order. A DO used here is an
        # event *descriptor*, not executable code or proof of occurrence.
        terms = tuple((key, Name(_term(value, env, budget))) for key, value in node.args)
        return render(Call('DO', terms))
    raise ProbeError(f'{node.name} cannot be used as a value in this probe')


def _evaluate(node: Name | String | Call, model: FiniteModel, world: str, env: dict[str, str], budget: _Budget) -> bool:
    budget.tick()
    if not isinstance(node, Call):
        raise ProbeError('a proposition must be a supported call, not a bare name or quoted string')
    name = node.name
    if name == 'IS':
        args = _roles(node, ('subject', 'property'))
        return (_term(args['subject'], env, budget), _term(args['property'], env, budget)) in model.facts[world]
    if name == 'COMPARE':
        args = _roles(node, ('left', 'right', 'by'))
        left, right = (_term(args[k], env, budget) for k in ('left', 'right'))
        comparator = _as_name(args['by'], 'COMPARE.by')
        if comparator == 'EQUAL':
            return left == right
        if comparator == 'GREATER_THAN':
            if left not in model.order or right not in model.order:
                raise ProbeError(f'no order rank for: {left!r} or {right!r}')
            return model.order[left] > model.order[right]
        raise ProbeError(f'unsupported comparator: {comparator}')
    if name == 'AND':
        args = _roles(node, ('left', 'right'))
        # Evaluate both sides, including errors; AND does not encode order.
        left = _evaluate(args['left'], model, world, env, budget)
        right = _evaluate(args['right'], model, world, env, budget)
        return left and right
    if name == 'NOT':
        args = _roles(node, ('claim',))
        return not _evaluate(args['claim'], model, world, env, budget)
    if name == 'BEFORE':
        args = _roles(node, ('earlier', 'later'))
        return (_term(args['earlier'], env, budget, event=True), _term(args['later'], env, budget, event=True)) in model.before[world]
    if name == 'MAY':
        args = _roles(node, ('claim',))
        return any(_evaluate(args['claim'], model, accessible_world, env, budget)
                   for accessible_world in model.accessible[world])
    if name in ('FORALL', 'EXISTS'):
        args = _roles(node, ('var', 'domain', 'claim'))
        variable = _as_name(args['var'], f'{name}.var')
        domain = _as_name(args['domain'], f'{name}.domain')
        if domain not in model.domains:
            raise ProbeError(f'unknown finite domain: {domain}')
        outcomes = []
        for value in model.domains[domain]:
            env_next = dict(env)
            env_next[variable] = value   # lexical shadowing is explicit
            outcomes.append(_evaluate(args['claim'], model, world, env_next, budget))
        return all(outcomes) if name == 'FORALL' else any(outcomes)
    raise ProbeError(f'operator has no finite-probe semantics: {name}')


def evaluate(expression: str | Name | String | Call, model: FiniteModel, *, world: str = 'actual', budget: int = 100000) -> bool:
    if world not in model.facts:
        raise ProbeError(f'unknown world: {world}')
    if type(budget) is not int or budget < 1:
        raise ProbeError('budget must be a positive integer')
    try:
        node = parse(expression) if isinstance(expression, str) else expression
        inspect_calls(node, relations(DEFAULT_REGISTRY))
        return _evaluate(node, model, world, {}, _Budget(budget))
    except (ParseError, BenchmarkError) as exc:
        raise ProbeError(str(exc)) from exc


def check_cases(path: Path = DEFAULT_CASES, model_path: Path = DEFAULT_MODEL) -> dict[str, Any]:
    model = FiniteModel.load(model_path)
    cases = jsonl(path)
    if not cases:
        raise ProbeError('probe set must not be empty')
    seen: set[str] = set()
    count_true = count_false = 0
    for case in cases:
        if set(case) != {'id', 'focus', 'world', 'expression', 'expected', 'note'}:
            raise ProbeError(f'invalid probe fields: {case!r}')
        identifier = case['id']
        if not _nonblank(identifier) or identifier in seen:
            raise ProbeError(f'empty or duplicate probe id: {identifier!r}')
        seen.add(identifier)
        if not all(_nonblank(case[k]) for k in ('focus', 'world', 'expression', 'note')) or type(case['expected']) is not bool:
            raise ProbeError(f'invalid probe value: {identifier}')
        actual = evaluate(case['expression'], model, world=case['world'])
        if actual != case['expected']:
            raise ProbeError(f'{identifier} failed: expected {case["expected"]}, got {actual}')
        count_true += bool(actual)
        count_false += not actual
    return {'version': '0.4-finite-demo', 'cases_checked': len(cases),
            'expected_true': count_true, 'expected_false': count_false,
            'status': 'all toy-model expectations matched',
            'independent_ai_reading_score': None,
            'caution': 'Only stipulated finite-world truth; no model-independent theorem or natural-language equivalence is established.'}


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.4 finite semantics probes (limited subset)')
    cli.add_argument('command', choices=['check', 'eval'])
    cli.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    cli.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    cli.add_argument('--world', default='actual')
    cli.add_argument('--expression', help='For eval: one ALCG expression')
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            result = check_cases(args.cases, args.model)
        else:
            if args.expression is None:
                raise ProbeError('eval requires --expression')
            result = {'world': args.world, 'result': evaluate(args.expression, FiniteModel.load(args.model), world=args.world)}
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ProbeError, BenchmarkError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
