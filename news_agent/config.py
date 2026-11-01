"""Cấu hình đọc từ biến môi trường.

Thứ tự nạp file: $ATLAS_NEWS_ENV → news_agent/.env (Windows) → /etc/atlas-news.env (Linux/systemd).
Biến đã có trong môi trường luôn được ưu tiên.
"""
import os
import sys
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent


def _load_env_file(path: str) -> None:
    """Nạp file KEY=VALUE khi chạy tay (systemd đã nạp sẵn qua EnvironmentFile)."""
    p = Path(path)
    if not p.is_file():
        return
    try:
        lines = p.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip("'\"")
        os.environ.setdefault(key.strip(), val)


if os.environ.get("ATLAS_NEWS_ENV"):
    _load_env_file(os.environ["ATLAS_NEWS_ENV"])
else:
    _load_env_file(str(PKG_DIR / ".env"))
    _load_env_file("/etc/atlas-news.env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


SOURCE_URL = _get("SOURCE_URL", "https://vnexpress.net/tag/tai-san-so-1064801")
SOURCE_NAME = _get("SOURCE_NAME", "VnExpress")
MAX_PER_RUN = int(_get("MAX_PER_RUN", "3"))
# Chỉ lấy bài đăng trong bấy nhiêu giờ gần nhất (0 = không giới hạn).
MAX_AGE_HOURS = float(_get("MAX_AGE_HOURS", "12"))
DRAFT_TTL_DAYS = int(_get("DRAFT_TTL_DAYS", "7"))
USER_AGENT = _get("USER_AGENT", "AtlasResearchNewsBot/1.0 (+https://atlas-research-vn.pages.dev/)")

# Khoá riêng cho vai trò viết lại (giống Social_product), không có thì dùng khoá chung.
OPENROUTER_API_KEY = _get("LLM_REWRITE_API_KEY") or _get("OPENROUTER_API_KEY")
# Ép một model cụ thể (thử đầu tiên); để trống = tự chọn model rẻ nhất trong danh mục.
LLM_REWRITE_MODEL = _get("LLM_REWRITE_MODEL") or _get("OPENROUTER_TEXT_MODEL")
# Danh mục model đã kiểm định, cách nhau bằng dấu phẩy; để trống = danh mục mặc định trong llm.py.
LLM_REWRITE_CATALOG = [m.strip() for m in _get("LLM_REWRITE_CATALOG").split(",") if m.strip()]
LLM_MAX_TOKENS = int(_get("LLM_MAX_TOKENS", "3500"))
OPENROUTER_IMAGE_MODEL = _get("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image")
OPENROUTER_URL = _get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
FIGURES_PER_ARTICLE = int(_get("FIGURES_PER_ARTICLE", "1"))

# Tạo ảnh: "comfy" = GPU máy nhà (ComfyUI + FLUX.2 klein qua lib/images.py của studio),
# "openrouter" = model ảnh trả phí trên OpenRouter.
IMAGE_BACKEND = _get("IMAGE_BACKEND", "comfy").lower()
IMAGE_FALLBACK = _get("IMAGE_FALLBACK").lower()          # "openrouter" để dùng khi GPU bận/lỗi
STUDIO_LIB_DIR = Path(_get("STUDIO_LIB_DIR", "D:/youtube/studio/lib"))
STUDIO_PYTHON = _get("STUDIO_PYTHON", sys.executable)
COMFY_URL = _get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
COMFY_SHARED = _get("COMFY_SHARED", "0") == "1"           # 1 = dùng chung ComfyUI đang chạy sẵn
COMFY_SIZE = tuple(int(x) for x in _get("COMFY_SIZE", "1344x768").lower().split("x"))
COMFY_TIMEOUT = int(_get("COMFY_TIMEOUT", "600"))

TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
TELEGRAM_ALLOWED_USER_IDS = {
    int(x) for x in _get("TELEGRAM_ALLOWED_USER_IDS").replace(" ", "").split(",") if x.lstrip("-").isdigit()
}

REPO_DIR = Path(_get("REPO_DIR", str(PKG_DIR.parent)))
GIT_BRANCH = _get("GIT_BRANCH", "main")
GIT_REMOTE = _get("GIT_REMOTE", "origin")
SITE_URL = _get("SITE_URL", "https://atlas-research-vn.pages.dev").rstrip("/")

_DEFAULT_STATE = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "atlas-news" if os.name == "nt" else Path("/var/lib/atlas-news")
)
STATE_DIR = Path(_get("STATE_DIR", str(_DEFAULT_STATE)))
DRAFTS_DIR = STATE_DIR / "drafts"
DB_PATH = STATE_DIR / "state.sqlite3"
LOCK_PATH = STATE_DIR / "agent.lock"

TEMPLATE_PATH = REPO_DIR / "templates" / "news-article.html"
NEWS_DIR = REPO_DIR / "affiliate_hub" / "news"
NEWS_INDEX = NEWS_DIR / "index.html"
SITEMAP = REPO_DIR / "affiliate_hub" / "sitemap.xml"
PROMPTS_DIR = PKG_DIR / "prompts"


def require(*names: str) -> None:
    missing = [n for n in names if not globals().get(n) or str(globals().get(n)).startswith("__CHANGE_ME")]
    if missing:
        raise SystemExit("Thiếu cấu hình: " + ", ".join(missing) + " (xem /etc/atlas-news.env)")
