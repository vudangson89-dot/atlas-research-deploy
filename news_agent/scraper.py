"""Lấy danh sách bài và nội dung bài gốc từ trang tag VnExpress."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import config

log = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ARTICLE_URL_RE = re.compile(r"^https://vnexpress\.net/[a-z0-9-]+-\d{6,}\.html$")


@dataclass
class SourceArticle:
    url: str
    title: str
    description: str
    paragraphs: list[str] = field(default_factory=list)
    published: str = ""  # ISO 8601 nếu đọc được
    category: str = ""

    def published_at(self) -> datetime | None:
        """Giờ đăng bài gốc (múi giờ Việt Nam nếu nguồn không ghi múi giờ); None nếu không đọc được."""
        raw = (self.published or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", raw)
            if not m:
                return None
            dt = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
        return dt if dt.tzinfo else dt.replace(tzinfo=VN_TZ)

    def age_hours(self) -> float | None:
        dt = self.published_at()
        return None if dt is None else (datetime.now(VN_TZ) - dt).total_seconds() / 3600

    def content_hash(self) -> str:
        """Hash nội dung (chống viết trùng khi cùng bài đổi URL)."""
        norm = re.sub(r"\s+", " ", " ".join([self.title, *self.paragraphs])).strip().lower()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def as_text(self) -> str:
        return "\n\n".join([self.title, self.description, *self.paragraphs])


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "vi-VN,vi;q=0.9"})
    return s


def _get(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def list_article_urls(session: requests.Session | None = None) -> list[str]:
    """Trả về URL bài trên trang tag, theo thứ tự trang hiển thị (mới nhất trước)."""
    session = session or new_session()
    soup = BeautifulSoup(_get(session, config.SOURCE_URL), "html.parser")
    anchors = soup.select("article.item-news h3.title-news a[href], article.item-news h2.title-news a[href]")
    if not anchors:  # dự phòng khi VnExpress đổi giao diện
        anchors = soup.select("a[href]")
    urls: list[str] = []
    for a in anchors:
        href = urljoin(config.SOURCE_URL, a["href"]).split("?")[0].split("#")[0]
        if ARTICLE_URL_RE.match(href) and href not in urls:
            urls.append(href)
    return urls


def _ld_json(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") in ("NewsArticle", "Article"):
                return item
    return {}


def too_old(src: "SourceArticle") -> bool:
    """Bài cũ hơn MAX_AGE_HOURS. Không đọc được giờ đăng thì coi là quá cũ để chắc chắn chỉ lấy tin mới."""
    if config.MAX_AGE_HOURS <= 0:
        return False
    age = src.age_hours()
    return age is None or age > config.MAX_AGE_HOURS


def fetch_article(url: str, session: requests.Session | None = None) -> SourceArticle:
    if urlparse(url).hostname != "vnexpress.net":
        raise ValueError(f"URL không thuộc nguồn cho phép: {url}")
    session = session or new_session()
    soup = BeautifulSoup(_get(session, url), "html.parser")
    ld = _ld_json(soup)

    def text(sel: str) -> str:
        el = soup.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    title = text("h1.title-detail") or ld.get("headline", "")
    desc = text("p.description") or ld.get("description", "")
    body = soup.select_one("article.fck_detail")
    paragraphs: list[str] = []
    if body:
        for p in body.select("p.Normal, p"):
            if p.find_parent("figure") or p.find_parent("table"):
                continue
            t = p.get_text(" ", strip=True)
            if t and t not in paragraphs:
                paragraphs.append(t)
        # Dòng cuối thường là tên tác giả — bỏ nếu quá ngắn.
        if paragraphs and len(paragraphs[-1]) < 40:
            paragraphs.pop()

    published = ld.get("datePublished", "")
    if not published:
        meta = soup.find("meta", attrs={"name": "pubdate"}) or soup.find("meta", itemprop="datePublished")
        published = meta.get("content", "") if meta else ""
    category = text("ul.breadcrumb li:last-child a") or text("ul.breadcrumb li a")

    if not title or len(paragraphs) < 2:
        raise ValueError(f"Không đọc được nội dung bài (giao diện nguồn có thể đã đổi): {url}")
    return SourceArticle(url, title, desc, paragraphs, published, category)



def now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="minutes")
