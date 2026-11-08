"""ALCG v0.12: deterministic mining from frozen benchmarks, review ONLY."""
import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alcg import Call, parse
from compact_surface import locked_patterns, check_cases
from pattern_lab import PATTERNS, expand, sha256
from pattern_evolution import evaluate_one, _signature, _mapping_with_candidate, STAGED
from pattern_discovery import (
    ROOT, REPORT, PROPOSALS, DiscoveryError, SOURCES, _check_sources,
    _equality_classes, _structural_identity, discover, generated_jsonl,
    review, verify_snapshot,
)
from semantic_lab import normalize


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.disc = discover()
        cls.report = review(cls.disc)
        cls.mapping = locked_patterns()

    def test_frozen_corpus_and_staged_counts(self):
        self.assertEqual(self.disc['source_candidates'], 64)
        self.assertEqual(self.disc['shape_groups'], 31)
        self.assertEqual(len(self.disc['suggestions']), 4)
        self.assertEqual(self.report['structural_gate_outcomes'], {STAGED: 4})
        self.assertFalse(self.report['registry_automatically_modified'])
        self.assertIsNone(self.report['heldout_transfer_results'])
        self.assertIsNone(self.report['semantic_quality_scores'])

    def test_dual_domain_cause(self):
        cause = next(s for s in self.disc['suggestions']
                     if s['proposal']['pattern']['name'].startswith('P_DISC_CAUSE_'))
        self.assertEqual(cause['domains'], ['computing', 'science'])
        self.assertEqual(cause['source_ids'], ['C04', 'S02'])
        self.assertEqual(cause['support'], 2)

    def test_names_are_repeatable_and_order_independent(self):
        rows = _check_sources()
        forward = discover(rows=rows)
        reversed_data = discover(rows=list(reversed(rows)))
        self.assertEqual(forward['suggestions'], reversed_data['suggestions'])
        self.assertEqual(generated_jsonl(forward), generated_jsonl(reversed_data))

    def test_inferred_shared_actor_does_not_merge_different_objects(self):
        pattern = next(s for s in self.disc['suggestions']
                       if s['proposal']['pattern']['name'].startswith('P_DISC_BEFORE_'))
        template = parse(pattern['proposal']['pattern']['template'])
        earlier, later = dict(template.args)['earlier'], dict(template.args)['later']
        a, b = dict(earlier.args), dict(later.args)
        self.assertEqual(a['actor'], b['actor'])
        self.assertNotEqual(a['object'], b['object'])
        self.assertNotEqual(a['action'], b['action'])

    def test_quantifier_binder_remains_same_hole_as_ref(self):
        item = next(s for s in self.disc['suggestions']
                    if s['proposal']['pattern']['name'].startswith('P_DISC_EXISTS_'))
        node = parse(item['proposal']['pattern']['template'])
        binder = dict(node.args)['var']
        claim = dict(node.args)['claim']
        referenced = dict(dict(claim.args)['left'].args)['var']
        self.assertEqual(binder, referenced)
        self.assertIsInstance(binder, Call)
        self.assertEqual(binder.name, 'HOLE')

    def test_active_generic_may_do_skipped_as_false_novelty(self):
        self.assertGreaterEqual(self.disc['skipped']['existing_active_structure'], 1)
        self.assertFalse(any(s['proposal']['pattern']['template'].startswith('MAY(')
                             for s in self.disc['suggestions']))

    def test_no_raw_or_unmodeled_text_mined(self):
        for item in self.disc['suggestions']:
            text = item['proposal']['pattern']['template']
            self.assertNotIn('RAW(', text)
            self.assertNotIn('PARTIAL(', text)
            self.assertGreaterEqual(len(item['proposal']['examples']), 2)

    def test_reversible_and_original_examples_unchanged(self):
        base = json.loads(PATTERNS.read_text(encoding='utf-8'))
        for item in self.disc['suggestions']:
            candidate = item['proposal']
            mapping = _mapping_with_candidate(base, candidate['pattern'])
            for example in candidate['examples']:
                with self.subTest(id=candidate['id']):
                    self.assertEqual(normalize(expand(example['input'], mapping)),
                                     normalize(example['expected']))

    def test_gate_detects_wrong_reference(self):
        item = copy.deepcopy(self.disc['suggestions'][0]['proposal'])
        item['examples'][0]['expected'] = 'DO(actor=PERSON, action=RUN)'
        old = json.loads(PATTERNS.read_text(encoding='utf-8'))
        signatures = {_signature(n, self.mapping): n for n in self.mapping}
        result = evaluate_one(item, old, self.mapping, set(), signatures)
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(result['reason'], 'reference_structure_mismatch')

    def test_inferred_equality_requires_all_examples(self):
        a = parse('DO(actor=AI, action=HELP, object=AI)')
        b = parse('DO(actor=PROGRAM, action=READ, object=FILE)')
        self.assertEqual(_equality_classes([a, b]), (0, 1, 2))
        c = parse('DO(actor=PROGRAM, action=READ, object=PROGRAM)')
        self.assertEqual(_equality_classes([a, c]), (0, 1, 1))

    def test_identity_does_not_conflate_role_direction(self):
        a = parse('BEFORE(earlier=DO(actor=PROGRAM, action=CHECK), later=DO(actor=PROGRAM, action=DELETE))')
        b = parse('BEFORE(earlier=DO(actor=PROGRAM, action=DELETE), later=DO(actor=PROGRAM, action=CHECK))')
        # Outline same, but *specific* canonical descriptions differ. Therefore
        # induction here makes ONLY a shape proposal and never claims English equivalence.
        self.assertEqual(_structural_identity(a), _structural_identity(b))
        self.assertNotEqual(normalize(a), normalize(b))

    def test_cost_claim_includes_definition(self):
        for candidate in self.report['ranked_candidates']:
            self.assertGreater(candidate['incremental_definition_bytes_estimate'], 0)
            self.assertEqual(candidate['net_bytes_after_single_definition'],
                             candidate['sample_payload_bytes_saved'] - candidate['incremental_definition_bytes_estimate'])
            self.assertGreater(candidate['estimated_reuses_to_amortize_definition'], 0)
        self.assertEqual(self.report['independent_ai_participants'], 0)

    def test_report_matches_frozen_artifact(self):
        self.assertEqual(verify_snapshot(), self.report)
        self.assertEqual(PROPOSALS.read_text(encoding='utf-8'), generated_jsonl(self.disc))
        self.assertEqual(json.loads(REPORT.read_text(encoding='utf-8')), self.report)

    def test_frozen_v010_registry_never_modified(self):
        before = sha256(PATTERNS)
        discover()
        self.assertEqual(before, sha256(PATTERNS))
        self.assertEqual(check_cases()['exact_expanded_canonical_roundtrips'], 24)

    def test_modified_frozen_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'modified.jsonl'
            fake.write_bytes(SOURCES[0][0].read_bytes() + b'\n')
            with patch('pattern_discovery.SOURCES', ((fake, SOURCES[0][1]), SOURCES[1])):
                with self.assertRaisesRegex(DiscoveryError, 'frozen corpus changed'):
                    _check_sources()

    def test_export_requires_new_destination(self):
        # Exporting never modifies the active dictionary or overwrites an existing file.
        import pattern_discovery
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'external-proposals.jsonl'
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(pattern_discovery.main(['export-proposals', '--out', str(out)]), 0)
                self.assertEqual(out.read_text(encoding='utf-8'), generated_jsonl(self.disc))
                self.assertEqual(pattern_discovery.main(['export-proposals', '--out', str(out)]), 1)


if __name__ == '__main__':
    unittest.main()
