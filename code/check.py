#!/usr/bin/env python3
"""Verify scientific inputs, data structure, and reproduced result tables."""
from __future__ import annotations

import csv
import gzip
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
CORE_INPUTS = (
    "data/cases.csv.gz",
    "data/institutions.csv",
    "data/aggregates.csv",
)
SUMMARY_METRICS = (
    "audited_cases",
    "valid_a",
    "valid_b",
    "invalid",
    "accepted",
    "eligible",
    "shared",
    "accepted_only",
    "eligible_only",
    "neither",
    "union",
    "membership_difference",
    "membership_difference_rate",
    "jaccard_overlap",
    "accepted_precision",
    "eligible_retention",
    "net_size_difference",
    "net_size_difference_relative_to_eligible",
    "invalid_type_failures",
    "invalid_affiliation_failures",
    "invalid_type_affiliation_overlap",
    "false_supported_type_failures",
    "false_supported_affiliation_failures",
    "false_supported_type_affiliation_overlap",
    "reviewer_exact_agreement_count",
    "reviewer_exact_agreement_rate",
    "reviewer_collapsed_agreement_count",
    "reviewer_collapsed_agreement_rate",
    "third_adjudication_cases",
    "conference_source_labeled",
    "conference_excluded_by_type",
    "conference_eligible",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_cases():
    with gzip.open(DATA / "cases.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def eligible(row) -> bool:
    return row["reference_grade"] in {"VALID_A", "VALID_B"}


def accepted(row) -> bool:
    return row["decision"] == "SUPPORTED"


def close(actual, expected, tol: float = 1e-8) -> bool:
    return abs(float(actual) - float(expected)) <= tol


def verify_checksums() -> None:
    manifest = ROOT / "checksums.sha256"
    entries = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, rel = line.split("  ", 1)
        except ValueError:
            fail("invalid checksum manifest line")
        if rel in entries:
            fail(f"duplicate checksum path: {rel}")
        entries[rel] = digest

    required = set(CORE_INPUTS)
    if set(entries) != required:
        missing = sorted(required - set(entries))
        unexpected = sorted(set(entries) - required)
        fail(f"checksum manifest paths differ; missing={missing}, unexpected={unexpected}")

    for rel in CORE_INPUTS:
        path = ROOT / rel
        if not path.is_file():
            fail(f"checksummed input missing: {rel}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != entries[rel]:
            fail(f"checksum mismatch: {rel}")


def unique_keyed(rows, key_fields, label):
    keys = [tuple(row[field] for field in key_fields) for row in rows]
    duplicates = sorted(key for key, n in Counter(keys).items() if n > 1)
    if duplicates:
        fail(f"duplicate {label} rows: {duplicates}")
    return {key: row for key, row in zip(keys, rows)}


def aggregate_map(rows):
    amap = unique_keyed(rows, ("section", "group", "metric"), "aggregate")
    return {key: float(row["value"]) for key, row in amap.items()}


def expect_float(row, field, expected, label):
    value = row[field]
    if value == "" or not close(value, expected):
        fail(f"{label}: expected {field}={expected}, found {value!r}")


def expect_int(row, field, expected, label):
    value = row[field]
    try:
        observed = int(value)
    except (TypeError, ValueError):
        fail(f"{label}: expected integer {field}={expected}, found {value!r}")
    if observed != int(expected):
        fail(f"{label}: expected {field}={expected}, found {observed}")


def validate_cross_file_integrity(cases, institutions, sources) -> None:
    if len(cases) != 400:
        fail(f"expected 400 cases, found {len(cases)}")
    if len({row["case_id"] for row in cases}) != 400:
        fail("case_id values are not unique")
    if len({(row["institution_id"], row["work_id"]) for row in cases}) != 400:
        fail("institution-work pairs are not unique")

    if len(institutions) != 50:
        fail(f"expected 50 institutions, found {len(institutions)}")
    inst_ids = [row["institution_id"] for row in institutions]
    if len(set(inst_ids)) != 50:
        fail("institution IDs are not unique")
    inst_map = {row["institution_id"]: row for row in institutions}

    case_counts = Counter(row["institution_id"] for row in cases)
    if set(case_counts) != set(inst_map):
        missing = sorted(set(inst_map) - set(case_counts))
        unexpected = sorted(set(case_counts) - set(inst_map))
        fail(f"case/institution ID sets differ; missing={missing}, unexpected={unexpected}")

    for institution_id, institution in inst_map.items():
        if case_counts[institution_id] != 8:
            fail(f"institution {institution_id} contributes {case_counts[institution_id]} cases, not 8")
        try:
            selected_count = int(institution["selected_count"])
        except ValueError:
            fail(f"invalid selected_count for {institution_id}")
        if selected_count != case_counts[institution_id]:
            fail(f"selected_count differs from public case count for {institution_id}")

    for row in cases:
        institution = inst_map[row["institution_id"]]
        if row["institution_name"] != institution["institution_name"]:
            fail(f"institution name mismatch for {row['case_id']}")
        if row["scale_quintile"] != institution["scale_quintile"]:
            fail(f"scale quintile mismatch for {row['case_id']}")

    source_ids = [row["source_id"] for row in sources]
    if len(set(source_ids)) != len(source_ids):
        fail("source IDs in data/sources.csv are not unique")
    source_set = set(source_ids)
    for row in cases:
        for field in ("source_1", "source_2"):
            source_id = row[field].strip()
            if source_id and source_id not in source_set:
                fail(f"unknown {field}={source_id} for {row['case_id']}")


def validate_case_values(cases) -> None:
    allowed_grades = {"VALID_A", "VALID_B", "INVALID"}
    allowed_decisions = {"SUPPORTED", "UNRESOLVED", "EXCLUDED"}
    allowed_membership = {"shared", "accepted-only", "eligible-only", "neither"}
    if {row["reference_grade"] for row in cases} - allowed_grades:
        fail("unexpected reference grade")
    if {row["decision"] for row in cases} - allowed_decisions:
        fail("unexpected decision value")
    if {row["membership"] for row in cases} - allowed_membership:
        fail("unexpected membership value")

    grade_counts = Counter(row["reference_grade"] for row in cases)
    decision_counts = Counter(row["decision"] for row in cases)
    membership_counts = Counter(row["membership"] for row in cases)
    if grade_counts != Counter({"VALID_A": 147, "VALID_B": 175, "INVALID": 78}):
        fail(f"reference-grade counts differ: {grade_counts}")
    if decision_counts != Counter({"SUPPORTED": 306, "UNRESOLVED": 53, "EXCLUDED": 41}):
        fail(f"decision counts differ: {decision_counts}")
    if membership_counts != Counter({"shared": 257, "eligible-only": 65, "accepted-only": 49, "neither": 29}):
        fail(f"membership counts differ: {membership_counts}")

    for row in cases:
        expected = (
            "shared" if accepted(row) and eligible(row)
            else "accepted-only" if accepted(row)
            else "eligible-only" if eligible(row)
            else "neither"
        )
        if row["membership"] != expected:
            fail(f"membership mismatch for {row['case_id']}")


def validate_summary(cases, aggregates, summary_rows) -> None:
    metrics = [row["metric"] for row in summary_rows]
    duplicates = sorted(metric for metric, n in Counter(metrics).items() if n > 1)
    if duplicates:
        fail(f"duplicate summary metrics: {duplicates}")
    expected_set = set(SUMMARY_METRICS)
    observed_set = set(metrics)
    if observed_set != expected_set:
        missing = sorted(expected_set - observed_set)
        unexpected = sorted(observed_set - expected_set)
        fail(f"summary metric set differs; missing={missing}, unexpected={unexpected}")
    summary = {row["metric"]: row for row in summary_rows}
    amap = aggregate_map(aggregates)

    n = len(cases)
    grade_counts = Counter(row["reference_grade"] for row in cases)
    accepted_n = sum(accepted(row) for row in cases)
    eligible_n = sum(eligible(row) for row in cases)
    shared = sum(accepted(row) and eligible(row) for row in cases)
    accepted_only = sum(accepted(row) and not eligible(row) for row in cases)
    eligible_only = sum((not accepted(row)) and eligible(row) for row in cases)
    neither = sum((not accepted(row)) and (not eligible(row)) for row in cases)
    union = shared + accepted_only + eligible_only
    difference = accepted_only + eligible_only

    invalid_rows = [row for row in cases if row["reference_grade"] == "INVALID"]
    false_supported = [row for row in invalid_rows if accepted(row)]
    type_fail = lambda row: row["type_status"] == "Ineligible / contradicted"
    affiliation_fail = lambda row: row["affiliation_status"] == "Not supported for focal institution"

    reviewer_total = amap[("reviewers", "all", "total")]
    reviewer_exact = amap[("reviewers", "all", "exact_agreement")]
    reviewer_collapsed = amap[("reviewers", "all", "collapsed_agreement")]
    third_adjudication = amap[("reviewers", "all", "third_adjudication")]
    conference_total = amap[("conference_papers", "all", "source_labelled")]
    conference_excluded = amap[("conference_papers", "all", "excluded_by_type")]
    conference_eligible = amap[("conference_papers", "all", "eligible")]

    expected = {
        "audited_cases": n,
        "valid_a": grade_counts["VALID_A"],
        "valid_b": grade_counts["VALID_B"],
        "invalid": grade_counts["INVALID"],
        "accepted": accepted_n,
        "eligible": eligible_n,
        "shared": shared,
        "accepted_only": accepted_only,
        "eligible_only": eligible_only,
        "neither": neither,
        "union": union,
        "membership_difference": difference,
        "membership_difference_rate": difference / n,
        "jaccard_overlap": shared / union,
        "accepted_precision": shared / accepted_n,
        "eligible_retention": shared / eligible_n,
        "net_size_difference": abs(eligible_n - accepted_n),
        "net_size_difference_relative_to_eligible": abs(eligible_n - accepted_n) / eligible_n,
        "invalid_type_failures": sum(type_fail(row) for row in invalid_rows),
        "invalid_affiliation_failures": sum(affiliation_fail(row) for row in invalid_rows),
        "invalid_type_affiliation_overlap": sum(type_fail(row) and affiliation_fail(row) for row in invalid_rows),
        "false_supported_type_failures": sum(type_fail(row) for row in false_supported),
        "false_supported_affiliation_failures": sum(affiliation_fail(row) for row in false_supported),
        "false_supported_type_affiliation_overlap": sum(type_fail(row) and affiliation_fail(row) for row in false_supported),
        "reviewer_exact_agreement_count": reviewer_exact,
        "reviewer_exact_agreement_rate": reviewer_exact / reviewer_total,
        "reviewer_collapsed_agreement_count": reviewer_collapsed,
        "reviewer_collapsed_agreement_rate": reviewer_collapsed / reviewer_total,
        "third_adjudication_cases": third_adjudication,
        "conference_source_labeled": conference_total,
        "conference_excluded_by_type": conference_excluded,
        "conference_eligible": conference_eligible,
    }

    for metric in SUMMARY_METRICS:
        if not close(summary[metric]["value"], expected[metric]):
            fail(f"summary mismatch: {metric}; expected {expected[metric]}, found {summary[metric]['value']}")

    documented = [row for row in cases if row["documented_conference_case"] == "yes"]
    if len(documented) != 34:
        fail("expected 34 individually documented conference cases")
    if not all(eligible(row) and row["decision"] == "EXCLUDED" for row in documented):
        fail("documented conference cases do not match the reported eligible/excluded pattern")
    if conference_total != 38 or conference_excluded != 38 or conference_eligible != 34:
        fail("conference-paper aggregate values differ from the reported totals")
    if reviewer_total != 400 or reviewer_exact != 331 or reviewer_collapsed != 367 or third_adjudication != 69:
        fail("reviewer aggregate values differ from the reported totals")


def validate_robustness(cases, institutions, aggregates, robustness) -> None:
    robust = unique_keyed(robustness, ("analysis", "group"), "robustness")
    amap = aggregate_map(aggregates)

    domain_groups = []
    for row in aggregates:
        if row["section"] == "broad_domain" and row["group"] not in domain_groups:
            domain_groups.append(row["group"])
    if len(domain_groups) != 5:
        fail(f"expected five broad-domain groups, found {len(domain_groups)}")

    expected_keys = {
        *{("scale_quintile", str(q)) for q in range(1, 6)},
        *{("broad_domain", group) for group in domain_groups},
        ("leave_one_institution_out", "accepted_precision"),
        ("leave_one_institution_out", "eligible_retention"),
        ("grade_b_sensitivity", "accepted_precision"),
        ("grade_b_sensitivity", "eligible_retention"),
        ("cluster_resampling", "accepted_precision"),
        ("cluster_resampling", "eligible_retention"),
    }
    if set(robust) != expected_keys:
        missing = sorted(expected_keys - set(robust))
        unexpected = sorted(set(robust) - expected_keys)
        fail(f"robustness row set differs; missing={missing}, unexpected={unexpected}")

    inst_map = {row["institution_id"]: row for row in institutions}
    quintile_counts = Counter(int(row["scale_quintile"]) for row in institutions)
    if quintile_counts != Counter({1: 10, 2: 10, 3: 10, 4: 10, 5: 10}):
        fail(f"institution scale-quintile counts differ: {quintile_counts}")

    for q in range(1, 6):
        subset = [row for row in cases if int(inst_map[row["institution_id"]]["scale_quintile"]) == q]
        n = len(subset)
        e = sum(eligible(row) for row in subset)
        a = sum(accepted(row) for row in subset)
        tp = sum(eligible(row) and accepted(row) for row in subset)
        row = robust[("scale_quintile", str(q))]
        label = f"scale_quintile/{q}"
        expect_int(row, "n", n, label)
        expect_int(row, "eligible", e, label)
        expect_int(row, "accepted", a, label)
        expect_int(row, "true_positive", tp, label)
        expect_float(row, "accepted_precision", tp / a, label)
        expect_float(row, "eligible_retention", tp / e, label)

    for group in domain_groups:
        expected = {
            metric: int(amap[("broad_domain", group, metric)])
            for metric in ("n", "eligible", "accepted", "true_positive")
        }
        row = robust[("broad_domain", group)]
        label = f"broad_domain/{group}"
        for field in ("n", "eligible", "accepted", "true_positive"):
            expect_int(row, field, expected[field], label)
        if expected["accepted"]:
            expect_float(row, "accepted_precision", expected["true_positive"] / expected["accepted"], label)
        elif row["accepted_precision"] != "":
            fail(f"{label}: accepted_precision should be blank when accepted=0")
        if expected["eligible"]:
            expect_float(row, "eligible_retention", expected["true_positive"] / expected["eligible"], label)
        elif row["eligible_retention"] != "":
            fail(f"{label}: eligible_retention should be blank when eligible=0")

    by_inst = defaultdict(list)
    for row in cases:
        by_inst[row["institution_id"]].append(row)
    precision_values = []
    retention_values = []
    for held_out in sorted(by_inst):
        subset = [row for row in cases if row["institution_id"] != held_out]
        tp = sum(eligible(row) and accepted(row) for row in subset)
        fp = sum((not eligible(row)) and accepted(row) for row in subset)
        fn = sum(eligible(row) and (not accepted(row)) for row in subset)
        precision_values.append(tp / (tp + fp))
        retention_values.append(tp / (tp + fn))
    loo_expected = {
        "accepted_precision": (min(precision_values), max(precision_values)),
        "eligible_retention": (min(retention_values), max(retention_values)),
    }
    for metric, (lower, upper) in loo_expected.items():
        row = robust[("leave_one_institution_out", metric)]
        label = f"leave_one_institution_out/{metric}"
        expect_float(row, "lower", lower, label)
        expect_float(row, "upper", upper, label)

    a_rows = [row for row in cases if row["reference_grade"] == "VALID_A"]
    b_rows = [row for row in cases if row["reference_grade"] == "VALID_B"]
    i_rows = [row for row in cases if row["reference_grade"] == "INVALID"]
    ac = lambda rows: sum(accepted(row) for row in rows)
    na = lambda rows: sum(not accepted(row) for row in rows)
    grade_expected = {
        "accepted_precision": (
            ac(a_rows) / (ac(a_rows) + ac(b_rows) + ac(i_rows)),
            (ac(a_rows) + ac(b_rows)) / (ac(a_rows) + ac(b_rows) + ac(i_rows)),
        ),
        "eligible_retention": (
            ac(a_rows) / (ac(a_rows) + na(a_rows) + na(b_rows)),
            (ac(a_rows) + ac(b_rows)) / (ac(a_rows) + ac(b_rows) + na(a_rows)),
        ),
    }
    for metric, (lower, upper) in grade_expected.items():
        row = robust[("grade_b_sensitivity", metric)]
        label = f"grade_b_sensitivity/{metric}"
        expect_float(row, "lower", lower, label)
        expect_float(row, "upper", upper, label)

    replicates = int(amap[("cluster_resampling", "all", "replicates")])
    if replicates != 20000:
        fail(f"cluster resampling replicate count differs: {replicates}")
    for metric in ("accepted_precision", "eligible_retention"):
        row = robust[("cluster_resampling", metric)]
        label = f"cluster_resampling/{metric}"
        expect_int(row, "replicates", replicates, label)
        expect_float(row, "lower", amap[("cluster_resampling", metric, "lower")], label)
        expect_float(row, "upper", amap[("cluster_resampling", metric, "upper")], label)


def main() -> None:
    verify_checksums()
    cases = read_cases()
    institutions = read_csv(DATA / "institutions.csv")
    aggregates = read_csv(DATA / "aggregates.csv")
    sources = read_csv(DATA / "sources.csv")
    summary_rows = read_csv(RESULTS / "summary.csv")
    robustness_rows = read_csv(RESULTS / "robustness.csv")

    validate_cross_file_integrity(cases, institutions, sources)
    validate_case_values(cases)
    validate_summary(cases, aggregates, summary_rows)
    validate_robustness(cases, institutions, aggregates, robustness_rows)

    print(
        "Checks passed: core input hashes, data structure, summary results, robustness results, "
        "source references, and cross-file consistency."
    )


if __name__ == "__main__":
    main()
