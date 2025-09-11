#!/usr/bin/env python3
"""
Quick verifier for CPU/GPU wattage on macOS using powermetrics.

Usage examples:
- sudo -E python3 test_power_monitor.py
- sudo -E python3 test_power_monitor.py --samples 10 --interval-ms 1000 --log out.log

Notes:
- powermetrics typically requires root. Run with sudo for real readings.
- On success, prints min/avg/max for CPU/GPU power and writes the raw log if requested.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ANSI = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=int, default=10, help="number of samples (-n)")
    p.add_argument("--interval-ms", type=int, default=1000, help="interval between samples in ms (-i)")
    p.add_argument("--log", type=str, default=None, help="optional file to save raw powermetrics output")
    return p.parse_args()

def check_tools():
    if not shutil.which("powermetrics"):
        print("Error: 'powermetrics' not found on PATH (macOS only).", file=sys.stderr)
        sys.exit(1)
    if os.name == "posix" and sys.platform == "darwin" and os.geteuid() != 0:
        print("Notice: running without sudo; power readings may be unavailable.", file=sys.stderr)

def detect_samplers(samples: int, interval_ms: int):
    # Try a series of sampler combinations known across macOS versions.
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
        cmd = [
            "powermetrics", "--samplers", combo, "-n", str(samples), "-i", str(interval_ms)
        ]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if res.stdout.strip():
                return combo, res.stdout
        except subprocess.CalledProcessError as e:
            last_err = e
    if last_err:
        print("powermetrics failed:", last_err, file=sys.stderr)
        if getattr(last_err, "stdout", None):
            print(last_err.stdout or "", file=sys.stderr)
        if getattr(last_err, "stderr", None):
            print(last_err.stderr or "", file=sys.stderr)
    return None, ""

def parse_watts(log_text: str):
    cpu, gpu, ane = [], [], []
    for raw in log_text.splitlines():
        s = ANSI.sub("", raw.strip())
        # Match e.g. "CPU Power: 12.3 W" or "Average power: 800 mW" within CPU/GPU sections.
        # Direct power lines
        for label, arr in (("CPU", cpu), ("GPU", gpu), ("ANE", ane)):
            m = re.search(fr"{label}.*?Power:\s*([\d.]+)\s*(m?W)", s, re.I)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                arr.append(val / 1000.0 if unit == "mw" else val)
        # Average power lines (some OS versions)
        # Example inside a CPU/GPU block: "Average power: 850 mW"
        m = re.search(r"^(CPU|GPU|ANE).*", s)
        if m:
            current = m.group(1).upper()
        m2 = re.search(r"Average power:\s*([\d.]+)\s*(m?W)", s, re.I)
        if m2:
            val = float(m2.group(1))
            unit = m2.group(2).lower()
            watts = val / 1000.0 if unit == "mw" else val
            if current == "CPU":
                cpu.append(watts)
            elif current == "GPU":
                gpu.append(watts)
            elif current == "ANE":
                ane.append(watts)
    return cpu, gpu, ane

def stats(arr):
    return {
        "samples": len(arr),
        "min": min(arr) if arr else None,
        "max": max(arr) if arr else None,
        "avg": (sum(arr) / len(arr)) if arr else None,
    }

def main():
    args = parse_args()
    check_tools()
    combo, text = detect_samplers(args.samples, args.interval_ms)
    if combo:
        print(f"Using powermetrics samplers: {combo}")
    if args.log:
        try:
            with open(args.log, "w") as f:
                f.write(text)
            print(f"Raw log saved to: {args.log}")
        except Exception as e:
            print(f"Warning: could not write log: {e}", file=sys.stderr)

    cpu, gpu, ane = parse_watts(text)

    print("\nPower metrics summary (W):")
    print(f" CPU: {stats(cpu)}")
    print(f" GPU: {stats(gpu)}")
    print(f" ANE: {stats(ane)}")

    if not cpu and not gpu:
        print("\nNo CPU/GPU power samples parsed.", file=sys.stderr)
        if os.name == "posix" and sys.platform == "darwin" and os.geteuid() != 0:
            print("Likely due to missing privileges. Re-run with: sudo -E python3 test_power_monitor.py", file=sys.stderr)
        else:
            print("Try different samplers manually, e.g.:", file=sys.stderr)
            print("  sudo powermetrics --samplers cpu_power,gpu_power -n 5 -i 1000", file=sys.stderr)
            print("  sudo powermetrics --samplers all -n 5 -i 1000", file=sys.stderr)
            print("Then share the log so we can adapt the parser.", file=sys.stderr)

if __name__ == "__main__":
    main()
