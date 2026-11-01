"""Quy trình chung: bài nguồn → viết lại → ảnh → bản nháp → gửi Telegram."""
from __future__ import annotations

import logging
import shutil
from dataclasses import asdict
from html import escape
from pathlib import Path

from . import builder, config, db, imager, rewriter, telegram
from .scraper import SourceArticle, now_iso

log = logging.getLogger(__name__)


def unique_slug(slug: str) -> str:
    taken = db.pending_slugs()
    candidate, n = slug, 2
    while candidate in taken or (config.NEWS_DIR / candidate).exists() or (config.DRAFTS_DIR / candidate).exists():
        candidate, n = f"{slug}-{n}", n + 1
    return candidate


def draft_dir(slug: str) -> Path:
    return config.DRAFTS_DIR / slug


def build_draft(src: SourceArticle, feedback: str = "", out_root: Path | None = None) -> dict:
    """Viết lại + tạo ảnh + dựng trang. Trả về dict bài viết (đã có slug, files)."""
    article = rewriter.rewrite(src, feedback)
    article["slug"] = unique_slug(article["slug"]) if out_root is None else article["slug"]
    article["source_url"] = src.url
    article["source"] = asdict(src)
    article["published"] = now_iso()
    folder = (out_root or config.DRAFTS_DIR) / article["slug"]
    try:
        make_images(article, folder)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return article


def make_images(article: dict, folder: Path) -> None:
    """Tạo (lại) toàn bộ ảnh với seed mới rồi dựng lại trang. Gọi trong imager.session()."""
    article["hero_image"]["seed"] = imager.generate(article["hero_image"]["prompt"], folder / "thumb.jpg")
    for i, fig in enumerate(article["figures"], 1):
        fig.pop("file", None)
        try:
            fig["seed"] = imager.generate(fig["prompt"], folder / f"fig-{i}.jpg")
            fig["file"] = f"fig-{i}.jpg"
        except RuntimeError as e:  # ảnh phụ lỗi thì bỏ qua, ảnh đầu bài bắt buộc
            log.warning("Bỏ ảnh minh hoạ %d: %s", i, e)
            (folder / f"fig-{i}.jpg").unlink(missing_ok=True)
    builder.write_draft(article, folder)
    builder.write_preview(folder)


def send_for_review(article: dict, draft_id: int) -> None:
    folder = draft_dir(article["slug"])
    caption = (
        f"<b>{escape(article['title'])}</b>\n\n{escape(article['lead'])}\n\n"
        f"Chuyên mục: {escape(article['category'])} · model: {escape(article.get('model', '?'))}\n"
        f"Bài gốc ({escape(article.get('source', {}).get('source_name', ''))}): {escape(article['source_url'])}"
    )
    telegram.send_photo(folder / "thumb.jpg", caption)
    telegram.send_document(folder / "preview.html", "Mở file để đọc toàn văn bài viết lại.")
    msg = telegram.send_message(
        f"Bản nháp #{draft_id} · <code>{escape(article['slug'])}</code>\n"
        "Duyệt để đăng lên tab Tin tức. 🎨 Ảnh khác: chỉ vẽ lại ảnh (seed mới).\n"
        "Muốn sửa bài: trả lời (reply) tin này bằng yêu cầu, agent sẽ viết lại.",
        reply_markup=telegram.review_keyboard(draft_id),
    )
    db.set_message_id(draft_id, msg["message_id"])


def create_and_send(src: SourceArticle, feedback: str = "") -> int:
    """Gọi trong imager.session()."""
    article = build_draft(src, feedback)
    draft_id = db.add_draft(article["slug"], src.url, article["title"], article)
    try:
        send_for_review(article, draft_id)
    except Exception:
        db.set_status(draft_id, "failed")
        shutil.rmtree(draft_dir(article["slug"]), ignore_errors=True)
        raise
    return draft_id


def discard(draft: dict) -> None:
    shutil.rmtree(draft_dir(draft["slug"]), ignore_errors=True)
