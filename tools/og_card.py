"""Make site/assets/img/og-card.png, the 1200 × 630 picture that link previews show (Open Graph / Twitter card;
woland/prerender.py points to it), from the site's own colours, fonts and masthead:

    pip install playwright      # with its Chromium: python -m playwright install chromium
    python tools/og_card.py

Run once; the result is committed."""
from __future__ import annotations

import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "img" / "og-card.png"


def card_html() -> str:
    masthead = (ROOT / "site" / "partials" / "masthead.html").read_text(encoding="utf-8")
    cat = re.search(r'<svg class="cat".*?</svg>', masthead, re.S).group(0)
    css = (ROOT / "site" / "assets" / "css" / "woland.css").as_uri()
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;1,400&family=PT+Sans:wght@400;700&family=PT+Serif:ital,wght@0,400;1,400&display=swap">
<link rel="stylesheet" href="{css}">
<style>
  html, body {{ margin: 0; width: 1200px; height: 630px; overflow: hidden; }}
  .masthead {{ position: absolute; inset: 0; border: 0; }}
  .moon {{ right: 150px; top: -40px; width: 260px; height: 260px; }}
  .cat {{ position: absolute; right: 150px; bottom: 70px; width: 120px; height: 150px; color: #050407; }}
  .card {{ position: absolute; left: 90px; top: 180px; right: 420px; }}
  .w {{ font: 500 118px/1 var(--display); letter-spacing: .32em; text-transform: uppercase; color: var(--text); }}
  .sub {{ font: italic 400 40px/1.25 var(--display); color: var(--text-2); margin-top: 22px; }}
  .what {{ font: 400 25px/1.45 var(--sans); color: var(--text-3); margin-top: 48px; }}
  .what b {{ color: var(--gilt-text); font-weight: 700; }}
  .rule {{ position: absolute; left: 90px; right: 90px; bottom: 56px; border-top: 1px solid var(--rule-2); }}
</style></head><body>
<div class="masthead"><div class="moon"></div>{cat}</div>
<div class="card">
  <div class="w">Woland</div>
  <div class="sub">A chronicle of the Russian state press</div>
  <div class="what">Every day since 1 September 2026: headlines, <b>propaganda framings</b> and a searchable,
  citable archive, in English, Finnish and Swedish.</div>
</div>
<div class="rule"></div>
</body></html>"""


def main() -> None:
    page_file = OUT.with_suffix(".html")
    page_file.write_text(card_html(), encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)  # (another Chromium)
            page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
            page.goto(page_file.as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(OUT))
            browser.close()
    finally:
        page_file.unlink()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
