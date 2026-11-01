"""Quét trang nguồn, tạo bản nháp cho bài mới và gửi Telegram. Chạy mỗi giờ bằng systemd timer.

    python -m news_agent.scan                 # chạy thật
    python -m news_agent.scan --dry-run --limit 1 --out /tmp/x   # thử, không gửi/không ghi trạng thái
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from html import escape
from pathlib import Path

from . import config, db, imager, pipeline, scraper, telegram

log = logging.getLogger("news_agent.scan")


def cleanup_expired() -> None:
    for d in db.expired_pending(config.DRAFT_TTL_DAYS):
        if db.set_status(d["id"], "expired", expect="pending"):
            pipeline.discard(d)
            if d.get("tg_message_id"):
                telegram.clear_keyboard(config.TELEGRAM_CHAT_ID, d["tg_message_id"])
            log.info("Nháp #%s quá hạn, đã xoá", d["id"])


def notify_error(text: str) -> None:
    try:
        telegram.send_message("⚠️ Agent tin tức: " + escape(text)[:3500])
    except Exception as e:  # noqa: BLE001 — chỉ ghi log khi không báo được
        log.error("Không gửi được cảnh báo Telegram: %s", e)


def run(limit: int) -> int:
    config.require("OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    cleanup_expired()
    session = scraper.new_session()
    try:
        urls = [u for u in scraper.list_article_urls(session) if not db.is_seen(u)]
    except Exception as e:  # noqa: BLE001
        log.error("Không tải được trang nguồn: %s", e)
        notify_error(f"không tải được trang nguồn {config.SOURCE_URL}: {e}")
        return 1
    if not db.get_kv("initialized"):
        # Lần chạy đầu: chỉ lấy `limit` bài mới nhất, các bài cũ hơn coi như đã xem.
        for u in urls[limit:]:
            db.mark_seen(u)
        db.set_kv("initialized", "1")
    urls = urls[:limit]

    sources = []
    failures = 0
    for url in reversed(urls):  # cũ trước, mới sau
        try:
            src = scraper.fetch_article(url, session)
        except Exception as e:  # noqa: BLE001
            failures += 1
            log.exception("Không đọc được %s", url)
            notify_error(f"không đọc được {url}: {e}")
            continue
        if scraper.too_old(src):
            log.info("Bỏ qua (đăng quá %s giờ hoặc không rõ giờ đăng: %r): %s", config.MAX_AGE_HOURS, src.published, url)
            db.mark_seen(url)
            continue
        if db.hash_seen(src.content_hash()):
            log.info("Bỏ qua (trùng nội dung đã viết): %s", url)
            db.mark_seen(url)
            continue
        sources.append(src)
    log.info("Có %d bài mới cần viết", len(sources))
    if not sources:
        return 1 if failures else 0

    try:
        with imager.session():
            for src in sources:
                try:
                    draft_id = pipeline.create_and_send(src)
                except imager.GpuBusy:
                    raise
                except Exception as e:  # noqa: BLE001 — một bài lỗi không chặn bài khác
                    failures += 1
                    log.exception("Lỗi xử lý %s", src.url)
                    notify_error(f"lỗi xử lý {src.url}: {e}")
                    continue
                db.mark_seen(src.url)
                db.mark_hash(src.content_hash())
                log.info("Đã gửi nháp #%d cho %s", draft_id, src.url)
    except imager.GpuBusy as e:
        # Không đánh dấu đã xem: lượt sau làm lại khi GPU rảnh.
        log.warning("GPU bận, để lượt sau: %s", e)
        return 0
    return 1 if failures else 0


def dry_run(limit: int, out: Path) -> int:
    config.require("OPENROUTER_API_KEY")
    session = scraper.new_session()
    urls = scraper.list_article_urls(session)
    print(f"Tìm thấy {len(urls)} bài trên trang nguồn:")
    for u in urls:
        print("  ", u)
    fresh = []
    for url in urls:
        if len(fresh) >= limit:
            break
        src = scraper.fetch_article(url, session)
        age = src.age_hours()
        print(f"  {url} — đăng {'?' if age is None else f'{age:.1f}'} giờ trước")
        if scraper.too_old(src):
            print(f"    dừng: quá {config.MAX_AGE_HOURS} giờ hoặc không rõ giờ đăng (các bài sau còn cũ hơn)")
            break
        fresh.append(src)
    if not fresh:
        print(f"Không có bài nào trong {config.MAX_AGE_HOURS} giờ gần nhất.")
        return 0
    with imager.session():
        for src in fresh:
            article = pipeline.build_draft(src, out_root=out)
            folder = out / article["slug"]
            (folder / "article.json").write_text(json.dumps(article, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Đã dựng nháp ({article['model']}): {folder / 'index.html'} (xem nhanh: {folder / 'preview.html'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=config.MAX_PER_RUN)
    p.add_argument("--dry-run", action="store_true", help="không gửi Telegram, không ghi trạng thái")
    p.add_argument("--out", type=Path, default=Path("./news-agent-dry-run"))
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return dry_run(args.limit, args.out) if args.dry_run else run(args.limit)


if __name__ == "__main__":
    sys.exit(main())
