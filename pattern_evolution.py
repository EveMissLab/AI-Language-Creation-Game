"""ALCG v0.11: deterministic, review-only gate for AI-authored pattern proposals.

No model/API calls, no automatic promotion, no claims of semantic equivalence.
The pinned v0.8 registry is never written to by this module.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from typing import Any

from alcg import Call, Name, ParseError, parse
from compact_surface import CompactError, check_cases, decode, encode, locked_patterns
from pattern_lab import PATTERNS, FORMAT as REGISTRY_FORMAT, Pattern, PatternError, expand, load_patterns, sha256
from semantic_lab import LabError, normalize

ROOT = Path(__file__).resolve().parent
PROPOSALS = ROOT / 'benchmarks' / 'pattern-proposals-v0.11.jsonl'
REPORT = ROOT / 'reports' / 'pattern-evolution-v0.11.json'
PREVIEW = ROOT / 'reports' / 'staged-patterns-v0.11.json'
FORMAT = 'ALCG-pattern-evolution-v0.11'
ID = re.compile(r'[A-Z][A-Z0-9_-]{2,40}\Z')
MAX_BYTES = 256_000
MAX_PROPOSALS = 48
MAX_EXAMPLES = 6
STAGED = 'staged_for_human_review'
REJECTED = 'rejected'
NEEDS_EVIDENCE = 'needs_more_evidence'
STATUSES = {STAGED, REJECTED, NEEDS_EVIDENCE}


class EvolutionError(ValueError):
    """Invalid input stream, reproducibility boundary or frozen-fixture expectation."""


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def read_proposals(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise EvolutionError('proposal file exceeds 256000-byte limit')
    try:
        data = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise EvolutionError('proposal file must be UTF-8') from exc
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for lineno, line in enumerate(data.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvolutionError(f'line {lineno}: malformed JSON: {exc.msg}') from exc
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not ID.fullmatch(row['id']):
            raise EvolutionError(f'line {lineno}: invalid proposal ID')
        if row['id'] in ids:
            raise EvolutionError(f'line {lineno}: duplicate proposal ID {row["id"]}')
        ids.add(row['id'])
        result.append(row)
        if len(result) > MAX_PROPOSALS:
            raise EvolutionError(f'no more than {MAX_PROPOSALS} proposals per run')
    if not result:
        raise EvolutionError('proposal set is empty')
    return result


def _mapping_with_candidate(base_doc: dict, proposal: dict) -> dict[str, Pattern]:
    # Reuse v0.8's strict validator: HOLE usage, relation roles, binders,
    # unknown calls, cycles, RAW leaks and required slots.  This is an in-memory
    # construction written only to a temporary file, never the live registry.
    doc = dict(base_doc)
    doc['patterns'] = list(base_doc['patterns']) + [proposal]
    with TemporaryDirectory(prefix='alcg-candidate-') as folder:
        temporary = Path(folder) / 'patterns.json'
        temporary.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        return load_patterns(temporary)


def _signature(name: str, patterns: dict[str, Pattern]) -> str:
    # Fixed, slot-INDEX placeholders deliberately distinguish positional roles.
    # This is syntactic identity, not mathematical/semantic equivalence.
    call = Call(name, tuple((slot, Name(f'ALCG_SIG_{i}'))
                            for i, slot in enumerate(patterns[name].slots)))
    return normalize(expand(call, patterns, budget=3000))


def _bad(reason: str, **extra: Any) -> dict[str, Any]:
    return {'status': REJECTED, 'reason': reason, 'examples_checked': 0, **extra}


def evaluate_one(row: dict[str, Any], base_doc: dict[str, Any],
                 base: dict[str, Pattern], seen_names: set[str],
                 fingerprints: dict[str, str]) -> dict[str, Any]:
    name = row.get('pattern', {}).get('name') if isinstance(row.get('pattern'), dict) else None
    out = {'id': row['id'], 'name': name if isinstance(name, str) else None,
           'origin': row.get('origin') if isinstance(row.get('origin'), str) else None}
    if set(row) - {'id', 'origin', 'pattern', 'examples', 'expected_status', 'note'}:
        return {**out, **_bad('unknown_proposal_fields')}
    if not isinstance(row.get('origin'), str) or not 3 <= len(row['origin']) <= 120:
        return {**out, **_bad('missing_or_invalid_provenance')}
    if not isinstance(row.get('note'), str) or not 8 <= len(row['note']) <= 600:
        return {**out, **_bad('missing_rationale')}
    proposal = row.get('pattern')
    if not isinstance(proposal, dict) or set(proposal) != {'name', 'slots', 'template', 'gloss'}:
        return {**out, **_bad('invalid_pattern_fields')}
    if not isinstance(name, str) or len(name) > 72:
        return {**out, **_bad('invalid_pattern_name')}
    if name in base:
        return {**out, **_bad('existing_registry_name_collision')}
    if name in seen_names:
        return {**out, **_bad('duplicate_proposal_name')}
    seen_names.add(name)
    if not isinstance(proposal['template'], str) or len(proposal['template']) > 5000:
        return {**out, **_bad('invalid_or_oversized_template')}
    examples = row.get('examples')
    if not isinstance(examples, list) or len(examples) > MAX_EXAMPLES:
        return {**out, **_bad('invalid_example_list')}
    try:
        mapping = _mapping_with_candidate(base_doc, proposal)
        fingerprint = _signature(name, mapping)
    except (PatternError, ParseError, LabError, ValueError, RecursionError) as exc:
        return {**out, **_bad('template_validation_failed', detail=str(exc)[:240])}
    if fingerprint in fingerprints:
        return {**out, **_bad('duplicate_expansion_signature', duplicate_of=fingerprints[fingerprint])}

    valid_samples = []
    seen_examples: set[str] = set()
    total_expanded = total_compact = 0
    for index, example in enumerate(examples, 1):
        if (not isinstance(example, dict) or set(example) != {'input', 'expected'} or
                not all(isinstance(v, str) and 1 <= len(v) <= 4000 for v in example.values())):
            return {**out, **_bad('invalid_example_shape', failing_example=index)}
        try:
            call = parse(example['input'])
            if not isinstance(call, Call) or call.name != name:
                return {**out, **_bad('example_must_call_candidate', failing_example=index)}
            if set(dict(call.args)) != set(mapping[name].slots):
                return {**out, **_bad('example_slot_mismatch', failing_example=index)}
            expanded = expand(call, mapping, budget=3000)
            actual = normalize(expanded)
            expected = normalize(example['expected'])
            if actual != expected:
                return {**out, **_bad('reference_structure_mismatch', failing_example=index)}
            if actual in seen_examples:
                return {**out, **_bad('duplicate_example', failing_example=index)}
            # Same public registry + candidate -> verify shorter notation can
            # roundtrip without changing canonical expanded syntax.
            compact = encode(call, mapping)
            if normalize(decode(compact, mapping)) != actual:
                return {**out, **_bad('compact_roundtrip_mismatch', failing_example=index)}
            seen_examples.add(actual)
            expanded_bytes = len(example['expected'].encode('utf-8'))
            compact_bytes = len(compact.encode('utf-8'))
            total_expanded += expanded_bytes
            total_compact += compact_bytes
            valid_samples.append({'index': index, 'expanded_sha256': _stable_digest(actual),
                                  'expanded_bytes': expanded_bytes, 'compact_bytes': compact_bytes})
        except (ParseError, PatternError, CompactError, LabError, ValueError, RecursionError) as exc:
            return {**out, **_bad('example_validation_failed', failing_example=index,
                                  detail=str(exc)[:240])}

    # No mutation of fingerprints for weak or missing evidence.  Staged
    # proposals still require a human review before any registry promotion.
    status = STAGED if len(valid_samples) >= 2 else NEEDS_EVIDENCE
    if status == STAGED:
        fingerprints[fingerprint] = name
    return {**out, 'status': status,
            'reason': 'structural_gate_passed_human_review_required' if status == STAGED else 'at_least_two_distinct_examples_required',
            'examples_checked': len(valid_samples),
            'candidate_sha256': _stable_digest(proposal),
            'signature_sha256': _stable_digest(fingerprint),
            'example_checks': valid_samples,
            'sample_bytes': {'expanded': total_expanded, 'compact': total_compact,
                             'difference_excluding_registry': total_expanded - total_compact}}


def audit(proposals: Path = PROPOSALS, *, enforce_fixture: bool = False) -> dict[str, Any]:
    # The live registry and all previous 24 shorthand fixtures must still pass.
    baseline = check_cases()
    if baseline['exact_expanded_canonical_roundtrips'] != 24:
        raise EvolutionError('v0.10 baseline regression')
    base = locked_patterns()
    base_doc = json.loads(PATTERNS.read_text(encoding='utf-8'))
    if base_doc['format'] != REGISTRY_FORMAT:
        raise EvolutionError('unexpected base registry format')
    rows = read_proposals(proposals)
    signatures = {_signature(name, base): name for name in base}
    seen_names: set[str] = set()
    evaluations = []
    for row in rows:
        item = evaluate_one(row, base_doc, base, seen_names, signatures)
        if enforce_fixture and row.get('expected_status') != item['status']:
            raise EvolutionError(f'{row["id"]}: expected {row.get("expected_status")}, got {item["status"]}: {item["reason"]}')
        evaluations.append(item)
    counts = Counter(item['status'] for item in evaluations)
    report = {
        'format': FORMAT,
        'base_registry_sha256': sha256(PATTERNS),
        'base_definitions_unchanged': len(base),
        'frozen_v0_10_roundtrips': baseline['exact_expanded_canonical_roundtrips'],
        'proposals_sha256': sha256(proposals),
        'candidate_count': len(rows),
        'decisions': {key: counts.get(key, 0) for key in (STAGED, NEEDS_EVIDENCE, REJECTED)},
        'cases': evaluations,
        'promotion_performed': False,
        'independent_ai_reader_results': None,
        'warning': ('Assistant-authored example proposals, not external AI trials. '
                    'Structural reconstruction is not a proof of intended meaning, truth, '
                    'semantic completeness or improved English coverage. Staged patterns are NOT installed.'),
    }
    return report


def staging_preview(report: dict[str, Any], proposals: Path = PROPOSALS) -> dict[str, Any]:
    rows = {row['id']: row for row in read_proposals(proposals)}
    return {'format': 'ALCG-staging-preview-v0.11-NOT-ACTIVE',
            'base_registry_sha256': report['base_registry_sha256'],
            'promotion_performed': False,
            'patterns_for_human_review': [
                {'id': case['id'], 'origin': case['origin'],
                 'candidate_sha256': case['candidate_sha256'],
                 'pattern': rows[case['id']]['pattern'],
                 'evidence': rows[case['id']]['examples']}
                for case in report['cases'] if case['status'] == STAGED]}


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description='ALCG v0.11 deterministic proposal gate; never auto-merges registry')
    cmds = cli.add_subparsers(dest='command', required=True)
    for command in ('check', 'report', 'export-preview', 'verify-report'):
        p = cmds.add_parser(command)
        p.add_argument('--proposals', type=Path, default=PROPOSALS)
        if command == 'export-preview':
            p.add_argument('--out', type=Path, required=True)
    args = cli.parse_args(argv)
    try:
        summary = audit(args.proposals, enforce_fixture=(args.command == 'check' and args.proposals.resolve() == PROPOSALS.resolve()))
        if args.command == 'verify-report':
            if args.proposals.resolve() != PROPOSALS.resolve():
                raise EvolutionError('verify-report only applies to the pinned v0.11 fixture')
            if json.loads(REPORT.read_text(encoding='utf-8')) != summary:
                raise EvolutionError('committed evaluation report differs from reproducible audit')
            if json.loads(PREVIEW.read_text(encoding='utf-8')) != staging_preview(summary):
                raise EvolutionError('committed non-active preview differs from reproducible staging decision')
            print('OK: committed report and review-only preview match exactly')
        elif args.command == 'check':
            print('OK: ' + json.dumps(summary['decisions'], sort_keys=True) + '; live registry unchanged')
        elif args.command == 'report':
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            doc = staging_preview(summary, args.proposals)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x', encoding='utf-8', newline='\n') as f:
                json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write('\n')
            print(f'Wrote {len(doc["patterns_for_human_review"])} NON-ACTIVE candidate patterns to {args.out}')
        return 0
    except (EvolutionError, PatternError, CompactError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
