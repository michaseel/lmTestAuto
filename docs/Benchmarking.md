# Benchmarking Details

This document explains how the benchmark script works and how to tune it.

Entry point
- `bench_lmstudio_models.py`
- Output folder per run: `reports/lmstudio-bench-YYYYMMDD-HHMMSS/`

Workflow per model
1. Unload any loaded models (`lms unload --all`).
2. Snapshot memory baseline (system used, LM Studio RSS aggregate).
3. Load the model and time it.
   - Uses CLI key mapping and fallbacks to handle names like `lmstudio-community/ERNIE-4.5-21B-A3B-MLX-8bit`.
4. Start samplers:
   - Power sampling via `powermetrics` (auto‑detects samplers; warns if no sudo).
   - RAM high‑water mark sampler.
5. Generate once via LM Studio REST/OpenAI API.
   - Live timer outputs every 2s.
   - Per‑request timeout (default 200s). No fallback on timeout (to respect your limit).
   - Removes `<think>…</think>` before extracting HTML.
6. Stop samplers and parse results:
   - Power: CPU/GPU/ANE avg/min/max (W), sampler combo used.
   - Memory: baseline/after‑load/after‑generation with deltas; HWMs during generation.
7. Save artifacts and metrics:
   - `<model>.html` (extracted website)
   - `<model>.txt` (raw LLM output)
   - `<model>_powermetrics.log`
   - `<model>.json` (metrics + metadata)
8. Unload the model again.
9. Update the report (`index.html`) incrementally after each model.

Key configuration
- `GEN_TIMEOUT_SECONDS`: max time for a single generation request (default 200s).
- `POWERMETRICS_INTERVAL_MS`: sampling interval for power metrics (default 1000ms).
- `GPU_SETTING`: offload behavior for `lms load` (e.g., `max`).
- `NUM_CTX`: context length (tokens), e.g., `16384` for 16k.
- `REASONING_EFFORT`: `'low' | 'medium' | 'high'` to hint reasoning effort for supported models.
- `TEMP`, `TOP_P`, `MAX_TOKENS`: are only sent if not `None` (defaults to server/model settings).

Model key mapping
- REST API ids (used for generation) often differ from CLI load keys.
- The script builds a map from `lms ls --llm --json`, then tries multiple candidates:
  - Reported CLI key
  - API id
  - `@` replaced with `-`
  - Uppercased base
  - `lmstudio-community/<key>` variants

Chain‑of‑thought filtering
- The script removes `<think>…</think>` blocks before extracting HTML so only the final answer is rendered.
- The raw `.txt` still contains the full output for auditing.

Timeout semantics
- Requests use `(connect=5s, read=GEN_TIMEOUT_SECONDS)`.
- On timeout, the error is recorded and there is no retry to a second endpoint.
- Fallback to the OpenAI‑compatible endpoint happens only on 404/connection errors.

