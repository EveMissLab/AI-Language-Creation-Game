"""ALCG v0.3: a reproducible *unscored* AI reading challenge.

Two distinct tasks:
  reconstruct: recover ordinary English from ALCG (source English omitted)
  choose: select which ALCG candidate expresses a visible English target

The contrast task can be automatically scored, but does not prove open-ended
semantic understanding. Reconstruction needs *independent* human adjudication.
No network, APIs or third-party packages are required.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
from typing import Any

from alcg import Call, String, parse, walk
from coverage_lab import (
    BenchmarkError,
    DOMAINS,
    DEFAULT_BENCHMARK,
    DEFAULT_RELATIONS,
    inspect_calls,
    jsonl,
    load_benchmark,
    relations,
)

ROOT = Path(__file__).resolve().parent
CONTRAST_BENCHMARK = ROOT / "benchmarks" / "contrast-v0.3.jsonl"
CONTRAST_FIELDS = {"id", "domain", "target", "correct", "foil", "contrast", "note"}
PAIR_ID = re.compile(r"K[0-9]{2,4}\Z")
TASKS = frozenset({"reconstruct", "choose"})


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return ("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                    for row in rows)).encode("utf-8")


def load_contrasts(path: Path = CONTRAST_BENCHMARK,
                   registry_path: Path = DEFAULT_RELATIONS) -> list[dict[str, str]]:
    registry = relations(registry_path)
    rows = jsonl(path)
    if not rows:
        raise BenchmarkError("contrast benchmark is empty")
    seen: set[str] = set()
    for row in rows:
        if set(row) != CONTRAST_FIELDS:
            raise BenchmarkError(f"contrast record has unexpected fields: {sorted(set(row) ^ CONTRAST_FIELDS)}")
        identifier = row["id"]
        if not isinstance(identifier, str) or not PAIR_ID.fullmatch(identifier) or identifier in seen:
            raise BenchmarkError(f"duplicate or invalid contrast id: {identifier!r}")
        seen.add(identifier)
        if row["domain"] not in DOMAINS:
            raise BenchmarkError(f"{identifier}: unknown domain")
        for field in ("target", "correct", "foil", "contrast", "note"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise BenchmarkError(f"{identifier}: empty or invalid {field}")
        correct, foil = parse(row["correct"]), parse(row["foil"])
        if correct == foil:
            raise BenchmarkError(f"{identifier}: correct and foil are identical")
        for expression in (correct, foil):
            inspect_calls(expression, registry)
            if any(isinstance(node, String) or
                   (isinstance(node, Call) and node.name in {"RAW", "PARTIAL"})
                   for node in walk(expression)):
                raise BenchmarkError(f"{identifier}: contrast items must be fully structured")
    return rows


def validate_sources(coverage_path: Path = DEFAULT_BENCHMARK,
                     contrast_path: Path = CONTRAST_BENCHMARK,
                     registry_path: Path = DEFAULT_RELATIONS) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    coverage_rows = load_benchmark(coverage_path, registry_path)
    contrasts = load_contrasts(contrast_path, registry_path)
    candidates = [row for row in coverage_rows if row["hypothesis"] == "candidate"]
    if not candidates:
        raise BenchmarkError("no fully structured reconstruction candidates")
    return candidates, contrasts


def prepare(coverage_path: Path = DEFAULT_BENCHMARK,
            contrast_path: Path = CONTRAST_BENCHMARK,
            registry_path: Path = DEFAULT_RELATIONS,
            seed: int = 20261108) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates, contrasts = validate_sources(coverage_path, contrast_path, registry_path)
    rng = random.Random(seed)
    candidates = list(candidates)
    contrasts = list(contrasts)
    rng.shuffle(candidates)
    rng.shuffle(contrasts)
    # Equal numbers of A and B answers (for 12 pairs: six each).
    correct_sides = ["A"] * (len(contrasts) // 2) + ["B"] * (len(contrasts) - len(contrasts) // 2)
    rng.shuffle(correct_sides)

    packet: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    for n, row in enumerate(candidates, 1):
        identifier = f"R{n:04}"
        packet.append({"id": identifier, "task": "reconstruct", "expression": row["expression"]})
        gold.append({"id": identifier, "task": "reconstruct", "source_id": row["id"],
                     "domain": row["domain"], "english": row["english"]})
    for n, (row, correct_side) in enumerate(zip(contrasts, correct_sides), 1):
        identifier = f"C{n:04}"
        options = ({"A": row["correct"], "B": row["foil"]} if correct_side == "A"
                   else {"A": row["foil"], "B": row["correct"]})
        packet.append({"id": identifier, "task": "choose", "target": row["target"], "options": options})
        gold.append({"id": identifier, "task": "choose", "source_id": row["id"],
                     "domain": row["domain"], "correct_option": correct_side,
                     "contrast": row["contrast"], "note": row["note"]})
    rng.shuffle(packet)
    # The response packet never contains source-English answers to the reconstruction task.
    if any("english" in case or "source_id" in case or "correct_option" in case for case in packet):
        raise AssertionError("reader packet leaked a key field")
    source_hashes = {
        "coverage": digest(coverage_path.read_bytes()),
        "contrasts": digest(contrast_path.read_bytes()),
        "relations": digest(registry_path.read_bytes()),
    }
    key = {"schema": "ALCG-reconstruction-v0.3", "seed": seed,
           "packet_sha256": digest(jsonl_bytes(packet)), "sources_sha256": source_hashes,
           "items": gold,
           "warning": "Key must not be sent to a reader. Public development benchmarks are not secure holdouts."}
    return packet, key


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create to avoid silently overwriting another experiment or an existing key.
    with path.open("xb") as handle:
        handle.write(data)
    if "key" in path.name.lower():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Best-effort; platform support differs.


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def evaluate(packet_path: Path, key_path: Path, response_path: Path,
             ratings_path: Path | None = None) -> dict[str, Any]:
    packet = jsonl(packet_path)
    try:
        key = json.loads(key_path.read_text(encoding="utf-8"))
    except (ValueError, TypeError) as exc:
        raise BenchmarkError("invalid private scoring key") from exc
    if not isinstance(key, dict) or key.get("schema") != "ALCG-reconstruction-v0.3":
        raise BenchmarkError("unrecognized scoring key schema")
    if key.get("packet_sha256") != digest(packet_path.read_bytes()):
        raise BenchmarkError("packet digest does not match scoring key")
    answer_items = key.get("items")
    if not isinstance(answer_items, list):
        raise BenchmarkError("missing scoring key items")
    gold: dict[str, dict[str, Any]] = {}
    for item in answer_items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in gold:
            raise BenchmarkError("duplicate or invalid key case")
        gold[item["id"]] = item
    record_ids = [r.get("id") for r in packet]
    if len(record_ids) != len(gold) or set(record_ids) != set(gold) or len(set(record_ids)) != len(record_ids):
        raise BenchmarkError("packet/key case IDs do not match")
    packet_types: dict[str, str] = {}
    for case in packet:
        identifier, task = case["id"], case.get("task")
        if task not in TASKS or task != gold[identifier].get("task"):
            raise BenchmarkError(f"{identifier}: inconsistent task type")
        if task == "reconstruct" and set(case) != {"id", "task", "expression"}:
            raise BenchmarkError(f"{identifier}: malformed reconstruction item")
        if task == "choose" and (set(case) != {"id", "task", "target", "options"}
                                 or not isinstance(case["options"], dict)
                                 or set(case["options"]) != {"A", "B"}):
            raise BenchmarkError(f"{identifier}: malformed contrast item")
        packet_types[identifier] = task

    responses = jsonl(response_path)
    response_by_id: dict[str, dict[str, Any]] = {}
    for response in responses:
        identifier = response.get("id")
        if not isinstance(identifier, str) or identifier not in gold or identifier in response_by_id:
            raise BenchmarkError(f"invalid, duplicate, or unknown response ID: {identifier!r}")
        task = packet_types[identifier]
        if task == "reconstruct":
            if set(response) != {"id", "reconstruction", "uncertainty"}:
                raise BenchmarkError(f"{identifier}: reconstruction responses require id, reconstruction, uncertainty")
            if not all(isinstance(response[k], str) for k in ("reconstruction", "uncertainty")):
                raise BenchmarkError(f"{identifier}: reconstruction/uncertainty must be strings")
            if not response["reconstruction"].strip():
                raise BenchmarkError(f"{identifier}: reconstruction must not be empty")
        else:
            if set(response) != {"id", "choice", "rationale"}:
                raise BenchmarkError(f"{identifier}: choice responses require id, choice, rationale")
            if response["choice"] not in ("A", "B", "ABSTAIN"):
                raise BenchmarkError(f"{identifier}: invalid choice; expected A, B, or ABSTAIN")
            if not isinstance(response["rationale"], str):
                raise BenchmarkError(f"{identifier}: rationale must be a string")
        response_by_id[identifier] = response

    choices = [i for i in gold if packet_types[i] == "choose"]
    reconstructions = [i for i in gold if packet_types[i] == "reconstruct"]
    selected = [i for i in choices if response_by_id.get(i, {}).get("choice") in ("A", "B")]
    abstained = sum(response_by_id.get(i, {}).get("choice") == "ABSTAIN" for i in choices)
    correct = sum(response_by_id[i]["choice"] == gold[i]["correct_option"] for i in selected)
    responses_submitted = [i for i in reconstructions if i in response_by_id]

    ratings_by_id: dict[str, dict[str, Any]] = {}
    if ratings_path is not None:
        for rating in jsonl(ratings_path):
            identifier = rating.get("id")
            if (not isinstance(identifier, str) or identifier not in reconstructions
                    or identifier in ratings_by_id or identifier not in response_by_id):
                raise BenchmarkError(f"invalid or unsubmitted reconstruction rating: {identifier!r}")
            if set(rating) != {"id", "rating", "notes"}:
                raise BenchmarkError(f"{identifier}: rating fields must be id, rating, notes")
            if type(rating["rating"]) is not int or rating["rating"] not in range(4):
                raise BenchmarkError(f"{identifier}: rating must be integer 0..3")
            if not isinstance(rating["notes"], str) or not rating["notes"].strip():
                raise BenchmarkError(f"{identifier}: rating notes must be nonempty")
            ratings_by_id[identifier] = rating

    distribution = Counter(x["rating"] for x in ratings_by_id.values())
    domain_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"assigned": 0, "correct": 0, "selected": 0})
    for identifier in choices:
        domain = gold[identifier]["domain"]
        domain_stats[domain]["assigned"] += 1
        if identifier in selected:
            domain_stats[domain]["selected"] += 1
            if response_by_id[identifier]["choice"] == gold[identifier]["correct_option"]:
                domain_stats[domain]["correct"] += 1
    return {
        "schema": "ALCG-reconstruction-v0.3-score",
        "assigned": {"reconstruct": len(reconstructions), "choose": len(choices)},
        "reconstruction": {
            "submitted": len(responses_submitted), "missing": len(reconstructions) - len(responses_submitted),
            "independently_rated": len(ratings_by_id),
            "unrated_submissions": len(responses_submitted) - len(ratings_by_id),
            "rating_distribution": {str(i): distribution[i] for i in range(4)},
            "mean_on_rated_only": (round(sum(k * v for k, v in distribution.items()) / len(ratings_by_id), 4)
                                   if ratings_by_id else None),
            "faithful_rating_3_on_rated_only": (round(distribution[3] / len(ratings_by_id), 4)
                                              if ratings_by_id else None),
        },
        "contrast": {
            "selected": len(selected), "abstained": abstained,
            "missing": len(choices) - len(selected) - abstained,
            "correct": correct,
            "accuracy_all_assigned": round(correct / len(choices), 4) if choices else None,
            "accuracy_selected_only": round(correct / len(selected), 4) if selected else None,
            "domains": dict(sorted(domain_stats.items())),
            "always_A_baseline_on_balanced_key": (sum(gold[i]["correct_option"] == "A" for i in choices)
                                                  / len(choices) if choices else None),
        },
        "limitations": [
            "Contrast is forced-choice discrimination, not open-ended reconstruction.",
            "Reconstruction is unscored until external adjudications are supplied.",
            "Examples and answer keys are public in source data; require independent held-out trials for generalization claims.",
            "No claim of independent AI testing unless a separate reader actually participated."
        ],
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="ALCG v0.3 blind reading and contrast trials")
    subs = cli.add_subparsers(dest="command", required=True)
    check = subs.add_parser("check", help="validate the immutable v0.2 base and new contrast fixtures")
    prep = subs.add_parser("prepare", help="write blind challenge and local scoring key")
    prep.add_argument("--out", type=Path, required=True, help="reader packet (share only this file)")
    prep.add_argument("--key", type=Path, required=True, help="private scoring key (never send to reader)")
    prep.add_argument("--seed", type=int, default=20261108)
    grade = subs.add_parser("grade", help="grade a reader's submitted JSONL responses")
    grade.add_argument("--packet", type=Path, required=True)
    grade.add_argument("--key", type=Path, required=True)
    grade.add_argument("--responses", type=Path, required=True)
    grade.add_argument("--ratings", type=Path, help="optional independent 0-3 ratings for reconstruction")
    args = cli.parse_args(argv)
    try:
        if args.command == "check":
            reconstructed, contrasts = validate_sources()
            print(f"OK: {len(reconstructed)} reconstruction candidates and {len(contrasts)} contrast pairs valid")
            return 0
        if args.command == "prepare":
            if args.out.resolve() == args.key.resolve():
                raise BenchmarkError("reader packet and scoring key must be different paths")
            if args.out.exists() or args.key.exists():
                raise BenchmarkError("output already exists; refusing to overwrite experiment data")
            packet, key = prepare(seed=args.seed)
            write_new(args.out, jsonl_bytes(packet))
            write_new(args.key, json_bytes(key))
            print(f"Created reader packet with {len(packet)} cases: {args.out}")
            print(f"Keep private scoring key separate: {args.key}")
            return 0
        report = evaluate(args.packet, args.key, args.responses, args.ratings)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (BenchmarkError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
