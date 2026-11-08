import unittest

from coverage_bridge import report


class CoverageBridgeTests(unittest.TestCase):
    def test_frozen_case_count_and_english(self):
        result = report()
        self.assertEqual(result['fixed_english_cases'], 36)
        self.assertEqual(result['changed_cases'], ['C05', 'D05', 'M06', 'S05'])

    def test_labels_are_proposals_not_semantic_success(self):
        result = report()
        self.assertEqual(result['v0_2'], {'candidate': 24, 'partial': 6, 'raw': 6})
        self.assertEqual(result['v0_4'], {'candidate': 28, 'partial': 3, 'raw': 5})
        self.assertEqual(result['unverified_proposal_delta'], 4)
        self.assertIsNone(result['independent_reader_scores'])


if __name__ == '__main__':
    unittest.main()
