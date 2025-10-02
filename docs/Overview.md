# Benchmark Overview

This repository provides repeatable benchmarks for local and API-based LLMs.

**What it does**
- **Local (LM Studio):** Iterates through installed models, measuring load time, generation speed, power, and memory.
- **Remote (OpenRouter):** Queries API-based models, measuring generation speed and cost.
- Both workflows extract HTML from responses, save artifacts, and generate detailed JSON metrics.
- A final script builds a self-contained, interactive HTML report from the collected data.

**Key Components**
- `bench_lmstudio_models.py`: Orchestrates local model benchmarking.
- `bench_openrouter_models.py`: Orchestrates API model benchmarking.
- `build_bench_report.py`: Aggregates JSON data from any run into a shareable HTML report.
- `test_power_monitor.py`: A simple utility to verify power sampling on macOS.

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

