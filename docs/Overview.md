# LM Studio Benchmark — Overview

This repository provides a repeatable way to benchmark local, open‑weight LLMs with LM Studio.

What it does
- Iterates through all installed LLMs in LM Studio and benchmarks each one.
- Measures: model load time, generation time, tokens/sec, RAM deltas, CPU/GPU/ANE power.
- Extracts HTML from the response (ignores chain‑of‑thought `<think>…</think>` blocks) and saves artifacts.
- Writes a per‑model JSON with metrics and metadata.
- Builds a self‑contained, interactive HTML report with sortable/filterable tables and charts.

Key components
- `bench_lmstudio_models.py` — main orchestrator for loading, generating, sampling, and saving.
- `build_bench_report.py` — aggregates per‑model JSON data and produces a shareable report.
- `test_power_monitor.py` — minimal standalone power sampling verifier for macOS.

Highlights
- Robust model loading: maps REST API model IDs to the proper CLI load keys with sensible fallbacks.
- Power sampling: uses `powermetrics` with dynamic sampler detection; parses W/mW formats.
- RAM tracking: high‑water mark sampler during generation plus deltas at baseline → after‑load → after‑generation.
- Reasoning: can optionally pass `reasoning_effort` to reasoning‑capable models.
- Context length: can set `num_ctx` to control context window (e.g., 16k).
- Reports: links to model HTML/JSON/TXT and includes TPS vs GPU W scatter and generation time bars.

Limitations & notes
- macOS specific for power metrics (relies on `powermetrics`). Run with `sudo` for full access.
- Not all models/server versions return the same stats fields; tokens/sec may fall back to a derived value.
- Timeout is enforced per request; no retries on timeouts to avoid extended runs.

