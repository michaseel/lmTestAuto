#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenRouter Benchmark Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: sans-serif; }}
        .table-container {{ margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px 12px; border: 1px solid #ddd; text-align: left; }}
        th {{ background-color: #f4f4f4; }}
    </style>
</head>
<body class="bg-gray-50">
    <div class="container mx-auto p-4">
        <h1 class="text-2xl font-bold mb-4">OpenRouter Benchmark Report</h1>
        <div id="prompt" class="mb-4 p-4 bg-gray-100 border rounded-md">
            <h2 class="font-semibold">Prompt:</h2>
            <pre class="whitespace-pre-wrap">{PROMPT}</pre>
        </div>
        <div id="report-table" class="overflow-x-auto">
            {TABLE_CONTENT}
        </div>
        <p class="text-sm text-gray-500 mt-4">Last updated: {TIMESTAMP}</p>
    </div>
</body>
</html>
"""

def get_report_data(results_dir: Path):
    results = []
    prompt_text = ""
    for json_file in sorted(results_dir.glob("*.json")):
        if json_file.name == 'report.json':
            continue
        
        try:
            data = json.loads(json_file.read_text())
            if not prompt_text:
                prompt_text = data.get("prompt", {}).get("text", "")

            results.append({
                "model": data.get("model"),
                "generation_time_seconds": data.get("generation_time_seconds"),
                "tokens_per_second": data.get("derived", {}).get("tokens_per_second"),
                "cost": data.get("cost"),
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "html_file": Path(data.get("files", {}).get("html", "")).name if data.get("files", {}).get("html") else None,
            })
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Skipping corrupted or incomplete file {json_file.name}: {e}")
    
    return {
        "prompt": prompt_text,
        "results": sorted(results, key=lambda x: x.get("model") or "")
    }

def build_html_table(results):
    if not results:
        return '<p class="text-center p-4">No results yet. Benchmarks may be running...</p>'

    table = '<table class="table-auto w-full">'
    table += """
        <thead class="bg-gray-200">
            <tr>
                <th class="px-4 py-2">Model</th>
                <th class="px-4 py-2">Time (s)</th>
                <th class="px-4 py-2">Tokens/s</th>
                <th class="px-4 py-2">Cost ($)</th>
                <th class="px-4 py-2">Prompt Tokens</th>
                <th class="px-4 py-2">Completion Tokens</th>
                <th class="px-4 py-2">Output</th>
            </tr>
        </thead>
        <tbody>
    """
    for row in results:
        time_s = f"{row['generation_time_seconds']:.2f}" if row.get('generation_time_seconds') is not None else 'N/A'
        tps = f"{row['tokens_per_second']:.2f}" if row.get('tokens_per_second') is not None else 'N/A'
        cost = f"{row['cost']:.4f}" if row.get('cost') is not None else 'N/A'
        html_link = f'<a href="{row["html_file"]}" target="_blank" class="text-blue-600 hover:underline">View</a>' if row.get("html_file") else 'N/A'
        table += f"""
            <tr class="border-t">
                <td class="border px-4 py-2">{row.get('model', 'N/A')}</td>
                <td class="border px-4 py-2">{time_s}</td>
                <td class="border px-4 py-2">{tps}</td>
                <td class="border px-4 py-2">{cost}</td>
                <td class="border px-4 py-2">{row.get('prompt_tokens', 0)}</td>
                <td class="border px-4 py-2">{row.get('completion_tokens', 0)}</td>
                <td class="border px-4 py-2">{html_link}</td>
            </tr>
        """
    table += "</tbody></table>"
    return table

def update_report(results_dir: Path):
    report_dir = Path(results_dir)
    report_dir.mkdir(exist_ok=True)

    report_data = get_report_data(report_dir)
    
    table_html = build_html_table(report_data["results"])
    
    final_html = HTML_TEMPLATE.format(
        PROMPT=report_data.get('prompt', 'Not available.'),
        TABLE_CONTENT=table_html,
        TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    (report_dir / "index.html").write_text(final_html)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        update_report(Path(sys.argv[1]))
    else:
        print("Usage: python openrouter_report.py <path_to_results_dir>")