# University portfolio validity

This repository contains the data and code used to reproduce a portfolio-validity analysis of 400 institution-work pairs from 50 universities. The normal notebook rebuilds the reported summary and descriptive robustness and sensitivity results from the deposited data.

## Reproduce the reported results

[Open the reproduction notebook in Colab](https://colab.research.google.com/github/evidenceworks/university-portfolio-validity/blob/main/notebooks/reproduce.ipynb)

This is the normal route. Run all cells to check the included scientific inputs, regenerate the result tables and verify the main reported quantities.

## Optional: verify the historical sample

[Open the sample-selection audit in Colab](https://colab.research.google.com/github/evidenceworks/university-portfolio-validity/blob/main/notebooks/selection-audit.ipynb)

This optional route verifies the deterministic selection of the 400 deposited institution-work pairs from the bundled two-column selection universe. See `selection.md` for the exact specification and local command.

## Files

- `notebooks/reproduce.ipynb` — normal Colab reproduction notebook.
- `notebooks/selection-audit.ipynb` — optional historical sample-selection audit.
- `data/cases.csv.gz` — 400 institution-work validation cases.
- `data/institutions.csv` — institution identifiers, scale quintiles and sample counts.
- `data/aggregates.csv` — aggregate inputs not represented at case level.
- `data/sources.csv` — source locators used for documentary inspection.
- `data/excluded-works.csv` — 354 work identifiers omitted before the historical sample selection.
- `data/selection-universe.csv.gz` — two-column institution-work universe for the optional selection audit.
- `results/summary.csv` — main portfolio-validity results.
- `results/robustness.csv` — descriptive robustness and sensitivity diagnostics.
- `code/reproduce.py` — deterministic result regeneration.
- `code/check.py` — integrity and scientific consistency checks.
- `code/verify-selection.py` — optional deterministic sample-selection verifier.
- `checksums.sha256` — hashes for the three stable scientific inputs used by the normal reproduction.

## Data

Each row in `data/cases.csv.gz` is an institution-work pair. The reference distinguishes grade A, grade B and invalid cases. Historical decisions are supported, unresolved or excluded. The case file records evidence provenance for bibliographic identity, publication timing, research-output type and organizational attribution. See `data/README.md` for field-level technical definitions.

## Local use (optional)

From the repository root:

```bash
python code/check.py
python code/reproduce.py
python code/check.py
```

For the optional sample-selection audit, see `selection.md`.

## Licenses

Original software, documentation, annotations and derived outputs are covered as described in `LICENSE`. Full license texts and the note on external source material are in `licenses/`.
