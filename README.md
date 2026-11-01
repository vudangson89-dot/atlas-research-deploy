# Atlas Research — Gói triển khai (Deploy Package)

Cấu trúc gói khớp với PRD (Hybrid: WordPress động + Affiliate Hub tĩnh).

```
atlas-research-deploy/
├── nginx/
│   └── atlasresearch.blog.conf   # cấu hình HTTPS đầy đủ — setup.sh tự cài
├── scripts/
│   ├── setup.sh                  # thư mục + Affiliate Hub + phân quyền + WP-CLI + Nginx
│   ├── wp-install.sh             # WordPress core + DB + plugin (RankMath, LiteSpeed, Redis)
│   └── maintenance.sh            # dọn lock file, kill process treo, reset quyền
└── affiliate_hub/                # trang /doi-tac/ (HTML tĩnh, không qua PHP)
    ├── index.html                # SEO + Open Graph + schema.org sẵn
    ├── css/style.css             # giao diện sáng/tối tự động theo thiết bị
    ├── js/main.js                # nút sao chép tên miền + đo lượt click (tuỳ chọn)
    └── img/
        ├── logo.svg              # logo Atlas Research (dùng làm favicon)
        ├── favicon-32.png
        ├── apple-touch-icon.png  # icon khi lưu trang ra màn hình iPhone
        ├── og-cover.jpg          # ảnh chia sẻ Facebook/Zalo/Telegram (1200×630)
        └── partners/             # logo các sàn: moonbase, scex, tcex, caex
```

## Thứ tự triển khai trên server (Ubuntu/Debian + LEMP)

Trỏ DNS `atlasresearch.blog` và `www.atlasresearch.blog` về IP server trước khi bắt đầu.

1. **Cài LEMP** (nếu chưa có):
   ```bash
   sudo apt update
   sudo apt install -y nginx php-fpm php-mysql php-cli php-curl php-xml php-mbstring php-zip php-gd php-intl mysql-server curl unzip
   ```

2. **Upload gói lên server rồi chạy setup lần 1:**
   ```bash
   sudo bash scripts/setup.sh
   ```
   Script sẽ tạo thư mục, copy Affiliate Hub vào `/var/www/atlasresearch.blog/affiliate_hub`,
   phân quyền, cài WP-CLI, cài script bảo trì vào `/usr/local/sbin/atlas-maintenance`.
   Vì chưa có chứng chỉ SSL, script cài **cấu hình Nginx tạm (chỉ HTTP)** và in ra lệnh xin chứng chỉ.

3. **Xin chứng chỉ Let's Encrypt** (webroot — tự gia hạn và reload Nginx):
   ```bash
   sudo apt install -y certbot
   sudo certbot certonly --webroot -w /var/www/atlasresearch.blog/wordpress \
        -d atlasresearch.blog -d www.atlasresearch.blog \
        --deploy-hook "systemctl reload nginx"
   ```

4. **Chạy setup lần 2** — lúc này đã có chứng chỉ nên script cài cấu hình HTTPS đầy đủ
   (tự nhận đúng phiên bản PHP-FPM đang chạy: 8.1 / 8.2 / 8.3 …):
   ```bash
   sudo bash scripts/setup.sh
   ```

5. **Cài WordPress** — truyền mật khẩu qua biến môi trường (không cần sửa file,
   script từ chối chạy nếu mật khẩu còn là giá trị mẫu hoặc ngắn hơn 12 ký tự):
   ```bash
   sudo DB_PASS='mat-khau-db-manh' ADMIN_PASS='mat-khau-admin-manh' bash scripts/wp-install.sh
   ```
   Có thể đổi thêm `ADMIN_USER`, `ADMIN_EMAIL`, `DB_NAME`, `DB_USER`, `SITE_TITLE` theo cách tương tự.
   Script chạy lại được nhiều lần: bước nào đã xong sẽ được bỏ qua.

6. **Kiểm tra routing:**
   - `https://atlasresearch.blog/` → WordPress (Góc Kiến Thức)
   - `https://atlasresearch.blog/doi-tac/` → Affiliate Hub tĩnh (bỏ qua PHP-FPM hoàn toàn)
   - `http://…` và `https://www.…` → tự chuyển về `https://atlasresearch.blog/…`
   - Chia sẻ thử link `/doi-tac/` qua [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/) để kiểm tra ảnh OG.

## Cập nhật Affiliate Hub

- Sửa `affiliate_hub/…` rồi chạy lại `sudo bash scripts/setup.sh` (hoặc copy thẳng vào
  `/var/www/atlasresearch.blog/affiliate_hub/`). HTML không bị cache nên có hiệu lực ngay.
- CSS/JS/ảnh được cache 30 ngày. Khi sửa `style.css` hoặc `main.js`, **đổi số phiên bản**
  trong `index.html` (`style.css?v=20261003` → ngày hiện tại) để trình duyệt tải bản mới.
- Thêm sàn mới (mỗi sàn là một "chương" màu tràn viền):
  - nhân bản một khối `<article class="partner frame">` trong `index.html`. Màu pastel đặt qua
    `style="--brand:#nền-pastel;--brand-ink:#0F1B2D;--brand-deep:#pastel-đậm-hơn"`. Logo chữ
    trắng dùng thêm class `partner__plate--dark`. Nội dung mỗi khung phải vừa một màn hình;
  - thêm một ô logo vào danh sách `.hero__logos` ở khung mở đầu;
  - thêm sàn vào mảng `OFFICIAL` trong `js/main.js` (công cụ "Kiểm tra link");
  - thêm một mục trong `<script type="application/ld+json">`.
- Khi có link giới thiệu: thay thẻ `<span class="btn btn--soon" …>…</span>` bằng
  `<a class="btn btn--secondary" href="…" target="_blank" rel="noopener sponsored" data-partner="tên-sàn" data-placement="referral">Link giới thiệu</a>`
  (nút viền, đặt cạnh nút "Truy cập website").
- Nếu site gắn Google Analytics / Tag Manager, mỗi lượt click sang sàn được gửi thành sự kiện
  `partner_click` (kèm tên sàn và vị trí nút) — không cần cấu hình thêm.

## Đăng bài tin tức (tab "Tin tức", thư mục `affiliate_hub/news/`)

Mỗi bài là một thư mục riêng: `affiliate_hub/news/<duong-dan-bai>/` chứa `index.html` và ảnh của bài.

1. Copy `templates/news-article.html` thành `affiliate_hub/news/<duong-dan-bai>/index.html`
   (đường dẫn viết thường, không dấu, nối bằng gạch ngang) rồi thay mọi chỗ `{{...}}`.
2. Đặt ảnh đầu bài (tỉ lệ 16:9) và ảnh minh hoạ cạnh file `index.html`, tham chiếu bằng tên file.
3. Dán thẻ bài (mẫu ở cuối file template) vào `affiliate_hub/news/index.html`, ngay sau dòng
   `<!-- BÀI VIẾT: bắt đầu -->`. Bài mới nhất để trên cùng. Ghi giờ đăng đầy đủ trong `datetime`
   (ví dụ `2026-10-30T17:45+07:00`) để trang tự hiện "34 phút trước", "3 giờ trước"…
   `view-transition-name:thumb-<duong-dan-bai>` ở ảnh thu nhỏ và ảnh đầu bài phải giống nhau,
   để khi bấm vào bài, ảnh thu nhỏ phóng to thành ảnh đầu bài (trình duyệt hỗ trợ View Transitions).
4. Thêm URL bài vào `sitemap.xml`.

## Agent tin tức tự động (VnExpress → viết lại → duyệt qua Telegram)

Thư mục `news_agent/` (không deploy lên web). Chạy trên **máy Windows có GPU** (máy studio YouTube),
vì ảnh được vẽ miễn phí bằng ComfyUI + FLUX.2 klein qua `lib\images.py` của studio.

- **Mỗi 60 phút** (tác vụ `AtlasNews-Scan`): quét `https://vnexpress.net/tag/tai-san-so-1064801`,
  với mỗi bài mới đăng trong 12 giờ gần nhất (`MAX_AGE_HOURS`; tối đa `MAX_PER_RUN` bài, chống trùng theo URL và hash nội dung):
  1. viết lại bằng lời văn của Atlas Research qua OpenRouter (`llm.py`, theo bộ rewrite kit của
     Social_product: tự chọn model rẻ nhất trong danh mục đã kiểm định, bảng giá cache 24h,
     model lỗi thì thử model kế tiếp, lỗi 401/402/403 thì dừng, luôn tắt reasoning);
  2. vẽ ảnh đầu bài + ảnh minh hoạ bằng GPU (16:9, phong cách ảnh bìa tin crypto 3D);
  3. gửi lên Telegram: ảnh + sapo, file `preview.html` đọc toàn văn, và các nút
     **✅ Duyệt / 🔁 Viết lại / 🎨 Ảnh khác / ❌ Bỏ**. Lần chạy đầu chỉ lấy vài bài mới nhất.
- **Bot duyệt** (tác vụ `AtlasNews-Bot`, luôn chạy): **Duyệt** → thêm bài vào
  `affiliate_hub/news/<slug>/`, chèn thẻ vào `news/index.html`, thêm URL vào `sitemap.xml`,
  commit `Tin tức: <tiêu đề>`, push lên `GIT_BRANCH` → Cloudflare Pages tự deploy.
  **🎨 Ảnh khác** chỉ vẽ lại ảnh (seed mới). Muốn sửa chữ: **reply** tin có nút bằng yêu cầu.
  Chỉ id trong `TELEGRAM_ALLOWED_USER_IDS` mới bấm được; nháp không duyệt sau 7 ngày tự xoá.
- **Quy tắc GPU** (theo "Họa sĩ GPU"): card 6 GB chỉ làm một việc một lúc. Nếu ComfyUI đang chạy sẵn
  (studio đang dùng), agent **nhường** và để lượt sau (`COMFY_SHARED=1` để dùng chung,
  `IMAGE_FALLBACK=openrouter` để vẽ bằng OpenRouter khi GPU bận). Agent tự bật ComfyUI khi cần
  và **tắt ngay** khi vẽ xong. Máy tắt thì lượt quét bị lỡ sẽ chạy bù khi bật lại.
- Bài luôn ghi "Nguồn tham khảo: VnExpress" kèm link gốc và dòng miễn trừ; prompt ép trung thực,
  diễn đạt lại hoàn toàn. Ảnh không vẽ người thật, không logo thương hiệu thật.
  Sửa giọng văn: `news_agent/prompts/rewrite.md`; phong cách ảnh: `news_agent/prompts/image.md`.

Cài trên máy Windows (Python ≥ 3.10, git đã đăng nhập GitHub có quyền push):

1. Tạo bot qua [@BotFather](https://t.me/BotFather) lấy token. Nhắn cho bot (hoặc thêm bot vào nhóm),
   mở `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy `chat.id` và id người duyệt (`from.id`).
2. Clone repo vào thư mục riêng của agent rồi chạy script từ đó (lần đầu script tạo venv và
   file cấu hình rồi dừng):
   ```powershell
   git clone https://github.com/Hoang-Minh-Nghia/atlas-research-deploy.git D:\atlas-news\repo
   cd D:\atlas-news\repo
   powershell -ExecutionPolicy Bypass -File scripts\news-agent-install.ps1 -RepoDir D:\atlas-news\repo
   ```
3. Điền `%LOCALAPPDATA%\atlas-news\atlas-news.env`: `OPENROUTER_API_KEY`, `TELEGRAM_*`,
   `STUDIO_LIB_DIR` (thư mục `lib` có `images.py`), `STUDIO_PYTHON` (Python có torch/gguf của studio).
4. Chạy lại lệnh ở bước 2 để đăng ký 2 tác vụ. Kiểm tra:
   ```powershell
   Start-ScheduledTask AtlasNews-Scan
   Get-Content "$env:LOCALAPPDATA\atlas-news\logs\bot.log" -Wait
   ```

Chạy thử không gửi Telegram, không ghi trạng thái (trong thư mục repo, đã điền `news_agent\.env`):
```powershell
python -m news_agent.scan --dry-run --limit 1 --out .\news-agent-dry-run
```

Lưu ý: thư mục `-RepoDir` là bản clone riêng của agent — mỗi lần đăng bài agent `reset --hard` về
`origin/<GIT_BRANCH>`, đừng sửa tay ở đó. Danh mục model mặc định được đo trên bài tiếng Anh ngắn;
chạy `--dry-run` vài bài rồi chỉnh `LLM_REWRITE_CATALOG` nếu cần. Không có GPU (VPS Linux) thì dùng
`sudo bash scripts/news-agent-install.sh` với `IMAGE_BACKEND=openrouter` (systemd). Bản Nginx trên server
(`/doi-tac/`) không tự cập nhật — chạy lại `setup.sh` như mục "Cập nhật Affiliate Hub" nếu dùng.

## Bảo trì định kỳ

```bash
sudo atlas-maintenance all                     # dọn lock + kiểm tra process nặng + fix quyền
sudo atlas-maintenance kill-zombies --force    # chỉ cưỡng chế kill khi thực sự cần
```

Khuyến nghị chạy `fix-permissions` định kỳ qua cron (ví dụ mỗi đêm) để tránh lỗi
`Permission denied (errno=13)` tích tụ theo thời gian — tạo file `/etc/cron.d/atlas-maintenance`:
```
0 3 * * * root /usr/local/sbin/atlas-maintenance fix-permissions >> /var/log/atlas-maintenance.log 2>&1
```
Script được cài ngoài thư mục web và chỉ root sửa được — **không** trỏ cron root vào file
nằm trong `/var/www/…`, vì `www-data` có quyền ghi ở đó (nếu WordPress bị xâm nhập,
kẻ tấn công có thể sửa script và chiếm quyền root).

## Lưu ý an toàn

- `killall -9` trong `maintenance.sh` chỉ nhắm vào tiến trình `php-fpm`/`nginx` và chỉ
  chạy khi gọi kèm `--force` — tránh vô tình kill nhầm dịch vụ khác trên server dùng chung.
- Nginx đã chặn: thực thi PHP trong `uploads`, file ẩn (`.env`, `.git`…), `wp-config.php`.
  Sau khi HTTPS chạy ổn định có thể bật HSTS (dòng `Strict-Transport-Security` đang để comment).
- Nếu không dùng Jetpack / ứng dụng WordPress trên điện thoại, bỏ comment dòng chặn `xmlrpc.php`.
- Trên Nginx, plugin LiteSpeed Cache chỉ dùng được phần tối ưu CSS/JS/ảnh; page cache của
  plugin chỉ chạy trên máy chủ LiteSpeed.
- Sau khi cài xong, đổi mật khẩu admin WordPress trong `wp-admin` nếu đã từng gửi mật khẩu qua kênh không an toàn.
