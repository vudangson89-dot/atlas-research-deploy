"""Dựng trang bài viết từ templates/news-article.html, thẻ story và mục sitemap."""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from html import escape
from pathlib import Path

from . import config

STORY_START = "<!-- BÀI VIẾT: bắt đầu -->"


def e(text: str) -> str:
    return escape(str(text), quote=True)


def _prose(article: dict) -> str:
    figures_by_section: dict[int, list[dict]] = {}
    for f in article.get("figures", []):
        if f.get("file"):
            figures_by_section.setdefault(int(f.get("after_section", 0) or 0), []).append(f)
    out: list[str] = []
    last = len(article["sections"]) - 1
    for i, sec in enumerate(article["sections"]):
        if sec["heading"]:
            out.append(f"    <h2>{e(sec['heading'])}</h2>")
        out += [f"    <p>{e(p)}</p>" for p in sec["paragraphs"]]
        for f in figures_by_section.pop(i, []) + (sum(figures_by_section.values(), []) if i == last else []):
            out.append(
                "    <figure>\n"
                f"      <img src=\"{e(f['file'])}\" alt=\"{e(f.get('alt', ''))}\" width=\"1600\" height=\"900\" loading=\"lazy\">\n"
                f"      <figcaption>{e(f.get('caption', ''))}</figcaption>\n"
                "    </figure>"
            )
    src = article["source_url"]
    out.append(
        f'    <p class="source">Nguồn tham khảo: <a href="{e(src)}" target="_blank" rel="nofollow noopener">{e(article.get("source", {}).get("source_name") or config.SOURCE_NAME)}</a></p>'
    )
    return "\n".join(out)


def render_article(article: dict) -> str:
    """article: JSON đã viết lại + slug, published (ISO), source_url, figures[].file."""
    html = config.TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.split("<!--\n  THẺ BÀI TRONG", 1)[0].rstrip() + "\n"  # bỏ ghi chú mẫu thẻ ở cuối
    html = re.sub(r"<!DOCTYPE html>\n<!--.*?-->\n", "<!DOCTYPE html>\n", html, count=1, flags=re.S)
    pub = datetime.fromisoformat(article["published"])
    prose_start = html.index('<div class="prose">') + len('<div class="prose">')
    prose_end = html.index("</div>", prose_start)
    html = html[:prose_start] + "\n" + _prose(article) + "\n  " + html[prose_end:]
    headline = json.dumps(article["title"], ensure_ascii=False).replace("</", "<\\/")
    html = html.replace('"headline": "{{TIÊU ĐỀ}}"', f'"headline": {headline}')
    repl = {
        "{{TIÊU ĐỀ}}": e(article["title"]),
        "{{MÔ TẢ NGẮN 1–2 CÂU}}": e(article["description"]),
        "{{SLUG}}": article["slug"],
        "{{YYYY-MM-DD}}": e(article["published"]),
        "{{DD/MM/YYYY}}": pub.strftime("%d/%m/%Y"),
        "{{CHUYÊN MỤC}}": e(article["category"]),
        "{{SAPO: 1–2 CÂU TÓM TẮT}}": e(article["lead"]),
        "{{MÔ TẢ ẢNH}}": e(article["hero_image"].get("alt", "")),
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    leftover = re.findall(r"\{\{[^}]+\}\}", html)
    if leftover:
        raise ValueError(f"Template còn chỗ chưa điền: {leftover}")
    return html


def render_story(article: dict) -> str:
    pub = datetime.fromisoformat(article["published"])
    slug = article["slug"]
    return (
        '    <article class="story">\n'
        f'      <a href="{slug}/">\n'
        '        <div class="story__body">\n'
        f'          <p class="story__meta"><time data-relative datetime="{e(article["published"])}">{pub:%d/%m/%Y}</time> · {e(article["category"])}</p>\n'
        f'          <h2 class="story__title">{e(article["title"])}</h2>\n'
        f'          <p class="story__excerpt">{e(article["excerpt"])}</p>\n'
        "        </div>\n"
        f'        <img class="story__thumb" src="{slug}/thumb.jpg" alt="" width="1600" height="900" loading="lazy" style="view-transition-name:thumb-{slug}">\n'
        "      </a>\n"
        "    </article>"
    )


def write_draft(article: dict, draft_dir: Path) -> Path:
    draft_dir.mkdir(parents=True, exist_ok=True)
    page = draft_dir / "index.html"
    page.write_text(render_article(article), encoding="utf-8")
    (draft_dir / "story.html").write_text(render_story(article) + "\n", encoding="utf-8")
    return page


def write_preview(draft_dir: Path) -> Path:
    """Bản xem trước một file (CSS từ site thật) để gửi qua Telegram."""
    html = (draft_dir / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="../../css/', f'href="{config.SITE_URL}/css/')
    html = html.replace('src="../../', f'src="{config.SITE_URL}/').replace('href="../../', f'href="{config.SITE_URL}/')
    for img in draft_dir.glob("*.jpg"):
        data = base64.b64encode(img.read_bytes()).decode()
        html = html.replace(f'src="{img.name}"', f'src="data:image/jpeg;base64,{data}"')
    out = draft_dir / "preview.html"
    out.write_text(html, encoding="utf-8")
    return out


def insert_story(index_html: str, story: str) -> str:
    if STORY_START not in index_html:
        raise ValueError("Không tìm thấy dấu '<!-- BÀI VIẾT: bắt đầu -->' trong news/index.html")
    return index_html.replace(STORY_START, STORY_START + "\n" + story.rstrip("\n"), 1)


def add_sitemap_url(sitemap: str, slug: str, date: str) -> str:
    loc = f"{config.SITE_URL}/news/{slug}/"
    if loc in sitemap:
        return sitemap
    sitemap = re.sub(
        rf"(<loc>{re.escape(config.SITE_URL)}/news/</loc>\s*<lastmod>)[^<]*(</lastmod>)",
        rf"\g<1>{date}\g<2>",
        sitemap,
    )
    entry = f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{date}</lastmod>\n  </url>\n"
    return sitemap.replace("</urlset>", entry + "</urlset>")
