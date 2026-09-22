# Data guide

## `cases.csv.gz`

Each row is one institution-work pair from the 400-case validation sample.

| Field | Meaning |
| --- | --- |
| `case_id` | Stable case identifier. |
| `institution_id` | OpenAlex institution locator. |
| `institution_name` | Canonical institution name. |
| `work_id` | OpenAlex work locator. |
| `scale_quintile` | Fixed publication-scale quintile, 1–5. |
| `reference_grade` | Reference classification: grade A, grade B or invalid. |
| `decision` | Historical decision: supported, unresolved or excluded. |
| `membership` | Relation between the eligible and accepted portfolios. |
| `evidence_tier` | Concise evidence-provenance category for the reference decision. |
| `identity_status` | Bibliographic identity status. |
| `timing_status` | Publication-timing status. |
| `type_status` | Research-output type status. |
| `affiliation_status` | Organizational-attribution status for the focal institution. |
| `identity_basis` | Evidence supporting the adjudicated reference for bibliographic identity. |
| `timing_basis` | Evidence supporting the adjudicated reference for publication timing. |
| `type_basis` | Evidence supporting the adjudicated reference for research-output type. |
| `affiliation_basis` | Evidence supporting the adjudicated reference for organizational attribution. |
| `documented_conference_case` | `yes` for the 34 individually documented eligible conference-paper cases. |
| `source_1`, `source_2` | Keys into `sources.csv` for evidence available for documentary inspection. |

For compatibility with the reproduction code, the deposited case file stores grade A, grade B and invalid as `VALID_A`, `VALID_B` and `INVALID`, and historical supported, unresolved and excluded decisions as `SUPPORTED`, `UNRESOLVED` and `EXCLUDED`. Reader-facing materials use the natural labels.

These fields describe the evidence supporting the adjudicated reference; the historical decision inputs are summarized separately.

The case-level data reproduce the portfolio sizes, membership overlap, precision, retention and corrected type and organizational-attribution failure counts. They also support the publication-scale quintile summaries, leave-one-institution-out ranges and grade-B logical sensitivity bounds.

## `institutions.csv`

This file contains the 50 institutions in the fixed study frame, their publication-scale quintile, the candidate count after the prior-work exclusion and the selected count. Each institution contributes eight validation cases.

## `sources.csv`

This file contains public source locators retained for case-level documentary inspection. `source_id` values are referenced by `cases.csv.gz`. The reproduction scripts do not contact these URLs.

## `aggregates.csv`

Some reported quantities are available only in aggregate form in the deposited data. They are stored separately at the aggregate level:

- reviewer agreement: 331/400 exact four-label agreement across grade A, grade B, invalid and unresolved, and 367/400 after combining grade A and grade B versus invalid and unresolved;
- broad-domain counts used in the descriptive domain summaries;
- percentile ranges from 20,000 institution-cluster resamples;
- 38 source-labeled conference papers excluded by the historical type rule and 34 adjudicated eligible conference-paper cases.

The 34 individually documented eligible conference-paper cases are identified in `cases.csv.gz`. The remaining four conference-paper cases contribute to the aggregate total because equivalent case-level evidence is unavailable.

Individual reviewer assignments, case-level broad-domain labels and the resampling draw sequence are not part of the deposited data. `reproduce.py` therefore uses the aggregate inputs for those quantities while recomputing the case-level and institution-level diagnostics supported directly by the included files.

## Rates

Proportions in the result files use a 0–1 scale. For example, `0.83986928` corresponds to 83.99%.
