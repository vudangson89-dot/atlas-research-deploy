"""Lấy danh sách bài và nội dung bài gốc.

Hai loại nguồn:
* VnExpress (trang tag) — đọc HTML riêng của VnExpress.
* Trang WordPress có RSS (vd. Blog Tiền Ảo) — đọc feed để biết link + giờ đăng,
  rồi lấy nội dung từ feed (content:encoded) hoặc từ trang bài.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
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
    source_name: str = "VnExpress"

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


def list_article_urls(session: requests.Session | None = None, tag_url: str | None = None) -> list[str]:
    """Trả về URL bài trên trang tag VnExpress, theo thứ tự trang hiển thị (mới nhất trước)."""
    session = session or new_session()
    tag_url = tag_url or config.SOURCE_URL
    soup = BeautifulSoup(_get(session, tag_url), "html.parser")
    anchors = soup.select("article.item-news h3.title-news a[href], article.item-news h2.title-news a[href]")
    if not anchors:  # dự phòng khi VnExpress đổi giao diện
        anchors = soup.select("a[href]")
    urls: list[str] = []
    for a in anchors:
        href = urljoin(tag_url, a["href"]).split("?")[0].split("#")[0]
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


def fetch_vnexpress(url: str, session: requests.Session | None = None) -> SourceArticle:
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
    return SourceArticle(url, title, desc, paragraphs, published, category, "VnExpress")


# Giữ tên cũ cho mã gọi trước đây.
fetch_article = fetch_vnexpress


# ---------------------------------------------------------------------------
# Nguồn RSS (WordPress)
# ---------------------------------------------------------------------------
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"
BODY_SELECTORS = (
    ".entry-content", ".td-post-content", ".post-content", ".single-content",
    ".article-content", ".content-detail", "article .content", "article",
)
JUNK_RE = re.compile(r"(tham gia (nhóm|kênh|cộng đồng)|theo dõi (chúng tôi|blogtienao)|telegram|twitter|facebook|zalo|youtube|đăng ký nhận tin|bài viết liên quan|xem thêm:)", re.I)


@dataclass
class FeedItem:
    url: str
    title: str
    published: str          # ISO 8601 ("" nếu feed không ghi)
    html: str = ""          # content:encoded nếu feed có toàn văn
    summary: str = ""
    category: str = ""


def _to_iso(rfc822: str) -> str:
    try:
        return parsedate_to_datetime(rfc822.strip()).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def list_feed(feed_url: str, session: requests.Session | None = None) -> list[FeedItem]:
    """Đọc RSS 2.0; trả về bài theo thứ tự feed (mới nhất trước)."""
    session = session or new_session()
    r = session.get(feed_url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items: list[FeedItem] = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip().split("#")[0]
        if not link.startswith("http"):
            continue
        items.append(
            FeedItem(
                url=link,
                title=(it.findtext("title") or "").strip(),
                published=_to_iso(it.findtext("pubDate") or ""),
                html=it.findtext(CONTENT_NS) or "",
                summary=BeautifulSoup(it.findtext("description") or "", "html.parser").get_text(" ", strip=True),
                category=(it.findtext("category") or "").strip(),
            )
        )
    return items


def list_listing(listing_url: str, session: requests.Session | None = None) -> list[FeedItem]:
    """Dự phòng khi feed lỗi: lấy link bài từ trang danh sách (không biết giờ đăng)."""
    session = session or new_session()
    soup = BeautifulSoup(_get(session, listing_url), "html.parser")
    host = urlparse(listing_url).hostname
    out: list[FeedItem] = []
    seen: set[str] = set()
    for a in soup.select("h2 a[href], h3 a[href], .entry-title a[href], article a[href]"):
        href = urljoin(listing_url, a["href"]).split("?")[0].split("#")[0]
        path = urlparse(href).path.strip("/")
        if urlparse(href).hostname != host or not path or path.count("/") > 1 or href in seen:
            continue
        if path.split("/")[0] in ("tag", "category", "author", "page", "tin-tuc", "wp-content"):
            continue
        seen.add(href)
        out.append(FeedItem(url=href, title=a.get_text(" ", strip=True), published=""))
    return out


def _paragraphs_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("script, style, figure, figcaption, table, .sharedaddy, .jp-relatedposts, .related, .wp-block-embed, blockquote.twitter-tweet"):
        bad.decompose()
    out: list[str] = []
    for p in soup.find_all(["p", "li"]):
        t = p.get_text(" ", strip=True)
        if len(t) < 30 or JUNK_RE.search(t) or t in out:
            continue
        out.append(t)
    return out


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def fetch_feed_article(item: FeedItem, source_name: str, session: requests.Session | None = None) -> SourceArticle:
    """Nội dung bài từ nguồn RSS: ưu tiên toàn văn trong feed, thiếu thì đọc trang bài."""
    paragraphs = _paragraphs_from_html(item.html) if item.html else []
    title, desc, published, category = item.title, item.summary, item.published, item.category
    if len(paragraphs) < 3:
        session = session or new_session()
        soup = BeautifulSoup(_get(session, item.url), "html.parser")
        ld = _ld_json(soup)
        title = title or _meta(soup, "og:title") or (soup.h1.get_text(" ", strip=True) if soup.h1 else "")
        desc = desc or _meta(soup, "og:description", "description")
        published = published or _meta(soup, "article:published_time") or ld.get("datePublished", "")
        for sel in BODY_SELECTORS:
            body = soup.select_one(sel)
            if body:
                paragraphs = _paragraphs_from_html(str(body))
                if len(paragraphs) >= 3:
                    break
    if not title or len(paragraphs) < 2:
        raise ValueError(f"Không đọc được nội dung bài (giao diện nguồn có thể đã đổi): {item.url}")
    return SourceArticle(item.url, title, desc[:500], paragraphs, published, category, source_name)


@dataclass
class Candidate:
    """Một bài trên trang nguồn, chưa tải nội dung."""
    url: str
    source_name: str
    published: str = ""                      # biết trước nếu nguồn là RSS
    feed_item: FeedItem | None = None

    def load(self, session: requests.Session) -> SourceArticle:
        if self.feed_item is not None:
            return fetch_feed_article(self.feed_item, self.source_name, session)
        return fetch_vnexpress(self.url, session)

    def known_too_old(self) -> bool:
        """Đã biết giờ đăng từ RSS và quá MAX_AGE_HOURS → khỏi tải nội dung."""
        if not self.published or config.MAX_AGE_HOURS <= 0:
            return False
        age = SourceArticle(self.url, "", "", published=self.published).age_hours()
        return age is not None and age > config.MAX_AGE_HOURS


def list_candidates(source: dict, session: requests.Session) -> list[Candidate]:
    """source: {"name", "kind": "vnexpress"|"rss", "url", "listing"?}. Mới nhất trước."""
    if source["kind"] == "vnexpress":
        return [Candidate(u, source["name"]) for u in list_article_urls(session, source["url"])]
    try:
        items = list_feed(source["url"], session)
    except (requests.RequestException, ET.ParseError) as e:
        if not source.get("listing"):
            raise
        log.warning("Feed %s lỗi (%s) — đọc trang danh sách", source["url"], e)
        items = list_listing(source["listing"], session)
    return [Candidate(i.url, source["name"], i.published, i) for i in items]



def now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="minutes")
