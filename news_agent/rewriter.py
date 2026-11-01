"""Viết lại bài nguồn qua OpenRouter (llm.chat), trả về JSON bài viết + prompt ảnh."""
from __future__ import annotations

import json
import logging
import re
import unicodedata

from . import config, llm
from .scraper import SourceArticle

log = logging.getLogger(__name__)

MAX_SOURCE_CHARS = 4000  # nguồn quá dài tốn token mà bài ra không tốt hơn
MIN_SOURCE_CHARS = 200
DISCLAIMER = "Bài viết chỉ nhằm cung cấp thông tin, không phải lời khuyên đầu tư. Tài sản số biến động mạnh — hãy tự nghiên cứu và quản lý rủi ro."
_DISCLAIMER_MARKER = "không phải lời khuyên đầu tư"


def slugify(text: str, max_words: int = 8) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:max_words]) or "bai-viet"


def truncate_source(text: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    """Cắt ở ranh giới đoạn/câu — tin tức viết kiểu kim tự tháp ngược, phần đầu quan trọng nhất."""
    if len(text) <= max_chars:
        return text
    cut = text.rfind("\n\n", 0, max_chars)
    if cut < max_chars * 0.5:
        cut = text.rfind(". ", 0, max_chars)
    return text[: cut if cut >= 200 else max_chars].rstrip()


def clean_output(text: str) -> str:
    """Bỏ rào ``` và câu dạo đầu kiểu "Here is the JSON:" mà model hay lỡ thêm."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return re.sub(r"^(Here is|Here's|Sure|Certainly|Below is|Dưới đây là)[^\n{]*\n+", "", text, flags=re.I).strip()


def _extract_json(content: str) -> dict:
    content = clean_output(content)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("Mô hình không trả về JSON")
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON hỏng: {e}") from e


def _strip_md(text: str) -> str:
    return str(text).replace("**", "").replace("__", "").strip()


def add_disclaimer(sections: list[dict]) -> list[dict]:
    """Gắn dòng miễn trừ đúng một lần (nhận diện bằng marker cố định)."""
    if any(_DISCLAIMER_MARKER in p for s in sections for p in s["paragraphs"]):
        return sections
    sections[-1]["paragraphs"].append(DISCLAIMER)
    return sections


def validate(content: str) -> dict:
    d = _extract_json(content)
    for key in ("title", "lead", "sections", "hero_image"):
        if not d.get(key):
            raise ValueError(f"JSON thiếu trường '{key}'")
    if not isinstance(d["hero_image"], dict) or not d["hero_image"].get("prompt"):
        raise ValueError("Thiếu prompt ảnh đầu bài")
    d["title"] = _strip_md(d["title"])
    d["lead"] = _strip_md(d["lead"])
    secs = []
    for s in d["sections"]:
        if not isinstance(s, dict):
            continue
        paras = [_strip_md(p) for p in s.get("paragraphs", []) if _strip_md(p)]
        if paras:
            secs.append({"heading": _strip_md(s.get("heading", "")), "paragraphs": paras})
    words = sum(len(p.split()) for s in secs for p in s["paragraphs"])
    if words < 200:
        raise ValueError(f"Bài viết lại quá ngắn ({words} từ)")
    d["sections"] = add_disclaimer(secs)
    d["slug"] = slugify(d.get("slug") or d["title"])
    d["category"] = _strip_md(d.get("category") or "Thị trường")
    d["excerpt"] = _strip_md(d.get("excerpt") or d["lead"])
    d["description"] = _strip_md(d.get("description") or d["lead"])[:200]
    d["figures"] = [f for f in d.get("figures", []) if isinstance(f, dict) and f.get("prompt")][: config.FIGURES_PER_ARTICLE]
    return d


def build_messages(src: SourceArticle, feedback: str = "") -> list[dict]:
    system = (config.PROMPTS_DIR / "rewrite.md").read_text(encoding="utf-8").replace(
        "{{FIGURES}}", str(config.FIGURES_PER_ARTICLE)
    )
    user = (
        f"Viết lại bài báo nguồn dưới đây ({src.source_name}) thành bài tin của Atlas Research.\n"
        "Chỉ dùng sự kiện, số liệu, tên riêng có trong bài nguồn.\n\n"
        "Bài nguồn:\n-------------------------\n"
        f"{truncate_source(src.as_text())}\n-------------------------\n"
    )
    if feedback:
        user += f"\nYÊU CẦU SỬA CỦA BIÊN TẬP VIÊN: {feedback}\n"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def rewrite(src: SourceArticle, feedback: str = "") -> dict:
    if len(src.as_text()) < MIN_SOURCE_CHARS:
        raise ValueError("Bài nguồn quá ngắn để viết lại")
    model, article = llm.chat(
        build_messages(src, feedback),
        validate=validate,
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    article["model"] = model
    return article
