import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.site_render import html_document  # noqa: E402
from app.styles import REFERENCE_DOCUMENT, render_document, styles  # noqa: E402

target = root / ".runtime/style-previews"
target.mkdir(parents=True, exist_ok=True)
reference_styles = [style for style in styles() if style["id"] in ("linear", "notion", "spotify")]
for style in reference_styles:
    (target / f"{style['id']}.html").write_text(html_document(render_document(REFERENCE_DOCUMENT, style["id"])), encoding="utf-8")
print(f"Prepared {len(reference_styles)} built-in reference documents. Generate added MD previews in the studio.")
