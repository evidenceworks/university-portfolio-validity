# Historical sample selection

This optional audit verifies the deterministic selection of the 400 institution-work pairs in the deposited validation sample.

The bundled public universe contains **1,045,601 institution-work pairs** across the 50 institutions in the study frame. Before selection, **354 previously inspected works** were omitted. The public exclusion file contains the 354 work identifiers omitted before sample selection.

For each remaining pair, identifiers are trimmed and bare OpenAlex work identifiers such as `W123...` are expanded to `https://openalex.org/W123...`. The historical ranking value is:

```text
SHA256(seed|focal_openalex_id|work_openalex_id)
```

using UTF-8 encoding and a fixed study seed. The executable verifier contains the exact technical seed required for historical selection reproduction. Within each institution, the eight lowest SHA-256 values are retained, with work ID as the tie-breaker. This yields eight works for each of 50 institutions, or 400 pairs in total.

The bundled universe is `data/selection-universe.csv.gz`. Its SHA-256 is:

```text
f80461d1b9e9c0ddbde2c7d35749332ae5cce06b571b0beaaaf78845543e4dd3
```

To verify the sample locally from the repository root, run:

```bash
python code/verify-selection.py
```

An exact run reports `400/400` selected-pair agreement and `50/50` institution candidate-count agreement.
