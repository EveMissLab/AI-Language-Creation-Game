"""Regression tests for the v0.3 challenge packaging and nonsemantic grading plumbing.

These use known keys to create synthetic responses. They are NOT AI reader results.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alcg import parse
from reconstruction_lab import (
    BenchmarkError,
    evaluate,
    json_bytes,
    jsonl_bytes,
    load_contrasts,
    prepare,
    validate_sources,
    write_new,
)


class ReconstructionLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet, cls.key = prepare(seed=12345)

    def test_source_data_has_six_domains(self):
        candidate, contrast = validate_sources()
        self.assertEqual(len(candidate), 24)
        self.assertEqual(len(contrast), 12)
        self.assertEqual(dict(Counter(r["domain"] for r in contrast)),
                         {d: 2 for d in ("daily", "science", "mathematics", "computing", "society", "epistemic")})
        for row in contrast:
            self.assertNotEqual(parse(row["correct"]), parse(row["foil"]))

    def test_packet_key_separation_and_balance(self):
        packet = self.packet
        key = self.key
        self.assertEqual(len(packet), 36)
        self.assertEqual(sum(r["task"] == "reconstruct" for r in packet), 24)
        self.assertEqual(sum(r["task"] == "choose" for r in packet), 12)
        self.assertEqual(Counter(r["correct_option"] for r in key["items"] if r["task"] == "choose"),
                         {"A": 6, "B": 6})
        for row in packet:
            self.assertNotIn("english", row)
            self.assertNotIn("source_id", row)
            self.assertNotIn("correct_option", row)
            if row["task"] == "reconstruct":
                self.assertEqual(set(row), {"id", "task", "expression"})
            else:
                self.assertEqual(set(row), {"id", "task", "target", "options"})

    def test_same_seed_reproduces_exact_bytes(self):
        packet, key = prepare(seed=12345)
        self.assertEqual(jsonl_bytes(packet), jsonl_bytes(self.packet))
        self.assertEqual(json_bytes(key), json_bytes(self.key))
        other_packet, _ = prepare(seed=2)
        self.assertNotEqual(jsonl_bytes(other_packet), jsonl_bytes(self.packet))

    def test_atomic_exclusive_write(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "packet.jsonl"
            write_new(path, jsonl_bytes(self.packet))
            with self.assertRaises(FileExistsError):
                write_new(path, jsonl_bytes(self.packet))

    def _files(self, folder: Path, responses, ratings=None):
        packet_path, key_path, response_path = [folder / f for f in
            ("packet.jsonl", "key.json", "reader.jsonl")]
        packet_path.write_bytes(jsonl_bytes(self.packet))
        key_path.write_bytes(json_bytes(self.key))
        response_path.write_bytes(jsonl_bytes(responses))
        if ratings is not None:
            ratings_path = folder / "ratings.jsonl"
            ratings_path.write_bytes(jsonl_bytes(ratings))
            return packet_path, key_path, response_path, ratings_path
        return packet_path, key_path, response_path

    def test_no_responses_never_invents_scores(self):
        with TemporaryDirectory() as temp:
            args = self._files(Path(temp), [])
            report = evaluate(*args)
        self.assertEqual(report["assigned"], {"reconstruct": 24, "choose": 12})
        self.assertEqual(report["reconstruction"]["independently_rated"], 0)
        self.assertIsNone(report["reconstruction"]["mean_on_rated_only"])
        self.assertIsNone(report["contrast"]["accuracy_selected_only"])
        self.assertEqual(report["contrast"]["accuracy_all_assigned"], 0)
        self.assertEqual(report["contrast"]["always_A_baseline_on_balanced_key"], 0.5)

    def test_synthetic_all_correct_and_human_ratings(self):
        # Synthetic responses from key: verify *only* the calculator, not AI skill.
        responses = []
        ratings = []
        for gold in self.key["items"]:
            if gold["task"] == "choose":
                responses.append({"id": gold["id"], "choice": gold["correct_option"],
                                  "rationale": "SYNTHETIC UNIT TEST; answer from key"})
            else:
                responses.append({"id": gold["id"], "reconstruction": "Synthetic placeholder", "uncertainty": "test"})
                ratings.append({"id": gold["id"], "rating": 2, "notes": "SYNTHETIC UNIT TEST"})
        with TemporaryDirectory() as temp:
            report = evaluate(*self._files(Path(temp), responses, ratings))
        self.assertEqual(report["contrast"]["correct"], 12)
        self.assertEqual(report["contrast"]["accuracy_all_assigned"], 1)
        self.assertEqual(report["reconstruction"]["mean_on_rated_only"], 2)
        self.assertEqual(report["reconstruction"]["faithful_rating_3_on_rated_only"], 0)

    def test_abstain_and_missed_are_distinguished(self):
        choices = [r["id"] for r in self.packet if r["task"] == "choose"]
        responses = [{"id": choices[0], "choice": "ABSTAIN", "rationale": "Unsure"}]
        with TemporaryDirectory() as temp:
            report = evaluate(*self._files(Path(temp), responses))
        self.assertEqual(report["contrast"]["abstained"], 1)
        self.assertEqual(report["contrast"]["missing"], 11)
        self.assertEqual(report["contrast"]["correct"], 0)

    def test_tampering_packet_rejected(self):
        with TemporaryDirectory() as temp:
            p, k, r = self._files(Path(temp), [])
            p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(BenchmarkError, "digest"):
                evaluate(p, k, r)

    def test_duplicate_response_rejected(self):
        row = {"id": next(r["id"] for r in self.packet if r["task"] == "reconstruct"),
               "reconstruction": "Some phrase", "uncertainty": "none"}
        with TemporaryDirectory() as temp:
            args = self._files(Path(temp), [row, row])
            with self.assertRaisesRegex(BenchmarkError, "duplicate"):
                evaluate(*args)

    def test_invalid_bool_rating_rejected(self):
        identifier = next(r["id"] for r in self.packet if r["task"] == "reconstruct")
        responses = [{"id": identifier, "reconstruction": "Some phrase", "uncertainty": "none"}]
        ratings = [{"id": identifier, "rating": True, "notes": "synthetic"}]
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(BenchmarkError, "rating"):
                evaluate(*self._files(Path(temp), responses, ratings))

    def test_raw_and_partials_are_not_readers_challenge(self):
        for row in self.packet:
            if row["task"] == "reconstruct":
                self.assertNotIn("RAW(", row["expression"])
                self.assertNotIn("PARTIAL(", row["expression"])

    def test_invalid_foil_rejected(self):
        from reconstruction_lab import CONTRAST_BENCHMARK
        with TemporaryDirectory() as temp:
            path = Path(temp) / "contrast.jsonl"
            rows = [json.loads(line) for line in CONTRAST_BENCHMARK.read_text(encoding="utf-8").splitlines()]
            rows[0]["foil"] = rows[0]["correct"]
            path.write_bytes(jsonl_bytes(rows))
            with self.assertRaisesRegex(BenchmarkError, "identical"):
                load_contrasts(path)


if __name__ == "__main__":
    unittest.main()
