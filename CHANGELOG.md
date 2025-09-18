# Changelog

All notable changes to this project are documented here.

2025-09-12
- Add robust powermetrics sampler detection and parsing (CPU/GPU/ANE, W/mW).
- Add RAM baseline/after‑load/after‑generation snapshots + HWMs.
- Add per‑model artifacts: `.html`, `.txt`, `.json`, powermetrics log.
- Add chain‑of‑thought filtering: strip `<think>…</think>` when extracting HTML.
- Enforce 200s generation timeout with live timer and no retry on timeout.
- Improve model loading mapping (API id → CLI key) with fallbacks.
- Move runs under `reports/lmstudio-bench-…/` and auto‑build `index.html`.
- Report: sortable/filterable table, column toggles, machine info, prompt section.
- Report: charts (TPS vs GPU avg W; generation time bars), artifacts links (HTML/Text/JSON).
- Optional settings: `REASONING_EFFORT` and `NUM_CTX` (context length).

