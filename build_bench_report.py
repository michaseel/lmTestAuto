#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urljoin


def load_results(folder: Path):
    rows = []
    for p in sorted(folder.glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        rows.append((p, data))
    return rows


def pick_tokens_per_sec(d):
    stats = d.get("rest_stats") or {}
    keys = [
        "tokens_per_second",
        "token_per_second",
        "tok_per_sec",
        "tps",
    ]
    for k in keys:
        v = stats.get(k)
        if isinstance(v, (int, float)):
            return v
    derived = d.get("derived") or {}
    v = derived.get("tokens_per_second_fallback")
    if isinstance(v, (int, float)):
        return v
    return None


def fmt_float(v, digits=2):
    return (f"{v:.{digits}f}" if isinstance(v, (int, float)) else "-")


def to_file_url(path: Path):
    try:
        return path.resolve().as_uri()
    except Exception:
        return str(path)


def build_html(rows, title="LM Studio Bench Report", prompt_text=None, out_path: Path = None):
    # Prepare normalized rows for the table
    records = []
    for p, d in rows:
        files = d.get("files") or {}
        power = d.get("power") or {}
        mem = d.get("memory") or {}
        usage = d.get("usage") or {}
        prompt = d.get("prompt") or {}
        prompt_text_in_json = d.get("prompt_text") or prompt.get("text")
        if prompt_text is None:
            prompt_text = prompt_text_in_json
        rec = {
            "model": d.get("model"),
            "timestamp": d.get("timestamp"),
            "load_time_seconds": d.get("load_time_seconds"),
            "generation_time_seconds": d.get("generation_time_seconds"),
            "tokens_per_second": pick_tokens_per_sec(d),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cpu_w_avg": (power.get("cpu_watts") or {}).get("avg"),
            "cpu_w_max": (power.get("cpu_watts") or {}).get("max"),
            "gpu_w_avg": (power.get("gpu_watts") or {}).get("avg"),
            "gpu_w_max": (power.get("gpu_watts") or {}).get("max"),
            "ane_w_avg": (power.get("ane_watts") or {}).get("avg"),
            "ane_w_max": (power.get("ane_watts") or {}).get("max"),
            "samplers": power.get("samplers"),
            "mem_deltas": {
                "after_load_lms": ((mem.get("delta_since_baseline_after_load") or {}).get("lmstudio_rss_bytes")),
                "after_gen_lms": ((mem.get("delta_since_baseline_after_generation") or {}).get("lmstudio_rss_bytes")),
                "after_gen_vs_load_lms": ((mem.get("delta_since_load_after_generation") or {}).get("lmstudio_rss_bytes")),
                "after_load_sys": ((mem.get("delta_since_baseline_after_load") or {}).get("system_used_bytes")),
                "after_gen_sys": ((mem.get("delta_since_baseline_after_generation") or {}).get("system_used_bytes")),
            },
            "errors": d.get("errors") or {},
            "html_path": files.get("html"),
            "log_path": files.get("powermetrics_log"),
            "raw_json_path": str(p),
            "settings": {
                "temperature": prompt.get("temperature"),
                "top_p": prompt.get("top_p"),
                "max_tokens": prompt.get("max_tokens"),
                "gpu_setting": prompt.get("gpu_setting"),
            },
        }
        records.append(rec)

    # Inline CSS and JS for a self-contained report
    css = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,'Noto Sans',sans-serif;line-height:1.35;margin:20px;color:#111}
h1{margin:0 0 8px 0}
.muted{color:#666}
table{border-collapse:collapse;width:100%;margin-top:12px}
th,td{border-bottom:1px solid #eee;padding:8px 10px;text-align:left}
th{cursor:pointer;user-select:none;background:#fafafa;position:sticky;top:0}
tr:hover{background:#fcfcfc}
.tag{display:inline-block;padding:2px 6px;border-radius:6px;background:#f1f5f9;border:1px solid #e2e8f0;font-size:12px;color:#0f172a}
.toolbar{display:flex;gap:12px;align-items:center;margin:8px 0 4px}
input[type="search"]{padding:6px 8px;border:1px solid #ddd;border-radius:6px;min-width:280px}
.small{font-size:12px}
details{margin:4px 0}
code{background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;padding:1px 4px}
.nowrap{white-space:nowrap}
"""

    # JS sorting/filtering and rendering
    js = """
const DATA = REPLACEME_DATA;

let sortKey = 'model';
let sortDir = 1; // 1 asc, -1 desc

function num(v){ return (v===null||v===undefined||v==='-'||v==='')?null:Number(v); }

function formatBytes(b){
  if (b==null) return '-';
  const abs = Math.abs(b);
  const sign = b < 0 ? '-' : '';
  if (abs < 1024) return sign + abs + ' B';
  const units=['KB','MB','GB','TB'];
  let u=-1; let v=abs;
  do{ v/=1024; u++; }while(v>=1024&&u<units.length-1);
  return sign + v.toFixed(2)+' '+units[u];
}

function render(){
  const q = document.querySelector('#search').value.toLowerCase();
  const tbody = document.querySelector('#tbl tbody');
  tbody.innerHTML='';
  let rows = DATA.slice();
  rows.sort((a,b)=>{
    const av=a[sortKey], bv=b[sortKey];
    const an = num(av), bn = num(bv);
    if(an!=null && bn!=null){ return (an-bn)*sortDir; }
    return String(av||'').localeCompare(String(bv||''))*sortDir;
  });
  for(const r of rows){
    if(q && !(String(r.model).toLowerCase().includes(q))) continue;
    const tr = document.createElement('tr');
    const linkHtml = r.html_path ? `<a href="${r.html_url}" target="_blank">HTML</a>` : '<span class="muted">n/a</span>';
    const linkLog = r.log_path ? `<a href="${r.log_url}" target="_blank">Log</a>` : '<span class="muted">n/a</span>';
    tr.innerHTML = `
      <td class="nowrap">${r.model || '-'}</td>
      <td>${r.timestamp ? new Date(r.timestamp).toLocaleString() : '-'}</td>
      <td class="nowrap">${r.settings.gpu_setting?`<span class="tag">gpu:${r.settings.gpu_setting}</span>`:''} <span class="tag">T=${r.settings.temperature ?? '-'}</span> <span class="tag">p=${r.settings.top_p ?? '-'}</span></td>
      <td>${r.load_time_seconds?.toFixed?.(2) ?? '-'}</td>
      <td>${r.generation_time_seconds?.toFixed?.(2) ?? '-'}</td>
      <td>${r.tokens_per_second?.toFixed?.(2) ?? '-'}</td>
      <td>${r.prompt_tokens ?? '-'}</td>
      <td>${r.completion_tokens ?? '-'}</td>
      <td>${r.total_tokens ?? '-'}</td>
      <td>${r.cpu_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td>${r.gpu_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td>${r.ane_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td>${formatBytes(r.mem_deltas.after_load_lms)}</td>
      <td>${formatBytes(r.mem_deltas.after_gen_lms)}</td>
      <td>${linkHtml} · ${linkLog} · <a href="${r.json_url}" target="_blank">JSON</a></td>
    `;
    tbody.appendChild(tr);
  }
  document.querySelector('#count').textContent = rows.length;
}

function setupSort(){
  document.querySelectorAll('#tbl th').forEach(th=>{
    th.addEventListener('click',()=>{
      const key = th.dataset.key;
      if(!key) return;
      if(sortKey===key){ sortDir*=-1; } else { sortKey=key; sortDir=1; }
      render();
    });
  });
}

window.addEventListener('DOMContentLoaded',()=>{
  setupSort();
  document.querySelector('#search').addEventListener('input', render);
  render();
});
"""

    # Compute file URLs
    for r in records:
        r["html_url"] = to_file_url(Path(r["html_path"])) if r.get("html_path") else None
        r["log_url"] = to_file_url(Path(r["log_path"])) if r.get("log_path") else None
        r["json_url"] = to_file_url(Path(r["raw_json_path"]))

    # Build HTML doc
    data_json = json.dumps(records)
    prompt_html = (f"<pre style='white-space:pre-wrap'>{(prompt_text or 'Not available')}</pre>")
    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
  <h1>{title}</h1>
  <div class="muted small">Generated from {len(records)} result files.</div>
  <div class="toolbar">
    <input id="search" type="search" placeholder="Filter by model name">
    <div class="small muted">Rows: <span id="count"></span></div>
  </div>
  <table id="tbl">
    <thead>
      <tr>
        <th data-key="model">Model</th>
        <th data-key="timestamp">Timestamp</th>
        <th data-key="settings">Settings</th>
        <th data-key="load_time_seconds">Load s</th>
        <th data-key="generation_time_seconds">Gen s</th>
        <th data-key="tokens_per_second">Tok/s</th>
        <th data-key="prompt_tokens">Prompt tok</th>
        <th data-key="completion_tokens">Compl tok</th>
        <th data-key="total_tokens">Total tok</th>
        <th data-key="cpu_w_avg">CPU W(avg)</th>
        <th data-key="gpu_w_avg">GPU W(avg)</th>
        <th data-key="ane_w_avg">ANE W(avg)</th>
        <th data-key="mem_deltas.after_load_lms">LM RSS Δ load</th>
        <th data-key="mem_deltas.after_gen_lms">LM RSS Δ gen</th>
        <th>Artifacts</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>Prompt</h2>
  {prompt_html}

  <script>
  {js.replace('REPLACEME_DATA', data_json)}
  </script>
</body>
</html>
"""
    return html


def main():
    ap = argparse.ArgumentParser(description="Build an interactive HTML report from bench JSON files.")
    ap.add_argument("folder", help="Path to folder containing per-model JSON files")
    ap.add_argument("--out", default=None, help="Output HTML file (default: <folder>/index.html)")
    ap.add_argument("--title", default="LM Studio Bench Report", help="Title for the report")
    ap.add_argument("--prompt-file", default=None, help="Optional file containing the original prompt text to embed")
    args = ap.parse_args()

    folder = Path(args.folder)
    out = Path(args.out) if args.out else folder / "index.html"
    prompt_text = None
    if args.prompt_file:
        try:
            prompt_text = Path(args.prompt_file).read_text()
        except Exception:
            pass

    rows = load_results(folder)
    html = build_html(rows, title=args.title, prompt_text=prompt_text, out_path=out)
    out.write_text(html)
    print(f"Wrote report: {out.resolve()}")


if __name__ == "__main__":
    main()

