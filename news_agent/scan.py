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


def collect(limit: int, session, failures: list) -> list:
    """Bài mới (chưa xem, trong MAX_AGE_HOURS, chưa trùng nội dung) từ mọi nguồn, tối đa `limit` bài mỗi nguồn."""
    picked = []
    for source in config.sources():
        try:
            cands = [c for c in scraper.list_candidates(source, session) if not db.is_seen(c.url)]
        except Exception as e:  # noqa: BLE001 — một nguồn lỗi không chặn nguồn khác
            failures.append(e)
            log.error("Không tải được nguồn %s: %s", source["name"], e)
            notify_error(f"không tải được nguồn {source['name']} ({source['url']}): {e}")
            continue
        key = f"initialized:{source['url']}"
        if not db.get_kv(key):
            # Lần đầu gặp nguồn này: các bài cũ hơn `limit` bài mới nhất coi như đã xem.
            for c in cands[limit:]:
                db.mark_seen(c.url)
            db.set_kv(key, "1")
            cands = cands[:limit]
        taken = 0
        for c in cands:
            if taken >= limit:
                break
            if c.known_too_old():
                db.mark_seen(c.url)
                continue
            try:
                src = c.load(session)
            except Exception as e:  # noqa: BLE001
                failures.append(e)
                log.exception("Không đọc được %s", c.url)
                notify_error(f"không đọc được {c.url}: {e}")
                continue
            if scraper.too_old(src):
                log.info("Bỏ qua (đăng quá %s giờ hoặc không rõ giờ đăng: %r): %s", config.MAX_AGE_HOURS, src.published, c.url)
                db.mark_seen(c.url)
                continue
            if db.hash_seen(src.content_hash()):
                log.info("Bỏ qua (trùng nội dung đã viết): %s", c.url)
                db.mark_seen(c.url)
                continue
            picked.append(src)
            taken += 1
    picked.sort(key=lambda s: s.published_at() or scraper.datetime.min.replace(tzinfo=scraper.VN_TZ))  # cũ trước
    return picked


def run(limit: int) -> int:
    config.require("OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    cleanup_expired()
    session = scraper.new_session()
    errors: list = []
    sources = collect(limit, session, errors)
    failures = len(errors)
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
    fresh = []
    for source in config.sources():
        print(f"\n== {source['name']} ({source['url']})")
        try:
            cands = scraper.list_candidates(source, session)
        except Exception as e:  # noqa: BLE001
            print(f"   lỗi tải nguồn: {e}")
            continue
        print(f"   tìm thấy {len(cands)} bài")
        taken = 0
        for c in cands:
            if taken >= limit:
                break
            if c.known_too_old():
                print(f"   dừng: {c.url} đăng quá {config.MAX_AGE_HOURS} giờ (các bài sau còn cũ hơn)")
                break
            try:
                src = c.load(session)
            except Exception as e:  # noqa: BLE001
                print(f"   không đọc được {c.url}: {e}")
                continue
            age = src.age_hours()
            print(f"   {c.url} — đăng {'?' if age is None else f'{age:.1f}'} giờ trước, {len(src.paragraphs)} đoạn")
            if scraper.too_old(src):
                print(f"   dừng: quá {config.MAX_AGE_HOURS} giờ hoặc không rõ giờ đăng")
                break
            fresh.append(src)
            taken += 1
    if not fresh:
        print(f"\nKhông có bài nào trong {config.MAX_AGE_HOURS} giờ gần nhất.")
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
