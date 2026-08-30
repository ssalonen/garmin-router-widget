#!/usr/bin/env python3
"""Generate a self-contained HTML e2e report and a GitHub step-summary fragment.

Usage:
    python3 gen_report.py --screenshots DIR [--log FILE] --output HTML

The script:
  - Embeds every *.png in DIR as a base64 data URI (no external dependencies).
  - Colorises the test log (PASS green / FAIL red / INFO blue / WARN amber).
  - Writes the complete page to --output.
  - Prints a Markdown+HTML step-summary fragment to stdout (pipe to
    $GITHUB_STEP_SUMMARY).  GitHub renders data-URI <img> tags in step
    summaries, so the screenshots appear inline in the Actions UI.
"""

import argparse
import base64
import html
import re
import sys
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _colorise(log: str) -> str:
    out = []
    for raw in log.splitlines():
        esc = html.escape(raw)
        if "[assert] PASS" in raw:
            esc = f'<span class="pass">{esc}</span>'
        elif "[assert] FAIL" in raw or ("FAIL" in raw and "[e2e]" in raw):
            esc = f'<span class="fail">{esc}</span>'
        elif raw.startswith("ERROR:"):
            esc = f'<span class="fail">{esc}</span>'
        elif raw.startswith("INFO:"):
            esc = f'<span class="info">{esc}</span>'
        elif raw.startswith("WARN:"):
            esc = f'<span class="warn">{esc}</span>'
        out.append(esc)
    return "\n".join(out)


def _label(line: str, pattern: str) -> str:
    m = re.search(rf"{pattern} '([^']+)'", line)
    return m.group(1) if m else line.strip()


def _parse_screenshot_assertions(log: str) -> dict:
    """Return {screenshot_stem: [("PASS"|"FAIL", label), ...]} from the log.

    Assertions are attributed to the most-recently-seen screenshot line, so
    each assertion ends up under the image that was captured just before it.
    """
    mapping: dict = {}
    current = None
    for raw in log.splitlines():
        m = re.search(r'\[e2e\] Screenshot: (\S+?)\.png', raw)
        if m:
            current = m.group(1)
            mapping.setdefault(current, [])
            continue
        if current is None:
            continue
        m = re.search(r'\[assert\] (PASS|FAIL) \'([^\']+)\'', raw)
        if m:
            mapping[current].append((m.group(1), m.group(2)))
    return mapping


# ── HTML template ─────────────────────────────────────────────────────────────

_CSS = """
body{font-family:monospace;background:#1a1a1a;color:#e0e0e0;margin:20px;max-width:1400px}
h1,h2{color:#fff}
.badge{display:inline-block;padding:4px 10px;border-radius:4px;font-weight:bold;margin-bottom:8px}
.badge.ok{background:#2e7d32;color:#fff}
.badge.fail{background:#b71c1c;color:#fff}
.grid{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0;align-items:flex-start}
.shot{text-align:center;max-width:300px}
.shot img{max-height:260px;border:1px solid #444;display:block;cursor:zoom-in;width:100%}
.shot-name{margin:6px 0 4px;font-size:.82em;color:#aaa;font-weight:bold}
.shot-asserts{text-align:left;margin-top:4px}
.assert-row{font-size:.78em;margin:2px 0;display:flex;gap:4px;align-items:baseline}
.assert-row .icon{flex-shrink:0}
.assert-row .alabel{color:#ccc}
.assert-row.ok .alabel{color:#66bb6a}
.assert-row.fail .alabel{color:#ef5350;font-weight:bold}
.no-assert{font-size:.76em;color:#555;font-style:italic;margin-top:4px}
.log-wrap{position:relative}
pre{background:#111;padding:14px;overflow-x:auto;white-space:pre-wrap;
    word-break:break-all;font-size:.80em;line-height:1.5;border-radius:4px}
.copy-btn{position:absolute;top:8px;right:8px;padding:4px 10px;font-size:.78em;
    font-family:monospace;background:#333;color:#ccc;border:1px solid #555;
    border-radius:3px;cursor:pointer;user-select:none}
.copy-btn:hover{background:#444;color:#fff}
.copy-btn.ok{background:#2e7d32;color:#fff;border-color:#2e7d32}
.pass{color:#66bb6a}
.fail{color:#ef5350;font-weight:bold}
.info{color:#42a5f5}
.warn{color:#ffa726}
table{border-collapse:collapse;margin:12px 0}
td,th{border:1px solid #444;padding:6px 12px;text-align:left}
th{background:#222}
"""

_JS = """
document.querySelectorAll('.copy-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const text = btn.closest('.log-wrap').querySelector('pre').innerText;
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('ok');
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('ok'); }, 2000);
    });
  });
});
"""


def _build_html(pngs, log_html, pass_lines, fail_lines,
                shot_asserts=None, title="E2E Test Report"):
    shot_asserts = shot_asserts or {}
    overall_cls = "ok" if not fail_lines else "fail"
    overall_txt = "PASS" if not fail_lines else f"FAIL — {len(fail_lines)} assertion(s) failed"

    rows = ""
    for line in pass_lines:
        rows += f"<tr><td>✅</td><td>{html.escape(_label(line, 'PASS'))}</td></tr>\n"
    for line in fail_lines:
        rows += f"<tr><td>❌</td><td>{html.escape(_label(line, 'FAIL'))}</td></tr>\n"

    shots = ""
    for idx, (stem, data) in enumerate(pngs, 1):
        asserts = shot_asserts.get(stem, [])
        assert_html = ""
        if asserts:
            for status, lbl in asserts:
                icon = "✅" if status == "PASS" else "❌"
                cls  = "ok" if status == "PASS" else "fail"
                assert_html += (
                    f'<div class="assert-row {cls}">'
                    f'<span class="icon">{icon}</span>'
                    f'<span class="alabel">{html.escape(lbl)}</span>'
                    f'</div>\n'
                )
        else:
            assert_html = '<p class="no-assert">— no assertions</p>\n'

        shots += (
            f'<div class="shot">'
            f'<img src="data:image/png;base64,{data}" alt="{html.escape(stem)}">'
            f'<p class="shot-name">#{idx} {html.escape(stem)}</p>'
            f'<div class="shot-asserts">{assert_html}</div>'
            f'</div>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="badge {overall_cls}">{overall_txt}</div>
<p>{len(pass_lines)} passed &nbsp;·&nbsp; {len(fail_lines)} failed &nbsp;·&nbsp; {len(pngs)} screenshots</p>

<table>
<tr><th>Result</th><th>Assertion</th></tr>
{rows}
</table>

<h2>Screenshots</h2>
<div class="grid">
{shots}
</div>

<h2>Full test output</h2>
<div class="log-wrap">
<button class="copy-btn">Copy</button>
<pre>{log_html}</pre>
</div>
</body>
<script>{_JS}</script>
</html>"""


# ── step-summary fragment (printed to stdout → $GITHUB_STEP_SUMMARY) ──────────

def _colorise_inline(log: str) -> str:
    """Like _colorise but uses inline styles (safe for GitHub step summaries)."""
    styles = {
        "pass": "color:#66bb6a",
        "fail": "color:#ef5350;font-weight:bold",
        "info": "color:#42a5f5",
        "warn": "color:#ffa726",
    }
    out = []
    for raw in log.splitlines():
        esc = html.escape(raw)
        if "[assert] PASS" in raw:
            esc = f'<span style="{styles["pass"]}">{esc}</span>'
        elif "[assert] FAIL" in raw or ("FAIL" in raw and "[e2e]" in raw):
            esc = f'<span style="{styles["fail"]}">{esc}</span>'
        elif raw.startswith("ERROR:"):
            esc = f'<span style="{styles["fail"]}">{esc}</span>'
        elif raw.startswith("INFO:"):
            esc = f'<span style="{styles["info"]}">{esc}</span>'
        elif raw.startswith("WARN:"):
            esc = f'<span style="{styles["warn"]}">{esc}</span>'
        out.append(esc)
    return "\n".join(out)


def _build_summary(pngs, pass_lines, fail_lines, shot_asserts=None, log_raw=""):
    shot_asserts = shot_asserts or {}
    overall = "✅ PASS" if not fail_lines else f"❌ FAIL ({len(fail_lines)} assertion(s) failed)"
    lines = [
        f"## E2E Test Report — {overall}",
        "",
        "| | Assertion |",
        "|-|-----------|",
    ]
    for l in pass_lines:
        lines.append(f"| ✅ | {_label(l, 'PASS')} |")
    for l in fail_lines:
        lines.append(f"| ❌ | {_label(l, 'FAIL')} |")
    lines += ["", "### Screenshots", ""]
    for idx, (stem, data) in enumerate(pngs, 1):
        asserts = shot_asserts.get(stem, [])
        # Header line: number + name
        lines.append(f"**#{idx} {stem}**  ")
        lines.append(
            f'<img src="data:image/png;base64,{data}" '
            f'alt="{html.escape(stem)}" height="220">  '
        )
        # Assertion results under the image
        if asserts:
            for status, lbl in asserts:
                icon = "✅" if status == "PASS" else "❌"
                lines.append(f"{icon} {html.escape(lbl)}  ")
        else:
            lines.append("*— no assertions*  ")
        lines.append("")
    if log_raw:
        log_html = _colorise_inline(log_raw)
        lines += [
            "",
            "<details><summary>Full test log</summary>",
            "",
            f'<pre style="background:#111;color:#e0e0e0;padding:12px;'
            f'font-size:.80em;line-height:1.5;white-space:pre-wrap;'
            f'word-break:break-all;border-radius:4px">{log_html}</pre>',
            "",
            "</details>",
        ]
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", required=True, help="Directory of *.png files")
    ap.add_argument("--log", help="Path to the captured test-run log file")
    ap.add_argument("--output", required=True, help="Output HTML file path")
    args = ap.parse_args()

    scr_dir = Path(args.screenshots)
    out = Path(args.output)

    pngs = [(p.stem, _b64(p)) for p in sorted(scr_dir.glob("*.png"))]

    log_raw = ""
    if args.log:
        lp = Path(args.log)
        if lp.exists():
            log_raw = lp.read_text(errors="replace")

    pass_lines = [l for l in log_raw.splitlines() if "[assert] PASS" in l]
    fail_lines = [l for l in log_raw.splitlines() if "[assert] FAIL" in l]
    shot_asserts = _parse_screenshot_assertions(log_raw)

    log_html = _colorise(log_raw) if log_raw else "(no log captured)"

    out.write_text(_build_html(pngs, log_html, pass_lines, fail_lines, shot_asserts))
    print(f"[gen_report] wrote {out} ({out.stat().st_size // 1024} KB)", file=sys.stderr)

    # stdout → caller pipes to $GITHUB_STEP_SUMMARY
    print(_build_summary(pngs, pass_lines, fail_lines, shot_asserts, log_raw))


if __name__ == "__main__":
    main()
