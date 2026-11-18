# University research output indicators

Data and code for “Bibliographic corrections and university research output indicators: Institutional consequences and validation requirements.”

**[Run Quick and Core in Google Colab](https://colab.research.google.com/github/evidenceworks/university-portfolio-validity/blob/main/notebooks/reproduce.ipynb)**

Open the notebook and select **Runtime → Run all**. It retrieves the public repository automatically, verifies the inputs and reproduces both sets of results. No file upload is needed.

The study examines 400 audited institution–work pairs and 2,000 additional pairs sampled from 50 US universities. The pilot-conditioned estimate is 65,785 additional institutional credits (approximate 95% interval: 48,753–82,817). This is an indicator change, not a count of newly confirmed eligible publications. In the historical sample, the grouped-count comparison requires at least 41 additional eligible findings, including 32 on unchanged decisions.

`data/` contains the fixed inputs and source provenance; `code/` contains the calculations. `checksums.sha256` verifies the 17 data, code and dependency files. Core writes the reproduced numerical tables to `results/` within the Colab runtime.

Code is licensed under MIT; authored documentation and results under CC BY 4.0. Source rights and attribution are described in `LICENSE`.
