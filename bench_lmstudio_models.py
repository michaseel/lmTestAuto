#!/usr/bin/env python3
import os, re, sys, json, time, signal, shutil, threading, subprocess
from datetime import datetime
from pathlib import Path

import requests
import psutil

# --------- Config ----------
API_BASE       = os.environ.get("LMSTUDIO_API_BASE", "http://127.0.0.1:1234")
OPENAI_BASE    = f"{API_BASE}/v1"
REST_BASE      = f"{API_BASE}/api/v0"        # returns tokens/sec, TTFT, etc. (LM Studio 0.3.6+)
OUT_DIR        = Path(f"lmstudio-bench-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
PROMPT         = """Create a fully functional Kanban board in a single HTML file using vanilla JavaScript (no frameworks).

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
- modern and vibrant design"""
MAX_TOKENS     = -1
TEMP           = 0.2
TOP_P          = 0.95
GPU_SETTING    = "max"                       # lms load --gpu max
USE_ASITOP_CSV = False                       # set True if you installed asitop-csv-logger and want to use it
POWERMETRICS_INTERVAL_MS = 1000              # sample every 1s
# ---------------------------

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
    # Prefer REST so we get IDs compatible with REST chat calls
    r = requests.get(f"{REST_BASE}/models", timeout=5)
    r.raise_for_status()
    data = r.json()
    models = [m for m in data.get("data", []) if m.get("type") == "llm"]
    # Fallback if empty: use `lms ls --llm --json`
    if not models:
        ls = run(["lms", "ls", "--llm", "--json"]).stdout
        arr = json.loads(ls)
        # normalize to REST-like ids if present
        models = [{"id": m.get("id") or m.get("name") or m.get("model")} for m in arr if m]
    return [m["id"] for m in models if m.get("id")]

def unload_all():
    try:
        run(["lms", "unload", "--all"])
    except subprocess.CalledProcessError:
        pass

def load_model(model_id):
    t0 = time.perf_counter()
    # Allow JIT via REST too, but we want explicit load to measure load time
    # lms load accepts a "model key" from `lms ls`; use --gpu to maximize offload
    # We pass model_id; LM Studio resolves it (works for downloaded model keys).
    run(["lms", "load", model_id, "--gpu", GPU_SETTING, "-y"])
    return time.perf_counter() - t0

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

def extract_html(text):
    # Prefer explicit HTML tags
    m = re.search(r"(<html[\s\S]*?</html>)", text, re.I)
    if m:
        return m.group(1)
    # Try fenced code blocks ```html ... ```
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", text, re.I)
    if m:
        block = m.group(1).strip()
        if "<html" in block.lower():
            return block
    # Fallback: wrap content
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Output</title></head><body><pre>{json.dumps(text)[:20000]}</pre></body></html>"

def chat_once(model_id):
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a careful front-end engineer."},
            {"role": "user", "content": PROMPT}
        ],
        "temperature": TEMP,
        "top_p": TOP_P,
        "max_tokens": MAX_TOKENS,
        "stream": False
    }
    # Prefer REST API for rich stats; fallback to OpenAI-compatible /v1
    try:
        r = requests.post(f"{REST_BASE}/chat/completions", json=payload, timeout=600)
        if r.ok:
            return r.json()
        # Some versions may not expose REST chat; fall through
    except Exception:
        pass
    r = requests.post(f"{OPENAI_BASE}/chat/completions", json=payload, timeout=600)
    r.raise_for_status()
    return r.json()

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

    print(f"Found {len(models)} models: {models}")
    for model in models:
        print(f"\n=== Benchmarking {model} ===", flush=True)
        unload_all()

        # Load model and time it
        load_time_s = load_model(model)
        print(f"Loaded in {load_time_s:.2f}s")

        # Make safe filenames (model ids may contain slashes or spaces)
        safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(model))[:200]

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

        # Generate once
        gen_t0 = time.perf_counter()
        try:
            result = chat_once(model)
        finally:
            # stop samplers
            ram_stop_evt.set()
            t.join(timeout=3)
            psamp.stop()
        gen_time_s = time.perf_counter() - gen_t0

        # Parse powermetrics
        power_stats = parse_powermetrics_log(str(log_path))
        if isinstance(power_stats, dict) and sampler_combo:
            power_stats["samplers"] = sampler_combo

        # Extract HTML
        text = result["choices"][0]["message"]["content"]
        html = extract_html(text)
        html_path = OUT_DIR / f"{safe_model}.html"
        html_path.write_text(html)

        # Build metrics JSON
        usage = result.get("usage", {}) or {}
        # Fallback tokens/sec if REST stats absent
        completion_tokens = usage.get("completion_tokens") or usage.get("completion_tokens", 0)
        tokens_per_sec_fallback = None
        try:
            if gen_time_s > 0 and completion_tokens:
                tokens_per_sec_fallback = completion_tokens / gen_time_s
        except Exception:
            pass
        metrics = {
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "load_time_seconds": load_time_s,
            "generation_time_seconds": gen_time_s,
            "rest_stats": result.get("stats", {}),
            "usage": usage,
            "model_info": result.get("model_info", {}),
            "runtime": result.get("runtime", {}),
            "power": power_stats,
            "memory": ram_results,
            "derived": {
                "tokens_per_second_fallback": tokens_per_sec_fallback
            },
            "files": {
                "html": str(html_path.resolve()),
                "powermetrics_log": str(log_path.resolve())
            },
            "prompt": {
                "temperature": TEMP,
                "top_p": TOP_P,
                "max_tokens": MAX_TOKENS
            }
        }
        json_path = OUT_DIR / f"{safe_model}.json"
        json_path.write_text(json.dumps(metrics, indent=2))
        print(f"Saved: {html_path.name}, {json_path.name}")

    print(f"\nAll done. Output in: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
