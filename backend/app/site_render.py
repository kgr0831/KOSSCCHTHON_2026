import base64
import hashlib
import html
import json
import re
import shutil
import subprocess

from bs4 import BeautifulSoup

# Only the separately stored JS bundle can execute. Previews are opaque-origin
# sandbox frames inside a trusted parent whose frame-src blocks external navigation.
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
ALLOWED = {"div", "span", "main", "section", "article", "header", "footer", "nav", "aside", "h1", "h2", "h3", "h4",
           "p", "br", "hr", "ul", "ol", "li", "dl", "dt", "dd", "strong", "b", "em", "i", "small", "blockquote",
           "pre", "code", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td", "a", "img", "details", "summary", "button"}


def safe_markup(markup: str) -> str:
    soup = BeautifulSoup(markup, "html.parser")
    for node in list(soup.find_all(True)):
        if not node.name:
            continue
        if node.name not in ALLOWED:
            if node.name in ("html", "head", "body"):
                node.unwrap()
            else:
                node.decompose()
            continue
        for key in list(node.attrs):
            value = node.attrs[key]
            if key in ("class", "id", "title", "alt", "style", "data-field", "data-section", "open", "tabindex", "role", "type", "disabled") or key.startswith("aria-"):
                continue
            if key == "href" and isinstance(value, str) and value.startswith("#"):
                continue
            if key == "src" and isinstance(value, str) and value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
                continue
            del node.attrs[key]
    return str(soup)


def html_document(code: dict, title="두드리 프로필") -> str:
    css = code.get("css", "").replace("<", "\\3c ")
    javascript = code.get("javascript", "").replace("</", "<\\/")
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{html.escape(content_policy(code), quote=True)}">'
            '<meta name="referrer" content="no-referrer">'
            f'<title>{html.escape(title)}</title><style>{css}</style></head><body>'
            + safe_markup(code.get("html", "")) + f"<script>{javascript}</script></body></html>")


def content_policy(code, sandbox=False):
    javascript = code.get("javascript", "").replace("</", "<\\/")
    digest = base64.b64encode(hashlib.sha256(javascript.encode()).digest()).decode()
    return CSP + f"; script-src 'sha256-{digest}'" + ("; sandbox allow-scripts" if sandbox else "")


def update_fields(code, document, previous=None, *, preserve_layout=False):
    soup = BeautifulSoup(code.get("html", ""), "html.parser")
    for name in ("title", "headline", "summary"):
        for node in soup.select(f'[data-field="{name}"]'):
            node.clear()
            node.append(document[name])
    editable_ids = {section["id"] for section in document.get("sections", [])}
    editable_ids.update(section["id"] for section in (previous or {}).get("sections", []))
    existing = {node.get("data-section"): node for node in soup.select("[data-section]") if node.get("data-section") in editable_ids}
    parent = next(iter(existing.values())).parent if existing else soup.find("main")
    groups = {}
    for node in existing.values():
        group = groups.setdefault(id(node.parent), {"parent": node.parent, "nodes": [], "ordered": []})
        group["nodes"].append(node)
    for section in document.get("sections", []):
        node = existing.pop(section["id"], None)
        if node is None:
            # New sections stay in the same marked container, leaving free code alone.
            if parent is None:
                continue
            node = soup.new_tag("section", attrs={"data-section": section["id"], "class": "section"})
            for tag, field in (("h2", "heading"), ("p", "body"), ("ul", "items")):
                node.append(soup.new_tag(tag, attrs={"data-field": field}))
            parent.append(node)
            groups.setdefault(id(parent), {"parent": parent, "nodes": [], "ordered": []})["nodes"].append(node)
        for name in ("heading", "body", "items"):
            for target in node.select(f'[data-field="{name}"]'):
                if target.find_parent(attrs={"data-section": True}) is not node:
                    continue
                # An AI layout may nest project cards inside a section body.
                # Keep those containers intact while replacing only its own copy.
                for child in list(target.contents):
                    if getattr(child, "attrs", {}).get("data-section") or (getattr(child, "name", None) and child.select_one("[data-section]")):
                        continue
                    child.extract()
                if name == "items":
                    for item in section.get(name, []):
                        li = soup.new_tag("li")
                        li.string = item
                        target.append(li)
                else:
                    target.append(section[name])
        groups[id(node.parent)]["ordered"].append(node)
    for node in existing.values():
        node.decompose()
    if not preserve_layout:
        # Reorder only within each original container. Placeholders preserve
        # free markup between editable sections and never flatten project grids.
        for group in groups.values():
            wanted = group["ordered"]
            slots = []
            for node in group["parent"].contents[:]:
                if any(node is item for item in wanted):
                    slot = soup.new_string("")
                    node.replace_with(slot)
                    slots.append(slot)
            for slot, node in zip(slots, wanted):
                slot.replace_with(node)
    if preserve_layout:
        return {**code, "html": str(soup)}
    # Replace only our own variables, never regenerate the user's free CSS.
    css = re.sub(r"/\* dudri-gui:start \*/.*?/\* dudri-gui:end \*/", "", code.get("css", ""), flags=re.DOTALL)
    accent = document.get("accent", "#7060d9")
    font = document.get("font", "sans-serif")
    spacing = document.get("spacing", 24)
    css += f"\n/* dudri-gui:start */\n:root{{--accent:{accent};--section-gap:{spacing}px}}body{{font-family:{font}}}[data-section]{{margin-block:{spacing}px}}\n/* dudri-gui:end */"
    return {**code, "html": str(soup), "css": css}


def read_fields(code, fallback):
    document = json.loads(json.dumps(fallback))
    soup = BeautifulSoup(code.get("html", ""), "html.parser")
    for name in ("title", "headline", "summary"):
        node = soup.select_one(f'[data-field="{name}"]')
        if node:
            document[name] = node.get_text()
    sections = []
    for node in soup.select("[data-section]"):
        if not node.select_one('[data-field="heading"]') or not node.select_one('[data-field="body"]'):
            continue
        def value(name):
            target = node.select_one(f'[data-field="{name}"]')
            return target.get_text() if target else ""
        sections.append({"id": node["data-section"], "heading": value("heading"), "body": value("body"),
                         "items": [li.get_text() for li in node.select('[data-field="items"] li')]})
    document["sections"] = sections
    return document


def validate_code(code):
    soup = BeautifulSoup(code.get("html", ""), "html.parser")
    if not soup.get_text(strip=True):
        return "내용이 있는 HTML을 입력해 주세요."
    if not soup.find("h1"):
        return "문서의 대표 제목(h1)이 필요해요. 초안을 수정하거나 다시 생성해 주세요."
    if code.get("javascript", "").strip():
        node = shutil.which("node")
        if not node:
            return "JavaScript 검증에 Node.js가 필요합니다."
        try:
            result = subprocess.run([node, "--check", "--input-type=commonjs"], input=code["javascript"],
                                    text=True, encoding="utf-8", capture_output=True, timeout=10)
            if result.returncode:
                return "JavaScript 문법 오류가 있어요. 초안은 저장됐으며 수정 후 게시할 수 있습니다."
        except (OSError, subprocess.TimeoutExpired):
            return "JavaScript 검증을 완료하지 못했어요. 초안을 다시 저장해 주세요."
    return None
