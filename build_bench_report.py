#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urljoin
import platform
import subprocess
try:
    import psutil
except Exception:
    psutil = None


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


def _is_macos():
    return platform.system() == "Darwin"


def _machine_info():
    info = {"cpu": None, "gpu": None, "ram_bytes": None}
    # CPU
    cpu = None
    if _is_macos():
        try:
            out = subprocess.run(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=2)
            if out.stdout.strip():
                cpu = out.stdout.strip()
        except Exception:
            pass
    info["cpu"] = cpu or (platform.processor() or platform.machine())
    # RAM
    if psutil is not None:
        try:
            info["ram_bytes"] = psutil.virtual_memory().total
        except Exception:
            info["ram_bytes"] = None
    else:
        info["ram_bytes"] = None
    # GPU (macOS)
    gpu = None
    if _is_macos():
        try:
            out = subprocess.run(["/usr/sbin/system_profiler", "SPDisplaysDataType"], capture_output=True, text=True, timeout=5)
            models = []
            for line in out.stdout.splitlines():
                if "Chipset Model:" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        models.append(parts[1].strip())
            if models:
                # dedupe preserving order
                gpu = ", ".join(dict.fromkeys(models))
        except Exception:
            pass
    info["gpu"] = gpu
    return info


def build_html(rows, title="LM Studio Bench Report", prompt_text=None, out_path: Path = None):
    # Prepare normalized rows for the table
    records = []
    total_gen_time = 0.0
    for p, d in rows:
        files = d.get("files") or {}
        power = d.get("power") or {}
        mem = d.get("memory") or {}
        usage = d.get("usage") or {}
        prompt = d.get("prompt") or {}
        prompt_text_in_json = d.get("prompt_text") or prompt.get("text")
        if prompt_text is None:
            prompt_text = prompt_text_in_json
        mi = d.get("model_info") or {}
        rt = d.get("runtime") or {}
        params = mi.get("parameters") or mi.get("n_params") or mi.get("params") or rt.get("n_params")
        quant = mi.get("quantization") or mi.get("quant") or rt.get("quantization") or rt.get("q_type")
        def _pretty_params(x):
            try:
                v = float(x)
                if v >= 1e9:
                    return f"{v/1e9:.1f}B"
                if v >= 1e6:
                    return f"{v/1e6:.1f}M"
                return str(int(v))
            except Exception:
                return str(x) if x is not None else None
        model_size = _pretty_params(params)
        gstats = power.get("gpu_watts") or {}
        gen_time = d.get("generation_time_seconds")
        if isinstance(gen_time, (int, float)):
            total_gen_time += gen_time
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
            "gpu_w_avg": gstats.get("avg"),
            "gpu_w_max": gstats.get("max"),
            "gpu_w_min": gstats.get("min"),
            "ane_w_avg": (power.get("ane_watts") or {}).get("avg"),
            "ane_w_max": (power.get("ane_watts") or {}).get("max"),
            "samplers": power.get("samplers"),
            "mem_after_load_lms": ((mem.get("delta_since_baseline_after_load") or {}).get("lmstudio_rss_bytes")),
            "mem_after_gen_lms": ((mem.get("delta_since_baseline_after_generation") or {}).get("lmstudio_rss_bytes")),
            "mem_after_gen_vs_load_lms": ((mem.get("delta_since_load_after_generation") or {}).get("lmstudio_rss_bytes")),
            "mem_after_load_sys": ((mem.get("delta_since_baseline_after_load") or {}).get("system_used_bytes")),
            "mem_after_gen_sys": ((mem.get("delta_since_baseline_after_generation") or {}).get("system_used_bytes")),
            "errors": d.get("errors") or {},
            "html_path": files.get("html"),
            "log_path": files.get("powermetrics_log"),
            "raw_json_path": str(p),
            "raw_text_path": files.get("raw_text"),
            "model_size": model_size,
            "quantization": quant,
            "settings": {
                "temperature": prompt.get("temperature"),
                "top_p": prompt.get("top_p"),
                "max_tokens": prompt.get("max_tokens"),
                "num_ctx": prompt.get("num_ctx"),
                "gpu_setting": prompt.get("gpu_setting"),
            },
        }
        records.append(rec)

    summary = {
        "models": len(records),
        "total_generation_time_seconds": total_gen_time,
        "avg_generation_time_seconds": (total_gen_time/len(records) if records else None),
        "machine": _machine_info(),
    }

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
.cols{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px}
.cols label{display:flex;align-items:center;gap:6px;border:1px solid #e2e8f0;padding:4px 8px;border-radius:8px;background:#f8fafc}
.hidden{display:none}
"""

    # JS sorting/filtering and rendering
    js = """
const DATA = REPLACEME_DATA;
const SUMMARY = REPLACEME_SUMMARY;

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
    const linkHtml = r.html_path ? `<a href=\"${r.html_url}\" target=\"_blank\">HTML</a>` : '<span class=\"muted\">n/a</span>';
    const linkText = r.raw_text_path ? `<a href=\"${r.text_url}\" target=\"_blank\">Text</a>` : '<span class=\"muted\">n/a</span>';
    tr.innerHTML = `
      <td class="col-model nowrap">${r.model || '-'}</td>
      <td class="col-timestamp">${r.timestamp ? new Date(r.timestamp).toLocaleString() : '-'}</td>
      <td class="col-settings nowrap">${r.settings.gpu_setting?`<span class=\"tag\">gpu:${r.settings.gpu_setting}</span>`:''} <span class="tag">T=${r.settings.temperature ?? '-'}</span> <span class="tag">p=${r.settings.top_p ?? '-'}</span></td>
      <td class="col-load_time_seconds">${r.load_time_seconds?.toFixed?.(2) ?? '-'}</td>
      <td class="col-generation_time_seconds">${r.generation_time_seconds?.toFixed?.(2) ?? '-'}</td>
      <td class="col-tokens_per_second">${r.tokens_per_second?.toFixed?.(2) ?? '-'}</td>
      <td class="col-prompt_tokens">${r.prompt_tokens ?? '-'}</td>
      <td class="col-completion_tokens">${r.completion_tokens ?? '-'}</td>
      <td class="col-total_tokens">${r.total_tokens ?? '-'}</td>
      <td class="col-model_size">${r.model_size ?? '-'}</td>
      <td class="col-quantization">${r.quantization ?? '-'}</td>
      <td class="col-cpu_w_avg">${r.cpu_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td class="col-gpu_w_avg">${r.gpu_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td class="col-gpu_w_max">${r.gpu_w_max?.toFixed?.(2) ?? '-'}</td>
      <td class="col-gpu_w_min">${r.gpu_w_min?.toFixed?.(2) ?? '-'}</td>
      <td class="col-ane_w_avg">${r.ane_w_avg?.toFixed?.(2) ?? '-'}</td>
      <td class="col-mem_after_load_lms">${formatBytes(r.mem_after_load_lms)}</td>
      <td class="col-mem_after_gen_lms">${formatBytes(r.mem_after_gen_lms)}</td>
      <td class=\"col-artifacts\">${linkHtml} · ${linkText} · <a href=\"${r.json_url}\" target=\"_blank\">JSON</a></td>
    `;
    tbody.appendChild(tr);
  }
  document.querySelector('#count').textContent = rows.length;
  applyColumnVisibility();
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
const DEFAULT_HIDDEN = new Set(["timestamp","settings","total_tokens","cpu_w_avg","ane_w_avg"]);

function setupColumnToggles(){
  const wrapper = document.querySelector('#col-toggles');
  const cols = Array.from(document.querySelectorAll('#tbl th')).map(th=>({ key: th.dataset.key, label: th.textContent }));
  for(const c of cols){
    if(!c.key) continue;
    const id = `col_${c.key}`;
    const checked = !DEFAULT_HIDDEN.has(c.key);
    const lab = document.createElement('label');
    lab.innerHTML = `<input type="checkbox" id="${id}" ${checked?'checked':''}> ${c.label}`;
    wrapper.appendChild(lab);
    lab.querySelector('input').addEventListener('change', applyColumnVisibility);
  }
  applyColumnVisibility();
}

function applyColumnVisibility(){
  const checks = Array.from(document.querySelectorAll('#col-toggles input[type="checkbox"]'));
  const visible = new Set(checks.filter(c=>c.checked).map(c=>c.id.replace('col_','')));
  const controllable = new Set(Array.from(checks).map(c=>c.id.replace('col_','')));
  document.querySelectorAll('#tbl th').forEach(th=>{
    const key = th.dataset.key;
    if(!key) return;
    th.classList.toggle('hidden', !visible.has(key));
  });
  document.querySelectorAll('#tbl tbody tr').forEach(tr=>{
    Array.from(tr.children).forEach(td=>{
      const m = td.className.match(/col-([A-Za-z0-9_.-]+)/);
      if(!m) return;
      const key = m[1];
      if(!controllable.has(key)) return;
      td.classList.toggle('hidden', !visible.has(key));
    });
  });
}

window.addEventListener('DOMContentLoaded',()=>{
  setupSort();
  setupColumnToggles();
  document.querySelector('#search').addEventListener('input', render);
  // Fill summary
  if(SUMMARY){
    const el = document.querySelector('#summary');
    const ram = SUMMARY.machine.ram_bytes;
    const ramStr = ram? (ram/1073741824).toFixed(1)+' GB' : '-';
    el.innerHTML = `<div class="small"><strong>Machine:</strong> CPU: ${SUMMARY.machine.cpu || '-'} · GPU: ${SUMMARY.machine.gpu || '-'} · RAM: ${ramStr}<br><strong>Models:</strong> ${SUMMARY.models} · <strong>Total gen time:</strong> ${(SUMMARY.total_generation_time_seconds||0).toFixed(2)} s · <strong>Avg gen time:</strong> ${SUMMARY.avg_generation_time_seconds?SUMMARY.avg_generation_time_seconds.toFixed(2):'-'} s</div>`;
  }
  render();
  drawCharts();
});

function drawCharts(){
  try{ drawScatterTPSvsGPU(); }catch(e){ console.warn('scatter failed', e); }
  try{ drawBarsTimes(); }catch(e){ console.warn('bars failed', e); }
}

function drawScatterTPSvsGPU(){
  const canvas = document.getElementById('chart_tps_gpu');
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  const data = DATA.filter(d=> num(d.tokens_per_second)!=null && num(d.gpu_w_avg)!=null);
  const pad = 40; const W = canvas.width, H = canvas.height;
  ctx.clearRect(0,0,W,H);
  if(data.length===0){ ctx.fillText('No data for TPS vs GPU (avg W)', 10, 20); return; }
  const xs = data.map(d=>num(d.gpu_w_avg));
  const ys = data.map(d=>num(d.tokens_per_second));
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = 0, yMax = Math.max(...ys)*1.1;
  const xScale = v => pad + (W-2*pad) * ((v - xMin) / (xMax - xMin || 1));
  const yScale = v => H - pad - (H-2*pad) * ((v - yMin) / (yMax - yMin || 1));
  // axes
  ctx.strokeStyle = '#ccc';
  ctx.beginPath(); ctx.moveTo(pad, pad); ctx.lineTo(pad, H-pad); ctx.lineTo(W-pad, H-pad); ctx.stroke();
  ctx.fillStyle = '#333'; ctx.font = '12px system-ui';
  ctx.fillText('GPU avg W', W/2 - 30, H - 10);
  ctx.save(); ctx.translate(12, H/2); ctx.rotate(-Math.PI/2); ctx.fillText('Tokens/sec', 0, 0); ctx.restore();
  // points
  for(const d of data){
    const x = xScale(num(d.gpu_w_avg));
    const y = yScale(num(d.tokens_per_second));
    ctx.fillStyle = '#2563eb';
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI*2); ctx.fill();
  }
  // labels (truncated)
  ctx.fillStyle = '#555';
  for(const d of data){
    const x = xScale(num(d.gpu_w_avg));
    const y = yScale(num(d.tokens_per_second));
    const label = String(d.model).slice(0, 18);
    ctx.fillText(label, x+6, y-6);
  }
}

function drawBarsTimes(){
  const canvas = document.getElementById('chart_times');
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  const data = DATA.filter(d=> num(d.generation_time_seconds)!=null).slice().sort((a,b)=>num(b.generation_time_seconds)-num(a.generation_time_seconds)).slice(0,20);
  const pad = 60; const W = canvas.width, H = canvas.height;
  ctx.clearRect(0,0,W,H);
  if(data.length===0){ ctx.fillText('No generation time data', 10, 20); return; }
  const xs = data.map(d=>num(d.generation_time_seconds));
  const xMax = Math.max(...xs) * 1.1; const xMin = 0;
  const barH = (H-2*pad) / data.length;
  const xScale = v => pad + (W-2*pad) * ((v - xMin) / (xMax - xMin || 1));
  // axes
  ctx.strokeStyle = '#ccc'; ctx.beginPath(); ctx.moveTo(pad, pad); ctx.lineTo(pad, H-pad); ctx.lineTo(W-pad, H-pad); ctx.stroke();
  ctx.fillStyle = '#333'; ctx.font = '12px system-ui'; ctx.fillText('Generation time (s)', W/2 - 50, H - 10);
  // bars
  data.forEach((d,i)=>{
    const y = pad + i*barH + 2;
    const w = xScale(num(d.generation_time_seconds)) - pad;
    ctx.fillStyle = '#10b981';
    ctx.fillRect(pad, y, w, barH-4);
    ctx.fillStyle = '#111';
    const label = `${String(d.model).slice(0,18)}  ${num(d.generation_time_seconds).toFixed(1)}s`;
    ctx.fillText(label, pad+4, y + barH/2 + 4);
  });
}
"""

    # Compute file URLs
    for r in records:
        r["html_url"] = to_file_url(Path(r["html_path"])) if r.get("html_path") else None
        r["log_url"] = to_file_url(Path(r["log_path"])) if r.get("log_path") else None
        r["json_url"] = to_file_url(Path(r["raw_json_path"]))
        r["text_url"] = to_file_url(Path(r["raw_text_path"])) if r.get("raw_text_path") else None

    # Build HTML doc
    data_json = json.dumps(records)
    summary_json = json.dumps(summary)
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
  <details>
    <summary><strong>Prompt, Machine & Run Info</strong> (click to expand)</summary>
    <div id="summary" style="margin:8px 0"></div>
    {prompt_html}
  </details>
  <div class="toolbar">
    <input id="search" type="search" placeholder="Filter by model name">
    <div class="small muted">Rows: <span id="count"></span></div>
  </div>
  <div id="col-toggles" class="cols small"></div>
  <table id="tbl">
    <thead>
      <tr>
        <th class="col-model" data-key="model">Model</th>
        <th class="col-timestamp" data-key="timestamp">Timestamp</th>
        <th class="col-settings" data-key="settings">Settings</th>
        <th class="col-load_time_seconds" data-key="load_time_seconds">Load s</th>
        <th class="col-generation_time_seconds" data-key="generation_time_seconds">Gen s</th>
        <th class="col-tokens_per_second" data-key="tokens_per_second">Tok/s</th>
        <th class="col-prompt_tokens" data-key="prompt_tokens">Prompt tok</th>
        <th class="col-completion_tokens" data-key="completion_tokens">Compl tok</th>
        <th class="col-total_tokens" data-key="total_tokens">Total tok</th>
        <th class="col-model_size" data-key="model_size">Model size</th>
        <th class="col-quantization" data-key="quantization">Quantization</th>
        <th class="col-cpu_w_avg" data-key="cpu_w_avg">CPU W(avg)</th>
        <th class="col-gpu_w_avg" data-key="gpu_w_avg">GPU W(avg)</th>
        <th class="col-gpu_w_max" data-key="gpu_w_max">GPU W(peak)</th>
        <th class="col-gpu_w_min" data-key="gpu_w_min">GPU W(low)</th>
        <th class="col-ane_w_avg" data-key="ane_w_avg">ANE W(avg)</th>
        <th class="col-mem_after_load_lms" data-key="mem_after_load_lms">LM RSS Δ load</th>
        <th class="col-mem_after_gen_lms" data-key="mem_after_gen_lms">LM RSS Δ gen</th>
        <th class="col-artifacts" data-key="artifacts">Artifacts</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <h2>Charts</h2>
  <div class="small muted">Quick visualizations (auto from data below)</div>
  <div style="max-width:100%;">
    <canvas id="chart_tps_gpu" width="900" height="360" style="width:100%;max-width:100%;"></canvas>
  </div>
  <div style="height:8px"></div>
  <div style="max-width:100%;">
    <canvas id="chart_times" width="900" height="480" style="width:100%;max-width:100%;"></canvas>
  </div>

  <script>
  {js.replace('REPLACEME_DATA', data_json).replace('REPLACEME_SUMMARY', summary_json)}
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
