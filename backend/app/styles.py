import html
import re

from fastapi import HTTPException

from .config import get_settings


def styles(db=None, user=None):
    result = []
    for path in sorted((get_settings().project_root / "Design").glob("*.md")):
        markdown = path.read_text(encoding="utf-8-sig")
        def field(name):
            match = re.search(r"^" + name + r":\s*(.*?)\s*$", markdown, re.MULTILINE)
            return match.group(1).strip('"') if match else ""
        style_id = field("style_id")
        if not re.fullmatch(r"[a-z0-9-]+", style_id):
            continue
        has_reference = style_id in ("linear", "notion", "spotify")
        result.append({"id": style_id, "name": field("display_name") or path.stem, "description": field("gui_summary"),
                       "reference_image": f"/styles/{style_id}.png" if has_reference else None,
                       "mobile_reference_image": f"/styles/{style_id}-mobile.png" if has_reference else None,
                       "status": "ready" if has_reference else "missing",
                       "markdown": markdown, "source_file": path.name})
    if db is not None and user is not None:
        from sqlalchemy import select

        from .models import Material
        for row in db.scalars(select(Material).where(Material.user_id == user.id, Material.material_kind == "design_md", Material.access_status == "available").order_by(Material.created_at)):
            item = style_data(row)
            source_id = row.metadata_json.get("source_style_id")
            if source_id:
                original = next((x for x in result if x["id"] == source_id), None)
                if original and original["markdown"] == row.text_content:
                    original.update({key: item[key] for key in ("reference_image", "mobile_reference_image", "status", "error")})
            else:
                result.append(item)
    return result


def get_style(style_id, db=None, user=None):
    style = next((x for x in styles(db, user) if x["id"] == style_id), None)
    if not style:
        raise HTTPException(404, "Design 폴더의 스타일을 선택해 주세요.")
    return style


def style_data(row):
    meta = row.metadata_json
    return {"id": f"uploaded-{row.id}", "name": row.display_name, "description": meta.get("description", "직접 추가한 디자인"),
            "reference_image": meta.get("reference_image"), "mobile_reference_image": meta.get("mobile_reference_image"),
            "markdown": row.text_content, "source_file": meta.get("source_file", "design.md"),
            "status": meta.get("status", "queued"), "error": meta.get("error")}


def render_document(document, style_id):
    """Deterministic editable document layout, also used for reference images."""
    themes = {
        "linear": {"bg": "#010102", "surface": "#0f1011", "ink": "#f7f8f8", "muted": "#8a8f98", "accent": "#5e6ad2", "line": "#23252a", "radius": "10px", "hero": "#010102"},
        "notion": {"bg": "#ffffff", "surface": "#f6f5f4", "ink": "#1a1a1a", "muted": "#5d5b54", "accent": "#5645d4", "line": "#e5e3df", "radius": "12px", "hero": "#0a1530"},
        "spotify": {"bg": "#121212", "surface": "#252525", "ink": "#ffffff", "muted": "#b3b3b3", "accent": "#1ed760", "line": "#4d4d4d", "radius": "14px", "hero": "#193d2b"},
    }
    theme = themes.get(style_id, themes["linear"])
    def esc(value):
        return html.escape(str(value))
    sections = "".join(f'<section class="section" id="section-{i}"><span class="section-index">0{i + 1}</span><h2>{esc(section["heading"])}</h2><p>{esc(section["body"])}</p><ul>' +
                       "".join(f"<li>{esc(item)}</li>" for item in section.get("items", [])) + "</ul></section>"
                       for i, section in enumerate(document.get("sections", [])))
    markup = f'<div class="page {style_id}"><nav><strong data-field="title">{esc(document["title"])}</strong><span>ABOUT &nbsp; / &nbsp; EXPERIENCE &nbsp; / &nbsp; PROJECTS</span></nav><header><div class="hero-copy"><span class="eyebrow">MY STORY, MY NEXT CHAPTER</span><h1 data-field="headline">{esc(document["headline"])}</h1><p data-field="summary">{esc(document["summary"])}</p><a class="cta" href="#section-0">경험 살펴보기 ↗</a></div><div class="hero-art"><div class="art-tile">D</div><span>Ideas into experiences.</span></div></header><main>{sections}</main><footer>{esc(document["title"])} · 나의 경험으로 만드는 다음 이야기</footer></div>'
    variables = ";".join(f"--{key}:{value}" for key, value in theme.items())
    css = f":root{{{variables}}}" + """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,'Malgun Gothic',sans-serif;line-height:1.65}a{color:inherit;text-decoration:none}.page{max-width:1320px;margin:auto;padding:0 58px}nav{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:32px 0;border-bottom:1px solid var(--line)}nav strong{font-size:20px}nav span{font-size:10px;letter-spacing:1px;color:var(--muted)}header{display:grid;grid-template-columns:1.4fr 1fr;gap:50px;align-items:center;padding:76px 0 80px;background:var(--hero)}.eyebrow{font-size:11px;font-weight:700;letter-spacing:2px;color:var(--accent)}h1{font-size:56px;letter-spacing:-1.8px;line-height:1.14;margin:23px 0;font-weight:600;white-space:pre-line}header p{color:var(--muted);font-size:16px;max-width:590px;white-space:pre-line}.cta{display:inline-block;margin-top:23px;padding:12px 22px;background:var(--accent);color:white;border-radius:8px;font-size:13px;font-weight:700}.hero-art{aspect-ratio:1;border:1px solid var(--line);border-radius:18px;background:linear-gradient(140deg,var(--surface),var(--bg));display:flex;flex-direction:column;align-items:center;justify-content:center;transform:rotate(-4deg)}.art-tile{height:130px;width:130px;border-radius:24px;background:var(--accent);color:white;display:grid;place-items:center;font-size:70px;font-weight:700;box-shadow:18px 18px 0 #ffffff12}.hero-art span{font-size:11px;color:var(--muted);margin-top:38px;letter-spacing:2px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:35px 0 65px}.section{padding:26px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);min-width:0}.section-index{color:var(--accent);font-size:12px}.section h2{font-size:25px;letter-spacing:-.6px;margin:22px 0 14px}.section p,.section li{font-size:13px;color:var(--muted);white-space:pre-line;overflow-wrap:anywhere}.section ul{padding-left:17px}.section li{padding:6px 0}footer{padding:22px 0;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}
.notion header{margin:28px 0 0;padding:47px;border-radius:16px;color:white;gap:25px}.notion h1{font-size:48px}.notion header p{color:#d6ddef}.notion .hero-art{background:#ffffff10;border-color:#ffffff25}.notion .hero-art span{color:#d6ddef}.notion .cta{border-radius:999px}.notion .section:nth-child(3n+1){background:#ffe8d4}.notion .section:nth-child(3n+2){background:#d9f3e1}.notion .section:nth-child(3n){background:#e6e0f5}
.spotify nav{border:0}.spotify header{padding:50px;border-radius:16px;grid-template-columns:1.35fr 1fr}.spotify h1{font-weight:800;font-size:58px;letter-spacing:-2px}.spotify .hero-art{background:linear-gradient(130deg,#1ed760,#153c75);transform:rotate(5deg);border:0;box-shadow:0 8px 24px #0008}.spotify .art-tile{background:#121212;color:#1ed760;border-radius:50%;box-shadow:0 0 0 18px #ffffff22}.spotify .hero-art span{color:#fff}.spotify header p{color:#d3dfd8}.spotify .cta{border-radius:999px;color:#121212}.spotify .section-index{display:block;min-height:80px;font-size:38px;line-height:80px;background:linear-gradient(125deg,#153e32,#4c3475);text-align:center;border-radius:8px}.spotify .section{border:0;box-shadow:0 8px 8px #0004}
@media(max-width:700px){.page{padding:0 22px}nav{padding:22px 0}nav span{display:none}header{grid-template-columns:1fr;padding:45px 0;gap:26px}h1{font-size:38px}header p{font-size:14px}.hero-art{width:72%;margin:10px auto}.art-tile{width:100px;height:100px;font-size:52px}.hero-art span{margin-top:25px}main{grid-template-columns:1fr;gap:15px;padding:25px 0}.section{padding:23px}.notion header,.spotify header{grid-template-columns:1fr;padding:26px 23px}.notion h1,.spotify h1{font-size:36px}.notion .hero-art,.spotify .hero-art{width:100%;margin:15px auto}.section h2{font-size:24px}.section p,.section li{font-size:14px}}
@media print{body{background:white;color:black}.page{padding:0}nav,footer{padding:10px 0}.hero-art,.cta{display:none!important}header,.notion header,.spotify header{display:block;background:white!important;color:black!important;padding:15px 0!important}h1,.notion h1,.spotify h1{font-size:30px}header p{color:#333!important}main{display:block;padding:0}.section{break-inside:avoid;box-shadow:none!important;background:white!important;color:black!important;margin-bottom:12px}.section p,.section li{color:#333}.section-index{display:none!important}}
"""
    return {"html": markup, "css": css, "javascript": ""}


REFERENCE_DOCUMENT = {
    "title": "김민준 · Portfolio",
    "headline": "작은 아이디어를\n쓸모 있는 경험으로.",
    "summary": "배우고, 만들고, 함께 성장하는 개발자 김민준입니다.\n사람들의 일상을 조금 더 편리하게 만드는 서비스를 고민합니다.",
    "sections": [
        {"heading": "About me", "body": "문제를 이해하는 것에서 개발을 시작합니다. 작은 기능을 끝까지 완성하며 배운 내용을 기록합니다.", "items": ["국민대학교 소프트웨어학부", "React · TypeScript · Python", "사용자 경험과 접근성"]},
        {"heading": "Selected work", "body": "캠퍼스에서 함께 쓰는 커피챗 서비스를 만들었습니다.", "items": ["질문에서 약속까지 이어지는 흐름", "반응형 화면과 상태 관리", "팀의 의사결정과 회고 기록"]},
        {"heading": "My journey", "body": "완성한 경험을 다음 시작의 밑거름으로 삼고 있습니다.", "items": ["2026 · 캠퍼스 서비스 프로젝트", "2025 · 웹 개발 스터디", "다음 · 함께 성장할 동료 만나기"]},
    ],
}
