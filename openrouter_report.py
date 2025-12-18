#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime
import subprocess
import sys

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenRouter Benchmark Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: sans-serif; }}
        .table-container {{ margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px 12px; border: 1px solid #ddd; text-align: left; }}
        th {{
            background-color: #f4f4f4;
            cursor: pointer;
            user-select: none;
            position: relative;
        }}
        th:hover {{ background-color: #e8e8e8; }}
        th.sorted-asc::after {{
            content: ' ▲';
            font-size: 0.8em;
        }}
        th.sorted-desc::after {{
            content: ' ▼';
            font-size: 0.8em;
        }}
        .preview-container {{
            position: relative;
        }}
        .preview-img {{
            display: none;
            position: fixed;
            z-index: 1000;
            border: 2px solid #333;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            max-width: 600px;
            max-height: 400px;
            pointer-events: none;
        }}
        tbody tr:hover .preview-img {{
            display: block;
        }}
    </style>
</head>
<body class="bg-gray-50">
    <div class="container mx-auto p-4">
        <h1 class="text-2xl font-bold mb-4">OpenRouter Benchmark Report</h1>
        <details class="mb-4">
            <summary class="cursor-pointer font-semibold p-2 bg-gray-100 border rounded-md hover:bg-gray-200">
                Prompt (click to expand)
            </summary>
            <div class="mt-2 p-4 bg-gray-50 border rounded-md">
                <pre class="whitespace-pre-wrap">{PROMPT}</pre>
            </div>
        </details>
        <div id="report-table" class="overflow-x-auto">
            {TABLE_CONTENT}
        </div>
        <p class="text-sm text-gray-500 mt-4">Last updated: {TIMESTAMP}</p>
    </div>
    <script>
        const DATA = {DATA_JSON};
        let sortKey = null;
        let sortDir = 1; // 1 = ascending, -1 = descending

        function parseNumber(val) {{
            if (val === null || val === undefined || val === 'N/A' || val === '') return null;
            const num = parseFloat(val);
            return isNaN(num) ? null : num;
        }}

        function compareValues(a, b, key) {{
            const aVal = a[key];
            const bVal = b[key];

            const aNum = parseNumber(aVal);
            const bNum = parseNumber(bVal);

            if (aNum !== null && bNum !== null) {{
                return (aNum - bNum) * sortDir;
            }}

            const aStr = String(aVal || '');
            const bStr = String(bVal || '');
            return aStr.localeCompare(bStr) * sortDir;
        }}

        function renderTable() {{
            const tbody = document.querySelector('#data-table tbody');
            tbody.innerHTML = '';

            let sortedData = [...DATA];
            if (sortKey) {{
                sortedData.sort((a, b) => compareValues(a, b, sortKey));
            }}

            for (const row of sortedData) {{
                const tr = document.createElement('tr');
                tr.className = 'border-t preview-container';

                const timestamp = row.timestamp ? new Date(row.timestamp).toLocaleString() : 'N/A';
                const time_s = row.generation_time_seconds !== null ? row.generation_time_seconds.toFixed(2) : 'N/A';
                const tps = row.tokens_per_second !== null ? row.tokens_per_second.toFixed(2) : 'N/A';
                const cost = row.cost !== null ? row.cost.toFixed(4) : 'N/A';
                const html_link = row.html_file ?
                    `<a href="${{row.html_file}}" target="_blank" class="text-blue-600 hover:underline">View</a>` : 'N/A';

                const screenshot_img = row.screenshot_file ?
                    `<img src="${{row.screenshot_file}}" class="preview-img" alt="Screenshot">` : '';

                tr.innerHTML = `
                    <td class="border px-4 py-2">${{row.model || 'N/A'}}</td>
                    <td class="border px-4 py-2">${{time_s}}</td>
                    <td class="border px-4 py-2">${{tps}}</td>
                    <td class="border px-4 py-2">${{cost}}</td>
                    <td class="border px-4 py-2">${{row.prompt_tokens || 0}}</td>
                    <td class="border px-4 py-2">${{row.completion_tokens || 0}}</td>
                    <td class="border px-4 py-2">${{timestamp}}</td>
                    <td class="border px-4 py-2">${{html_link}}</td>
                    ${{screenshot_img}}
                `;

                // Position screenshot on hover
                if (row.screenshot_file) {{
                    const img = tr.querySelector('.preview-img');
                    tr.addEventListener('mousemove', (e) => {{
                        const x = e.clientX + 15;
                        const y = e.clientY + 15;
                        img.style.left = x + 'px';
                        img.style.top = y + 'px';
                    }});
                }}

                tbody.appendChild(tr);
            }}

            // Update header sort indicators
            document.querySelectorAll('#data-table th').forEach(th => {{
                th.classList.remove('sorted-asc', 'sorted-desc');
                if (th.dataset.key === sortKey) {{
                    th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
                }}
            }});
        }}

        function setupSorting() {{
            document.querySelectorAll('#data-table th').forEach(th => {{
                th.addEventListener('click', () => {{
                    const key = th.dataset.key;
                    if (!key) return;

                    if (sortKey === key) {{
                        sortDir *= -1;
                    }} else {{
                        sortKey = key;
                        sortDir = 1;
                    }}

                    renderTable();
                }});
            }});
        }}

        window.addEventListener('DOMContentLoaded', () => {{
            setupSorting();
            renderTable();
        }});
    </script>
</body>
</html>
"""

def create_screenshot(html_path: Path, screenshot_path: Path) -> bool:
    """Create a screenshot of an HTML file using playwright."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=screenshot_path)
            browser.close()
        return True
    except ImportError:
        print("Warning: playwright not installed. Run: pip install playwright && playwright install chromium")
        return False
    except Exception as e:
        print(f"Error creating screenshot for {html_path}: {e}")
        return False

def get_report_data(results_dir: Path, create_screenshots: bool = True):
    results = []
    prompt_text = ""
    for json_file in sorted(results_dir.glob("*.json")):
        if json_file.name == 'report.json':
            continue

        try:
            data = json.loads(json_file.read_text())
            if not prompt_text:
                prompt_text = data.get("prompt", {}).get("text", "")

            html_file_path = data.get("files", {}).get("html")
            html_file = Path(html_file_path).name if html_file_path else None

            screenshot_file = None
            if html_file and create_screenshots:
                html_full_path = results_dir / html_file
                screenshot_name = html_file.replace(".html", "_screenshot.png")
                screenshot_full_path = results_dir / screenshot_name

                # Create screenshot if it doesn't exist
                if html_full_path.exists() and not screenshot_full_path.exists():
                    print(f"Creating screenshot for {html_file}...")
                    if create_screenshot(html_full_path, screenshot_full_path):
                        screenshot_file = screenshot_name
                elif screenshot_full_path.exists():
                    screenshot_file = screenshot_name

            results.append({
                "timestamp": data.get("timestamp"),
                "model": data.get("model"),
                "generation_time_seconds": data.get("generation_time_seconds"),
                "tokens_per_second": data.get("derived", {}).get("tokens_per_second"),
                "cost": data.get("cost"),
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "html_file": html_file,
                "screenshot_file": screenshot_file,
            })
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Skipping corrupted or incomplete file {json_file.name}: {e}")

    return {
        "prompt": prompt_text,
        "results": sorted(results, key=lambda x: x.get("timestamp") or "", reverse=True)
    }

def build_html_table(results):
    if not results:
        return '<p class="text-center p-4">No results yet. Benchmarks may be running...</p>'

    table = '<table id="data-table" class="table-auto w-full">'
    table += """
        <thead class="bg-gray-200">
            <tr>
                <th class="px-4 py-2" data-key="model">Model</th>
                <th class="px-4 py-2" data-key="generation_time_seconds">Time (s)</th>
                <th class="px-4 py-2" data-key="tokens_per_second">Tokens/s</th>
                <th class="px-4 py-2" data-key="cost">Cost ($)</th>
                <th class="px-4 py-2" data-key="prompt_tokens">Prompt Tokens</th>
                <th class="px-4 py-2" data-key="completion_tokens">Completion Tokens</th>
                <th class="px-4 py-2" data-key="timestamp">Timestamp</th>
                <th class="px-4 py-2">Output</th>
            </tr>
        </thead>
        <tbody>
        </tbody>
    """
    table += "</table>"
    return table

def update_report(results_dir: Path, create_screenshots: bool = True):
    report_dir = Path(results_dir)
    report_dir.mkdir(exist_ok=True)

    report_data = get_report_data(report_dir, create_screenshots=create_screenshots)

    table_html = build_html_table(report_data["results"])

    # Convert results to JSON for JavaScript
    data_json = json.dumps(report_data["results"])

    final_html = HTML_TEMPLATE.format(
        PROMPT=report_data.get('prompt', 'Not available.'),
        TABLE_CONTENT=table_html,
        DATA_JSON=data_json,
        TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    (report_dir / "index.html").write_text(final_html)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        create_screenshots = "--no-screenshots" not in sys.argv
        results_path = sys.argv[1]
        update_report(Path(results_path), create_screenshots=create_screenshots)
    else:
        print("Usage: python openrouter_report.py <path_to_results_dir> [--no-screenshots]")