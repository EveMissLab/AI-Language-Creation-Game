"""ALCG v0.6: curated coverage extension + explicit English polysemy registry.

This checks *authored syntax and label discipline*, NOT meaning preservation or
independent AI comprehension. Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from alcg import Call, Name, parse, walk
from coverage_lab import BenchmarkError, jsonl, load_benchmark, relations, score_rows, summarize, write_jsonl

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "benchmarks/coverage-v0.4.jsonl"
NEW = ROOT / "benchmarks/coverage-v0.6.jsonl"
REGISTRY = ROOT / "data/relations-v0.4.json"
SENSES = ROOT / "data/concept-senses-v0.6.json"
OLD_SHA256 = "4569e6b8507340d7c26b1012504f73cdbe078448cf9f887fe256f1e90f2107c6"
REGISTRY_SHA256 = "8ea3fbb5ceba073eac2904ada7469809be2556f319a4a627f705a7db4e08f34e"
PREFIX = {"daily": "D", "science": "S", "mathematics": "M", "computing": "C", "society": "O", "epistemic": "E"}
SENSE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_senses(path: Path = SENSES) -> list[dict[str, str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BenchmarkError(f"unreadable sense registry: {path}") from exc
    if not isinstance(document, dict) or set(document) != {"version", "purpose", "entries"}:
        raise BenchmarkError("sense registry must have version, purpose and entries")
    if document["version"] != "0.6-experimental" or not isinstance(document["purpose"], str):
        raise BenchmarkError("unexpected sense registry version")
    entries = document["entries"]
    if not isinstance(entries, list) or not entries:
        raise BenchmarkError("sense registry needs entries")
    seen_ids: set[str] = set()
    by_surface: dict[str, set[str]] = defaultdict(set)
    out: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"surface", "sense_id", "kind", "gloss"}:
            raise BenchmarkError("each sense must have surface, sense_id, kind and gloss")
        surface, sense_id, kind, gloss = (item[k] for k in ("surface", "sense_id", "kind", "gloss"))
        if not all(isinstance(v, str) for v in (surface, sense_id, kind, gloss)):
            raise BenchmarkError("sense fields must be strings")
        if not re.fullmatch(r"[a-z]+", surface) or not SENSE_PATTERN.fullmatch(sense_id):
            raise BenchmarkError(f"invalid surface/sense spelling: {surface!r}/{sense_id!r}")
        if not sense_id.startswith(surface.upper() + "_"):
            raise BenchmarkError(f"sense prefix must match English surface: {sense_id}")
        if kind not in {"noun", "adjective", "verb", "adverb"} or len(gloss.strip()) < 25:
            raise BenchmarkError(f"invalid grammatical kind or underspecified gloss: {sense_id}")
        if sense_id in seen_ids:
            raise BenchmarkError(f"duplicate sense id: {sense_id}")
        seen_ids.add(sense_id)
        by_surface[surface].add(sense_id)
        out.append(item)
    if any(len(ids) < 2 for ids in by_surface.values()):
        raise BenchmarkError("each listed surface must demonstrate at least two distinct meanings")
    return out


def inspect_benchmark(rows: list[dict[str, Any]], entries: list[dict[str, str]],
                      baseline: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail on data leakage or label ambiguity; never infer that syntax proves meaning."""
    if len(baseline) != 36 or len(rows) != 48:
        raise BenchmarkError("baseline must be 36 rows and v0.6 must contain 48 additional rows")
    baseline_ids = {r["id"] for r in baseline}
    baseline_sources = {r["english"].strip().casefold() for r in baseline}
    case_ids = {r["id"] for r in rows}
    seen_sources: set[str] = set()
    case_domains = Counter(r["domain"] for r in rows)
    expected_ids = {f"{prefix}{num}" for prefix in PREFIX.values() for num in range(101, 109)}
    if case_ids != expected_ids or case_ids & baseline_ids:
        raise BenchmarkError("v0.6 IDs must be disjoint D/S/M/C/O/E101..108")
    if case_domains != Counter({domain: 8 for domain in PREFIX}):
        raise BenchmarkError("each of the six domains must contain eight cases")
    entry_ids = {item["sense_id"] for item in entries}
    ambiguous_bare = {item["surface"].upper() for item in entries}
    usage = Counter()
    old_symbols = {node.value for row in baseline for node in walk(parse(row["expression"])) if isinstance(node, Name)}
    all_symbols = set()
    relations_used = set()
    candidate_nested = 0
    status_counts: Counter[str] = Counter()
    domain_status: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        identifier, domain = row["id"], row["domain"]
        source = row["english"].strip().casefold()
        if source in seen_sources or source in baseline_sources:
            raise BenchmarkError(f"{identifier}: source English duplicates a previous case")
        seen_sources.add(source)
        if not identifier.startswith(PREFIX[domain]):
            raise BenchmarkError(f"{identifier}: domain prefix mismatch")
        expr = parse(row["expression"])
        atom_names = {node.value for node in walk(expr) if isinstance(node, Name)}
        if atom_names & ambiguous_bare:
            raise BenchmarkError(f"{identifier}: ambiguous bare English labels: {sorted(atom_names & ambiguous_bare)}")
        # Reject an escaped sentence masquerading as a candidate. The legacy
        # coverage validator already rejects RAW, PARTIAL and quoted strings.
        if row["hypothesis"] == "candidate" and not isinstance(expr, Call):
            raise BenchmarkError(f"{identifier}: candidate must have relation structure")
        relation_nodes = [node for node in walk(expr) if isinstance(node, Call)]
        if row["hypothesis"] == "candidate" and len(relation_nodes) > 1:
            candidate_nested += 1
        for node in relation_nodes:
            relations_used.add(node.name)
        usage.update(atom_names & entry_ids)  # Count cases, not number of occurrences.
        all_symbols.update(atom_names)
        status_counts[row["hypothesis"]] += 1
        domain_status[domain][row["hypothesis"]] += 1
    if set(usage) != entry_ids:
        raise BenchmarkError(f"some sense IDs are not exercised: {sorted(entry_ids - set(usage))}")
    if status_counts != Counter({"candidate": 36, "partial": 6, "raw": 6}):
        raise BenchmarkError("expected six candidate, one partial and one raw per domain")
    for domain, counts in domain_status.items():
        if counts != Counter({"candidate": 6, "partial": 1, "raw": 1}):
            raise BenchmarkError(f"{domain}: status distribution mismatch")
    return {
        "version": "0.6",
        "baseline": {"cases": len(baseline), "sha256": checksum(OLD)},
        "new_curated_cases": len(rows),
        "combined_curated_cases": len(baseline) + len(rows),
        "proposal_labels": dict(sorted(status_counts.items())),
        "author_candidate_fraction_of_new_curated_set": round(status_counts["candidate"] / len(rows), 4),
        "candidate_with_nested_relations": candidate_nested,
        "registered_relation_operators_reused": len(relations_used),
        "additional_relation_operators_introduced": 0,
        "new_distinct_lexical_atom_labels_vs_v0_4": len(all_symbols - old_symbols),
        "ambiguous_english_surfaces_reviewed": len({item["surface"] for item in entries}),
        "disambiguated_sense_ids": len(entry_ids),
        "sense_ids_represented_in_cases": len(usage),
        "independent_ai_reader_score": None,
        "wordnet_or_general_english_coverage": None,
        "warning": "All proposals are hand-authored on curated samples. Explicit sense labels and syntactic checks do NOT demonstrate faithful English meaning or AI comprehension.",
    }


def report() -> dict[str, Any]:
    if checksum(OLD) != OLD_SHA256 or checksum(REGISTRY) != REGISTRY_SHA256:
        raise BenchmarkError("frozen v0.4 baseline or relation registry changed")
    entries = validate_senses()
    baseline = load_benchmark(OLD, REGISTRY)
    rows = load_benchmark(NEW, REGISTRY)
    data = inspect_benchmark(rows, entries, baseline)
    data["new_benchmark_sha256"] = checksum(NEW)
    data["sense_registry_sha256"] = checksum(SENSES)
    data["by_domain"] = summarize(rows, relations(REGISTRY))["by_domain"]
    return data


def blind_packet(rows: list[dict[str, Any]], entries: list[dict[str, str]], condition: str) -> list[dict]:
    if condition not in {"unaided", "glossary"}:
        raise BenchmarkError("condition must be unaided or glossary")
    gloss = {item["sense_id"]: item["gloss"] for item in entries}
    packet = []
    for row in rows:
        # RAW/PARTIAL expressions contain the English target inside RAW(text=...),
        # so including them would leak the answer to a purportedly blind reader.
        if row["hypothesis"] != "candidate":
            continue
        answer = {"id": row["id"], "expression": row["expression"]}
        if condition == "glossary":
            used = {n.value for n in walk(parse(row["expression"])) if isinstance(n, Name)}
            answer["sense_glossary"] = {key: gloss[key] for key in sorted(used & gloss.keys())}
        packet.append(answer)
    return packet


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="ALCG v0.6 curated concept coverage and polysemy checks")
    cli.add_argument("command", choices=["check", "report", "blind", "score"])
    cli.add_argument("--condition", choices=["unaided", "glossary"], default="unaided")
    cli.add_argument("--out", type=Path, help="Destination JSONL for blind reader challenge")
    cli.add_argument("--judgments", type=Path, help="External adjudications of candidate-only reader responses")
    args = cli.parse_args(argv)
    try:
        result = report()
        if args.command == "check":
            print("OK: 48 curated new cases, 17 explicit sense labels, 36 candidate hypotheses; NO comprehension score")
        elif args.command == "report":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "score":
            if args.judgments is None:
                raise BenchmarkError("score requires --judgments PATH; never invent reader scores")
            candidate_rows = [row for row in load_benchmark(NEW, REGISTRY) if row["hypothesis"] == "candidate"]
            result = score_rows(candidate_rows, jsonl(args.judgments))
            result["condition"] = args.condition
            result["note"] = "Reader identity, prompt condition, responses and human adjudication provenance must be recorded separately. A score alone cannot establish comprehension."
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            rows = load_benchmark(NEW, REGISTRY)
            packet = blind_packet(rows, validate_senses(), args.condition)
            if args.out:
                write_jsonl(args.out, packet)
                print(f"Wrote {len(packet)} {args.condition} reader prompts to {args.out}")
            else:
                for item in packet:
                    print(json.dumps(item, ensure_ascii=False))
    except (BenchmarkError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
