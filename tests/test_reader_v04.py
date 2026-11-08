import json
from pathlib import Path
import tempfile
import unittest

from reader_v04 import build
from reconstruction_lab import evaluate, jsonl_bytes, json_bytes


class ReaderV04Tests(unittest.TestCase):
    def test_v04_packet_and_key_separation(self):
        packet, key = build(seed=20261108)
        self.assertEqual(len(packet), 40)
        self.assertEqual(sum(x['task'] == 'reconstruct' for x in packet), 28)
        self.assertEqual(sum(x['task'] == 'choose' for x in packet), 12)
        self.assertFalse(any('english' in x or 'correct_option' in x for x in packet))
        self.assertEqual(sum(x['correct_option'] == 'A' for x in key['items'] if x['task']=='choose'), 6)
        self.assertEqual(sum(x['correct_option'] == 'B' for x in key['items'] if x['task']=='choose'), 6)

    def test_deterministic_seed(self):
        a, key_a = build(seed=104)
        b, key_b = build(seed=104)
        self.assertEqual(jsonl_bytes(a), jsonl_bytes(b))
        self.assertEqual(json_bytes(key_a), json_bytes(key_b))

    def test_empty_responses_not_fake_scores(self):
        packet, key = build(seed=98)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p, k, a = (root / s for s in ('packet.jsonl','private-key.json','answers.jsonl'))
            p.write_bytes(jsonl_bytes(packet))
            k.write_bytes(json_bytes(key))
            a.write_text('',encoding='utf-8')
            summary = evaluate(p,k,a)
            self.assertIsNone(summary['reconstruction']['mean_on_rated_only'])
            self.assertEqual(summary['contrast']['correct'],0)
            self.assertEqual(summary['contrast']['missing'],12)


if __name__ == '__main__':
    unittest.main()
