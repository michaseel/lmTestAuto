#!/usr/bin/env python3
import os, re, sys, json, time, threading, hashlib, argparse, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
import openrouter_report

# --------- Config ----------
OPENAI_BASE    = "https://openrouter.ai/api/v1"
# Save all runs under ./reports/<timestamped-folder>
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
GEN_TIMEOUT_SECONDS = 300                    # interrupt generation after ~3m20s
GEN_TIMER_INTERVAL_SECONDS = 2               # print timer update every 2s
# ---------------------------

def get_out_dir():
    # Create a hash of the settings
    settings_str = f"{PROMPT}{MAX_TOKENS}{TEMP}{TOP_P}"
    settings_hash = hashlib.sha256(settings_str.encode('utf-8')).hexdigest()[:10]
    return Path("reports") / f"openrouter-bench-{settings_hash}"

OUT_DIR = get_out_dir()
OUT_DIR.mkdir(parents=True, exist_ok=True)

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
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable not set.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a careful front-end engineer."},
            {"role": "user", "content": PROMPT}
        ],
        "usage": {
            "include": True
        }
    }
    if TEMP is not None:
        payload["temperature"] = TEMP
    if TOP_P is not None:
        payload["top_p"] = TOP_P
    if MAX_TOKENS is not None:
        payload["max_tokens"] = MAX_TOKENS

    r = requests.post(f"{OPENAI_BASE}/chat/completions", headers=headers, json=payload, timeout=(5, timeout_s))
    r.raise_for_status()
    return r.json()

report_lock = threading.Lock()

def benchmark_model(model_id):
    print(f"Starting benchmark for {model_id}", flush=True)
    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(model_id))[:200]
    json_path = OUT_DIR / f"{safe_model}.json"

    if json_path.exists():
        print(f"Skipping {model_id} as results already exist.")
        return

    result = None
    gen_time_s = None
    gen_error = None
    
    gen_t0 = time.perf_counter()
    
    try:
        result = chat_once(model_id, timeout_s=GEN_TIMEOUT_SECONDS)
        gen_time_s = time.perf_counter() - gen_t0
    except Exception as e:
        gen_error = f"generation_failed: {type(e).__name__}: {e}"
        print(f"\nGeneration failed for {model_id}: {e}", file=sys.stderr)

    html_path = None
    raw_text_path = None
    cost = None
    if result and not gen_error:
        try:
            text = result["choices"][0]["message"]["content"]
        except Exception:
            text = json.dumps(result)
        
        raw_text_path = OUT_DIR / f"{safe_model}.txt"
        try:
            raw_text_path.write_text(text)
        except Exception:
            raw_text_path = None

        html = extract_html(text)
        html_path = OUT_DIR / f"{safe_model}.html"
        html_path.write_text(html)

    usage = (result.get("usage", {}) if result else {}) or {}
    cost = usage.get("cost")
    completion_tokens = usage.get("completion_tokens") or usage.get("completion_tokens", 0)
    tokens_per_sec = None
    try:
        if gen_time_s is not None and gen_time_s > 0 and completion_tokens:
            tokens_per_sec = completion_tokens / gen_time_s
    except Exception:
        pass

    metrics = {
        "model": model_id,
        "timestamp": datetime.now().isoformat(),
        "generation_time_seconds": gen_time_s,
        "cost": cost,
        "usage": usage,
        "model_info": (result.get("model_info", {}) if result else {}),
        "derived": {
            "tokens_per_second": tokens_per_sec
        },
        "files": {
            "html": (str(html_path.resolve()) if html_path else None),
            "raw_text": (str(raw_text_path.resolve()) if raw_text_path else None),
        },
        "prompt": {
            "temperature": TEMP,
            "top_p": TOP_P,
            "max_tokens": MAX_TOKENS,
            "text": PROMPT,
        },
        "errors": {
            "generation": gen_error,
        }
    }
    json_path.write_text(json.dumps(metrics, indent=2))
    saved_html = html_path.name if html_path else "<no-html>"
    print(f"Saved: {saved_html}, {json_path.name}")
    with report_lock:
        openrouter_report.update_report(OUT_DIR)

def main():
    parser = argparse.ArgumentParser(description="Benchmark OpenRouter models.")
    parser.add_argument("--models_file", type=str, default="openrouter_models.txt", help="Path to a file containing a list of model names to benchmark, one per line.")
    parser.add_argument("--concurrency", type=int, default=8, help="Number of models to benchmark concurrently.")
    args = parser.parse_args()

    try:
        with open(args.models_file, 'r') as f:
            models_to_benchmark = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: Models file not found at '{args.models_file}'", file=sys.stderr)
        sys.exit(1)

    if not models_to_benchmark:
        print(f"No models found in '{args.models_file}'.", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking {len(models_to_benchmark)} models: {models_to_benchmark}")

    # Create initial empty report
    openrouter_report.update_report(OUT_DIR)
    print(f"Report is at: {OUT_DIR.resolve() / 'index.html'}")

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(benchmark_model, model_id) for model_id in models_to_benchmark]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"A benchmark task generated an exception: {e}", file=sys.stderr)

    # Final report update
    openrouter_report.update_report(OUT_DIR)
    print(f"Final report is at: {OUT_DIR.resolve() / 'index.html'}")

    print(f"\nAll done. Output in: {OUT_DIR.resolve()}")

if __name__ == "__main__":
    main()