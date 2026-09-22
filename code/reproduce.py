#!/usr/bin/env python3
"""Recompute the public result tables from the included data."""
from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"


def read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_cases():
    with gzip.open(DATA / "cases.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def eligible(row):
    return row["reference_grade"] in {"VALID_A", "VALID_B"}


def accepted(row):
    return row["decision"] == "SUPPORTED"


def load_aggregates():
    out = {}
    for row in read_csv(DATA / "aggregates.csv"):
        out[(row["section"], row["group"], row["metric"])] = row
    return out


def aval(aggregates, section, group, metric):
    return float(aggregates[(section, group, metric)]["value"])


def fmt_number(value):
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def build_summary(cases, aggregates):
    n = len(cases)
    valid_a = sum(r["reference_grade"] == "VALID_A" for r in cases)
    valid_b = sum(r["reference_grade"] == "VALID_B" for r in cases)
    invalid = sum(r["reference_grade"] == "INVALID" for r in cases)
    accepted_n = sum(accepted(r) for r in cases)
    eligible_n = sum(eligible(r) for r in cases)
    shared = sum(accepted(r) and eligible(r) for r in cases)
    accepted_only = sum(accepted(r) and not eligible(r) for r in cases)
    eligible_only = sum((not accepted(r)) and eligible(r) for r in cases)
    neither = sum((not accepted(r)) and (not eligible(r)) for r in cases)
    union = shared + accepted_only + eligible_only
    difference = accepted_only + eligible_only

    invalid_rows = [r for r in cases if r["reference_grade"] == "INVALID"]
    false_supported = [r for r in invalid_rows if accepted(r)]
    type_fail = lambda r: r["type_status"] == "Ineligible / contradicted"
    affiliation_fail = lambda r: r["affiliation_status"] == "Not supported for focal institution"

    reviewer_total = int(aval(aggregates, "reviewers", "all", "total"))
    reviewer_exact = int(aval(aggregates, "reviewers", "all", "exact_agreement"))
    reviewer_collapsed = int(aval(aggregates, "reviewers", "all", "collapsed_agreement"))
    third_adjudication = int(aval(aggregates, "reviewers", "all", "third_adjudication"))
    conference_total = int(aval(aggregates, "conference_papers", "all", "source_labelled"))
    conference_excluded = int(aval(aggregates, "conference_papers", "all", "excluded_by_type"))
    conference_eligible = int(aval(aggregates, "conference_papers", "all", "eligible"))

    values = [
        ("audited_cases", n, "count", "cases"),
        ("valid_a", valid_a, "count", "cases"),
        ("valid_b", valid_b, "count", "cases"),
        ("invalid", invalid, "count", "cases"),
        ("accepted", accepted_n, "count", "cases"),
        ("eligible", eligible_n, "count", "cases"),
        ("shared", shared, "count", "cases"),
        ("accepted_only", accepted_only, "count", "cases"),
        ("eligible_only", eligible_only, "count", "cases"),
        ("neither", neither, "count", "cases"),
        ("union", union, "count", "cases"),
        ("membership_difference", difference, "count", "cases"),
        ("membership_difference_rate", difference / n, "proportion", "cases"),
        ("jaccard_overlap", shared / union, "proportion", "cases"),
        ("accepted_precision", shared / accepted_n, "proportion", "cases"),
        ("eligible_retention", shared / eligible_n, "proportion", "cases"),
        ("net_size_difference", abs(eligible_n - accepted_n), "count", "cases"),
        ("net_size_difference_relative_to_eligible", abs(eligible_n - accepted_n) / eligible_n, "proportion", "cases"),
        ("invalid_type_failures", sum(type_fail(r) for r in invalid_rows), "count", "cases"),
        ("invalid_affiliation_failures", sum(affiliation_fail(r) for r in invalid_rows), "count", "cases"),
        ("invalid_type_affiliation_overlap", sum(type_fail(r) and affiliation_fail(r) for r in invalid_rows), "count", "cases"),
        ("false_supported_type_failures", sum(type_fail(r) for r in false_supported), "count", "cases"),
        ("false_supported_affiliation_failures", sum(affiliation_fail(r) for r in false_supported), "count", "cases"),
        ("false_supported_type_affiliation_overlap", sum(type_fail(r) and affiliation_fail(r) for r in false_supported), "count", "cases"),
        ("reviewer_exact_agreement_count", reviewer_exact, "count", "aggregate"),
        ("reviewer_exact_agreement_rate", reviewer_exact / reviewer_total, "proportion", "aggregate"),
        ("reviewer_collapsed_agreement_count", reviewer_collapsed, "count", "aggregate"),
        ("reviewer_collapsed_agreement_rate", reviewer_collapsed / reviewer_total, "proportion", "aggregate"),
        ("third_adjudication_cases", third_adjudication, "count", "aggregate"),
        ("conference_source_labeled", conference_total, "count", "aggregate"),
        ("conference_excluded_by_type", conference_excluded, "count", "aggregate"),
        ("conference_eligible", conference_eligible, "count", "cases+aggregate"),
    ]
    return [
        {"metric": metric, "value": fmt_number(value), "unit": unit, "provenance": provenance}
        for metric, value, unit, provenance in values
    ]


def build_robustness(cases, institutions, aggregates):
    rows = []
    quintile = {r["institution_id"]: int(r["scale_quintile"]) for r in institutions}

    for q in range(1, 6):
        subset = [r for r in cases if quintile[r["institution_id"]] == q]
        n = len(subset)
        e = sum(eligible(r) for r in subset)
        a = sum(accepted(r) for r in subset)
        tp = sum(eligible(r) and accepted(r) for r in subset)
        rows.append({
            "analysis": "scale_quintile", "group": str(q), "n": n, "eligible": e,
            "accepted": a, "true_positive": tp,
            "accepted_precision": fmt_number(tp / a), "eligible_retention": fmt_number(tp / e),
            "lower": "", "upper": "", "replicates": "",
            "note": "Descriptive within the fixed 50-university study frame.",
        })

    domain_groups = []
    for key in aggregates:
        section, group, metric = key
        if section == "broad_domain" and group not in domain_groups:
            domain_groups.append(group)
    for group in domain_groups:
        n = int(aval(aggregates, "broad_domain", group, "n"))
        e = int(aval(aggregates, "broad_domain", group, "eligible"))
        a = int(aval(aggregates, "broad_domain", group, "accepted"))
        tp = int(aval(aggregates, "broad_domain", group, "true_positive"))
        rows.append({
            "analysis": "broad_domain", "group": group, "n": n, "eligible": e,
            "accepted": a, "true_positive": tp,
            "accepted_precision": fmt_number(tp / a) if a else "",
            "eligible_retention": fmt_number(tp / e) if e else "",
            "lower": "", "upper": "", "replicates": "",
            "note": "Domain aggregate from the included inputs; case-level domain labels are not included.",
        })

    by_institution = defaultdict(list)
    for row in cases:
        by_institution[row["institution_id"]].append(row)
    precision_values = []
    retention_values = []
    all_ids = set(by_institution)
    for held_out in sorted(all_ids):
        subset = [r for r in cases if r["institution_id"] != held_out]
        tp = sum(eligible(r) and accepted(r) for r in subset)
        fp = sum((not eligible(r)) and accepted(r) for r in subset)
        fn = sum(eligible(r) and (not accepted(r)) for r in subset)
        precision_values.append(tp / (tp + fp))
        retention_values.append(tp / (tp + fn))
    rows.extend([
        {"analysis": "leave_one_institution_out", "group": "accepted_precision", "n": "", "eligible": "", "accepted": "", "true_positive": "", "accepted_precision": "", "eligible_retention": "", "lower": fmt_number(min(precision_values)), "upper": fmt_number(max(precision_values)), "replicates": "", "note": "Descriptive influence range."},
        {"analysis": "leave_one_institution_out", "group": "eligible_retention", "n": "", "eligible": "", "accepted": "", "true_positive": "", "accepted_precision": "", "eligible_retention": "", "lower": fmt_number(min(retention_values)), "upper": fmt_number(max(retention_values)), "replicates": "", "note": "Descriptive influence range."},
    ])

    a_rows = [r for r in cases if r["reference_grade"] == "VALID_A"]
    b_rows = [r for r in cases if r["reference_grade"] == "VALID_B"]
    i_rows = [r for r in cases if r["reference_grade"] == "INVALID"]
    ac = lambda rows_: sum(accepted(r) for r in rows_)
    na = lambda rows_: sum(not accepted(r) for r in rows_)
    precision_low = ac(a_rows) / (ac(a_rows) + ac(b_rows) + ac(i_rows))
    precision_high = (ac(a_rows) + ac(b_rows)) / (ac(a_rows) + ac(b_rows) + ac(i_rows))
    retention_low = ac(a_rows) / (ac(a_rows) + na(a_rows) + na(b_rows))
    retention_high = (ac(a_rows) + ac(b_rows)) / (ac(a_rows) + ac(b_rows) + na(a_rows))
    rows.extend([
        {"analysis": "grade_b_sensitivity", "group": "accepted_precision", "n": "", "eligible": "", "accepted": "", "true_positive": "", "accepted_precision": "", "eligible_retention": "", "lower": fmt_number(precision_low), "upper": fmt_number(precision_high), "replicates": "", "note": "Logical bounds with grade A and invalid classifications held fixed."},
        {"analysis": "grade_b_sensitivity", "group": "eligible_retention", "n": "", "eligible": "", "accepted": "", "true_positive": "", "accepted_precision": "", "eligible_retention": "", "lower": fmt_number(retention_low), "upper": fmt_number(retention_high), "replicates": "", "note": "Logical bounds with grade A and invalid classifications held fixed."},
    ])

    reps = int(aval(aggregates, "cluster_resampling", "all", "replicates"))
    for metric in ("accepted_precision", "eligible_retention"):
        rows.append({
            "analysis": "cluster_resampling", "group": metric, "n": "", "eligible": "", "accepted": "", "true_positive": "", "accepted_precision": "", "eligible_retention": "",
            "lower": fmt_number(aval(aggregates, "cluster_resampling", metric, "lower")),
            "upper": fmt_number(aval(aggregates, "cluster_resampling", metric, "upper")),
            "replicates": reps,
            "note": "Percentile range from the included aggregate inputs.",
        })
    return rows


def main():
    cases = read_cases()
    institutions = read_csv(DATA / "institutions.csv")
    aggregates = load_aggregates()

    summary = build_summary(cases, aggregates)
    robustness = build_robustness(cases, institutions, aggregates)

    write_csv(RESULTS / "summary.csv", ["metric", "value", "unit", "provenance"], summary)
    write_csv(
        RESULTS / "robustness.csv",
        ["analysis", "group", "n", "eligible", "accepted", "true_positive", "accepted_precision", "eligible_retention", "lower", "upper", "replicates", "note"],
        robustness,
    )
    print("Reproduced results/summary.csv and results/robustness.csv")


if __name__ == "__main__":
    main()
