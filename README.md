**Model Benchmark for LM Studio and OpenRouter**

This project provides scripts to benchmark LLMs from two sources:
1.  **Local models** via LM Studio.
2.  **API-based models** via OpenRouter.

Key features:
- **LM Studio:** Loads each model, times the load, generates a small website, and measures power/memory usage.
- **OpenRouter:** Queries specified models, records generation time, tokens/sec, and cost.
- Both produce detailed JSON metrics and save generated artifacts.

Output is written to a timestamped folder, e.g., `reports/lmstudio-bench-YYYYMMDD-HHMMSS/`.

**Requirements**
- **General:** Python 3.9+ (`python3 -m pip install -r requirements.txt`).
- **LM Studio Benchmarking:**
  - macOS with `powermetrics` (built-in).
  - LM Studio (0.3.6+ recommended) with the `lms` CLI installed and local server enabled.
  - Sudo access for power sampling (`sudo -E python3 ...`).
- **OpenRouter Benchmarking:**
  - An OpenRouter API key. Set it as an environment variable: `export OPENROUTER_API_KEY="your-key-here"`.

Permissions for power metrics:
- `powermetrics` typically requires admin privileges. The simplest way is to run the script with sudo: `sudo -E python3 bench_lmstudio_models.py`.
- If you run without sudo, the script still runs but CPU/GPU power stats may be empty.
- Optional alternative: install and use `asitop_csv_logger` and set `USE_ASITOP_CSV = True` in the script.

**Run Benchmarks**

**1. LM Studio (Local Models)**
- Run with `sudo` to capture power metrics:
  - `sudo -E python3 bench_lmstudio_models.py`
- The script enumerates all local models, loads each one, measures performance, and saves artifacts.

**2. OpenRouter (API Models)**
- Create a text file (e.g., `models.txt`) with a list of model names, one per line.
- Run the script, optionally adjusting concurrency:
  - `python3 bench_openrouter_models.py --models_file openrouter_models.txt --concurrency 8`
- It queries models in parallel (default: 4), recording performance and cost.

**What gets recorded**
- `MODEL.html`: Extracted HTML from the model’s response. If not detected, the full text is wrapped into a minimal HTML container.
- `MODEL.json`:
  - `load_time_seconds`: Measured model load time via `lms load`.
  - `generation_time_seconds`: Wall time to complete the chat request.
  - `rest_stats`: Raw stats from LM Studio REST (if available), e.g., tokens/sec, TTFT.
  - `usage`: Token usage if provided by the API.
  - `derived.tokens_per_second_fallback`: completion_tokens / generation_time_seconds fallback.
  - `power`: Aggregated CPU/GPU watts (avg/min/max) parsed from `powermetrics` output.
  - `memory`: High‑water marks during generation and snapshots at baseline/after-load/after-generation with deltas.
  - `files`: Paths to artifacts.
  - `prompt`: Includes temperature, top_p, max_tokens, gpu_setting, and the exact prompt text used.

**Customizing**
- **Prompts:** Edit the `PROMPT` variable in `bench_lmstudio_models.py` or `bench_openrouter_models.py`.
- **Parameters:** Adjust `TEMP`, `TOP_P`, `MAX_TOKENS`, etc., at the top of each script.
- **LM Studio:** `GPU_SETTING` controls GPU offload (`max`, `off`). `USE_ASITOP_CSV` offers an alternative to `powermetrics`.

**Build a Report**
- Generate an interactive HTML report from any run folder:
  - `python3 build_bench_report.py reports/lmstudio-bench-YYYYMMDD-HHMMSS --out report.html`
  - `python3 build_bench_report.py reports/openrouter-bench-YYYYMMDD-HHMMSS --out report.html`

The report includes:
- Sortable, filterable overview table with key metrics (load/gen time, tokens/sec, CPU/GPU/ANE power, memory deltas).
- Direct links to each model’s generated HTML, power log, and raw JSON.
- The original prompt text embedded for transparency.

After a run finishes, a consolidated report is also saved automatically to `<run-folder>/index.html` under the `reports/` directory.

**Documentation**
- docs/Overview.md — high‑level description and architecture.
- docs/Benchmarking.md — benchmark flow, configuration, timeouts, memory/power details, chain‑of‑thought handling.
- docs/Reporting.md — report structure, columns, charts, and standalone usage.
- CHANGELOG.md — notable changes.

**Troubleshooting**
- `Missing 'lms' CLI`: In LM Studio, enable CLI in Settings, or add the CLI to PATH.
- `Server didn’t come up`: Open LM Studio and enable Local Server (accept EULA). Ensure nothing else is bound to port 1234, or set `LMSTUDIO_API_BASE` env var.
- `Power metrics empty`: Run with sudo, or verify `powermetrics` exists (`which powermetrics`).
- `No models found`: Download models in LM Studio and ensure they’re listed by `lms ls --llm`.

**Notes**
- The script first tries the LM Studio REST API (`/api/v0/chat/completions`) to capture richer stats. If unavailable, it falls back to the OpenAI‑compatible API (`/v1/chat/completions`).
- Power sampling interval defaults to 1s; adjust `POWERMETRICS_INTERVAL_MS` in the script as needed.
- RAM tracking aggregates all processes whose `name`/`cmdline` suggests LM Studio or `lms`.



update docs report: python3 build_bench_report.py docs/openrouter-bench-3df72d1ae3 --out docs/openrouter-bench-3df72d1ae3/index.html