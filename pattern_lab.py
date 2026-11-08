"""ALCG v0.8: transparent, explicitly expanded English-symbol composition patterns.

This is a syntactic template experiment, NOT verified semantic understanding,
execution, cryptography, or a mesoscopic character system. Python >= 3.10.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from alcg import Call, Expr, Name, String, ParseError, parse, render, walk
from coverage_lab import BenchmarkError, DOMAINS, inspect_calls, jsonl, relations
from finite_probe import ProbeError, check_scopes
from semantic_lab import LabError, normalize

ROOT = Path(__file__).resolve().parent
PATTERNS = ROOT / 'data' / 'patterns-v0.8.json'
BENCHMARK = ROOT / 'benchmarks' / 'pattern-roundtrips-v0.8.jsonl'
SOURCE = ROOT / 'benchmarks' / 'coverage-v0.6.jsonl'
RELATIONS = ROOT / 'data' / 'relations-v0.4.json'
FORMAT = 'ALCG-patterns-v0.8'
PATTERN_ID = re.compile(r'P_[A-Z][A-Z0-9_]*\Z')
SLOT_ID = re.compile(r'[a-z][a-z0-9_]*\Z')
SOURCE_SHA256 = '1555814a6ec16a4083c198cf8e72fe8e6de28cd19c87e76c8c3e6b59ccfd9ea9'
RELATIONS_SHA256 = '8ea3fbb5ceba073eac2904ada7469809be2556f319a4a627f705a7db4e08f34e'


class PatternError(ValueError):
    """Malformed pattern registry, application, or fixture."""


@dataclass(frozen=True)
class Pattern:
    name: str
    slots: tuple[str, ...]
    template: Expr
    gloss: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roles(node: Call) -> dict[str, Expr]:
    return dict(node.args)


def _hole(node: Call, expected: set[str]) -> str:
    roles = _roles(node)
    if set(roles) != {'slot'} or not isinstance(roles['slot'], Name):
        raise PatternError('HOLE must be HOLE(slot=lowercase_name)')
    slot = roles['slot'].value
    if slot not in expected:
        raise PatternError(f'undeclared HOLE slot: {slot}')
    return slot


def load_patterns(path: Path = PATTERNS) -> dict[str, Pattern]:
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PatternError(f'could not read pattern registry: {exc}') from exc
    if not isinstance(document, dict) or set(document) != {'format', 'description', 'patterns'} or document['format'] != FORMAT:
        raise PatternError('unknown pattern registry format')
    rows = document['patterns']
    if not isinstance(rows, list) or not rows:
        raise PatternError('patterns must be a nonempty list')
    mapping: dict[str, Pattern] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'name', 'slots', 'template', 'gloss'}:
            raise PatternError('pattern fields must be name, slots, template, gloss')
        name, slots = row['name'], row['slots']
        if not isinstance(name, str) or not PATTERN_ID.fullmatch(name) or name in mapping:
            raise PatternError(f'invalid or duplicate pattern ID: {name!r}')
        if (not isinstance(slots, list) or len(slots) > 12 or not slots or
                any(not isinstance(s, str) or not SLOT_ID.fullmatch(s) for s in slots) or
                len(set(slots)) != len(slots)):
            raise PatternError(f'{name}: invalid slots')
        if not isinstance(row['gloss'], str) or len(row['gloss'].strip()) < 12:
            raise PatternError(f'{name}: missing intended-reading note')
        if not isinstance(row['template'], str):
            raise PatternError(f'{name}: missing template expression')
        try:
            node = parse(row['template'])
        except ParseError as exc:
            raise PatternError(f'{name}: {exc}') from exc
        mapping[name] = Pattern(name, tuple(slots), node, row['gloss'])

    native = relations(RELATIONS)
    for name, pattern in mapping.items():
        used: set[str] = set()
        for node in walk(pattern.template):
            if isinstance(node, String):
                raise PatternError(f'{name}: quoted strings not allowed in reusable patterns')
            if not isinstance(node, Call):
                continue
            if node.name == 'HOLE':
                used.add(_hole(node, set(pattern.slots)))
                continue
            roles = set(_roles(node))
            if node.name in mapping:
                needed = set(mapping[node.name].slots)
                if roles != needed:
                    raise PatternError(f'{name}: {node.name} requires exactly {sorted(needed)}')
            elif node.name in native:
                spec = native[node.name]
                required = set(spec['required'])
                allowed = required | set(spec['optional'])
                if not required.issubset(roles) or not roles.issubset(allowed):
                    raise PatternError(f'{name}: invalid roles for {node.name}')
                if node.name in {'RAW', 'PARTIAL'}:
                    raise PatternError(f'{name}: RAW/PARTIAL may not be hidden in a pattern')
                if node.name == 'REF':
                    var = _roles(node).get('var')
                    if not isinstance(var, Call) or var.name != 'HOLE':
                        raise PatternError(f'{name}: REF variables must be caller-supplied HOLE values')
                    _hole(var, set(pattern.slots))
                if node.name in {'FORALL', 'EXISTS'}:
                    # Binders must remain explicitly supplied by the caller.
                    # No implicit variable name may capture a supplied REF.
                    var = _roles(node).get('var')
                    if not isinstance(var, Call) or var.name != 'HOLE':
                        raise PatternError(f'{name}: quantified var must be a caller-supplied HOLE')
                    _hole(var, set(pattern.slots))
            else:
                raise PatternError(f'{name}: unknown operator {node.name}')
        if used != set(pattern.slots):
            raise PatternError(f'{name}: declared slots not used: {sorted(set(pattern.slots) - used)}')

    # Detect cycles before expansion; accidental cycles must not consume runtime.
    dependencies = {name: {n.name for n in walk(item.template)
                            if isinstance(n, Call) and n.name in mapping}
                    for name, item in mapping.items()}
    done: set[str] = set()
    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name in chain:
            raise PatternError('pattern cycle: ' + ' -> '.join(chain + (name,)))
        if name in done:
            return
        for child in sorted(dependencies[name]):
            visit(child, chain + (name,))
        done.add(name)
    for name in mapping:
        visit(name, ())
    return mapping


@dataclass
class _Budget:
    remaining: int
    def tick(self) -> None:
        self.remaining -= 1
        if self.remaining < 0:
            raise PatternError('expansion node budget exceeded')


def _substitute(node: Expr, supplied: dict[str, Expr], budget: _Budget, depth: int) -> Expr:
    if depth > 80:
        raise PatternError('template nesting limit exceeded')
    budget.tick()
    if not isinstance(node, Call):
        return node
    if node.name == 'HOLE':
        return supplied[_hole(node, set(supplied))]
    return Call(node.name, tuple((key, _substitute(v, supplied, budget, depth + 1))
                                 for key, v in node.args))


def _expand(node: Expr, mapping: dict[str, Pattern], budget: _Budget, depth: int) -> Expr:
    if depth > 80:
        raise PatternError('expression nesting limit exceeded')
    budget.tick()
    if not isinstance(node, Call):
        return node
    if node.name == 'HOLE':
        raise PatternError('HOLE is legal only in registered templates')
    if node.name not in mapping:
        return Call(node.name, tuple((k, _expand(v, mapping, budget, depth + 1))
                                     for k, v in node.args))
    definition = mapping[node.name]
    roles = _roles(node)
    if set(roles) != set(definition.slots):
        raise PatternError(f'{node.name} needs exactly {sorted(definition.slots)}')
    supplied = {k: _expand(roles[k], mapping, budget, depth + 1) for k in definition.slots}
    filled = _substitute(definition.template, supplied, budget, depth + 1)
    return _expand(filled, mapping, budget, depth + 1)


def expand(expression: str | Expr, mapping: dict[str, Pattern], *, budget: int = 10000) -> Expr:
    try:
        parsed = parse(expression) if isinstance(expression, str) else expression
        result = _expand(parsed, mapping, _Budget(budget), 0)
        inspect_calls(result, relations(RELATIONS))
        check_scopes(result)
        if any(isinstance(n, String) or (isinstance(n, Call) and n.name in {'RAW', 'PARTIAL'})
               for n in walk(result)):
            raise PatternError('patterns v0.8 only handle structured text, not RAW/strings')
        return result
    except (ParseError, ProbeError, BenchmarkError) as exc:
        raise PatternError(str(exc)) from exc


def check(mapping: dict[str, Pattern] | None = None, cases: Path = BENCHMARK) -> dict[str, Any]:
    mapping = mapping or load_patterns()
    if sha256(SOURCE) != SOURCE_SHA256 or sha256(RELATIONS) != RELATIONS_SHA256:
        raise PatternError('frozen source or relation file was altered')
    source = {r['id']: r for r in jsonl(SOURCE) if r['hypothesis'] == 'candidate'}
    rows = jsonl(cases)
    if len(rows) != 24:
        raise PatternError('v0.8 benchmark requires 24 curated roundtrips')
    count: Counter[str] = Counter()
    seen: set[str] = set()
    calls: Counter[str] = Counter()
    length_original = 0
    length_patterned = 0
    for row in rows:
        if set(row) != {'source_id', 'pattern', 'note'} or any(not isinstance(v, str) for v in row.values()):
            raise PatternError('incorrect roundtrip fields')
        sid = row['source_id']
        if sid in seen or sid not in source:
            raise PatternError(f'duplicate or invalid candidate ID: {sid}')
        if not row['note'].strip():
            raise PatternError(f'{sid}: missing reason for pattern choice')
        count[source[sid]['domain']] += 1
        original = source[sid]['expression']
        try:
            expanded = expand(row['pattern'], mapping)
            if normalize(expanded) != normalize(original):
                raise PatternError(f'{sid}: expansion changes the original structure')
        except (PatternError, LabError) as exc:
            raise PatternError(f'{sid}: {exc}') from exc
        calls.update(n.name for n in walk(parse(row['pattern'])) if isinstance(n, Call) and n.name in mapping)
        if not any(n.name in mapping for n in walk(parse(row['pattern'])) if isinstance(n, Call)):
            raise PatternError(f'{sid}: not a pattern experiment')
        seen.add(sid)
        length_original += len(original)
        length_patterned += len(row['pattern'])
    if any(count[d] != 4 for d in DOMAINS):
        raise PatternError('requires 4 frozen candidates per each of six domains')
    return {
        'version': '0.8',
        'pattern_definitions': len(mapping),
        'roundtrip_cases': len(rows),
        'domains': dict(sorted(count.items())),
        'source_candidates_remaining_frozen': len(source),
        'exact_canonical_roundtrips': len(rows),
        'pattern_invocations': dict(sorted(calls.items())),
        'source_characters_in_selected_examples': length_original,
        'pattern_characters_in_selected_examples': length_patterned,
        'new_relation_operators': 0,
        'new_english_coverage_claims': 0,
        'independent_ai_reader_results': None,
        'note': 'Exact structural expansion on 24 selected, public, authored expressions; NOT semantic coverage or AI comprehension.'
    }


def export(cases: Path, mapping: dict[str, Pattern]) -> list[dict[str, str]]:
    source = {r['id']: r for r in jsonl(SOURCE)}
    check(mapping, cases)
    return [
        {'source_id': r['source_id'], 'pattern': r['pattern'],
         'expanded': render(expand(r['pattern'], mapping)),
         'reference': source[r['source_id']]['expression']}
        for r in jsonl(cases)
    ]


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.8 transparent pattern expansion (no AI calls)')
    subs = cli.add_subparsers(dest='command', required=True)
    subs.add_parser('check')
    subs.add_parser('report')
    p = subs.add_parser('expand')
    p.add_argument('expression')
    p = subs.add_parser('export')
    p.add_argument('--out', type=Path, required=True)
    args = cli.parse_args(argv)
    try:
        mapping = load_patterns()
        if args.command == 'check':
            report = check(mapping)
            print(f"OK: {report['exact_canonical_roundtrips']} structural roundtrips across six domains")
        elif args.command == 'report':
            print(json.dumps(check(mapping), ensure_ascii=False, indent=2))
        elif args.command == 'expand':
            print(render(expand(args.expression, mapping)))
        else:
            payload = export(BENCHMARK, mapping)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf-8', newline='\n') as handle:
                for row in payload:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
            print(f'Wrote {len(payload)} expanded cases: {args.out}')
        return 0
    except (PatternError, OSError, BenchmarkError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
