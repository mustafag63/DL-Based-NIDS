"""
Builds DOCUMENTATION.html (self-contained, base64-embedded images) from
DOCUMENTATION.md, then renders DOCUMENTATION.pdf via headless Chrome.
Not part of the analysis pipeline -- a one-off report-build helper.
"""
import base64
import mimetypes
import os
import re
import subprocess

import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(HERE, "DOCUMENTATION.md")
HTML_PATH = os.path.join(HERE, "DOCUMENTATION.html")
PDF_PATH = os.path.join(HERE, "DOCUMENTATION.pdf")

with open(MD_PATH, encoding="utf-8") as f:
    md_text = f.read()


def embed_image(match):
    alt, src = match.group(1), match.group(2)
    img_path = os.path.normpath(os.path.join(HERE, src))
    with open(img_path, "rb") as img_f:
        data = base64.b64encode(img_f.read()).decode("ascii")
    mime = mimetypes.guess_type(img_path)[0] or "image/png"
    return f"![{alt}](data:{mime};base64,{data})"


md_text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", embed_image, md_text)

body_html = markdown.markdown(
    md_text,
    extensions=["tables", "fenced_code", "toc"],
)

title = "NIDS Projesi — Attack-Type Analizi ve apache_bench Kök Neden Analizi"

html = f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
@page {{
  size: A4;
  margin: 20mm 18mm 22mm 18mm;
  @bottom-center {{
    content: counter(page) " / " counter(pages);
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 9pt;
    color: #666;
  }}
}}

* {{ box-sizing: border-box; }}

html, body {{
  font-family: -apple-system, "Helvetica Neue", "Segoe UI", Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #1a1a1a;
}}

.cover {{
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 245mm;
  text-align: center;
}}
.cover h1 {{
  font-size: 26pt;
  margin-bottom: 0.4em;
  max-width: 80%;
  color: #111;
}}
.cover .subtitle {{
  font-size: 13pt;
  color: #444;
  margin-bottom: 2.2em;
}}
.cover .meta {{
  font-size: 11pt;
  color: #666;
  border-top: 1px solid #ccc;
  padding-top: 1em;
  margin-top: 2em;
}}
.cover .badge {{
  display: inline-block;
  background: #eef2ff;
  color: #3730a3;
  padding: 4px 14px;
  border-radius: 999px;
  font-size: 10pt;
  margin-bottom: 2em;
}}

h1 {{
  font-size: 19pt;
  color: #111;
  border-bottom: 2px solid #333;
  padding-bottom: 6px;
  margin-top: 1.4em;
  page-break-before: always;
}}
h1:first-of-type {{ page-break-before: avoid; }}
h2 {{
  font-size: 14.5pt;
  color: #1a1a1a;
  margin-top: 1.6em;
  border-left: 4px solid #4f46e5;
  padding-left: 10px;
}}
h3 {{
  font-size: 12pt;
  color: #222;
  margin-top: 1.3em;
}}

p {{ margin: 0.7em 0; text-align: justify; }}

table {{
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  font-size: 9pt;
  page-break-inside: avoid;
}}
th, td {{
  border: 1px solid #ccc;
  padding: 5px 7px;
  text-align: left;
}}
th {{
  background: #f3f4f6;
  font-weight: 600;
}}
tr:nth-child(even) td {{ background: #fafafa; }}

code {{
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 90%;
  font-family: "SF Mono", Menlo, Consolas, monospace;
}}

img {{
  max-width: 100%;
  display: block;
  margin: 1em auto;
  border: 1px solid #ddd;
  border-radius: 4px;
  page-break-inside: avoid;
}}

em {{ color: #444; }}

hr {{
  border: none;
  border-top: 1px solid #ddd;
  margin: 2em 0;
}}

a {{ color: #4338ca; text-decoration: none; }}

.toc-page {{
  page-break-after: always;
}}
.toc-page h2 {{
  border-left: none;
  padding-left: 0;
  font-size: 18pt;
}}
.toc-page ul {{
  list-style: none;
  padding-left: 0;
}}
.toc-page li {{
  margin: 0.5em 0;
  font-size: 11.5pt;
}}
.toc-page li a {{
  color: #1a1a1a;
}}
.toc-page ul ul {{
  padding-left: 1.4em;
  font-size: 10.5pt;
  color: #444;
}}
</style>
</head>
<body>

<div class="cover">
  <div class="badge">Teknik Dokümantasyon</div>
  <h1>NIDS Projesi<br>Attack-Type Analizi, Segmented Injection ve<br>apache_bench Kök Neden Analizi</h1>
  <div class="subtitle">VAE (clean-only, 20 seed) ve Dense Autoencoder v1 (5 seed) — Inference-Only Değerlendirme</div>
  <div class="meta">28 Temmuz 2026<br>Kapsam: 06_attack_type_analysis / 07_segmented_injection / 08_dense_v1_comparison / 04_apache_bench_diagnostics</div>
</div>

<div class="toc-page">
{{TOC}}
</div>

{body_html}
</body>
</html>
"""

toc_html = markdown.markdown(md_text, extensions=["toc"]).__class__ and None
md_converter = markdown.Markdown(extensions=["toc", "tables", "fenced_code"])
md_converter.convert(md_text)
toc = md_converter.toc
html = html.replace("{TOC}", "<h2>İçindekiler</h2>" + toc)

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"HTML written: {HTML_PATH} ({os.path.getsize(HTML_PATH)/1e6:.2f} MB)")

chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
subprocess.run(
    [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        "--print-to-pdf-no-header",
        "--no-sandbox",
        f"file://{HTML_PATH}",
    ],
    check=True,
    timeout=120,
)

print(f"PDF written: {PDF_PATH} ({os.path.getsize(PDF_PATH)/1e6:.2f} MB)")
