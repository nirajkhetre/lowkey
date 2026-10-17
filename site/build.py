"""Build the lowkey.nirajlabs.tech site into site/dist: the landing page, plus the real dashboard running the
demo week in the browser (lowkey's own Python via Pyodide, see demo.js). Static files only, no server.

python site/build.py
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE, DIST = ROOT / "site", ROOT / "site" / "dist"
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"
IMAGES = ["island-states.png", "island-focus.png", "dashboard.png", "invoice.png", "log-time.png", "mascot-moods.png"]

shutil.rmtree(DIST, ignore_errors=True)
(DIST / "demo").mkdir(parents=True)
(DIST / "img").mkdir()

shutil.copy(SITE / "index.html", DIST / "index.html")
shutil.copy(SITE / "guide.js", DIST / "guide.js")
for d in (DIST / "fonts", DIST / "demo" / "fonts"):
    shutil.copytree(ROOT / "lowkey" / "web" / "fonts", d)
for name in IMAGES:
    shutil.copy(ROOT / "docs" / "images" / name, DIST / "img" / name)

page = (ROOT / "lowkey" / "web" / "index.html").read_text(encoding="utf-8")
assert page.count("</head>") == 1
page = page.replace("</head>", f'<script src="{PYODIDE}"></script>\n<script src="demo.js"></script>\n</head>')
(DIST / "demo" / "index.html").write_text(page, encoding="utf-8")
shutil.copy(SITE / "demo.js", DIST / "demo" / "demo.js")

with zipfile.ZipFile(DIST / "demo" / "lowkey.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for name in ("__init__", "config", "focus", "labeler", "server"):  # the island and tracker aren't needed here
        z.write(ROOT / "lowkey" / f"{name}.py", f"lowkey/{name}.py")
    for p in sorted((ROOT / "demo").iterdir()):
        z.write(p, f"demo/{p.name}")
    z.write(ROOT / "clients.example.json", "clients.example.json")
    z.write(SITE / "webdemo.py", "webdemo.py")

(DIST / "CNAME").write_text("lowkey.nirajlabs.tech\n")
(DIST / ".nojekyll").write_text("")
print("built", DIST, sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file()) // 1024, "KB")
