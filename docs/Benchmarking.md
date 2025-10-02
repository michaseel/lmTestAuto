# Benchmarking Details

This document explains how the benchmark scripts work and how to tune them.

## 1. LM Studio (`bench_lmstudio_models.py`)

This script benchmarks local models running via LM Studio.

- **Entry point**: `bench_lmstudio_models.py`
- **Output**: `reports/lmstudio-bench-YYYYMMDD-HHMMSS/`

**Workflow per Model**
1.  **Unload**: Clears any loaded models (`lms unload --all`).
2.  **Memory Baseline**: Snapshots system and LM Studio memory usage.
3.  **Load**: Loads the target model and times the operation. It uses smart key mapping to find the model.
4.  **Start Samplers**:
    -   **Power**: `powermetrics` for CPU/GPU/ANE power (requires `sudo`).
    -   **Memory**: High-water mark sampler for RAM usage during generation.
5.  **Generate**: Calls the LM Studio API to generate a response.
    -   A live timer and a per-request timeout are active.
    -   It removes `<think>…</think>` blocks before extracting HTML.
6.  **Stop Samplers & Parse**: Gathers and processes power and memory data.
7.  **Save Artifacts**:
    -   `<model>.html`: The generated website.
    -   `<model>.txt`: Raw LLM output.
    -   `<model>_powermetrics.log`: Raw power data.
    -   `<model>.json`: Metrics and metadata.
8.  **Unload**: Frees the model.
9.  **Incremental Report**: Updates `index.html` after each model is benchmarked.

**Key Configuration**
-   `GEN_TIMEOUT_SECONDS`: Max time for a generation request (default: 200s).
-   `POWERMETRICS_INTERVAL_MS`: Power sampling frequency (default: 1000ms).
-   `GPU_SETTING`: GPU offload setting for `lms load` (e.g., `max`).
-   `NUM_CTX`: Context length (e.g., `16384`).
-   `REASONING_EFFORT`: Hints `'low' | 'medium' | 'high'` effort to the model.
-   `TEMP`, `TOP_P`, `MAX_TOKENS`: Sent only if not `None`, otherwise server defaults are used.

**Model Key Mapping**
- The script intelligently maps the model ID used in the REST API to the key required by the `lms` CLI for loading. It attempts several variations to ensure the correct model is loaded.

**Chain-of-Thought Filtering**
- The script removes `<think>…</think>` blocks from the LLM’s output before extracting HTML. This ensures only the final, rendered result is saved in the `.html` file, while the full, raw output (including reasoning) is preserved in the `.txt` file for auditing.

**Timeout Semantics**
- Generation requests use a connect timeout of 5 seconds and a read timeout of `GEN_TIMEOUT_SECONDS`.
- If a timeout occurs, the error is logged, and the script moves to the next model without a retry.

---

## 2. OpenRouter (`bench_openrouter_models.py`)

This script benchmarks API-based models via OpenRouter.

- **Entry point**: `bench_openrouter_models.py <models_file.txt>`
- **Output**: `reports/openrouter-bench-YYYYMMDD-HHMMSS/`
- **Requires**: `OPENROUTER_API_KEY` environment variable.

**Workflow**
The script processes models concurrently using a thread pool.

1.  **Read Models**: Loads a list of model names from the input text file.
2.  **Concurrent Generation**: For each model, a thread is spawned to call the OpenRouter API.
    -   The number of concurrent requests is controlled by the `--concurrency` flag (default: 4).
    -   A live timer and per-request timeout are active for each request.
    -   It removes `<think>…</think>` blocks before extracting HTML.
3.  **Save Artifacts**: Once a model's generation is complete, its artifacts are saved:
    -   `<model>.html`: The generated website.
    -   `<model>.txt`: Raw LLM output.
    -   `<model>.json`: Metrics and metadata, including cost.
4.  **Incremental Report**: The `index.html` report is updated in a thread-safe manner after each model finishes.

**Key Configuration**
-   `--concurrency`: Number of models to benchmark in parallel (default: 4).
-   `GEN_TIMEOUT_SECONDS`: Max time for a single generation request (default: 300s).
-   `TEMP`, `TOP_P`, `MAX_TOKENS`: Sent only if not `None`, otherwise API defaults are used.

