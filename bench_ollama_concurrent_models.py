#!/usr/bin/env python3
import os, re, sys, json, time, shutil, threading, subprocess, hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import requests
import psutil

# --------- Config ----------
OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
MODEL = "qwen3-coder:latest"  # The Ollama model to benchmark
CONCURRENCY_LEVELS = [1, 2, 3, 4, 5, 6, 7, 8] # Number of parallel requests
PROMPT = """write a short story about the city of Cologne in Germany
""" # The prompt to send to the model
POWERMETRICS_INTERVAL_MS = 1000 # Sample every 1s
# ---------------------------

def get_out_dir():
    settings_str = f"{MODEL}{PROMPT}{''.join(map(str, CONCURRENCY_LEVELS))}"
    settings_hash = hashlib.sha256(settings_str.encode('utf-8')).hexdigest()[:10]
    return Path("reports") / f"ollama-concurrent-bench-{settings_hash}"

OUT_DIR = get_out_dir()
OUT_DIR.mkdir(parents=True, exist_ok=True)

ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

class PowerSampler:
    def __init__(self, out_path, sampler_combo=None, interval_ms=1000):
        self.out_path = out_path
        self.proc = None
        self.sampler_combo = sampler_combo
        self.interval_ms = interval_ms

    def start(self):
        # Use powermetrics (needs sudo on macOS)
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
    cpu_watts, gpu_watts = [], []
    current_section = None
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                s = ansi_escape.sub("", line.strip())
                msec = re.match(r"^(CPU|GPU|ANE)", s, re.I)
                if msec:
                    current_section = msec.group(1).upper()
                for label, arr in (("CPU", cpu_watts), ("GPU", gpu_watts)):
                    m = re.search(fr"{label}.*?Power:\s*([\d.]+)\s*(m?W)", s, re.I)
                    if m:
                        val = float(m.group(1))
                        unit = m.group(2).lower()
                        arr.append(val / 1000.0 if unit == "mw" else val)
                m2 = re.search(r"Average power:\s*([\d.]+)\s*(m?W)", s, re.I)
                if m2 and current_section:
                    val = float(m2.group(1))
                    unit = m2.group(2).lower()
                    watts = val / 1000.0 if unit == "mw" else val
                    if current_section == "CPU":
                        cpu_watts.append(watts)
                    elif current_section == "GPU":
                        gpu_watts.append(watts)
    except FileNotFoundError:
        print(f"Warning: Powermetrics log file not found at {path}", file=sys.stderr)
        return {{}}

    def stats(arr):
        return {
            "avg": (sum(arr) / len(arr)) if arr else None,
            "max": max(arr) if arr else None,
            "min": min(arr) if arr else None,
            "samples": len(arr),
        }
    return {"cpu_watts": stats(cpu_watts), "gpu_watts": stats(gpu_watts)}

def sample_ram_hwm(stop_evt, interval=1.0):
    ollama_hwm = 0
    while not stop_evt.is_set():
        rss_sum = 0
        for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
            name = (p.info.get("name") or "").lower()
            if "ollama" in name:
                try:
                    rss_sum += p.info["memory_info"].rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        ollama_hwm = max(ollama_hwm, rss_sum)
        time.sleep(interval)
    return ollama_hwm

def generate_once(model: str, prompt: str, result_list: list):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        t0 = time.perf_counter()
        r = requests.post(f"{OLLAMA_API_BASE}/api/generate", json=payload)
        r.raise_for_status()
        response_data = r.json()
        gen_time_s = time.perf_counter() - t0

        eval_count = response_data.get("eval_count", 0)
        eval_duration_ns = response_data.get("eval_duration", 1)
        tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0

        result_list.append({
            "tps": tps,
            "generation_time_seconds": gen_time_s,
            "eval_count": eval_count,
            "eval_duration_ns": eval_duration_ns,
            "error": None
        })
    except requests.RequestException as e:
        result_list.append({"error": str(e)})
    except Exception as e:
        result_list.append({"error": f"An unexpected error occurred: {e}"})


def main():
    print(f"Starting concurrent benchmark for model: {MODEL}")
    print(f"Output directory: {OUT_DIR.resolve()}")

    all_results = []

    for concurrency in CONCURRENCY_LEVELS:
        print(f"\n--- Testing with {concurrency} parallel requests ---")

        log_path = OUT_DIR / f"concurrency_{concurrency}_powermetrics.log"
        psamp = PowerSampler(str(log_path), interval_ms=POWERMETRICS_INTERVAL_MS)
        
        ram_stop_evt = threading.Event()
        ram_hwm = 0
        def _ram_thread():
            nonlocal ram_hwm
            ram_hwm = sample_ram_hwm(ram_stop_evt, interval=1.0)
        
        ram_sampler_thread = threading.Thread(target=_ram_thread, daemon=True)

        threads: List[threading.Thread] = []
        thread_results: List[Dict] = []
        
        start_time = time.perf_counter()
        
        psamp.start()
        ram_sampler_thread.start()

        for _ in range(concurrency):
            thread = threading.Thread(target=generate_once, args=(MODEL, PROMPT, thread_results))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()
            
        end_time = time.perf_counter()
        
        ram_stop_evt.set()
        ram_sampler_thread.join()
        psamp.stop()

        total_time = end_time - start_time
        power_stats = parse_powermetrics_log(str(log_path))

        successful_runs = [r for r in thread_results if r.get("error") is None]
        
        if not successful_runs:
            print("All requests failed for this concurrency level.", file=sys.stderr)
            # Log errors from thread_results
            for i, res in enumerate(thread_results):
                print(f"  Request {i+1} error: {res.get('error')}", file=sys.stderr)
            continue

        total_tokens = sum(r.get("eval_count", 0) for r in successful_runs)
        avg_tps = sum(r.get("tps", 0) for r in successful_runs) / len(successful_runs)
        
        level_result = {
            "concurrency": concurrency,
            "total_time_seconds": total_time,
            "avg_tps": avg_tps,
            "total_tokens": total_tokens,
            "ram_hwm_bytes": ram_hwm,
            "power": power_stats,
            "runs": thread_results
        }
        all_results.append(level_result)

        print(f"  Avg. Tokens/Sec: {avg_tps:.2f}")
        print(f"  Total Time: {total_time:.2f}s")
        print(f"  Ollama RAM High-Water Mark: {ram_hwm / (1024**3):.2f} GB")
        if power_stats.get("cpu_watts", {}).get("avg"):
            print(f"  Avg. CPU Power: {power_stats['cpu_watts']['avg']:.2f} W")
        if power_stats.get("gpu_watts", {}).get("avg"):
            print(f"  Avg. GPU Power: {power_stats['gpu_watts']['avg']:.2f} W")

    # Save final report
    report_path = OUT_DIR / "summary_report.json"
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\nBenchmark finished. Full report saved to: {report_path.resolve()}")

    # Print summary table
    print("\n--- Benchmark Summary ---")
    print(f"{ 'Concurrency':<13} | {'Avg TPS':<10} | {'CPU Power (W)':<15} | {'GPU Power (W)':<15} | {'RAM HWM (GB)':<15}")
    print("-" * 75)
    for result in all_results:
        cpu_power = result.get("power", {}).get("cpu_watts", {}).get("avg", "N/A")
        gpu_power = result.get("power", {}).get("gpu_watts", {}).get("avg", "N/A")
        ram_gb = result.get("ram_hwm_bytes", 0) / (1024**3)
        
        cpu_str = f"{cpu_power:.2f}" if isinstance(cpu_power, float) else "N/A"
        gpu_str = f"{gpu_power:.2f}" if isinstance(gpu_power, float) else "N/A"

        print(f"{result['concurrency']:<13} | {result['avg_tps']:<10.2f} | {cpu_str:<15} | {gpu_str:<15} | {ram_gb:<15.2f}")


if __name__ == "__main__":
    # Check for sudo if on macOS for powermetrics
    if sys.platform == "darwin" and os.geteuid() != 0:
        print("NOTE: For accurate power metrics on macOS, this script should be run with sudo.", file=sys.stderr)
        print("Example: sudo python3 bench_ollama_concurrent_models.py", file=sys.stderr)
    
    # Check if ollama is running
    try:
        requests.get(OLLAMA_API_BASE, timeout=1.5)
    except requests.ConnectionError:
        print(f"Ollama server not found at {OLLAMA_API_BASE}", file=sys.stderr)
        print("Please ensure the Ollama application is running before starting the benchmark.", file=sys.stderr)
        sys.exit(1)

    main()
