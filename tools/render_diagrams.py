#!/usr/bin/env python3
"""Render Mermaid (.mmd) diagrams to PNG using headless Google Chrome.

No Node/mermaid-cli needed: loads mermaid from jsDelivr inside Chrome,
measures the SVG in a first pass, screenshots at exact size in a second.

Usage:
    python3 tools/render_diagrams.py                 # all tristhana_bot_*.mmd in the notes attachments
    python3 tools/render_diagrams.py path/to/x.mmd   # specific files
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ATTACHMENTS = Path("/home/pumpkin_vibe/Documents/pumpkin_notes/attachments")
CHROME = "google-chrome"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
SCALE = 2

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;background:#fff;font-family:'DejaVu Sans',sans-serif}}#d{{display:inline-block;padding:24px}}</style>
<script src="{mermaid}"></script></head><body><div id="d" style="{style}"><pre class="mermaid">{src}</pre></div>
<script>
mermaid.initialize({{startOnLoad:false, theme:'default', securityLevel:'loose',
  flowchart:{{useMaxWidth:false, htmlLabels:true}}, er:{{useMaxWidth:false}},
  sequence:{{useMaxWidth:false}}, gantt:{{useMaxWidth:false, leftPadding:220, barHeight:26, barGap:8, fontSize:14, sectionFontSize:15}}}});
mermaid.run().then(() => {{
  const r = document.getElementById('d').getBoundingClientRect();
  document.title = 'SIZE:' + JSON.stringify([Math.ceil(r.width), Math.ceil(r.height)]);
}}).catch(e => {{ document.title = 'ERR:' + (e && (e.message || e.str) || e); }});
</script></body></html>"""


def chrome(args):
    return subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", "--virtual-time-budget=15000", *args],
        capture_output=True, text=True, timeout=120,
    )


def render(mmd: Path) -> Path:
    src = mmd.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "d.html"
        page.write_text(PAGE.format(mermaid=MERMAID, src=html.escape(src),
                                   style="width:1800px" if "gantt" in src else ""), encoding="utf-8")
        dom = chrome(["--window-size=4000,4000", "--dump-dom", page.as_uri()]).stdout
        m = re.search(r"<title>(.*?)</title>", dom, re.S)
        title = html.unescape(m.group(1)) if m else ""
        if not title.startswith("SIZE:"):
            raise RuntimeError(f"{mmd.name}: mermaid failed: {title or 'no output'}")
        w, h = json.loads(title[5:])
        out = mmd.with_suffix(".png")
        chrome([f"--window-size={w},{h}", f"--force-device-scale-factor={SCALE}",
                f"--screenshot={out}", page.as_uri()])
    img = Image.open(out).convert("RGB")
    bbox = Image.eval(img, lambda p: 255 - p).getbbox()  # trim white margins
    if bbox:
        pad = 16 * SCALE
        img = img.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0),
                        min(bbox[2] + pad, img.width), min(bbox[3] + pad, img.height)))
    img.save(out, optimize=True)
    return out


if __name__ == "__main__":
    files = [Path(a) for a in sys.argv[1:]] or sorted(ATTACHMENTS.glob("tristhana_bot_*.mmd"))
    for f in files:
        print("rendered", render(f))
