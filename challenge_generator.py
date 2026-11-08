"""ALCG v0.14: deterministic synthetic challenge generation and invariant checks.

Produces novel AST combinations and programmatic metamorphic controls for the
four v0.12 review-only templates.  These are generated STRUCTURAL tasks, not
verified English meanings, independent AI reader outputs, or new base syntax.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from alcg import Call, Expr, Name, parse, render
from compact_surface import check_cases, locked_patterns
from coverage_lab import jsonl
from pattern_discovery import verify_snapshot
from pattern_lab import PATTERNS, Pattern, expand, sha256 as file_sha256
from semantic_lab import normalize
from transfer_lab import (
    _read_candidate_patterns, _training_normal_forms, HISTORICAL,
    HISTORICAL_PIN, PROBES, apply_pattern,
)

ROOT = Path(__file__).resolve().parent
LEXICON = ROOT / 'data' / 'generator-lexicon-v0.14.json'
SUITE = ROOT / 'benchmarks' / 'generated-challenges-v0.14.jsonl'
REPORT = ROOT / 'reports' / 'generated-challenges-v0.14.json'
FORMAT = 'ALCG-generated-challenges-v0.14'
REGISTRY_SHA = '5d97c41701b8196766a65bf08ac24f1942df3fa2e1a7546f3845b0df805d3bc6'
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z_0-9-]*$')


class GenerationError(ValueError):
    """Frozen inputs, grammar, novelty, or metamorphic property were violated."""


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest()


def validate_lexicon(lex: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(lex, dict):
        raise GenerationError('lexicon must be a JSON object')
    if set(lex) != {'format', 'seed', 'cases_per_candidate', 'status', 'banks'}:
        raise GenerationError('unexpected lexicon schema')
    if lex['format'] != 'ALCG-synthetic-lexical-banks-v0.14':
        raise GenerationError('unrecognized lexicon format')
    if (type(lex['seed']) is not int or lex['seed'] < 0 or
            type(lex['cases_per_candidate']) is not int or
            not 1 <= lex['cases_per_candidate'] <= 100):
        raise GenerationError('invalid seed or sample count')
    if not isinstance(lex['status'], str) or 'not factual' not in lex['status']:
        raise GenerationError('lexicon provenance boundary was removed')
    if not isinstance(lex['banks'], dict) or set(lex['banks']) != {'CAUSE', 'BEFORE', 'EXISTS', 'NOT'}:
        raise GenerationError('lexicon must declare exactly four frozen roots')
    patterns, _ = _read_candidate_patterns()
    for pattern in patterns:
        banks = lex['banks'][pattern.template.name]
        if not isinstance(banks, dict) or set(banks) != set(pattern.slots):
            raise GenerationError(f'{pattern.name}: missing/extra lexical slots')
        for slot, words in banks.items():
            if (not isinstance(words, list) or len(words) < (3 if slot == 'item_01' and pattern.template.name in ('EXISTS', 'NOT') else 6) or
                    any(not isinstance(w, str) or not IDENTIFIER.fullmatch(w) for w in words) or
                    len(set(words)) != len(words)):
                raise GenerationError(f'{pattern.name}/{slot}: lexical labels need six distinct identifiers')
    return lex


def read_lexicon(path: Path = LEXICON) -> dict[str, Any]:
    return validate_lexicon(json.loads(path.read_text(encoding='utf-8')))


def _choose(words: list[str], *, seed: int, pattern: str, serial: int,
            slot: str, retry: int = 0) -> str:
    """SHA-derived selection, independent of runtime random/hash seed."""
    selector = f'{seed}|{pattern}|{serial}|{slot}|{retry}'
    i = int(_digest(selector)[:16], 16) % len(words)
    return words[i]


def _reorder(expr: Expr) -> Expr:
    if isinstance(expr, Call):
        return Call(expr.name, tuple((key, _reorder(value)) for key, value in reversed(expr.args)))
    return expr


def _alter_shape(expr: Call) -> Call:
    """Valid different-root/operator or broken cross-role equality.

    Does not assert the new ALCG statement is true/false in a natural world.
    """
    args = dict(expr.args)
    if expr.name == 'CAUSE':
        effect = args['effect']
        assert isinstance(effect, Call) and effect.name == 'CHANGE'
        return Call('CAUSE', (('source', args['source']),
                              ('effect', Call('IS', effect.args))))
    if expr.name == 'BEFORE':
        later = args['later']
        assert isinstance(later, Call)
        largs = dict(later.args)
        actor = largs['actor']
        assert isinstance(actor, Name)
        largs['actor'] = Name('OTHER_' + actor.value)
        return Call('BEFORE', (('earlier', args['earlier']),
                               ('later', Call('DO', tuple(largs.items())))))
    if expr.name == 'EXISTS':
        return Call('FORALL', expr.args)
    if expr.name == 'NOT':
        return Call('MAY', expr.args)
    raise GenerationError(f'unknown candidate root: {expr.name}')


def _alpha_rename(expr: Call) -> Call:
    if expr.name != 'EXISTS':
        raise GenerationError('alpha rename is supported only for EXISTS')
    args = dict(expr.args)
    old = args['var']
    assert isinstance(old, Name)
    renamed = Name('NEW_' + old.value)
    claim = args['claim']
    assert isinstance(claim, Call) and claim.name == 'COMPARE'
    cargs = dict(claim.args)
    left = cargs['left']
    assert isinstance(left, Call) and left.name == 'REF'
    cargs['left'] = Call('REF', (('var', renamed),))
    args['var'] = renamed
    args['claim'] = Call('COMPARE', tuple(cargs.items()))
    return Call('EXISTS', tuple(args.items()))


def _old_nontraining_forms() -> set[str]:
    """Freeze the already used v0.13 positive/foil probes plus older contrasts."""
    found = _training_normal_forms()
    for path in HISTORICAL:
        relative = path.relative_to(ROOT).as_posix()
        if file_sha256(path) != HISTORICAL_PIN[relative]:
            raise GenerationError('pinned historical contrast changed')
        for row in jsonl(path):
            for side in ('correct', 'foil'):
                try:
                    found.add(normalize(row[side]))
                except ValueError:
                    # Original unbound-variable negative controls are not valid AST meanings.
                    pass
    for row in jsonl(PROBES):
        for side in ('positive', 'foil'):
            try:
                found.add(normalize(row[side]))
            except ValueError:
                pass
    return found


def _registry() -> tuple[list[Pattern], dict[str, Pattern]]:
    if file_sha256(PATTERNS) != REGISTRY_SHA or len(locked_patterns()) != 16:
        raise GenerationError('published pattern dictionary changed')
    if verify_snapshot()['generated_candidate_count'] != 4:
        raise GenerationError('the v0.12 candidate corpus changed')
    if check_cases()['exact_expanded_canonical_roundtrips'] != 24:
        raise GenerationError('v0.10 compact compatibility changed')
    return _read_candidate_patterns()


def generate(lexicon: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Produce new artificial syntax probes without taking gold answers as input."""
    lex = read_lexicon() if lexicon is None else validate_lexicon(lexicon)
    patterns, active = _registry()
    old = _old_nontraining_forms()
    seen = set(old)
    changed_seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for pattern in sorted(patterns, key=lambda x: x.template.name):
        bank = lex['banks'][pattern.template.name]
        temporary = dict(active)
        temporary[pattern.name] = pattern  # explicitly ephemeral
        for serial in range(1, lex['cases_per_candidate'] + 1):
            for retry in range(1024):
                slots = {slot: _choose(bank[slot], seed=lex['seed'],
                                       pattern=pattern.name, serial=serial,
                                       slot=slot, retry=retry)
                         for slot in pattern.slots}
                candidate_call = Call(pattern.name, tuple((s, Name(slots[s])) for s in pattern.slots))
                ast = expand(candidate_call, temporary)
                original = normalize(ast)
                if original not in seen:
                    break
            else:
                raise GenerationError('novelty pool exhausted')
            seen.add(original)
            match = apply_pattern(ast, pattern, active)
            if match is None or render(parse(match['call'])) == render(ast):
                # Candidate call and expanded AST are intentionally different syntax trees.
                raise GenerationError('positive pattern could not be losslessly matched')
            if normalize(expand(parse(match['call']), temporary)) != original:
                raise GenerationError('positive reconstruction failed')

            reordered = _reorder(ast)
            if normalize(reordered) != original or apply_pattern(reordered, pattern, active) is None:
                raise GenerationError('argument-order invariant failed')

            last_slot = pattern.slots[-1]  # not EXISTS binder, so canonical change survives
            alternate = bank[last_slot][(bank[last_slot].index(slots[last_slot]) + 1) % len(bank[last_slot])]
            shifted = dict(slots)
            shifted[last_slot] = alternate
            altered_call = Call(pattern.name, tuple((s, Name(shifted[s])) for s in pattern.slots))
            changed = expand(altered_call, temporary)
            changed_normal = normalize(changed)
            if changed_normal == original or apply_pattern(changed, pattern, active) is None:
                raise GenerationError('same-shape changed lexeme was not distinguishable')
            broken = _alter_shape(ast)
            broken_normal = normalize(broken)
            if broken_normal == original or apply_pattern(broken, pattern, active) is not None:
                raise GenerationError('shape-breaking foil was accepted or unchanged')
            if (changed_normal in seen or changed_normal in changed_seen or
                    broken_normal in seen or broken_normal in changed_seen or
                    changed_normal == broken_normal):
                raise GenerationError('mutated variant overlaps a frozen or generated AST')
            changed_seen.update((changed_normal, broken_normal))

            variants = [
                {'type': 'named_argument_reorder', 'expression': render(reordered),
                 'canonical_equal': True, 'matches_candidate': True},
                {'type': 'lexical_slot_change', 'expression': render(changed),
                 'canonical_equal': False, 'matches_candidate': True},
                {'type': 'operator_or_coreference_change', 'expression': render(broken),
                 'canonical_equal': False, 'matches_candidate': False},
            ]
            if pattern.template.name == 'EXISTS':
                alpha = _alpha_rename(ast)
                if normalize(alpha) != original or apply_pattern(alpha, pattern, active) is None:
                    raise GenerationError('bound variable renaming changed canonical form')
                variants.append({'type': 'bound_variable_alpha_rename', 'expression': render(alpha),
                                 'canonical_equal': True, 'matches_candidate': True})
            results.append({
                'id': f'G14_{pattern.template.name}_{serial:02d}',
                'pattern': pattern.name, 'root': pattern.template.name,
                'provenance': 'program_generated_from_human_curated_synthetic_lexical_banks',
                'expression': render(ast),
                'canonical_sha256': _digest(original),
                'compact': match['compact'], 'variants': variants,
            })
    if len(results) != len(patterns) * lex['cases_per_candidate']:
        raise GenerationError('incorrect generated number of probes')
    return results


def validate(rows: list[dict[str, Any]], *, lexicon: dict[str, Any] | None = None) -> dict[str, Any]:
    lex = read_lexicon() if lexicon is None else validate_lexicon(lexicon)
    expected = generate(lex)
    if rows != expected:
        raise GenerationError('generated fixture changed, reordered, or tampered with')
    patterns, active = _registry()
    by_name = {p.name: p for p in patterns}
    counts = {'equivalent_reordering': 0, 'equivalent_alpha_rename': 0,
              'same_shape_but_canonical_changed': 0,
              'non_matching_structural_controls': 0}
    matched = 0
    for row in rows:
        pat = by_name[row['pattern']]
        ast = parse(row['expression'])
        if _digest(normalize(ast)) != row['canonical_sha256']:
            raise GenerationError('positive canonical hash drift')
        hit = apply_pattern(ast, pat, active)
        if hit is None or hit['compact'] != row['compact']:
            raise GenerationError('positive shorthand mismatch')
        matched += 1
        for variant in row['variants']:
            alternate = parse(variant['expression'])
            same = normalize(alternate) == normalize(ast)
            match = apply_pattern(alternate, pat, active) is not None
            if same is not variant['canonical_equal'] or match is not variant['matches_candidate']:
                raise GenerationError('metamorphic expectation disagrees with actual AST')
            category = variant['type']
            if category == 'named_argument_reorder':
                counts['equivalent_reordering'] += 1
            elif category == 'bound_variable_alpha_rename':
                counts['equivalent_alpha_rename'] += 1
            elif category == 'lexical_slot_change':
                counts['same_shape_but_canonical_changed'] += 1
            elif category == 'operator_or_coreference_change':
                counts['non_matching_structural_controls'] += 1
            else:
                raise GenerationError('unrecognized variant type')
    return {'format': FORMAT, 'lexicon_sha256': file_sha256(LEXICON),
            'v0_12_non_active_proposals_sha256': file_sha256(ROOT / 'benchmarks/discovered-proposals-v0.12.jsonl'),
            'v0_13_frozen_probes_sha256': file_sha256(PROBES),
            'active_registry_sha256': file_sha256(PATTERNS),
            'seed': lex['seed'], 'concept_bank_design': 'human_curated_label_pools; combinatorial program generator',
            'old_ast_overlap_excluded': True,
            'positive_generated_expressions': len(rows),
            'positive_structural_matches': matched,
            'metamorphic_variants_checked': sum(counts.values()),
            'variant_classes': counts,
            'promoted_patterns': 0,
            'independent_ai_readers': 0,
            'semantic_comprehension_score': None,
            'actual_english_coverage_gain': None,
            'warning': ('Program-created probes are conditional on known candidate patterns and human-curated labels. '
                        'A lexical change proves AST non-identity, NOT truth-value difference in all models or '
                        'incorrect English meaning. This is synthetic invariant/regression testing, NOT '
                        'independent generalization, autonomous AI invention or human semantic verification.')}


def report() -> dict[str, Any]:
    return validate(generate())


def verify() -> dict[str, Any]:
    actual = report()
    stored = json.loads(REPORT.read_text(encoding='utf-8'))
    if actual != stored:
        raise GenerationError('checked-in report does not reproduce')
    if jsonl(SUITE) != generate():
        raise GenerationError('checked-in challenge suite does not reproduce')
    return actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='ALCG v0.14 deterministic synthetic challenge generator')
    cmds = parser.add_subparsers(dest='command', required=True)
    cmds.add_parser('check', help='verify committed fixture and report against pinned source data')
    cmds.add_parser('report', help='display computed generator metadata without changing files')
    trial = cmds.add_parser('generate', help='generate into a chosen output path; never update active dictionary')
    trial.add_argument('--out', required=True, type=Path, help='UTF-8 JSONL destination')
    args = parser.parse_args(argv)
    try:
        if args.command == 'generate':
            rows = generate()
            validate(rows)
            output = ''.join(_stable(row) + '\n' for row in rows)
            resolved = args.out.resolve()
            # Re-generating the committed fixture is fine only if bytes are unchanged.
            if resolved.is_relative_to(ROOT.resolve()) and resolved != SUITE.resolve():
                raise GenerationError('refuse to overwrite other repository artifacts')
            if args.out.exists() and args.out.read_text(encoding='utf-8') != output:
                raise GenerationError('refuse to overwrite a different existing file')
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output, encoding='utf-8')
            print(f'Wrote {len(rows)} synthetic cases ({sum(len(r["variants"]) for r in rows)} variants): {args.out}')
        elif args.command == 'check':
            result = verify()
            print(f'OK: {result["positive_generated_expressions"]} novel syntactic examples, '
                  f'{result["metamorphic_variants_checked"]} metamorphic checks; '
                  'no AI comprehension or active registry promotion')
        else:
            print(json.dumps(report(), ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (GenerationError, ValueError, OSError, AssertionError, RecursionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
