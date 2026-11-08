"""ALCG v0.12: deterministic AST motif mining, never semantic proof or promotion.

Induces *candidate structures* from frozen author-authored benchmark expressions.
No independent AI participates in discovery or evaluation in this edition.
The same in-sample items induce and illustrate a candidate: no held-out claim.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from alcg import Call, Expr, Name, String, parse, render, walk
from compact_surface import check_cases, locked_patterns
from coverage_lab import jsonl
from pattern_evolution import (
    _signature, evaluate_one, read_proposals, PROPOSALS as V011_PROPOSALS,
    STAGED,
)
from pattern_lab import PATTERNS, Pattern, expand, sha256
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parent
SOURCES = (
    (ROOT / 'benchmarks' / 'coverage-v0.4.jsonl',
     '4569e6b8507340d7c26b1012504f73cdbe078448cf9f887fe256f1e90f2107c6'),
    (ROOT / 'benchmarks' / 'coverage-v0.6.jsonl',
     '1555814a6ec16a4083c198cf8e72fe8e6de28cd19c87e76c8c3e6b59ccfd9ea9'),
)
PROPOSALS = ROOT / 'benchmarks' / 'discovered-proposals-v0.12.jsonl'
REPORT = ROOT / 'reports' / 'pattern-discovery-v0.12.json'
FORMAT = 'ALCG-pattern-discovery-v0.12'
MIN_SUPPORT = 2
MAX_LEAVES = 18
MAX_GROUPS = 100


class DiscoveryError(ValueError):
    """Corpus, generated fixture or immutability invariant failed."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _layout(node: Expr) -> Any:
    """Call tree and named roles, excluding English lexical tokens."""
    if isinstance(node, Name):
        return ['N']
    if isinstance(node, String):
        raise DiscoveryError('quoted source excluded from the structural miner')
    return [node.name, [[key, _layout(value)] for key, value in sorted(node.args)]]


def _leaves(node: Expr, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    if isinstance(node, Name):
        return [(prefix, node.value)]
    if isinstance(node, String):
        raise DiscoveryError('quoted source excluded')
    output: list[tuple[tuple[str, ...], str]] = []
    for key, value in sorted(node.args):
        output.extend(_leaves(value, prefix + (key,)))
    return output


def _equality_classes(nodes: list[Expr]) -> tuple[int, ...]:
    """Only co-reference equalities supported by EVERY observed example survive.

    This rule is conservative about role sharing; it is not a semantic theorem.
    """
    columns = [tuple(value for _, value in _leaves(n)) for n in nodes]
    if not columns or not columns[0] or any(len(c) != len(columns[0]) for c in columns):
        raise DiscoveryError('inconsistent leaf vectors')
    equivalence: list[int] = []
    for index in range(len(columns[0])):
        previous = next((j for j in range(index)
                         if all(col[j] == col[index] for col in columns)), index)
        equivalence.append(equivalence[previous] if previous != index else index)
    remap = {p: i for i, p in enumerate(dict.fromkeys(equivalence))}
    return tuple(remap[p] for p in equivalence)


def _structural_identity(node: Expr, equality: tuple[int, ...] | None = None) -> str:
    """Operator/role outline + leaf co-reference partition; ignores lexical tokens."""
    leaf_count = len(_leaves(node))
    if equality is None:
        values = [s for _, s in _leaves(node)]
        refs = [values.index(v) for v in values]
        remap = {p: i for i, p in enumerate(dict.fromkeys(refs))}
        equality = tuple(remap[x] for x in refs)
    if len(equality) != leaf_count:
        raise DiscoveryError('identity partition length mismatch')
    return _stable_json({'tree': _layout(node), 'same_leaf': equality})


def _base_identities(base: dict[str, Pattern]) -> dict[str, str]:
    identities: dict[str, str] = {}
    for name, pat in sorted(base.items()):
        node = Call(name, tuple((slot, Name(f'ALCG_SLOTVALUE_{i}'))
                                for i, slot in enumerate(pat.slots)))
        expanded = expand(node, base)
        identities.setdefault(_structural_identity(expanded), name)
    return identities


def _staged_identities(base: dict[str, Pattern]) -> dict[str, str]:
    """Avoid pretending an already-staged v0.11 structure was discovered first."""
    original = json.loads(PATTERNS.read_text(encoding='utf-8'))
    known = {_signature(name, base): name for name in base}
    seen: set[str] = set()
    identities: dict[str, str] = {}
    for row in read_proposals(V011_PROPOSALS):
        result = evaluate_one(row, original, base, seen, known)
        if result['status'] != STAGED:
            continue
        from pattern_evolution import _mapping_with_candidate
        mapping = _mapping_with_candidate(original, row['pattern'])
        pat = mapping[row['pattern']['name']]
        call = Call(pat.name, tuple((slot, Name(f'ALCG_SLOT_{i}'))
                                    for i, slot in enumerate(pat.slots)))
        identities.setdefault(_structural_identity(expand(call, mapping)), pat.name)
    return identities


def _replace_leaves(node: Expr, assignments: dict[tuple[str, ...], str],
                    prefix: tuple[str, ...] = ()) -> Expr:
    if isinstance(node, Name):
        return Call('HOLE', (('slot', Name(assignments[prefix])),))
    if not isinstance(node, Call):
        raise DiscoveryError('strings not admissible')
    return Call(node.name, tuple((key, _replace_leaves(value, assignments, prefix + (key,)))
                                 for key, value in sorted(node.args)))


def _check_sources() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path, digest in SOURCES:
        if sha256(path) != digest:
            raise DiscoveryError(f'frozen corpus changed: {path.name}')
        for row in jsonl(path):
            if set(row) != {'id', 'domain', 'english', 'expression', 'hypothesis', 'gap'}:
                raise DiscoveryError(f'bad input row fields: {row.get("id", "?")}')
            if row['id'] in seen_ids:
                raise DiscoveryError(f'duplicate source ID {row["id"]}')
            seen_ids.add(row['id'])
            if row['hypothesis'] != 'candidate':
                continue
            if not all(isinstance(row.get(k), str) for k in ('id', 'domain', 'expression', 'english')):
                raise DiscoveryError('invalid candidate row')
            expr = parse(row['expression'])
            if not isinstance(expr, Call):
                continue
            normalize(expr)  # Enforce original v0.5 call/scope restrictions.
            rows.append({**row, 'ast': expr})
    return rows


def discover(*, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Infer only supported repeated root motifs; no auto-install or execution."""
    # Baselines explicitly stay immutable; any source digest mismatch fails closed.
    old = check_cases()
    if old['exact_expanded_canonical_roundtrips'] != 24:
        raise DiscoveryError('frozen v0.10 regression')
    base = locked_patterns()
    active_id = _base_identities(base)
    staged_id = _staged_identities(base)
    candidates = _check_sources() if rows is None else rows
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if row.get('hypothesis') != 'candidate':
            continue
        expr = row.get('ast') or parse(row['expression'])
        if not isinstance(expr, Call):
            continue
        if any(isinstance(n, String) for n in walk(expr)):
            continue
        groups[_stable_json(_layout(expr))].append({**row, 'ast': expr})
    if len(groups) > MAX_GROUPS:
        raise DiscoveryError('too many corpus shape groups')

    stats = Counter()
    suggestions: list[dict[str, Any]] = []
    for outline, rows_of_shape in sorted(groups.items()):
        if len(rows_of_shape) < MIN_SUPPORT:
            stats['low_support_shape_groups'] += 1
            continue
        rows_of_shape = sorted(rows_of_shape, key=lambda x: x['id'])
        nodes = [r['ast'] for r in rows_of_shape]
        if sum(isinstance(n, Call) for n in walk(nodes[0])) < 2:
            stats['single_operator_shape_groups'] += 1
            continue
        flat = _leaves(nodes[0])
        if not 1 <= len(flat) <= MAX_LEAVES:
            stats['too_many_leaves'] += 1
            continue
        if any([key for key, _ in _leaves(n)] != [key for key, _ in flat]
               for n in nodes):
            raise DiscoveryError('source groups differ in positions')
        if len({normalize(n) for n in nodes}) < 2:
            stats['insufficient_distinct_expressions'] += 1
            continue
        eq = _equality_classes(nodes)
        identity = _structural_identity(nodes[0], eq)
        if identity in active_id:
            stats['existing_active_structure'] += 1
            continue
        if identity in staged_id:
            stats['existing_v011_staged_structure'] += 1
            continue
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:10].upper()
        name = f'P_DISC_{nodes[0].name}_{digest}'
        assignment = {path: f'item_{eq[i]+1:02}' for i, (path, _) in enumerate(flat)}
        slots = list(dict.fromkeys(assignment.values()))
        template = render(_replace_leaves(nodes[0], assignment))
        evidence: list[dict[str, str]] = []
        for row in rows_of_shape:
            values = [value for _, value in _leaves(row['ast'])]
            actual = {slot: values[i] for i, slot in enumerate([assignment[p] for p, _ in flat])}
            if any(actual[assignment[p]] != values[i] for i, (p, _) in enumerate(flat)):
                raise DiscoveryError('inferred equality violated')
            call = Call(name, tuple((slot, Name(actual[slot])) for slot in slots))
            evidence.append({'input': render(call), 'expected': row['expression']})
        proposal = {
            'id': f'DISC12-{digest}',
            'origin': 'deterministic-motif-miner-v0.12-pinned-authored-corpus',
            'pattern': {
                'name': name, 'slots': slots, 'template': template,
                'gloss': ('Machine-induced reusable AST shape; English lexical content '
                          'and intended meaning need independent human review.'),
            },
            'examples': evidence,
            'note': ('Root-tree motif inferred from existing annotated English examples; '
                     'roles and repeated names are preserved but semantics not inferred.'),
        }
        suggestions.append({'proposal': proposal,
                            'source_ids': [r['id'] for r in rows_of_shape],
                            'domains': sorted({r['domain'] for r in rows_of_shape}),
                            'support': len(rows_of_shape),
                            'structural_signature': hashlib.sha256(identity.encode('utf-8')).hexdigest(),
                            'shared_leaf_groups': len(slots),
                            'leaf_positions': len(flat)})
    # Evidence density and cross-domain exposure are ranking heuristics ONLY.
    suggestions.sort(key=lambda x: (-len(x['domains']), -x['support'],
                                    x['proposal']['pattern']['name']))
    if len(suggestions) > 48:
        raise DiscoveryError('too many candidate proposals for v0.11 gate')
    return {'source_candidates': len(candidates),
            'shape_groups': len(groups),
            'skipped': dict(sorted(stats.items())),
            'suggestions': suggestions,
            'promotion_performed': False}


def review(discovery: dict[str, Any] | None = None) -> dict[str, Any]:
    result = discover() if discovery is None else discovery
    base = locked_patterns()
    base_doc = json.loads(PATTERNS.read_text(encoding='utf-8'))
    known = {_signature(name, base): name for name in base}
    seen_names: set[str] = set()
    reviewed = []
    for item in result['suggestions']:
        proposal = item['proposal']
        decision = evaluate_one(proposal, base_doc, base, seen_names, known)
        total = decision.get('sample_bytes', {})
        saved = total.get('difference_excluding_registry', 0)
        definition_bytes = len(_stable_json(proposal['pattern']).encode('utf-8'))
        uses = len(proposal['examples'])
        reviewed.append({
            'id': proposal['id'], 'name': proposal['pattern']['name'],
            'source_ids': item['source_ids'], 'domains': item['domains'],
            'in_sample_support': item['support'], 'status': decision['status'],
            'gate_reason': decision['reason'],
            'normalized_expansion_checked': decision.get('examples_checked', 0),
            'leaf_positions': item['leaf_positions'],
            'slot_groups': item['shared_leaf_groups'],
            'sample_original_bytes': total.get('expanded'),
            'sample_compact_bytes': total.get('compact'),
            'sample_payload_bytes_saved': saved,
            'incremental_definition_bytes_estimate': definition_bytes,
            'net_bytes_after_single_definition': saved - definition_bytes,
            'estimated_reuses_to_amortize_definition': (
                (definition_bytes * uses + saved - 1) // saved if saved > 0 else None),
            'signature_sha256': item['structural_signature'],
        })
    return {
        'format': FORMAT,
        'corpus_sha256': {p.relative_to(ROOT).as_posix(): d for p, d in SOURCES},
        'public_registry_sha256': sha256(PATTERNS),
        'v0_10_frozen_roundtrips': 24,
        'v0_11_existing_gate_sha256': sha256(V011_PROPOSALS),
        'input_author_curated_candidates': result['source_candidates'],
        'root_shape_groups': result['shape_groups'],
        'skipped_group_reasons': result['skipped'],
        'generated_candidate_count': len(result['suggestions']),
        'structural_gate_outcomes': dict(sorted(Counter(r['status'] for r in reviewed).items())),
        'ranked_candidates': reviewed,
        'registry_automatically_modified': False,
        'new_operators': 0,
        'independent_ai_participants': 0,
        'heldout_transfer_results': None,
        'semantic_quality_scores': None,
        'caution': ('These structures were inferred and checked on the SAME author-curated '
                    'examples. No independent validation, semantic equivalence, new English '
                    'coverage or AI comprehension is demonstrated. Candidate list is NOT active.'),
    }


def generated_jsonl(discovery: dict[str, Any] | None = None) -> str:
    result = discover() if discovery is None else discovery
    return ''.join(_stable_json(item['proposal']) + '\n' for item in result['suggestions'])


def verify_snapshot() -> dict[str, Any]:
    discovery = discover()
    report = review(discovery)
    if PROPOSALS.read_text(encoding='utf-8') != generated_jsonl(discovery):
        raise DiscoveryError('committed candidate proposals differ from regenerated output')
    if json.loads(REPORT.read_text(encoding='utf-8')) != report:
        raise DiscoveryError('committed discovery report differs from regenerated output')
    if report['generated_candidate_count'] == 0:
        raise DiscoveryError('unexpected empty discovery set')
    if report['v0_10_frozen_roundtrips'] != 24 or report['registry_automatically_modified']:
        raise DiscoveryError('regression or unintended promotion')
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='ALCG v0.12 deterministic pattern discovery, NOT auto-promotion')
    p.add_argument('command', choices=['check', 'report', 'export-proposals'])
    p.add_argument('--out', type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == 'check':
            report = verify_snapshot()
            print(f'OK: {report["generated_candidate_count"]} review-only patterns from pinned corpus; frozen registry unchanged')
        elif args.command == 'report':
            print(json.dumps(review(), sort_keys=True, indent=2, ensure_ascii=False))
        else:
            if args.out is None:
                raise DiscoveryError('export-proposals requires --out')
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf-8', newline='\n') as f:
                f.write(generated_jsonl())
            print(f'wrote non-active proposals to {args.out}')
        return 0
    except (OSError, ValueError, RuntimeError, RecursionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
