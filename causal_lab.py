"""ALCG v0.16: opt-in, finite Boolean structural-causal-model demonstration.

Not a real-world causality detector, not an extension of v0.15's fixed oracle,
not a general interpretation of English CAUSE, and not an AI reader test.
All equations are explicit, finite, versioned, and deliberately synthetic.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterator

from alcg import Call, Expr, Name, parse
from coverage_lab import jsonl
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'data' / 'causal-models-v0.16.json'
SUITE = ROOT / 'benchmarks' / 'generated-challenges-v0.14.jsonl'
REPORT = ROOT / 'reports' / 'causal-intervention-v0.16.json'
ACTIVE_PATTERNS = ROOT / 'data' / 'patterns-v0.8.json'
V15_REPORT = ROOT / 'reports' / 'bounded-counterexamples-v0.15.json'
VERSION = 'ALCG-v0.16-binary-scm'
SOURCE_SHA256 = '0d40a9effbf8c3f559269d5a300a6160e5ed3ef251b0bd2b2ad18651c60f8802'
ACTIVE_SHA256 = '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'
V15_REPORT_SHA256 = 'efcbbf93b6cb8d72d6e04d4eee221f36f3b9f4efcda5ed644ae499d9ab4f98b1'
IDENT = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')
OPERATORS = {'copy': 1, 'not': 1, 'and': 2, 'or': 2, 'xor': 2}


class CausalError(ValueError):
    """Invalid opt-in SCM, incompatible expression or corrupted receipt."""


def _exact(obj: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or set(obj) != keys:
        raise CausalError(f'{label} must have exactly {sorted(keys)}')
    return obj


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise CausalError(f'{label} must be an ASCII identifier')
    return value


def _from_name(node: Expr, label: str) -> str:
    if not isinstance(node, Name):
        raise CausalError(f'{label} requires a plain name')
    return _identifier(node.value, label)


def _roles(node: Expr, name: str, roles: set[str]) -> dict[str, Expr]:
    if not isinstance(node, Call) or node.name != name or set(dict(node.args)) != roles:
        raise CausalError(f'expected {name} with roles {sorted(roles)}')
    return dict(node.args)


def parse_cause(expression: str) -> tuple[str, tuple[str, str]]:
    """Only accept CAUSE(source=NAME,effect=CHANGE(subject=NAME,property=NAME)).

    This is a v0.16 *typed opt-in* subset, not a claim that IS and CHANGE
    have the same meaning or that their effects are physically measurable.
    """
    try:
        node = parse(expression)
        args = _roles(node, 'CAUSE', {'source', 'effect'})
        effect = _roles(args['effect'], 'CHANGE', {'subject', 'property'})
        return _from_name(args['source'], 'CAUSE.source'), (
            _from_name(effect['subject'], 'CHANGE.subject'),
            _from_name(effect['property'], 'CHANGE.property'),
        )
    except (ValueError, RecursionError) as exc:
        raise CausalError(f'outside v0.16 CAUSE subset: {exc}') from exc


@dataclass(frozen=True)
class Equation:
    name: str
    op: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class BooleanSCM:
    case_id: str
    mechanism: str
    exogenous: tuple[str, ...]
    equations: tuple[Equation, ...]
    outcomes: dict[tuple[str, str], str]
    note: str

    @classmethod
    def from_data(cls, data: Any) -> 'BooleanSCM':
        data = _exact(data, {'case_id', 'mechanism', 'exogenous', 'equations', 'outcomes', 'note'}, 'scenario')
        case_id = _identifier(data['case_id'], 'case_id')
        mechanism = _identifier(data['mechanism'], 'mechanism')
        if not isinstance(data['note'], str) or not data['note'].strip():
            raise CausalError('scenario note missing')
        exogenous = data['exogenous']
        if not isinstance(exogenous, list) or not (1 <= len(exogenous) <= 4):
            raise CausalError('exogenous must have 1-4 unique identifiers')
        exogenous = tuple(_identifier(x, 'exogenous') for x in exogenous)
        if len(set(exogenous)) != len(exogenous):
            raise CausalError('duplicate exogenous variable')
        equations_data = data['equations']
        if not isinstance(equations_data, list) or not (1 <= len(equations_data) <= 24):
            raise CausalError('equations must have 1-24 entries')
        known = set(exogenous)
        equations: list[Equation] = []
        for row in equations_data:
            row = _exact(row, {'name', 'op', 'args'}, 'equation')
            name = _identifier(row['name'], 'equation name')
            if name in known:
                raise CausalError('duplicate equation or collision with exogenous')
            op = row['op']
            args = row['args']
            if not isinstance(op, str) or op not in OPERATORS or not isinstance(args, list) or len(args) != OPERATORS[op]:
                raise CausalError(f'invalid operation or arity for {name}')
            args = tuple(_identifier(x, 'argument') for x in args)
            if not set(args).issubset(known):
                raise CausalError(f'unknown, forward or cyclic dependency for {name}')
            equations.append(Equation(name, op, args))
            known.add(name)
        outcomes_data = data['outcomes']
        if not isinstance(outcomes_data, list) or not (1 <= len(outcomes_data) <= 16):
            raise CausalError('outcomes must have 1-16 mappings')
        outcome_map: dict[tuple[str, str], str] = {}
        equation_names = {e.name for e in equations}
        for row in outcomes_data:
            row = _exact(row, {'subject', 'property', 'indicator'}, 'outcome')
            key = (_identifier(row['subject'], 'outcome subject'),
                   _identifier(row['property'], 'outcome property'))
            indicator = _identifier(row['indicator'], 'outcome indicator')
            if key in outcome_map or indicator not in equation_names:
                raise CausalError('duplicate outcome mapping or indicator is not endogenous')
            outcome_map[key] = indicator
        return cls(case_id, mechanism, exogenous, tuple(equations), outcome_map, data['note'])

    def contexts(self) -> Iterator[dict[str, bool]]:
        # Enumerate *all* contexts, including ones not observed in any data.
        for bits in product((False, True), repeat=len(self.exogenous)):
            yield dict(zip(self.exogenous, bits))

    def run(self, context: dict[str, bool], *, intervene: dict[str, bool] | None = None) -> dict[str, bool]:
        if not isinstance(context, dict) or set(context) != set(self.exogenous) or any(type(x) is not bool for x in context.values()):
            raise CausalError('background context must assign exactly the exogenous binary variables')
        intervene = {} if intervene is None else intervene
        targets = {eq.name for eq in self.equations}
        if (not isinstance(intervene, dict) or not set(intervene).issubset(targets) or
                any(type(x) is not bool for x in intervene.values())):
            raise CausalError('interventions must target named endogenous binary variables')
        state = dict(context)
        for eq in self.equations:
            if eq.name in intervene:
                # do(X=x) replaces the entire structural equation of X.
                state[eq.name] = intervene[eq.name]
                continue
            vals = [state[arg] for arg in eq.args]
            if eq.op == 'copy': value = vals[0]
            elif eq.op == 'not': value = not vals[0]
            elif eq.op == 'and': value = vals[0] and vals[1]
            elif eq.op == 'or': value = vals[0] or vals[1]
            elif eq.op == 'xor': value = vals[0] != vals[1]
            else: raise CausalError(f'unsupported operation {eq.op}')
            state[eq.name] = value
        return state

    def influence(self, expression: str) -> dict[str, Any]:
        source, effect_key = parse_cause(expression)
        if source not in {eq.name for eq in self.equations}:
            raise CausalError(f'source {source} missing from declared SCM')
        if effect_key not in self.outcomes:
            raise CausalError(f'effect {effect_key} missing from declared SCM')
        output_var = self.outcomes[effect_key]
        witness = None
        examined = 0
        for ctx in self.contexts():
            observed = self.run(ctx)
            low = self.run(ctx, intervene={source: False})
            high = self.run(ctx, intervene={source: True})
            examined += 1
            if low[output_var] != high[output_var] and witness is None:
                witness = {
                    'context': ctx, 'source': source, 'outcome_indicator': output_var,
                    'observed_source': observed[source],
                    'observed_outcome': observed[output_var],
                    'do_source_false': low[output_var],
                    'do_source_true': high[output_var],
                }
        return {
            'source': source, 'effect_subject': effect_key[0], 'effect_property': effect_key[1],
            'influence_in_some_context': witness is not None,
            'contexts_examined': examined, 'witness': witness,
        }

    def observational_association(self, expression: str) -> dict[str, Any]:
        source, key = parse_cause(expression)
        if source not in {eq.name for eq in self.equations} or key not in self.outcomes:
            raise CausalError('unmapped source or outcome')
        y = self.outcomes[key]
        outcomes = {False: [], True: []}
        for ctx in self.contexts():
            observed = self.run(ctx)
            outcomes[observed[source]].append(observed[y])
        if not all(outcomes.values()):
            return {'observational_association': None, 'observed_rates': None}
        rates = {str(k).lower(): str(Fraction(sum(values),len(values))) for k,values in outcomes.items()}
        return {'observational_association': Fraction(sum(outcomes[True]),len(outcomes[True])) != Fraction(sum(outcomes[False]),len(outcomes[False])),
                'observed_rates': rates}


def load_models(path: Path = FIXTURE) -> dict[str, BooleanSCM]:
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CausalError(f'could not load SCM fixtures: {exc}') from exc
    obj = _exact(obj, {'format', 'provenance', 'scenarios'}, 'causal fixture')
    if obj['format'] != VERSION or not isinstance(obj['provenance'], str) or 'assistant-authored' not in obj['provenance']:
        raise CausalError('wrong format or missing synthetic provenance')
    if not isinstance(obj['scenarios'], list) or not obj['scenarios']:
        raise CausalError('missing causal scenarios')
    models = [BooleanSCM.from_data(row) for row in obj['scenarios']]
    if len(set(m.case_id for m in models)) != len(models):
        raise CausalError('duplicate case_id')
    return {m.case_id: m for m in models}


def _guard_sources() -> None:
    pinned = [(SUITE, SOURCE_SHA256), (ACTIVE_PATTERNS, ACTIVE_SHA256), (V15_REPORT, V15_REPORT_SHA256)]
    for path, expected in pinned:
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise CausalError(f'frozen input was modified: {path.name}')


def report() -> dict[str, Any]:
    _guard_sources()
    models = load_models()
    source_rows = [r for r in jsonl(SUITE) if r.get('root') == 'CAUSE']
    if len(source_rows) != 8 or set(models) != {r['id'] for r in source_rows}:
        raise CausalError('fixed cause set and fixture set do not align')
    rows = []
    status_counts: dict[str, int] = {}
    model_classes: dict[str, int] = {}
    observation_vs_intervention = []
    for row in source_rows:
        model = models[row['id']]
        original = model.influence(row['expression'])
        observational = model.observational_association(row['expression'])
        model_classes[model.mechanism] = model_classes.get(model.mechanism, 0) + 1
        observation_vs_intervention.append({
            'case_id': row['id'], 'observational': observational,
            'original_influence_in_some_context': original['influence_in_some_context'],
        })
        for variant in row['variants']:
            f = variant['expression']
            item: dict[str, Any] = {'case_id': row['id'], 'variant': variant['type'],
                                    'scenario_mechanism': model.mechanism,
                                    'original': original, 'alternate': None, 'status': None}
            if normalize(f) == normalize(row['expression']):
                foil = model.influence(f)
                if original != foil:
                    raise CausalError('argument order changed intervention result')
                item['alternate'] = foil
                item['status'] = 'canonical_equivalent_same_scm'
            else:
                try:
                    foil = model.influence(f)
                except CausalError as exc:
                    # The v0.14 IS(...) swap is outside this typed CHANGE subset.
                    if variant['type'] != 'operator_or_coreference_change':
                        raise
                    item['status'] = 'outside_typed_causal_subset'
                    item['reason'] = str(exc)
                else:
                    item['alternate'] = foil
                    item['status'] = ('intervention_difference_in_stipulated_scm'
                                      if original['influence_in_some_context'] != foil['influence_in_some_context']
                                      else 'not_separated_in_stipulated_scm')
            status_counts[item['status']] = status_counts.get(item['status'], 0) + 1
            rows.append(item)
    if len(rows) != 24:
        raise CausalError('wrong comparison dimensions')
    return {
        'format': VERSION, 'scenario_fixture_sha256': sha256(FIXTURE.read_bytes()).hexdigest(),
        'frozen_v014_sha256': SOURCE_SHA256,
        'frozen_active_patterns_sha256': ACTIVE_SHA256,
        'frozen_v015_report_sha256': V15_REPORT_SHA256,
        'provenance': 'assistant-authored toy SCMs; zero observed or learned causal mechanisms',
        'scenarios': len(models), 'comparisons': len(rows),
        'status_counts': dict(sorted(status_counts.items())),
        'mechanism_counts': dict(sorted(model_classes.items())),
        'observational_vs_intervention': observation_vs_intervention,
        'independent_ai_readers': 0, 'empirical_causal_evidence': None,
        'ai_comprehension_score': None, 'active_registry_changed': False,
        'interpretation': ('In each stipulated finite deterministic binary SCM, CAUSE means there exists at least '
                           'one exogenous assignment where do(source=0) and do(source=1) yield different Boolean '
                           'outcome indicators. CHANGE is only a named outcome indicator, not a physical time-series '
                           'or verified real-world change. Observational association is not intervention.'),
        'results': rows,
    }


def verify_report() -> dict[str, Any]:
    fresh = report()
    try:
        saved = json.loads(REPORT.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise CausalError(f'invalid committed report: {exc}') from exc
    if saved != fresh:
        raise CausalError('committed causal report diverges from executable fixtures')
    for row in fresh['results']:
        for side in ('original', 'alternate'):
            value = row[side]
            if value and value['witness'] is not None:
                replay(row['case_id'], row['variant'], side=side, result=fresh)
    return {'checked': len(fresh['results']), 'contexts_per_model': 4,
            'witness_receipts_replayed': sum(bool(v and v['witness'] is not None)
                for row in fresh['results'] for v in (row['original'], row['alternate'])),
            'report_matches': True, 'real_world_causality': 'not established'}


def replay(case_id: str, variant: str, *, side: str = 'original',
           result: dict[str, Any] | None = None) -> dict[str, Any]:
    if side not in ('original', 'alternate'):
        raise CausalError('invalid receipt side')
    _guard_sources()
    result = report() if result is None else result
    matches = [r for r in result['results'] if r['case_id'] == case_id and r['variant'] == variant]
    if len(matches) != 1:
        raise CausalError('unknown case and variant')
    receipt = matches[0][side]
    if not isinstance(receipt, dict) or receipt['witness'] is None:
        raise CausalError('selected result has no positive intervention witness')
    w = receipt['witness']
    model = load_models()[case_id]
    source_row = next((r for r in jsonl(SUITE) if r['id'] == case_id and r['root'] == 'CAUSE'), None)
    if source_row is None:
        raise CausalError('source case missing')
    if side == 'original':
        expression = source_row['expression']
    else:
        variants = [v['expression'] for v in source_row['variants'] if v['type'] == variant]
        if len(variants) != 1:
            raise CausalError('source variant missing')
        expression = variants[0]
    if model.influence(expression) != receipt:
        raise CausalError('receipt does not match source expression and SCM')
    ctx = w['context']
    var, y = w['source'], w['outcome_indicator']
    if not (isinstance(ctx, dict) and set(ctx)==set(model.exogenous) and
            all(type(x) is bool for x in ctx.values()) and
            isinstance(var,str) and isinstance(y,str)):
        raise CausalError('invalid witness shape')
    observed = model.run(ctx)
    do0 = model.run(ctx, intervene={var: False})
    do1 = model.run(ctx, intervene={var: True})
    if (y not in observed or do0[y] == do1[y] or
            w != {'context': ctx, 'source': var, 'outcome_indicator': y,
                  'observed_source': observed[var], 'observed_outcome': observed[y],
                  'do_source_false': do0[y], 'do_source_true': do1[y]}):
        raise CausalError('witness fails independently recomputed intervention')
    return {'case_id': case_id, 'variant': variant, 'side': side,
            'context': ctx, 'source': var, 'outcome': y,
            'observed': {'source': observed[var], 'outcome': observed[y]},
            'do_source_false': do0[y], 'do_source_true': do1[y],
            'model_only': True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='ALCG toy, opt-in finite intervention laboratory')
    parser.add_argument('command', choices=['check', 'report', 'replay'])
    parser.add_argument('--case', default='G14_CAUSE_01')
    parser.add_argument('--variant', default='lexical_slot_change')
    parser.add_argument('--side', choices=['original', 'alternate'], default='original')
    args = parser.parse_args(argv)
    try:
        output = (verify_report() if args.command == 'check'
                  else report() if args.command == 'report'
                  else replay(args.case, args.variant, side=args.side))
        print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
    except (CausalError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
