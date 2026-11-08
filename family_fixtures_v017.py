"""Deterministic, assistant-authored synthetic SCM families for ALCG v0.17.

Each row is deliberately *stipulated*. Reconstruct the public fixture with
``python family_fixtures_v017.py emit``; check without modifying any files.
This generator is not a causal discovery algorithm or an AI understanding test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'data' / 'causal-families-v0.17.json'
FORMAT = 'ALCG-v0.17-stipulated-binary-scm-families'


def _model(family: str, number: int, mechanism: str,
           equations: list[tuple[str, str, tuple[str, ...]]],
           subject: str, property_name: str, note: str) -> dict:
    steps = [('SIGNAL', 'copy', ('U',))] + equations
    return {
        'case_id': f'{family}_M{number}',
        'mechanism': mechanism,
        'exogenous': ['U', 'G'],
        'equations': [dict(name=n, op=o, args=list(a)) for n, o, a in steps],
        'outcomes': [{'subject': subject, 'property': property_name, 'indicator': 'Y'}],
        'note': note,
    }


def _family(family: str, subject: str, property_name: str, question: str,
            plans: list[tuple[str, list[tuple[str, str, tuple[str, ...]]], str]]) -> dict:
    return {
        'family_id': family,
        'expression': f'CAUSE(source=SIGNAL, effect=CHANGE(subject={subject}, property={property_name}))',
        'question': question,
        'models': [_model(family, i, name, equations, subject, property_name, note)
                   for i, (name, equations, note) in enumerate(plans, 1)],
    }


def build_fixture() -> dict:
    return {
        'format': FORMAT,
        'provenance': ('assistant-authored synthetic families, not inferred from observations, '
                       'not empirical causality or an independent AI reading experiment'),
        'context_alignment': ('Each family shares exactly the exogenous names U,G, the endogenous '
                              'source SIGNAL and one named Boolean output Y. All U,G assignments '
                              'are compared without probabilistic interpretation.'),
        'families': [
            _family('F17_DIRECT', 'NETWORK_NODE', 'RELIABILITY',
                    'Is the full do-response identical despite internal DAG changes?', [
                ('direct', [('Y','copy',('SIGNAL',))], 'Y copies SIGNAL.'),
                ('mediated', [('M','copy',('SIGNAL',)), ('Y','copy',('M',))], 'M mediates the same mapping.'),
                ('irrelevant_gate', [('NG','not',('G',)), ('NEVER','and',('G','NG')),
                                     ('Y','or',('SIGNAL','NEVER'))], 'Gate creates a zero-valued branch.'),
            ]),
            _family('F17_DIRECTION_ONLY', 'SENSOR_ARRAY', 'ACTIVE_STATE',
                    'Can intervention direction remain stable while the unresponsive baseline changes?', [
                ('gated_and', [('Y','and',('SIGNAL','G'))], 'Suppressed outcome is false when G is false.'),
                ('gated_or', [('NG','not',('G',)), ('Y','or',('SIGNAL','NG'))],
                 'Suppressed outcome is true when G is false.'),
                ('mediated_gate', [('M','copy',('SIGNAL',)), ('Y','and',('M','G'))],
                 'Intermediary preserves sign, not a new context.'),
            ]),
            _family('F17_CONTEXT', 'ROBOTIC_ARM', 'CONTROL_SIGNAL',
                    'Does agreement exist only when the background gate is true?', [
                ('gated_and', [('Y','and',('SIGNAL','G'))], 'Positive response only under G=true.'),
                ('direct', [('Y','copy',('SIGNAL',))], 'Positive response under both gate settings.'),
                ('conditional_xor', [('NG','not',('G',)), ('Y','xor',('SIGNAL','NG'))],
                 'Negative response under G=false; positive under G=true.'),
            ]),
            _family('F17_POLARITY', 'TEST_CHAMBER', 'PRESSURE_STATE',
                    'Can all mechanisms be causal while intervention signs disagree?', [
                ('excitatory', [('Y','copy',('SIGNAL',))], 'Positive intervention response.'),
                ('inhibitory', [('Y','not',('SIGNAL',))], 'Negative intervention response.'),
                ('conditional_xor', [('Y','xor',('SIGNAL','G'))], 'Sign changes with G.'),
            ]),
            _family('F17_DISPUTED', 'POWER_GRID', 'LOAD_STATE',
                    'Does observational co-movement identify robust intervention influence?', [
                ('direct', [('Y','copy',('SIGNAL',))], 'Positive intervention response.'),
                ('confounded_proxy', [('Y','copy',('U',))],
                 'Observed source and outcome agree but intervening on SIGNAL does nothing.'),
                ('gated', [('Y','and',('SIGNAL','G'))], 'Only G=true exhibits influence.'),
            ]),
            _family('F17_NO_EFFECT', 'MARKET_SYSTEM', 'SIGNAL_STATE',
                    'Can all mechanisms omit an effect of the named intervention?', [
                ('shared_driver', [('Y','copy',('U',))], 'Observation may correlate, do response is null.'),
                ('independent_gate', [('Y','copy',('G',))], 'No relation to SIGNAL.'),
                ('inverse_driver', [('Y','not',('U',))], 'Inverse association, still no do response.'),
            ]),
            _family('F17_NEGATIVE', 'CHEMICAL_REACTOR', 'SAFETY_STATE',
                    'Is a negative effect direction stable despite baseline differences?', [
                ('inhibitory_and', [('INV','not',('SIGNAL',)), ('Y','and',('INV','G'))],
                 'Negative only under G=true, else false.'),
                ('negated_or', [('NG','not',('G',)), ('MASK','or',('SIGNAL','NG')),
                                 ('Y','not',('MASK',))], 'Equivalent negative gate.'),
                ('inhibitory_or', [('INV','not',('SIGNAL',)), ('NG','not',('G',)),
                                    ('Y','or',('INV','NG'))],
                 'Negative only under G=true, but suppressed baseline is true.'),
            ]),
        ],
    }


def serialized_fixture() -> str:
    return json.dumps(build_fixture(), ensure_ascii=False, indent=2) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'emit'))
    args = parser.parse_args(argv)
    try:
        content = serialized_fixture()
        if args.command == 'emit':
            print(content, end='')
        else:
            actual = FIXTURE.read_text(encoding='utf-8')
            if content != actual:
                raise ValueError('committed family fixture differs from deterministic builder')
            print('OK: 7 deterministic model families, 21 stipulated models')
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
