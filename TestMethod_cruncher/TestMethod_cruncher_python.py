import base64
import json
import os
from datetime import datetime


SOURCE_FOLDER = r"C:\Users\maunahan\Projects\SOFTWARES\ETS88-HIB-Index-Parallel-Maintenance-Guide\TestMethod_txtfiles"
OUTPUT_HTML = r"C:\Users\maunahan\Projects\SOFTWARES\ETS88-HIB-Index-Parallel-Maintenance-Guide\TestMethod_cruncher\test_methods_report.html"
LOGO_FILE = r"C:\Users\maunahan\Projects\SOFTWARES\ETS88-HIB-Index-Parallel-Maintenance-Guide\TestMethod_cruncher\Infineon-Logo.svg"


def load_logo_data_uri(path):
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"
    except OSError:
        return ""


def _is_separator(inner):
    """Return True if comment-stripped line is just =, -, or | characters."""
    if not inner:
        return False
    cleaned = inner.replace("|", "").replace("-", "").replace("=", "").strip()
    return cleaned == ""


def parse_txt_structured(content):
    """Parse a TXT file into header info, section/table blocks, and notes.

    Section assignment rule:
    - Collect all comment-line titles (e.g. "Resource Status and Condition",
      "Relay Status") in document order.
    - Each occurrence of a `SECTORA` table marks the start of a new section,
      so SECTORA + SECTORB pairs are grouped under the same section label
      regardless of where the section header literally appears in the file.
    """
    lines = content.splitlines()
    header = []
    blocks = []
    section_titles = []
    notes_lines = []
    in_notes = False
    current_label = "General"

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()

        if in_notes:
            notes_lines.append(raw_line)
            i += 1
            continue

        lower = stripped.lower()
        if lower.startswith("additional notes") or lower.startswith("addtional notes"):
            in_notes = True
            i += 1
            continue

        # File-level header lines like "Test Function Name:  TF_xxx"
        if (
            not stripped.startswith("//")
            and ":" in stripped
            and "|" not in stripped
            and not blocks
        ):
            key, value = stripped.split(":", 1)
            if key.strip() and value.strip():
                header.append({"field": key.strip(), "value": value.strip()})
                i += 1
                continue

        if stripped.startswith("//"):
            inner = stripped[2:].strip()

            if not inner or _is_separator(inner):
                i += 1
                continue

            if "|" in inner:
                # Treat as table header row; next line should be a separator.
                header_cols = [c.strip() for c in inner.split("|")]
                sep_idx = i + 1
                sep_inner = ""
                if sep_idx < len(lines):
                    sep_line = lines[sep_idx].strip()
                    if sep_line.startswith("//"):
                        sep_inner = sep_line[2:].strip()

                if sep_inner and _is_separator(sep_inner) and "|" in sep_inner:
                    j = sep_idx + 1
                    rows = []
                    while j < len(lines):
                        row_line = lines[j].strip()
                        if not row_line.startswith("//"):
                            break
                        row_inner = row_line[2:].strip()
                        if not row_inner or _is_separator(row_inner) or "|" not in row_inner:
                            break
                        cells = [c.strip() for c in row_inner.split("|")]
                        if len(cells) < len(header_cols):
                            cells += [""] * (len(header_cols) - len(cells))
                        else:
                            cells = cells[: len(header_cols)]

                        # Expand shorthand by copying the corresponding value from the cell to the left.
                        for idx in range(1, len(cells)):
                            if cells[idx].strip().lower() in {"same as oldhib-a", "same as oldhib-b"}:
                                cells[idx] = cells[idx - 1]

                        rows.append(cells)
                        j += 1

                    blocks.append(
                        {
                            "section": None,  # resolved after parsing
                            "title": current_label,
                            "columns": header_cols,
                            "rows": rows,
                        }
                    )
                    i = j
                    continue

            # Title line (Section or Table label).
            if inner.upper().endswith("TABLE"):
                current_label = inner
            else:
                section_titles.append(inner)
                current_label = inner
            i += 1
            continue

        i += 1

    # Assign section labels: a new section starts at every SECTORA table.
    section_idx = -1
    for block in blocks:
        title_upper = (block["title"] or "").upper()
        if "SECTORA" in title_upper:
            section_idx += 1
        effective_idx = max(section_idx, 0)
        if section_titles:
            block["section"] = section_titles[min(effective_idx, len(section_titles) - 1)]
        else:
            block["section"] = "General"

    notes_text = "\n".join(notes_lines).strip()
    return {"header": header, "blocks": blocks, "notes": notes_text}


def collect_txt_file_details(folder_path):
    """Read every .txt file from a folder and return embedded structured details."""
    records = []

    for entry in sorted(os.listdir(folder_path)):
        if not entry.lower().endswith(".txt"):
            continue

        full_path = os.path.join(folder_path, entry)
        if not os.path.isfile(full_path):
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()

            stats = os.stat(full_path)
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            parsed = parse_txt_structured(content)
            table_count = len(parsed["blocks"])
            total_data_rows = sum(len(block["rows"]) for block in parsed["blocks"])

            records.append(
                {
                    "name": entry,
                    "size_kb": round(stats.st_size / 1024, 2),
                    "line_count": line_count,
                    "modified": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "table_count": table_count,
                    "row_count": total_data_rows,
                    "header": parsed["header"],
                    "blocks": parsed["blocks"],
                    "notes": parsed["notes"],
                }
            )
        except Exception as exc:
            print(f"Warning: could not read {full_path}: {exc}")

    return records


def build_catalog_rows(files):
    """Render the top catalog summary table HTML."""
    rows = []
    for item in files:
        rows.append(
            "<tr>"
            f"<td>{item['name']}</td>"
            f"<td>{item['size_kb']:.2f}</td>"
            f"<td>{item['line_count']}</td>"
            f"<td>{item['table_count']}</td>"
            f"<td>{item['row_count']}</td>"
            f"<td>{item['modified']}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def create_html_page(folder_path, output_file):
    files = collect_txt_file_details(folder_path)
    if not files:
        print("No .txt files found to include in the report.")
        return

    first_file_name = files[0]["name"]
    files_json = json.dumps(files, ensure_ascii=False)
    file_options_html = "\n".join(
        [f'                <option value="{item["name"]}">{os.path.splitext(item["name"])[0]}</option>' for item in files]
    )
    catalog_rows_html = build_catalog_rows(files)
    logo_src = load_logo_data_uri(LOGO_FILE)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TXT File Explorer - Electronics Theme</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
            color: #0f2540;
            background:
                radial-gradient(circle at 12% 10%, #e6f0ff 0, transparent 40%),
                radial-gradient(circle at 88% 8%, #e8f9f3 0, transparent 35%),
                linear-gradient(160deg, #eef4fb, #dbe7f5);
            min-height: 100vh;
            padding: 22px;
            font-size: 15.5px;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}

        .layout {{ max-width: 1280px; margin: 0 auto; display: grid; gap: 18px; }}

        .panel {{
            background: #ffffff;
            border: 1px solid #c9d8e8;
            border-radius: 14px;
            box-shadow: 0 6px 20px rgba(15, 37, 64, 0.08);
            overflow: hidden;
        }}

        .header {{
            padding: 26px 28px;
            border-left: 5px solid #0a66c2;
            background: linear-gradient(90deg, #f0f7ff, #f4fbff);
            border-bottom: 1px solid #c9d8e8;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
        }}

        .header .header-text {{ flex: 1; min-width: 0; }}

        .header .brand-logo {{
            height: 44px;
            width: auto;
            flex-shrink: 0;
        }}

        .header h1 {{
            font-size: 1.95rem;
            color: #0a66c2;
            margin-bottom: 6px;
            letter-spacing: 0.2px;
            font-weight: 700;
        }}

        .prepared-by {{
            color: #1f8a3b;
            font-weight: 700;
            font-size: 0.98rem;
        }}

        .controls {{ padding: 18px 28px 22px; display: grid; gap: 10px; }}
        .controls label {{
            color: #0a66c2;
            font-weight: 700;
            font-size: 0.98rem;
        }}
        .controls select {{
            background: #ffffff;
            color: #0f2540;
            border: 1px solid #c9d8e8;
            border-radius: 8px;
            padding: 11px 12px;
            font-size: 0.98rem;
            font-weight: 600;
            box-shadow: 0 1px 2px rgba(15, 37, 64, 0.05);
        }}
        .controls select:focus {{
            outline: 2px solid #0a66c2;
            outline-offset: 1px;
        }}
        .controls p {{ color: #4a6b8a; font-size: 0.88rem; }}

        .stats {{
            display: grid;
            gap: 12px;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            padding: 0 28px 22px;
        }}
        .stat {{
            border: 1px solid #c9d8e8;
            background: #f9fcff;
            border-radius: 10px;
            padding: 12px 14px;
            box-shadow: 0 1px 2px rgba(15, 37, 64, 0.04);
        }}
        .stat .label {{
            color: #4a6b8a;
            font-size: 0.78rem;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            font-weight: 700;
        }}
        .stat .value {{
            color: #0a66c2;
            font-size: 1.08rem;
            font-weight: 700;
            word-break: break-word;
        }}

        .section-title {{
            margin: 10px 28px 12px;
            color: #ffffff;
            font-weight: 800;
            font-size: 1.1rem;
            letter-spacing: 0.4px;
            padding: 10px 14px;
            background: linear-gradient(90deg, #0a66c2, #1e88e5);
            border: 2px solid #0a66c2;
            border-radius: 8px;
            text-transform: uppercase;
            box-shadow: 0 2px 6px rgba(10, 102, 194, 0.25);
        }}

        .table-wrap {{
            margin: 0 28px 18px;
            border: 1px solid #c9d8e8;
            border-radius: 10px;
            overflow-x: auto;
            overflow-y: hidden;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(15, 37, 64, 0.04);
        }}

        .table-scroll {{ overflow: auto; max-height: none; }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
        }}

        thead {{
            background: linear-gradient(90deg, #eaf3ff, #e6f7f5);
            position: sticky;
            top: 0;
        }}

        th, td {{
            padding: 10px 14px;
            border-bottom: 1px solid #c9d8e8;
            vertical-align: middle;
            text-align: left;
            color: #0f2540;
            white-space: nowrap;
        }}

        th {{
            color: #0a66c2;
            font-weight: 700;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            white-space: nowrap;
        }}

        tbody tr:nth-child(even) {{ background: #f4f8fc; }}
        tbody tr:hover {{ background: #e4f1ff; }}

        td.first-col {{
            color: #c46a00;
            font-weight: 700;
            white-space: nowrap;
        }}

        /* Freeze the first (Test Number) column when scrolling horizontally. */
        .table-scroll table td.first-col,
        .table-scroll table thead th:first-child {{
            position: sticky;
            left: 0;
            z-index: 2;
            background: #ffffff;
            box-shadow: 2px 0 4px rgba(15, 37, 64, 0.08);
        }}
        .table-scroll table thead th:first-child {{
            z-index: 3;
            background: #eaf3ff;
        }}
        .table-scroll table tbody tr:nth-child(even) td.first-col {{
            background: #f4f8fc;
        }}
        .table-scroll table tbody tr:hover td.first-col {{
            background: #e4f1ff;
        }}

        .badge {{
            display: inline-block;
            padding: 2px 9px;
            border-radius: 12px;
            font-size: 0.74rem;
            border: 1px solid #0a9396;
            color: #0a9396;
            background: #effaf9;
            margin-left: 8px;
            font-weight: 700;
        }}

        .skipped {{
            color: #c0392b;
            font-weight: 700;
            background: #fdecea;
            border: 1px solid #f3c2bd;
            border-radius: 4px;
            padding: 1px 6px;
        }}

        .table-block-title {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 11px 16px;
            background: #eaf3ff;
            color: #0a66c2;
            font-weight: 800;
            font-size: 1rem;
            border-bottom: 2px solid #0a66c2;
        }}

        .notes-box {{
            margin: 0 28px 24px;
            padding: 14px 16px;
            border: 1px solid #c9d8e8;
            border-radius: 10px;
            background: #fbfcfe;
            color: #0f2540;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 0.92rem;
            white-space: pre-wrap;
            line-height: 1.55;
        }}

        .empty {{ color: #4a6b8a; padding: 16px; text-align: center; font-style: italic; }}

        .footer {{
            padding: 14px 28px 20px;
            color: #4a6b8a;
            font-size: 0.88rem;
            border-top: 1px solid #c9d8e8;
            background: #f7fafd;
        }}

        @media (max-width: 768px) {{
            body {{ padding: 12px; font-size: 14.5px; }}
            .header h1 {{ font-size: 1.45rem; }}
            .controls, .stats {{ padding-left: 16px; padding-right: 16px; }}
            .table-wrap, .section-title, .notes-box {{ margin-left: 14px; margin-right: 14px; }}
        }}
    </style>
</head>
<body>
    <main class="layout">
        <section class="panel">
            <header class="header">
                <div class="header-text">
                    <h1>ETS88 HIB Index Parallel Maintenance Guide</h1>
                    <p class="prepared-by">Prepared by: Cromwel Miranda Maunahan (ATV MOS D TE)</p>
                    <p class="prepared-by">Last Modified: <span id="metaModified">-</span></p>
                </div>
                <img class="brand-logo"
                     src="{logo_src}"
                     alt="Infineon Technologies AG" />
            </header>

            <div class="controls">
                <label for="sectorSelect">Select Sector</label>
                <select id="sectorSelect">
                    <option value="ALL">Show Both Sectors</option>
                    <option value="SECTORA">SECTORA only</option>
                    <option value="SECTORB">SECTORB only</option>
                </select>
                <label for="hibSelect" style="margin-top:8px;">Select HIB Type</label>
                <select id="hibSelect">
                    <option value="ALL">Show Both (OldHIB &amp; NewHIB)</option>
                    <option value="OLDHIB">OldHIB only</option>
                    <option value="NEWHIB">NewHIB only</option>
                </select>
                <label for="fileSelect" style="margin-top:8px;">Select Test Label</label>
                <select id="fileSelect">
{file_options_html}
                </select>
                <p>This report is standalone: all TXT data is embedded directly in this HTML file.</p>
            </div>

            <h2 class="section-title">File Header Info</h2>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr><th style="width:30%">Field</th><th>Value</th></tr>
                    </thead>
                    <tbody id="headerBody"></tbody>
                </table>
            </div>

            <div id="blocksContainer"></div>

            <h2 class="section-title">Additional Notes</h2>
            <div class="notes-box" id="notesBox"></div>

            <footer class="footer">
                Each ASCII table inside the TXT is parsed and displayed as a clean HTML table for easy reading.
            </footer>
        </section>
    </main>

    <script>
        var files = {files_json};
        var fileSelect = document.getElementById("fileSelect");
        var hibSelect = document.getElementById("hibSelect");
        var sectorSelect = document.getElementById("sectorSelect");
        var metaModified = document.getElementById("metaModified");
        var headerBody = document.getElementById("headerBody");
        var blocksContainer = document.getElementById("blocksContainer");
        var notesBox = document.getElementById("notesBox");

        function strIncludes(haystack, needle) {{
            return String(haystack).indexOf(needle) !== -1;
        }}

        function escapeHtml(value) {{
            var text = (value === null || value === undefined) ? "" : String(value);
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }}

        function renderCell(value, isFirst) {{
            var safe = escapeHtml(value);
            var decorated = safe.replace(/\\[SKIPPED\\]/g, '<span class="skipped">[SKIPPED]</span>');
            var cls = isFirst ? ' class="first-col"' : '';
            return '<td' + cls + '>' + (decorated || '&nbsp;') + '</td>';
        }}

        function getVisibleIndexes(columns) {{
            var hib = hibSelect.value;
            var out = [];
            for (var idx = 0; idx < columns.length; idx++) {{
                if (idx === 0) {{ out.push(idx); continue; }}
                var upper = String(columns[idx]).toUpperCase();
                if (hib === "ALL") {{ out.push(idx); }}
                else if (hib === "OLDHIB" && strIncludes(upper, "OLDHIB")) {{ out.push(idx); }}
                else if (hib === "NEWHIB" && strIncludes(upper, "NEWHIB")) {{ out.push(idx); }}
            }}
            return out;
        }}

        function renderBlock(block) {{
            var visible = getVisibleIndexes(block.columns);
            var cols = [];
            for (var i = 0; i < visible.length; i++) {{ cols.push(block.columns[visible[i]]); }}

            var headParts = [];
            for (var h = 0; h < cols.length; h++) {{ headParts.push('<th>' + escapeHtml(cols[h]) + '</th>'); }}
            var head = '<tr>' + headParts.join('') + '</tr>';

            var body;
            if (block.rows.length === 0) {{
                body = '<tr><td colspan="' + cols.length + '" class="empty">No rows in this table.</td></tr>';
            }} else {{
                var rowParts = [];
                for (var r = 0; r < block.rows.length; r++) {{
                    var row = block.rows[r];
                    var cellParts = [];
                    for (var ci = 0; ci < visible.length; ci++) {{
                        cellParts.push(renderCell(row[visible[ci]], ci === 0));
                    }}
                    rowParts.push('<tr>' + cellParts.join('') + '</tr>');
                }}
                body = rowParts.join('');
            }}

            return (
                '<div class="table-wrap">' +
                    '<div class="table-block-title">' +
                        '<span>' + escapeHtml(block.title) + '</span>' +
                        '<span class="badge">' + escapeHtml(block.section) + '</span>' +
                    '</div>' +
                    '<div class="table-scroll">' +
                        '<table>' +
                            '<thead>' + head + '</thead>' +
                            '<tbody>' + body + '</tbody>' +
                        '</table>' +
                    '</div>' +
                '</div>'
            );
        }}

        function groupBySection(blocks) {{
            var order = [];
            var map = {{}};
            for (var i = 0; i < blocks.length; i++) {{
                var s = blocks[i].section;
                if (!Object.prototype.hasOwnProperty.call(map, s)) {{
                    map[s] = [];
                    order.push(s);
                }}
                map[s].push(blocks[i]);
            }}
            return {{ order: order, map: map }};
        }}

        function findFileByName(name) {{
            for (var i = 0; i < files.length; i++) {{
                if (files[i].name === name) return files[i];
            }}
            return null;
        }}

        function renderSelectedFile(fileName) {{
            var selected = findFileByName(fileName);
            if (!selected) return;

            metaModified.innerHTML = escapeHtml(selected.modified);

            if (selected.header && selected.header.length) {{
                var hdrParts = [];
                for (var i = 0; i < selected.header.length; i++) {{
                    var h = selected.header[i];
                    hdrParts.push('<tr><td class="first-col">' + escapeHtml(h.field) + '</td><td>' + escapeHtml(h.value) + '</td></tr>');
                }}
                headerBody.innerHTML = hdrParts.join('');
            }} else {{
                headerBody.innerHTML = '<tr><td colspan="2" class="empty">No header fields detected.</td></tr>';
            }}

            if (!selected.blocks || selected.blocks.length === 0) {{
                blocksContainer.innerHTML = '<h2 class="section-title">Parsed Tables</h2>' +
                    '<div class="table-wrap"><div class="empty">No structured tables detected in this file.</div></div>';
            }} else {{
                var sectorFilter = sectorSelect.value;
                var filteredBlocks = [];
                for (var b = 0; b < selected.blocks.length; b++) {{
                    var blk = selected.blocks[b];
                    if (sectorFilter === "ALL" || strIncludes(String(blk.title || "").toUpperCase(), sectorFilter)) {{
                        filteredBlocks.push(blk);
                    }}
                }}
                if (filteredBlocks.length === 0) {{
                    blocksContainer.innerHTML = '<div class="table-wrap"><div class="empty">No tables match the selected sector.</div></div>';
                }} else {{
                    var grouped = groupBySection(filteredBlocks);
                    var html = '';
                    for (var gi = 0; gi < grouped.order.length; gi++) {{
                        var section = grouped.order[gi];
                        html += '<h2 class="section-title">' + escapeHtml(section) + '</h2>';
                        var arr = grouped.map[section];
                        for (var ai = 0; ai < arr.length; ai++) {{
                            html += renderBlock(arr[ai]);
                        }}
                    }}
                    blocksContainer.innerHTML = html;
                }}
            }}

            var notesText = (selected.notes && selected.notes.length) ? selected.notes : 'No additional notes found in this file.';
            if ('textContent' in notesBox) {{ notesBox.textContent = notesText; }}
            else {{ notesBox.innerText = notesText; }}
        }}

        function onFileChange(event) {{
            var target = event.target || event.srcElement;
            renderSelectedFile(target.value);
        }}
        function onHibChange() {{ renderSelectedFile(fileSelect.value); }}
        function onSectorChange() {{ renderSelectedFile(fileSelect.value); }}

        if (fileSelect.addEventListener) {{
            fileSelect.addEventListener("change", onFileChange, false);
            hibSelect.addEventListener("change", onHibChange, false);
            sectorSelect.addEventListener("change", onSectorChange, false);
        }} else if (fileSelect.attachEvent) {{
            fileSelect.attachEvent("onchange", function () {{ renderSelectedFile(fileSelect.value); }});
            hibSelect.attachEvent("onchange", onHibChange);
            sectorSelect.attachEvent("onchange", onSectorChange);
        }}

        fileSelect.value = {json.dumps(first_file_name)};
        renderSelectedFile(fileSelect.value);
    </script>
</body>
</html>
"""

    try:
        with open(output_file, "w", encoding="utf-8") as handle:
            handle.write(html_content)
        print(f"HTML report created successfully: {output_file}")
        print(f"Total TXT files included: {len(files)}")
    except Exception as exc:
        print(f"Error writing HTML file: {exc}")


if __name__ == "__main__":
    if os.path.exists(SOURCE_FOLDER):
        create_html_page(SOURCE_FOLDER, OUTPUT_HTML)
    else:
        print(f"Folder not found: {SOURCE_FOLDER}")
