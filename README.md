**LM Studio Model Benchmark**

This script benchmarks all locally installed LM Studio models by:
- Loading each model via the `lms` CLI and timing model load.
- Generating a small website (HTML) from a fixed prompt.
- Sampling CPU/GPU power (W) using `powermetrics` (or optional `asitop_csv_logger`).
- Tracking RAM high‑water marks for the system and LM Studio processes.
- Saving the generated HTML per model and a JSON with metrics (tokens/sec, load time, etc.).

Output is written under `reports/lmstudio-bench-YYYYMMDD-HHMMSS/`.

**Requirements**
- macOS with `powermetrics` (built into macOS).
- LM Studio (0.3.6+ recommended) with local server enabled and the `lms` CLI available on PATH.
- Python 3.9+ with packages: `requests`, `psutil`.
- Optional: `asitop_csv_logger` (if you prefer that to `powermetrics`).

Install Python deps:
- `python3 -m pip install -r requirements.txt`

Enable the LM Studio CLI and server:
- In LM Studio: Settings → Developer → Enable Local Server (accept EULA).
- Ensure `lms` is on your PATH (LM Studio can install or you can symlink it).
- Verify with: `lms --version` and `lms server start`.

Permissions for power metrics:
- `powermetrics` typically requires admin privileges. The simplest way is to run the script with sudo: `sudo -E python3 bench_lmstudio_models.py`.
- If you run without sudo, the script still runs but CPU/GPU power stats may be empty.
- Optional alternative: install and use `asitop_csv_logger` and set `USE_ASITOP_CSV = True` in the script.

**Run**
- `python3 bench_lmstudio_models.py` (or `sudo -E python3 bench_lmstudio_models.py` to capture power).

The script will:
- Ensure the LM Studio server is running.
- Enumerate installed local LLMs.
- For each model: unload all, load the model (measure load time), start power + RAM sampling, call the LM Studio REST/OpenAI API once, stop samplers, save `MODEL.html`, `MODEL.json`, and a `MODEL_powermetrics.log`.

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
- Change the generation prompt by editing `PROMPT` near the top of `bench_lmstudio_models.py`.
- By default, temperature and top_p are not set (the model/server defaults are used). Set `TEMP`/`TOP_P` if you want to override.
- `MAX_TOKENS` is applied only if not `None`.
- Set `GPU_SETTING` to control `lms load --gpu` behavior (e.g., `max`, `off`, or a number).
- Set `USE_ASITOP_CSV = True` if you have `asitop_csv_logger` installed and prefer it.

**Build a Report**
- Generate an interactive HTML report from a run’s folder of JSON files:
  - `python3 build_bench_report.py lmstudio-bench-YYYYMMDD-HHMMSS --out report.html`
  - Optional: `--prompt-file prompt.txt` to embed the prompt if not present in JSONs.

The report includes:
- Sortable, filterable overview table with key metrics (load/gen time, tokens/sec, CPU/GPU/ANE power, memory deltas).
- Direct links to each model’s generated HTML, power log, and raw JSON.
- The original prompt text embedded for transparency.

After a run finishes, a consolidated report is also saved automatically to `<run-folder>/index.html` under the `reports/` directory.

**Troubleshooting**
- `Missing 'lms' CLI`: In LM Studio, enable CLI in Settings, or add the CLI to PATH.
- `Server didn’t come up`: Open LM Studio and enable Local Server (accept EULA). Ensure nothing else is bound to port 1234, or set `LMSTUDIO_API_BASE` env var.
- `Power metrics empty`: Run with sudo, or verify `powermetrics` exists (`which powermetrics`).
- `No models found`: Download models in LM Studio and ensure they’re listed by `lms ls --llm`.

**Notes**
- The script first tries the LM Studio REST API (`/api/v0/chat/completions`) to capture richer stats. If unavailable, it falls back to the OpenAI‑compatible API (`/v1/chat/completions`).
- Power sampling interval defaults to 1s; adjust `POWERMETRICS_INTERVAL_MS` in the script as needed.
- RAM tracking aggregates all processes whose `name`/`cmdline` suggests LM Studio or `lms`.
