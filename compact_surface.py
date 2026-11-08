"""ALCG v0.10: public-registry positional shorthand, with exact structural expansion.

This is optional syntax sugar on top of the v0.8 pattern registry; it is not
an encrypted encoding, a new logical operator, or a mesoscopic character.
Python >= 3.10, standard library only, no external AI calls.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from alcg import Call, Expr, Name, String, parse, render
from coverage_lab import DOMAINS, jsonl
from pattern_lab import BENCHMARK, PATTERNS, SOURCE, Pattern, PatternError, check, expand, load_patterns, sha256
from semantic_lab import normalize, compare

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / 'reports' / 'compact-surface-v0.10.json'
EXAMPLES = ROOT / 'benchmarks' / 'compact-roundtrips-v0.10.jsonl'
RISKS = ROOT / 'benchmarks' / 'compact-risk-probes-v0.10.jsonl'
FORMAT = 'ALCG-compact-surface-v0.10'

# Pinned public definitions from v0.8/v0.9. This is intentional: positional
# slots silently change meaning if somebody reorders the public registry.
LOCKED = {
    'patterns': (PATTERNS, '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'),
    'roundtrips': (BENCHMARK, 'b18682f859e2000bbc97dcc82d8520eef9b9ed9a5ee363106a89d86f4a315130'),
    'source': (SOURCE, '1555814a6ec16a4083c198cf8e72fe8e6de28cd19c87e76c8c3e6b59ccfd9ea9'),
}

_TOKEN = re.compile(r'@[A-Z][A-Z0-9_]*|[A-Za-z_][A-Za-z0-9_-]*|"(?:\\.|[^"\\])*"|[(),=\[\]|]')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_-]*\Z')
_ALIAS = re.compile(r'@[A-Z][A-Z0-9_]*\Z')
MAX_INPUT = 32768
MAX_TOKENS = 8000
MAX_DEPTH = 80


class CompactError(ValueError):
    """Invalid compact surface or non-reversible fixture."""


def locked_patterns() -> dict[str, Pattern]:
    for label, (path, expected_sha) in LOCKED.items():
        if sha256(path) != expected_sha:
            raise CompactError(f'{label} has changed; update registry version explicitly, not silently')
    try:
        return load_patterns()
    except PatternError as exc:
        raise CompactError(str(exc)) from exc


def tokenize(source: str) -> list[str]:
    if not isinstance(source, str) or len(source) > MAX_INPUT:
        raise CompactError('source must be a string with at most 32768 characters')
    tokens: list[str] = []
    pos = 0
    while pos < len(source):
        if source[pos].isspace():
            pos += 1
            continue
        match = _TOKEN.match(source, pos)
        if match is None:
            raise CompactError(f'invalid character at offset {pos}: {source[pos:pos+20]!r}')
        tokens.append(match.group())
        if len(tokens) > MAX_TOKENS:
            raise CompactError('token budget exceeded')
        pos = match.end()
    return tokens


class _Reader:
    def __init__(self, tokens: list[str], mapping: dict[str, Pattern]):
        self.tokens = tokens
        self.pos = 0
        self.mapping = mapping

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, token: str | None = None) -> str:
        value = self.peek()
        if value is None or (token is not None and token != value):
            raise CompactError(f'expected {token or "an expression"}, got {value!r}')
        self.pos += 1
        return value

    def expression(self, depth: int = 0) -> Expr:
        if depth > MAX_DEPTH:
            raise CompactError('surface recursion depth exceeded')
        item = self.take()
        if _ALIAS.fullmatch(item):
            name = 'P_' + item[1:]
            if name not in self.mapping:
                raise CompactError(f'unknown positional alias {item}; check registry')
            slots = self.mapping[name].slots
            self.take('[')
            values: list[Expr] = []
            if self.peek() != ']':
                while True:
                    values.append(self.expression(depth + 1))
                    if len(values) > len(slots):
                        raise CompactError(f'{item} has more than {len(slots)} slots')
                    if self.peek() != '|':
                        break
                    self.take('|')
            self.take(']')
            if len(values) != len(slots):
                raise CompactError(f'{item} needs exactly {len(slots)} slots in registry order {slots}')
            return Call(name, tuple(zip(slots, values)))
        if item.startswith('"'):
            # Quoted RAW content is disallowed in v0.8 patterns, and thus here.
            raise CompactError('quoted strings/RAW are not supported in lossless compact patterns')
        if not _NAME.fullmatch(item):
            raise CompactError(f'expected identifier or @alias, got {item!r}')
        if self.peek() != '(':
            return Name(item)
        self.take('(')
        args: list[tuple[str, Expr]] = []
        seen: set[str] = set()
        if self.peek() != ')':
            while True:
                role = self.take()
                if not _NAME.fullmatch(role):
                    raise CompactError(f'invalid named role: {role!r}')
                if role in seen:
                    raise CompactError(f'duplicate named role {role!r}')
                seen.add(role)
                self.take('=')
                args.append((role, self.expression(depth + 1)))
                if self.peek() != ',':
                    break
                self.take(',')
        self.take(')')
        return Call(item, tuple(args))


def parse_surface(source: str, mapping: dict[str, Pattern] | None = None) -> Expr:
    """Parse shorthand into an *unexpanded* pattern AST, not new core syntax."""
    mapping = mapping if mapping is not None else locked_patterns()
    reader = _Reader(tokenize(source), mapping)
    result = reader.expression()
    if reader.peek() is not None:
        raise CompactError(f'unexpected trailing token: {reader.peek()!r}')
    return result


def decode(source: str, mapping: dict[str, Pattern] | None = None) -> Expr:
    """Expand into the validated original ALCG AST; no interpretation inferred."""
    mapping = mapping if mapping is not None else locked_patterns()
    try:
        return expand(parse_surface(source, mapping), mapping)
    except PatternError as exc:
        raise CompactError(str(exc)) from exc


def _encode(node: Expr, mapping: dict[str, Pattern], depth: int) -> str:
    if depth > MAX_DEPTH:
        raise CompactError('encode recursion depth exceeded')
    if isinstance(node, Name):
        return node.value
    if isinstance(node, String):
        raise CompactError('quoted strings cannot be compacted into lossless patterns')
    args = dict(node.args)
    if node.name in mapping:
        slots = mapping[node.name].slots
        if set(args) != set(slots):
            raise CompactError(f'{node.name} does not match registry slots')
        return '@' + node.name[2:] + '[' + '|'.join(_encode(args[s], mapping, depth+1) for s in slots) + ']'
    return node.name + '(' + ','.join(k + '=' + _encode(value, mapping, depth+1)
                                       for k, value in node.args) + ')'


def encode(source: str | Expr, mapping: dict[str, Pattern] | None = None) -> str:
    """Re-serialize named v0.8 patterns with positional slots.

    Caller must supply registered named patterns if it wants a shorthand.
    This does not automatically invent or infer a new pattern from arbitrary English.
    """
    mapping = mapping if mapping is not None else locked_patterns()
    try:
        ast = parse(source) if isinstance(source, str) else source
        original = expand(ast, mapping)
        shorthand = _encode(ast, mapping, 0)
        result = decode(shorthand, mapping)
        if normalize(result) != normalize(original):
            raise CompactError('roundtrip changed the expanded canonical AST')
        return shorthand
    except PatternError as exc:
        raise CompactError(str(exc)) from exc


def structure_digest(expression: str | Expr, mapping: dict[str, Pattern] | None = None) -> str:
    """SHA-256 of the v0.5 canonical *expanded* AST, not a semantic theorem."""
    mapping = mapping if mapping is not None else locked_patterns()
    ast = decode(expression, mapping) if isinstance(expression, str) else expand(expression, mapping)
    return hashlib.sha256(normalize(ast).encode('utf-8')).hexdigest()


def risk_probes(mapping: dict[str, Pattern], path: Path = RISKS) -> dict[str, Any]:
    """Check selected *unlabelled slot* and scope mistakes are not misread as equal."""
    rows = jsonl(path)
    if (len(rows) != 10 or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows) or len({r['id'] for r in rows}) != len(rows)):
        raise CompactError('risk benchmark must have ten distinct cases')
    rejected = drift = finite_witnesses = 0
    for row in rows:
        if set(row) != {'id', 'category', 'intended', 'altered', 'expected', 'note'}:
            raise CompactError('invalid risk probe fields')
        if row['expected'] not in ('reject', 'structural_drift'):
            raise CompactError('invalid risk expectation')
        if not all(isinstance(row[k], str) and row[k].strip() for k in ('id', 'category', 'intended', 'altered', 'note')):
            raise CompactError('invalid risk text')
        reference = decode(row['intended'], mapping)
        if row['expected'] == 'reject':
            try:
                decode(row['altered'], mapping)
            except CompactError:
                rejected += 1
                continue
            raise CompactError(f'{row["id"]} should reject malformed shortening')
        alternate = decode(row['altered'], mapping)
        if normalize(alternate) == normalize(reference):
            raise CompactError(f'{row["id"]} unexpectedly matches canonical source')
        drift += 1
        if row['id'] in ('R07', 'R08'):
            try:
                result = compare(render(reference), render(alternate))
            except ValueError as exc:
                raise CompactError(f'{row["id"]} finite witness failed: {exc}') from exc
            if not result.first_witness:
                raise CompactError(f'{row["id"]} expected a finite-model counterexample')
            finite_witnesses += 1
    return {'risk_cases': len(rows), 'malformed_rejected': rejected,
            'canonical_drift_detected': drift, 'finite_world_counterexamples': finite_witnesses,
            'warning': 'Registry order is trusted; a role swap can be valid syntax but change intent.'}


def check_cases(examples: Path = EXAMPLES, risks: Path = RISKS) -> dict[str, Any]:
    mapping = locked_patterns()
    if check(mapping)['exact_canonical_roundtrips'] != 24:
        raise CompactError('frozen v0.8 roundtrips are not intact')
    original = {r['id']: r for r in jsonl(SOURCE)}
    old = {r['source_id']: r for r in jsonl(BENCHMARK)}
    rows = jsonl(examples)
    if len(rows) != 24 or len({r.get('source_id') for r in rows}) != 24:
        raise CompactError('requires exactly 24 fixed compact examples')
    domains: Counter[str] = Counter()
    lengths = Counter()
    patterns = Counter()
    for row in rows:
        if set(row) != {'source_id', 'compact', 'note'}:
            raise CompactError('bad compact fixture fields')
        sid = row['source_id']
        if sid not in old or row['note'] != old[sid]['note']:
            raise CompactError(f'{sid}: compact case does not match frozen benchmark')
        canonical = encode(old[sid]['pattern'], mapping)
        if row['compact'] != canonical:
            raise CompactError(f'{sid}: fixture differs from generated compact spelling')
        expected = original[sid]['expression']
        if normalize(decode(row['compact'], mapping)) != normalize(expected):
            raise CompactError(f'{sid}: compact expression loses the reference structure')
        domains[original[sid]['domain']] += 1
        lengths['original'] += len(expected)
        lengths['named_pattern'] += len(old[sid]['pattern'])
        lengths['compact'] += len(row['compact'])
        patterns.update(n.name for n in _walk_pattern(parse_surface(row['compact'], mapping)) if isinstance(n, Call) and n.name in mapping)
    if len(domains) != len(DOMAINS) or any(domains[d] != 4 for d in DOMAINS):
        raise CompactError('frozen six-domain balance changed')
    risks_report = risk_probes(mapping, risks)
    byte_savings = lengths['original'] - lengths['compact']
    registry_bytes = PATTERNS.stat().st_size
    return {
        'format': FORMAT,
        'registry_sha256': sha256(PATTERNS),
        'pattern_definitions': len(mapping),
        'frozen_cases': 24,
        'domains': dict(sorted(domains.items())),
        'exact_expanded_canonical_roundtrips': 24,
        'characters': dict(lengths),
        'characters_saved_vs_named_patterns': lengths['named_pattern'] - lengths['compact'],
        'characters_saved_vs_expanded_source': byte_savings,
        'registry_transfer_bytes': registry_bytes,
        'one_batch_payload_plus_registry_bytes': registry_bytes + lengths['compact'],
        'one_batch_expanded_source_bytes': lengths['original'],
        'repeated_24_case_batches_to_amortize_registry': (registry_bytes + byte_savings - 1) // byte_savings if byte_savings > 0 else None,
        'pattern_invocations': dict(sorted(patterns.items())),
        'risks': risks_report,
        'new_relation_operators': 0,
        'new_english_coverage_claims': 0,
        'independent_ai_comprehension_results': None,
        'disclaimer': 'Exact AST reconstruction requires the pinned public registry; no proof of cross-AI comprehension, truth, or lossless natural-language paraphrase.'
    }


def _walk_pattern(node: Expr):
    yield node
    if isinstance(node, Call):
        for _, value in node.args:
            yield from _walk_pattern(value)


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.10 positional abbreviation experiment')
    cmds = cli.add_subparsers(dest='command', required=True)
    cmds.add_parser('check')
    cmds.add_parser('report')
    p = cmds.add_parser('encode')
    p.add_argument('expression', help='An existing named P_ pattern expression')
    p = cmds.add_parser('decode')
    p.add_argument('expression', help='Compact surface expression such as @STATE[WATER|LIQUID]')
    p.add_argument('--expect-sha256', help='Expected SHA-256 of canonical expanded AST; mismatch fails closed')
    p = cmds.add_parser('digest')
    p.add_argument('expression', help='Compact surface expression to fingerprint')
    p = cmds.add_parser('export')
    p.add_argument('--out', type=Path, required=True)
    args = cli.parse_args(argv)
    try:
        if args.command == 'check':
            report = check_cases()
            print(f'OK: {report["exact_expanded_canonical_roundtrips"]} compact roundtrips; {report["risks"]["risk_cases"]} risk probes')
        elif args.command == 'report':
            print(json.dumps(check_cases(), ensure_ascii=False, indent=2))
        elif args.command == 'encode':
            print(encode(args.expression))
        elif args.command == 'decode':
            expanded = decode(args.expression)
            if args.expect_sha256 is not None:
                actual = structure_digest(expanded)
                if args.expect_sha256 != actual:
                    raise CompactError(f'expanded AST digest mismatch: expected {args.expect_sha256}, got {actual}')
            print(render(expanded))
        elif args.command == 'digest':
            print(structure_digest(args.expression))
        else:
            check_cases()
            data = [
                {'source_id': r['source_id'], 'compact': r['compact'],
                 'expanded': render(decode(r['compact'])),
                 'reference_sha256': structure_digest(r['compact'])}
                for r in jsonl(EXAMPLES)
            ]
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf-8', newline='\n') as f:
                for r in data:
                    f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
            print(f'Wrote {len(data)} nonblind examples: {args.out}')
        return 0
    except (CompactError, PatternError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
