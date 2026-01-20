#!/usr/bin/env python3
import os, re, sys, json, time, signal, shutil, threading, subprocess, hashlib
from datetime import datetime
from pathlib import Path

import requests
import psutil
try:
    import build_bench_report as report_builder
except Exception:
    report_builder = None

# --------- Config ----------
API_BASE       = os.environ.get("LMSTUDIO_API_BASE", "http://127.0.0.1:1234")
OPENAI_BASE    = f"{API_BASE}/v1"
REST_BASE      = f"{API_BASE}/api/v0"        # returns tokens/sec, TTFT, etc. (LM Studio 0.3.6+)
# Save all runs under ./reports/<timestamped-folder>
# OUT_DIR        = Path("reports") / f"lmstudio-bench-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
PROMPT         = """Create a fully functional Kanban board in a single HTML file using vanilla JavaScript (no frameworks like react).

Requirements:
- Columns: Backlog, In Progress, Review, Done.
- Cards must be:
  - draggable across columns,
  - editable in place,
  - persisted in localStorage (state survives reloads) - please use your own namespace,
  - deletable with a confirmation prompt.
- Each column provides an “Add card” action.
- Style with Tailwind via CDN.
- Add subtle CSS transitions and trigger a confetti animation when a card moves to “Done”.
- Thoroughly comment the code.
- dont use window.alert or window.prompt to add/edit/delete cards
- if there are no cards yet, create some dummy cards
- modern and vibrant design

As answer return the plain HTML of the working application (script and styles included)
"""
MAX_TOKENS     = -1                 # set to None to omit and use server default
TEMP           = .6               # None = use model/server default
TOP_P          = .95               # None = use model/server default
NUM_CTX        = 16384              # context length in tokens; set None to omit
REASONING_EFFORT = 'medium'            # 'low' | 'medium' | 'high' (None = omit)
GPU_SETTING    = "max"                       # lms load --gpu max
USE_ASITOP_CSV = False                       # set True if you installed asitop-csv-logger and want to use it
POWERMETRICS_INTERVAL_MS = 1000              # sample every 1s
GEN_TIMEOUT_SECONDS = 300                    # interrupt generation after ~3m20s
GEN_TIMER_INTERVAL_SECONDS = 2               # print timer update every 2s
# ---------------------------

def get_out_dir():
    # Create a hash of the settings
    settings_str = f"{PROMPT}{MAX_TOKENS}{TEMP}{TOP_P}{NUM_CTX}{REASONING_EFFORT}{GPU_SETTING}"
    settings_hash = hashlib.sha256(settings_str.encode('utf-8')).hexdigest()[:10]
    return Path("reports") / f"lmstudio-bench-{settings_hash}"

OUT_DIR = get_out_dir()
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run(cmd, check=True, capture_output=True, text=True):
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)

def assert_cli_tools():
    if not shutil.which("lms"):
        raise RuntimeError(
            "Missing 'lms' CLI. In LM Studio, enable CLI in Settings or add it to PATH."
        )
    if not shutil.which("powermetrics"):
        print("Warning: 'powermetrics' not found; power metrics will be unavailable.", file=sys.stderr)
    if os.name == "posix" and sys.platform == "darwin" and os.geteuid() != 0:
        # Not fatal, but likely required
        print("Note: running without sudo; powermetrics may lack permission.", file=sys.stderr)

def ensure_server():
    # start the local API server if not already running
    try:
        run(["lms", "server", "status"])
    except Exception:
        pass
    try:
        run(["lms", "server", "start"])
    except subprocess.CalledProcessError as e:
        # if it's already running, lms might non-zero; we’ll probe HTTP below
        pass
    # wait for REST to respond
    for _ in range(60):
        try:
            r = requests.get(f"{REST_BASE}/models", timeout=1.5)
            if r.ok:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("LM Studio server didn't come up at http://127.0.0.1:1234")

def list_models():
    # Gather all model variants from lms ls --llm --json
    # Each variant (e.g. @4bit, @8bit) is treated as a separate model to benchmark
    # Note: lms CLI doesn't support @variant syntax, but REST API does (JIT loading)
    results = []
    try:
        ls = run(["lms", "ls", "--llm", "--json"]).stdout
        arr = json.loads(ls)
        for m in arr or []:
            if not m:
                continue
            model_key = m.get("modelKey")
            if not model_key:
                continue

            variants = m.get("variants", [])
            display_name = m.get("displayName") or model_key

            if variants:
                # Add each variant as a separate model entry
                for variant in variants:
                    # Extract quantization suffix for display (e.g. "@4bit" -> "4bit")
                    quant_suffix = variant.split("@")[-1] if "@" in variant else ""
                    variant_display = f"{display_name} ({quant_suffix})" if quant_suffix else display_name
                    results.append({
                        "api_id": variant,         # Used for API calls (supports @variant)
                        "cli_key": model_key,      # Used for lms load (no @variant!)
                        "display": variant_display,
                    })
            else:
                # No variants array - use modelKey directly
                results.append({
                    "api_id": model_key,
                    "cli_key": model_key,
                    "display": display_name,
                })
    except Exception:
        pass

    return results

def unload_all():
    try:
        run(["lms", "unload", "--all"])
    except subprocess.CalledProcessError:
        pass

def load_model_cli(model_id):
    """Load model using lms CLI (does not support @variant syntax)."""
    t0 = time.perf_counter()
    cmd = ["lms", "load", model_id, "--gpu", GPU_SETTING]
    if NUM_CTX is not None:
        cmd.extend(["--context-length", str(NUM_CTX)])
    cmd.append("-y")
    run(cmd)
    return time.perf_counter() - t0

def load_model_jit(model_id, timeout_s=120):
    """Load model using REST API JIT loading (supports @variant syntax)."""
    t0 = time.perf_counter()
    # Make a minimal chat request to trigger JIT loading
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    if NUM_CTX is not None:
        payload["num_ctx"] = NUM_CTX
    r = requests.post(f"{REST_BASE}/chat/completions", json=payload, timeout=(5, timeout_s))
    r.raise_for_status()
    return time.perf_counter() - t0

def load_with_fallbacks(api_id: str, cli_key: str):
    """Load model, using JIT for variants with @ or CLI otherwise.
    Returns (used_key, load_time_seconds). Raises on failure.
    """
    # If api_id contains @, we need JIT loading (CLI doesn't support @variant)
    if "@" in api_id:
        t = load_model_jit(api_id)
        return api_id, t

    # Otherwise use CLI
    try:
        t = load_model_cli(cli_key)
        return cli_key, t
    except Exception as e:
        # Fallback to JIT if CLI fails
        try:
            t = load_model_jit(api_id)
            return api_id, t
        except Exception:
            pass
        raise e

ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

class PowerSampler:
    def __init__(self, out_path, sampler_combo=None, interval_ms=1000):
        self.out_path = out_path
        self.proc = None
        self.stop_evt = threading.Event()
        self.sampler_combo = sampler_combo
        self.interval_ms = interval_ms

    def start(self):
        if USE_ASITOP_CSV and shutil.which("asitop_csv_logger"):
            # Optional: CSV-logging fork of asitop
            # Will write CSV on its own; we redirect stdout too.
            cmd = ["asitop_csv_logger", "--interval", "1"]
        else:
            # Robust default: use powermetrics directly (needs sudo)
            # We don't set -n; we kill it after generation ends.
            sampler = self.sampler_combo or "all"
            cmd = ["powermetrics", "--samplers", sampler, "-i", str(self.interval_ms)]
            if os.name == "posix" and sys.platform == "darwin" and os.geteuid() != 0:
                print("Warning: powermetrics likely needs sudo; power stats may be empty.", file=sys.stderr)
        self.proc = subprocess.Popen(
            cmd, stdout=open(self.out_path, "w"), stderr=subprocess.STDOUT, text=True
        )

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except Exception:
                pass

def parse_powermetrics_log(path):
    # Extract CPU/GPU/ANE power numbers (W) from powermetrics dumps.
    cpu_watts, gpu_watts, ane_watts = [], [], []
    current_section = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            s = ansi_escape.sub("", line.strip())
            # Track current section if lines start with CPU/GPU/ANE
            msec = re.match(r"^(CPU|GPU|ANE)\b", s, re.I)
            if msec:
                current_section = msec.group(1).upper()
            # Direct power lines e.g., "CPU Power: 12.3 W" or "GPU Power: 800 mW"
            for label, arr in (("CPU", cpu_watts), ("GPU", gpu_watts), ("ANE", ane_watts)):
                m = re.search(fr"{label}.*?Power:\s*([\d.]+)\s*(m?W)", s, re.I)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2).lower()
                    arr.append(val / 1000.0 if unit == "mw" else val)
            # Average power lines within a section e.g., "Average power: 850 mW"
            m2 = re.search(r"Average power:\s*([\d.]+)\s*(m?W)", s, re.I)
            if m2 and current_section:
                val = float(m2.group(1))
                unit = m2.group(2).lower()
                watts = val / 1000.0 if unit == "mw" else val
                if current_section == "CPU":
                    cpu_watts.append(watts)
                elif current_section == "GPU":
                    gpu_watts.append(watts)
                elif current_section == "ANE":
                    ane_watts.append(watts)
    def stats(arr):
        return {
            "avg": (sum(arr)/len(arr)) if arr else None,
            "max": max(arr) if arr else None,
            "min": min(arr) if arr else None,
            "samples": len(arr),
        }
    return {"cpu_watts": stats(cpu_watts), "gpu_watts": stats(gpu_watts), "ane_watts": stats(ane_watts)}

def detect_powermetrics_samplers(samples=3, interval_ms=500):
    combos = [
        "cpu_power,gpu_power,ane_power",
        "cpu_power,gpu_power",
        "cpu_energy,gpu_energy",
        "cpu_power",
        "gpu_power",
        "all",
    ]
    last_err = None
    for combo in combos:
        cmd = ["powermetrics", "--samplers", combo, "-n", str(samples), "-i", str(interval_ms)]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if res.stdout.strip():
                return combo
        except subprocess.CalledProcessError as e:
            last_err = e
    if last_err:
        print("powermetrics detection failed:", last_err, file=sys.stderr)
    return None

def sample_ram_hwm(stop_evt, interval=1.0):
    # Track system used memory and LM Studio process RSS HWM while generating
    sys_hwm = 0
    lmstudio_hwm = 0
    while not stop_evt.is_set():
        vm = psutil.virtual_memory()
        sys_used = vm.total - vm.available
        sys_hwm = max(sys_hwm, sys_used)
        rss_sum = 0
        for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
            name = (p.info.get("name") or "").lower()
            cmd  = " ".join(p.info.get("cmdline") or []).lower()
            if "lm studio" in name or "lmstudio" in cmd or "lms " in cmd:
                try:
                    rss_sum += p.info["memory_info"].rss
                except Exception:
                    pass
        lmstudio_hwm = max(lmstudio_hwm, rss_sum)
        time.sleep(interval)
    return sys_hwm, lmstudio_hwm

def snapshot_memory():
    vm = psutil.virtual_memory()
    sys_used = vm.total - vm.available
    rss_sum = 0
    for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
        name = (p.info.get("name") or "").lower()
        cmd  = " ".join(p.info.get("cmdline") or []).lower()
        if "lm studio" in name or "lmstudio" in cmd or "lms " in cmd:
            try:
                rss_sum += p.info["memory_info"].rss
            except Exception:
                pass
    return {"system_used_bytes": sys_used, "lmstudio_rss_bytes": rss_sum}

def extract_html(text):
    # Strip chain-of-thought blocks like <think> ... </think>
    # Do not extract HTML from inside these reasoning blocks
    sanitized = re.sub(r"(?is)<think[\s\S]*?</think>", "", text)
    # Prefer explicit HTML tags
    m = re.search(r"(<html[\s\S]*?</html>)", sanitized, re.I)
    if m:
        return m.group(1)
    # Try fenced code blocks ```html ... ```
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", sanitized, re.I)
    if m:
        block = m.group(1).strip()
        if "<html" in block.lower():
            return block
    # Fallback: wrap content (also using sanitized text)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Output</title></head><body><pre>{json.dumps(sanitized)[:20000]}</pre></body></html>"

def chat_once(model_id, timeout_s=GEN_TIMEOUT_SECONDS):
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a careful front-end engineer."},
            {"role": "user", "content": PROMPT}
        ],
        "stream": False
    }
    if TEMP is not None:
        payload["temperature"] = TEMP
    if TOP_P is not None:
        payload["top_p"] = TOP_P
    if MAX_TOKENS is not None:
        payload["max_tokens"] = MAX_TOKENS
    if REASONING_EFFORT is not None:
        # Add both forms for compatibility with different OpenAI-compatible servers
        payload["reasoning"] = {"effort": REASONING_EFFORT}
        payload["reasoning_effort"] = REASONING_EFFORT
    if NUM_CTX is not None:
        payload["num_ctx"] = NUM_CTX
    # Prefer REST API for rich stats; only fallback to OpenAI API if REST endpoint is unavailable
    try:
        r = requests.post(f"{REST_BASE}/chat/completions", json=payload, timeout=(5, timeout_s))
        if r.ok:
            return r.json()
        # Fallback only if endpoint clearly not found
        if r.status_code == 404:
            raise requests.exceptions.ConnectionError("REST chat endpoint not available (404)")
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        # Do not retry on a timeout — respect the configured limit
        raise
    except (requests.exceptions.ConnectionError, requests.exceptions.InvalidURL):
        # Try OpenAI-compatible endpoint as a true fallback
        r2 = requests.post(f"{OPENAI_BASE}/chat/completions", json=payload, timeout=(5, timeout_s))
        r2.raise_for_status()
        return r2.json()

def main():
    assert_cli_tools()
    ensure_server()
    sampler_combo = None
    if shutil.which("powermetrics"):
        sampler_combo = detect_powermetrics_samplers(samples=3, interval_ms=500)
        if sampler_combo:
            print(f"Using powermetrics samplers: {sampler_combo}")
        else:
            print("Falling back to powermetrics default samplers; stats may be limited.", file=sys.stderr)
    models = list_models()
    if not models:
        print("No local LLMs found. Download models in LM Studio first.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(models)} models: {[m['display'] for m in models]}")
    for entry in models:
        model_api_id = entry["api_id"]
        model_cli_key = entry["cli_key"]
        print(f"\n=== Benchmarking {model_api_id} (load: {model_cli_key}) ===", flush=True)
        
        # Make safe filenames (model ids may contain slashes or spaces)
        safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(model_api_id))[:200]
        json_path = OUT_DIR / f"{safe_model}.json"
        
        # if there are already model run data for the current model in that folder: skip the benchmark and move to the next model
        if json_path.exists():
            print(f"Skipping {model_api_id} as results already exist.")
            continue

        unload_all()

        # Memory baseline
        mem_baseline = snapshot_memory()

        # Load model and time it
        load_time_s = None
        load_error = None
        used_load_key = model_cli_key
        try:
            used_load_key, load_time_s = load_with_fallbacks(model_api_id, model_cli_key)
            print(f"Loaded via '{used_load_key}' in {load_time_s:.2f}s")
        except Exception as e:
            load_error = f"load_failed: {type(e).__name__}: {e}"
            print(f"Load failed for {model_api_id}: {e}", file=sys.stderr)

        mem_after_load = snapshot_memory()

        # Make safe filenames (model ids may contain slashes or spaces)
        safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(model_api_id))[:200]

        # Start power logging + RAM sampler
        log_path = OUT_DIR / f"{safe_model}_powermetrics.log"
        psamp = PowerSampler(str(log_path), sampler_combo=sampler_combo, interval_ms=POWERMETRICS_INTERVAL_MS)
        psamp.start()
        ram_stop_evt = threading.Event()
        ram_results = {}
        def _ram_thread():
            hwm_sys, hwm_lms = sample_ram_hwm(ram_stop_evt, interval=1.0)
            ram_results["system_used_hwm_bytes"] = hwm_sys
            ram_results["lmstudio_rss_hwm_bytes"] = hwm_lms
        t = threading.Thread(target=_ram_thread, daemon=True)
        t.start()

        # Generate once (only if load succeeded)
        result = None
        gen_time_s = None
        gen_error = None
        if load_error is None:
            gen_t0 = time.perf_counter()
            # Start a small timer printer thread
            timer_stop_evt = threading.Event()
            def _timer():
                while not timer_stop_evt.is_set():
                    elapsed = int(time.perf_counter() - gen_t0)
                    print(f"\rGenerating... {elapsed}s", end="", flush=True)
                    time.sleep(GEN_TIMER_INTERVAL_SECONDS)
            timer_thread = threading.Thread(target=_timer, daemon=True)
            timer_thread.start()
            try:
                result = chat_once(model_api_id, timeout_s=GEN_TIMEOUT_SECONDS)
                gen_time_s = time.perf_counter() - gen_t0
            except Exception as e:
                gen_error = f"generation_failed: {type(e).__name__}: {e}"
                print(f"\nGeneration failed for {model_api_id}: {e}", file=sys.stderr)
            finally:
                # stop timer and print newline
                timer_stop_evt.set()
                timer_thread.join(timeout=1)
                print("", flush=True)
                # stop samplers
                ram_stop_evt.set()
                t.join(timeout=3)
                psamp.stop()
        else:
            # stop samplers if we didn't attempt generation
            ram_stop_evt.set()
            t.join(timeout=3)
            psamp.stop()

        # Parse powermetrics
        power_stats = parse_powermetrics_log(str(log_path))
        if isinstance(power_stats, dict) and sampler_combo:
            power_stats["samplers"] = sampler_combo

        # Memory after generation (before unload)
        mem_after_generation = snapshot_memory()

        # Extract HTML and save raw text if available
        html_path = None
        raw_text_path = None
        if result and not gen_error:
            try:
                text = result["choices"][0]["message"]["content"]
            except Exception:
                text = json.dumps(result)
            # Save raw text response
            raw_text_path = OUT_DIR / f"{safe_model}.txt"
            try:
                raw_text_path.write_text(text)
            except Exception:
                raw_text_path = None
            html = extract_html(text)
            html_path = OUT_DIR / f"{safe_model}.html"
            html_path.write_text(html)

        # Build metrics JSON
        usage = (result.get("usage", {}) if result else {}) or {}
        # Fallback tokens/sec if REST stats absent
        completion_tokens = usage.get("completion_tokens") or usage.get("completion_tokens", 0)
        tokens_per_sec_fallback = None
        try:
            if gen_time_s > 0 and completion_tokens:
                tokens_per_sec_fallback = completion_tokens / gen_time_s
        except Exception:
            pass
        metrics = {
            "model": model_api_id,
            "timestamp": datetime.now().isoformat(),
            "load_time_seconds": load_time_s,
            "generation_time_seconds": gen_time_s,
            "rest_stats": (result.get("stats", {}) if result else {}),
            "usage": usage,
            "model_info": (result.get("model_info", {}) if result else {}),
            "runtime": (result.get("runtime", {}) if result else {}),
            "power": power_stats,
            "memory": {
                "baseline": mem_baseline,
                "after_load": mem_after_load,
                "after_generation": mem_after_generation,
                "delta_since_baseline_after_load": {
                    "system_used_bytes": (mem_after_load["system_used_bytes"] - mem_baseline["system_used_bytes"]),
                    "lmstudio_rss_bytes": (mem_after_load["lmstudio_rss_bytes"] - mem_baseline["lmstudio_rss_bytes"]),
                },
                "delta_since_baseline_after_generation": {
                    "system_used_bytes": (mem_after_generation["system_used_bytes"] - mem_baseline["system_used_bytes"]),
                    "lmstudio_rss_bytes": (mem_after_generation["lmstudio_rss_bytes"] - mem_baseline["lmstudio_rss_bytes"]),
                },
                "delta_since_load_after_generation": {
                    "system_used_bytes": (mem_after_generation["system_used_bytes"] - mem_after_load["system_used_bytes"]),
                    "lmstudio_rss_bytes": (mem_after_generation["lmstudio_rss_bytes"] - mem_after_load["lmstudio_rss_bytes"]),
                },
                "hwm_during_generation": ram_results,
            },
            "derived": {
                "tokens_per_second_fallback": tokens_per_sec_fallback
            },
            "files": {
                "html": (str(html_path.resolve()) if html_path else None),
                "raw_text": (str(raw_text_path.resolve()) if raw_text_path else None),
                "powermetrics_log": str(log_path.resolve())
            },
            "prompt": {
                "temperature": TEMP,
                "top_p": TOP_P,
                "max_tokens": MAX_TOKENS,
                "num_ctx": NUM_CTX,
                "text": PROMPT,
                "gpu_setting": GPU_SETTING,
                "reasoning_effort": REASONING_EFFORT,
            },
            "load_key_used": used_load_key if load_time_s is not None else None,
            "errors": {
                "load": load_error,
                "generation": gen_error,
            }
        }
        json_path = OUT_DIR / f"{safe_model}.json"
        json_path.write_text(json.dumps(metrics, indent=2))
        saved_html = html_path.name if html_path else "<no-html>"
        print(f"Saved: {saved_html}, {json_path.name}")

        # Ensure model is unloaded after usage
        try:
            unload_all()
        except Exception:
            pass

        # Incremental report update after each model
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            report_path = OUT_DIR / "index.html"
            if report_builder is not None:
                rows = report_builder.load_results(OUT_DIR)
                html = report_builder.build_html(rows, title="LM Studio Bench Report", prompt_text=PROMPT, out_path=report_path)
                report_path.write_text(html)
                print(f"Updated report: {report_path.resolve()}")
            else:
                try:
                    run([sys.executable, str(Path(__file__).parent / 'build_bench_report.py'), str(OUT_DIR), '--out', str(report_path)])
                    print(f"Updated report: {report_path.resolve()}")
                except Exception as e:
                    print(f"Report generation failed: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Report generation error: {e}", file=sys.stderr)

    # Build an index.html report at the end
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = OUT_DIR / "index.html"
        if report_builder is not None:
            rows = report_builder.load_results(OUT_DIR)
            html = report_builder.build_html(rows, title="LM Studio Bench Report", prompt_text=PROMPT, out_path=report_path)
            report_path.write_text(html)
            print(f"\nReport written to: {report_path.resolve()}")
        else:
            # Fallback: shell out to the script if import failed
            try:
                run([sys.executable, str(Path(__file__).parent / 'build_bench_report.py'), str(OUT_DIR), '--out', str(report_path)])
                print(f"\nReport written to: {report_path.resolve()}")
            except Exception as e:
                print(f"\nReport generation failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nReport generation error: {e}", file=sys.stderr)

    print(f"All done. Output in: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
