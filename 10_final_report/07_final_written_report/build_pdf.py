"""
Builds rapport_final_attack_type_analysis.html (self-contained,
base64-embedded images) from rapport_final_attack_type_analysis.md, then
renders rapport_final_attack_type_analysis.pdf via headless Chrome.
Same pipeline as 08_documentation/build_pdf.py, with this report's own
style (no cover page, blue section headings, crimson bold emphasis --
matching the originally delivered PDF). Not part of the analysis
pipeline -- a one-off report-build helper.
"""
import base64
import mimetypes
import os
import re
import subprocess

import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(HERE, "rapport_final_attack_type_analysis.md")
HTML_PATH = os.path.join(HERE, "rapport_final_attack_type_analysis.html")
PDF_PATH = os.path.join(HERE, "rapport_final_attack_type_analysis.pdf")

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
body_html = markdown.markdown(md_text, extensions=["tables", "fenced_code"])

html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Analyse par type d'attaque — VAE clean-only vs Dense autoencoder v1</title>
<style>
@page {{ size: A4; margin: 20mm 18mm 22mm 18mm; }}
* {{ box-sizing: border-box; }}
html, body {{
  font-family: -apple-system, "Helvetica Neue", "Segoe UI", Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #1a1a1a;
}}
h1 {{
  font-size: 20pt;
  color: #111;
  border-bottom: 3px solid #1a7ab8;
  padding-bottom: 10px;
}}
h2 {{
  font-size: 15pt;
  color: #1a7ab8;
  margin-top: 1.8em;
  border-bottom: 1px solid #ddd;
  padding-bottom: 4px;
}}
h3 {{ font-size: 12.5pt; color: #222; margin-top: 1.4em; }}
p {{ margin: 0.7em 0; text-align: justify; }}
strong {{ color: #b0261c; }}
h1 strong, h2 strong, h3 strong, th strong {{ color: inherit; }}
table {{
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  font-size: 9.5pt;
  page-break-inside: avoid;
}}
th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
th {{ background: #f3f4f6; font-weight: 600; color: #1a1a1a; }}
code {{
  background: #f3f4f6;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 90%;
  font-family: "SF Mono", Menlo, Consolas, monospace;
  color: #1a1a1a;
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
hr {{ border: none; border-top: 1px solid #ddd; margin: 2em 0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""

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
