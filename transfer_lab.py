"""ALCG v0.13: out-of-miner-set structural transfer and adversarial probes.

No AI participants. Only deterministic syntax/AST matching and reversibility.
All v0.12 mined patterns are review-only and loaded ephemerally; nothing
is promoted to the active registry. The historical contrast data PRE-DATES
v0.12 induction but is not an independently sampled language benchmark.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256 as digest
import json
from pathlib import Path
import sys
from typing import Any

from alcg import Call, Expr, Name, String, parse, render
from compact_surface import check_cases, decode, encode, locked_patterns
from coverage_lab import jsonl
from pattern_discovery import (
    SOURCES as TRAIN_SOURCES,
    PROPOSALS as PROPOSALS_V012,
    REPORT as REPORT_V012,
    verify_snapshot as verify_v012,
)
from pattern_evolution import read_proposals
from pattern_lab import PATTERNS, Pattern, expand, sha256
from semantic_lab import normalize

ROOT = Path(__file__).resolve().parent
FORMAT = 'ALCG-transfer-lab-v0.13'
PROBES = ROOT / 'benchmarks' / 'transfer-pairs-v0.13.jsonl'
REPORT = ROOT / 'reports' / 'transfer-lab-v0.13.json'
# These contrast datasets were committed before v0.12 discovery. They were not
# inputs to the miner. They contain both valid readings and deliberate foils.
HISTORICAL = (
    ROOT / 'benchmarks' / 'contrast-v0.3.jsonl',
    ROOT / 'benchmarks' / 'contrast-v0.4.jsonl',
    ROOT / 'benchmarks' / 'reader-contrast-v0.7.jsonl',
)
# Anchored evidence: digests checked by verify_snapshot for training;
# these historical digests are pinned independently in the v0.13 fixture.
HISTORICAL_PIN = {'benchmarks/contrast-v0.3.jsonl': 'a09980c40f27c52f95b901332c63b7a3d696506be0e730700c47a3481b93d7fe', 'benchmarks/contrast-v0.4.jsonl': 'be12dd32a0b430996464f50dadbae203a2b802b92c8ef63fc635ac0a85079b74', 'benchmarks/reader-contrast-v0.7.jsonl': '6f0ad9d9c0164610059c9198e057d8edde21e49db601b2ed4fbe27935eb7b739'}
EXPECTED = {'historical_total': 96, 'historical_eligible': 57,
            'historical_exact_training_overlap': 39,
            'historical_matched': 3, 'historical_matched_foils': 3,
            'targeted_pairs': 16, 'targeted_matches': 16,
            'targeted_matching_foils': 8, 'targeted_rejected_foils': 8}


class TransferError(ValueError):
    """Input, matcher, no-leakage or output-contract validation failed."""


def _hash_text(text: str) -> str:
    return digest(text.encode('utf-8')).hexdigest()


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _match(template: Expr, target: Expr, bound: dict[str, str], depth: int = 0) -> bool:
    """Match explicit named roles and HOLE reference equalities, not semantics.

    No mutation leaks from a failed match: callers supply a fresh `bound`.
    All v0.12 HOLE positions are Name leaves, not arbitrary subexpressions.
    """
    if depth > 80:
        raise TransferError('template or sample nesting too deep')
    if isinstance(template, Call) and template.name == 'HOLE':
        roles = dict(template.args)
        if set(roles) != {'slot'} or not isinstance(roles['slot'], Name):
            raise TransferError('invalid HOLE in pinned proposal')
        if not isinstance(target, Name):
            return False
        slot = roles['slot'].value
        if slot in bound:
            return bound[slot] == target.value
        bound[slot] = target.value
        return True
    if isinstance(template, Name):
        return isinstance(target, Name) and template.value == target.value
    if isinstance(template, String) or isinstance(target, String):
        return False
    if not isinstance(template, Call) or not isinstance(target, Call):
        return False
    if template.name != target.name:
        return False
    template_roles, target_roles = dict(template.args), dict(target.args)
    if set(template_roles) != set(target_roles):
        return False
    return all(_match(template_roles[k], target_roles[k], bound, depth+1)
               for k in sorted(template_roles))


def apply_pattern(expression: str | Expr, pattern: Pattern,
                  active: dict[str, Pattern]) -> dict[str, Any] | None:
    """Infer a candidate *call* from a complete expression and verify expansion.

    Returns None for a non-matching operator/role/ref shape. A matching wrong
    English interpretation is still a match, and will NOT be called correct.
    """
    ast = parse(expression) if isinstance(expression, str) else expression
    bound: dict[str, str] = {}
    if not _match(pattern.template, ast, bound):
        return None
    if set(bound) != set(pattern.slots):
        raise TransferError(f'{pattern.name}: missing/extra slots in matcher')
    call = Call(pattern.name, tuple((slot, Name(bound[slot])) for slot in pattern.slots))
    trial_registry = dict(active)
    if pattern.name in trial_registry:
        raise TransferError('candidate collides with active registry')
    trial_registry[pattern.name] = pattern  # in-memory ONLY, never persisted
    original = normalize(ast)
    restored = normalize(expand(call, trial_registry))
    if restored != original:
        raise TransferError('reconstruction did not preserve canonical expanded AST')
    compact = encode(call, trial_registry)
    if normalize(decode(compact, trial_registry)) != original:
        raise TransferError('positional shorthand changed structure')
    return {'call': render(call), 'compact': compact,
            'sha256': _hash_text(original),
            'expanded_utf8_bytes': len(render(ast).encode('utf-8')),
            'compact_utf8_bytes': len(compact.encode('utf-8'))}


def _read_candidate_patterns() -> tuple[list[Pattern], dict[str, Pattern]]:
    report = verify_v012()
    if report['generated_candidate_count'] != 4 or report['registry_automatically_modified']:
        raise TransferError('expected four NON-ACTIVE proposals from frozen v0.12')
    active = locked_patterns()
    proposal_rows = read_proposals(PROPOSALS_V012)
    patterns = []
    for row in proposal_rows:
        p = row['pattern']
        patterns.append(Pattern(p['name'], tuple(p['slots']), parse(p['template']), p['gloss']))
    if len(patterns) != len({p.name for p in patterns}):
        raise TransferError('duplicate candidate name')
    return patterns, active


def _training_normal_forms() -> set[str]:
    """Only inputs the actual v0.12 miner saw (64 candidate ASTs)."""
    examples: set[str] = set()
    for path, expected in TRAIN_SOURCES:
        if sha256(path) != expected:
            raise TransferError(f'frozen mining input changed: {path.name}')
        for row in jsonl(path):
            if row['hypothesis'] == 'candidate':
                canonical = normalize(parse(row['expression']))
                if canonical in examples:
                    raise TransferError('duplicate training expression')
                examples.add(canonical)
    if len(examples) != 64:
        raise TransferError('unexpected actual training-set size')
    return examples


def historical_transfer(patterns: list[Pattern], active: dict[str, Pattern],
                        training: set[str]) -> dict[str, Any]:
    """Historical nontraining ASTs only. Exact training overlap excluded.

    Matching a contrast *foil* is explicitly NOT a correct answer to target English.
    """
    total, overlap, eligible = 0, 0, 0
    by_status: Counter[str] = Counter()
    by_source: dict[str, dict[str, int]] = {}
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in HISTORICAL:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in HISTORICAL_PIN or sha256(path) != HISTORICAL_PIN[relative]:
            raise TransferError(f'historical data changed or not pinned: {relative}')
        records = jsonl(path)
        counts: Counter[str] = Counter()
        for row in records:
            if not isinstance(row.get('id'), str):
                raise TransferError('bad historical record identifier')
            for side in ('correct', 'foil'):
                # Every pre-existing contrast deliberately contains two ALCG ASTs.
                ast = parse(row[side])
                canonical = normalize(ast)
                total += 1
                counts['total'] += 1
                if canonical in training:
                    overlap += 1
                    counts['overlap_with_training'] += 1
                    continue
                if canonical in seen:
                    raise TransferError('duplicate nontraining heldout AST across benchmarks')
                seen.add(canonical)
                eligible += 1
                counts['eligible'] += 1
                hits = [apply_pattern(ast, pattern, active) for pattern in patterns]
                hits = [(p, h) for p, h in zip(patterns, hits) if h is not None]
                if len(hits) > 1:
                    raise TransferError('ambiguous candidate match without selection rule')
                if hits:
                    p, h = hits[0]
                    by_status[side] += 1
                    counts['matched'] += 1
                    matches.append({'fixture': relative, 'id': row['id'],
                                    'side': side, 'pattern': p.name,
                                    'expression_sha256': h['sha256'],
                                    'matched_not_necessarily_correct': True})
        by_source[relative] = dict(sorted(counts.items()))
    return {'total_historical_expressions': total,
            'exact_training_overlaps_excluded': overlap,
            'nontraining_expressions': eligible,
            'distinct_nontraining_expressions': len(seen),
            'matches_to_candidates': len(matches),
            'matches_by_answer_role': dict(sorted(by_status.items())),
            'dataset_counts': by_source,
            'matched_cases': matches,
            'claim_boundary': ('Matched AST topology does not imply matching the English target. '
                               'A foil can match a candidate pattern and still be the WRONG answer.')}


def targeted_transfer(patterns: list[Pattern], active: dict[str, Pattern],
                      training: set[str], path: Path = PROBES) -> dict[str, Any]:
    """Post-discovery authored probes: diagnostic controls, NOT independent trial."""
    rows = jsonl(path)
    if len(rows) != 16 or len({r.get('id') for r in rows}) != len(rows):
        raise TransferError('expected 16 distinct authored diagnostic pairs')
    by_name = {p.name: p for p in patterns}
    seen_positive: set[str] = set()
    seen_probes: set[str] = set()
    matchable_foils = rejected_foils = 0
    examples: list[dict[str, Any]] = []
    costs: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        fields = {'id', 'pattern', 'domain', 'english', 'positive', 'foil',
                  'foil_type', 'foil_should_match', 'note'}
        if set(row) != fields:
            raise TransferError(f'{row.get("id")}: unexpected probe fields')
        if (not isinstance(row['foil_should_match'], bool) or
                row['pattern'] not in by_name or
                any(not isinstance(row[k], str) or not row[k].strip()
                    for k in fields - {'foil_should_match'})):
            raise TransferError('malformed authored probe')
        pattern = by_name[row['pattern']]
        canonical = normalize(parse(row['positive']))
        if canonical in training or canonical in seen_positive:
            raise TransferError(f'{row["id"]}: training leakage or duplicate positive AST')
        seen_positive.add(canonical)
        seen_probes.add(canonical)
        positive = apply_pattern(row['positive'], pattern, active)
        if positive is None:
            raise TransferError(f'{row["id"]}: expected positive was not expressible')
        foil_ast = parse(row['foil'])
        # Invalid scope foils are kept as explicit negative probes. They must
        # NOT be silently accepted as well-formed semantic claims.
        foil_scope_invalid = False
        try:
            foil_canonical = normalize(foil_ast)
        except ValueError:
            foil_canonical = None
            foil_scope_invalid = True
        if foil_canonical is not None:
            if foil_canonical == canonical:
                raise TransferError(f'{row["id"]}: foil is canonical-structure equivalent')
            if foil_canonical in training or foil_canonical in seen_probes:
                raise TransferError(f'{row["id"]}: foil leaks training data or duplicates another probe')
            seen_probes.add(foil_canonical)
        foil = apply_pattern(foil_ast, pattern, active)
        if foil_scope_invalid and foil is not None:
            raise TransferError(f'{row["id"]}: invalid scope was accepted')
        should_match = row['foil_should_match']
        if row['foil_type'].startswith('same_shape_') != should_match:
            raise TransferError(f'{row["id"]}: foil class disagrees with expected structure')
        if (foil is not None) != should_match:
            raise TransferError(f'{row["id"]}: unexpected foil match behavior')
        if should_match:
            matchable_foils += 1
        else:
            rejected_foils += 1
        cost = costs[pattern.name]
        cost['uses'] += 1
        cost['original_utf8_bytes'] += positive['expanded_utf8_bytes']
        cost['compact_utf8_bytes'] += positive['compact_utf8_bytes']
        examples.append({'id': row['id'], 'pattern': row['pattern'],
                         'domain': row['domain'], 'positive_expansion_sha256': positive['sha256'],
                         'positive_matched': True,
                         'foil_type': row['foil_type'],
                         'foil_matched': foil is not None,
                         'foil_changed_canonical_structure': True,
                         'foil_invalid_scope': foil_scope_invalid})
    if len(seen_positive) != 16 or matchable_foils != 8 or rejected_foils != 8:
        raise TransferError('unexpected authored probe balance')
    if set(costs) != set(by_name) or any(s['uses'] != 4 for s in costs.values()):
        raise TransferError('expected four unseen positive probes for each candidate')
    summary = []
    for pattern in patterns:
        c = costs[pattern.name]
        p = next(r['pattern'] for r in read_proposals(PROPOSALS_V012)
                 if r['pattern']['name'] == pattern.name)
        definition = len(_stable_json(p).encode('utf-8'))
        saved = c['original_utf8_bytes'] - c['compact_utf8_bytes']
        summary.append({'pattern': pattern.name,
                        'posthoc_positive_uses': c['uses'],
                        'expanded_utf8_bytes': c['original_utf8_bytes'],
                        'compact_utf8_bytes': c['compact_utf8_bytes'],
                        'payload_bytes_saved': saved,
                        'definition_utf8_bytes_estimate': definition,
                        'net_after_one_definition_bytes': saved-definition})
    return {'authored_after_discovery': True,
            'positive_tests': len(rows),
            'positive_structural_matches': len(examples),
            'role_or_structure_foils_rejected': rejected_foils,
            'same_shape_meaning_shift_foils_still_match': matchable_foils,
            'candidate_usage_costs': summary,
            'pairs': examples,
            'claim_boundary': ('These examples were written knowing the four patterns. '
                               'Matching positives is a matcher regression, not independent '
                               'distributional generalization; same-shape foils demonstrate '
                               'why correct English interpretation must be evaluated separately.')}


def report() -> dict[str, Any]:
    patterns, active = _read_candidate_patterns()
    training = _training_normal_forms()
    history = historical_transfer(patterns, active, training)
    authored = targeted_transfer(patterns, active, training)
    observed = {'historical_total': history['total_historical_expressions'],
                'historical_eligible': history['nontraining_expressions'],
                'historical_exact_training_overlap': history['exact_training_overlaps_excluded'],
                'historical_matched': history['matches_to_candidates'],
                'historical_matched_foils': history['matches_by_answer_role'].get('foil', 0),
                'targeted_pairs': authored['positive_tests'],
                'targeted_matches': authored['positive_structural_matches'],
                'targeted_matching_foils': authored['same_shape_meaning_shift_foils_still_match'],
                'targeted_rejected_foils': authored['role_or_structure_foils_rejected']}
    if observed != EXPECTED:
        raise TransferError(f'fixture expectation drift: {observed}')
    reg_sha = sha256(PATTERNS)
    if reg_sha != '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6':
        raise TransferError('active registry changed unexpectedly')
    if check_cases()['exact_expanded_canonical_roundtrips'] != 24:
        raise TransferError('v0.10 frozen fixture changed')
    return {'format': FORMAT,
            'frozen_v0_12_report_sha256': sha256(REPORT_V012),
            'frozen_v0_12_proposals_sha256': sha256(PROPOSALS_V012),
            'active_registry_sha256': reg_sha,
            'historical_sources_sha256': {p.relative_to(ROOT).as_posix(): sha256(p) for p in HISTORICAL},
            'posthoc_probe_file_sha256': sha256(PROBES),
            'actual_training_candidate_expressions': len(training),
            'review_only_patterns_considered': len(patterns),
            'historical_nontraining': history,
            'posthoc_diagnostic': authored,
            'promoted_patterns': 0,
            'independent_ai_readers': 0,
            'semantic_comprehension_accuracy': None,
            'external_generalization_claim': False,
            'caution': ('Historical contrast expressions were written before mining but may share '
                        'their author and design assumptions. Overlaps with actual mining inputs '
                        'are excluded by canonical AST. Diagnostic posthoc pairs were authored '
                        'to stress known templates. No independent semantic generalization, '
                        'AI comprehension, ontological correctness or actual execution is proven.')}


def verify() -> dict[str, Any]:
    actual = report()
    if json.loads(REPORT.read_text(encoding='utf-8')) != actual:
        raise TransferError('checked-in v0.13 report differs from recomputation')
    return actual


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description='ALCG v0.13 structural transfer; NOT AI comprehension')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='verify pinned report and all constraints')
    commands.add_parser('report', help='print complete reproducible metrics')
    matcher = commands.add_parser('match', help='try one ALCG AST against non-active candidates')
    matcher.add_argument('expression', help='a fully structured ALCG expression')
    args = p.parse_args(argv)
    try:
        if args.command == 'match':
            patterns, active = _read_candidate_patterns()
            value = parse(args.expression)
            matched = [(pat.name, result) for pat in patterns
                       if (result := apply_pattern(value, pat, active)) is not None]
            if len(matched) > 1:
                raise TransferError('multiple candidate matches; refuse ambiguous selection')
            result = {'input': args.expression,
                      'matched': bool(matched),
                      'candidate': matched[0][0] if matched else None,
                      'candidate_expansion': matched[0][1] if matched else None,
                      'active_registry_changed': False,
                      'semantic_accuracy': None,
                      'note': 'Topology/reconstruction only; not an English meaning judgment.'}
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return 0
        doc = verify() if args.command == 'check' else report()
        if args.command == 'check':
            a = doc['historical_nontraining']
            b = doc['posthoc_diagnostic']
            print(f'OK: historical {a["matches_to_candidates"]}/{a["nontraining_expressions"]} structural matches '
                  f'(all {a["matches_by_answer_role"].get("foil", 0)} are foils); '
                  f'posthoc {b["positive_structural_matches"]}/16 positive reconstructions; '
                  'no AI semantic claims or active dictionary changes')
        else:
            print(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (TransferError, ValueError, OSError, RecursionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
