# University research output indicators

Data and code for “Bibliographic corrections and university research output indicators: Institutional consequences and validation requirements.” The study combines a historical audit of 400 institution–work pairs with a stratified sample of 2,000 additional pairs from a frozen frame of fifty US universities.

Repository: https://github.com/evidenceworks/university-portfolio-validity

## Run

Use Python 3.11 or later. Quick uses the standard library to verify file hashes, reproduce the rule classifications and check the principal estimates and exact evidence requirements:

```sh
python reproduce.py quick
```

Core also reconstructs selection from the complete frame, calculates the paired bootstraps and date sensitivities, and checks finite-population coverage by exhaustive enumeration:

```sh
python -m pip install -r requirements.txt
python reproduce.py core
```

Both commands block network connections during calculation. Core writes numerical tables, attaining assignments and an execution record to `results/`. Inputs remain unchanged. NumPy is the sole external dependency, used for the seeded bootstrap.

## Inputs and calculations

| File | Contents |
|---|---|
| `data/cases.csv.gz` | All 400 original observations and recorded reference labels |
| `data/frame.csv.gz` | Complete institution–work frame |
| `data/rules.json`, `seed.json` | Fixed rules and original sampling seed |
| `data/historical.json.gz` | Historical classifier inputs, institutional boundaries, exclusions and HERD/Leiden scope data |
| `data/institutional.json.gz` | Selected pairs, complete sampled-work incidence and frozen OpenAlex/Crossref fields |
| `data/evidence.json.gz` | Classification passes, documentary findings and date checks |
| `data/provenance.json.gz` | Source URLs, receipt hashes and metadata-projection identity |
| `data/expected.json.gz` | Numerical reference values checked during execution |

The historical module reproduces the factorial comparisons, loss bounds and attainable evidence minima. The institutional module estimates operational changes and source sensitivities. The exact module inverts integer hypergeometric tails with explicit endpoint families. All calculations retain adverse and unresolved findings.

## Interpretation

The primary pilot-conditioned estimate is 65,785 additional institutional credits, with approximate 95% interval 48,753–82,817. The original full-forty expansion is 64,818. Both target the same operational effect within 1,044,517 unexamined frame pairs. Sampling inference assumes fixed potential source decisions and record screens, with independent uniform within-institution permutations. The seed reproduces sample selection; its original random generation is undocumented.

Conference mapping has a simultaneous one-sided lower bound of 3,578 additions. Its simultaneous two-sided 95% interval is [3,098–410,403]; sparse strata limit precision about magnitude. Documentary evidence leaves aggregate accuracy improvement in the new sample unresolved. For the 400 audited pairs, grouped-count validation requires at least 41 further eligible findings at optimal locations, including 32 on unchanged decisions. These minima are jointly attainable and count successful findings rather than documents examined. All loss differences use corrected minus baseline.

Code is licensed under MIT; authored documentation, annotations and results under CC BY 4.0. Source metadata retain their original status. Full publications and publisher HTML are excluded. See `LICENSE` for attribution and source rights.
