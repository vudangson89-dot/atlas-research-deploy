# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A deployment package (no build system, no tests, no package manager) for **atlasresearch.blog**, a hybrid site:

- **Dynamic block** — WordPress at `/` ("Góc Kiến Thức" blog), installed on the server by script; WordPress code is *not* in this repo.
- **Static block** — `affiliate_hub/`, a hand-written HTML/CSS/JS page listing partner crypto exchanges (Moonbase, SCEX, TCEX, CAEX).

All docs, comments, log messages and page copy are in Vietnamese; keep new text in Vietnamese to match.

## Two deployment targets for `affiliate_hub/`

The same folder is deployed in two ways — check which one a change affects:

1. **LEMP server (Nginx)** — served at `/doi-tac/` via `alias` in `nginx/atlasresearch.blog.conf` (`location ^~ /doi-tac/` so no request reaches PHP-FPM). This is the flow described in README.md.
2. **Cloudflare Pages** (`atlas-research-vn.pages.dev`) — served at the site root. `affiliate_hub/_redirects` maps `/doi-tac/*` → `/`. The canonical URL, `og:url`/`og:image`, schema.org `url`, `robots.txt` and `sitemap.xml` currently all point to the pages.dev domain, not atlasresearch.blog.

Because the page is served under different base paths, all asset references in `index.html` must stay **relative** (`css/…`, `img/…`), never root-absolute.

## Server scripts (`scripts/`, run as root on Ubuntu/Debian)

- `setup.sh` — idempotent. Creates `/var/www/atlasresearch.blog/{wordpress,affiliate_hub,logs}`, copies `affiliate_hub/`, sets `www-data` ownership (dirs 755 / files 644, logs 775/664), installs WP-CLI, installs `maintenance.sh` as `/usr/local/sbin/atlas-maintenance` (root-owned, 750), then installs the Nginx config. It is a **two-pass** flow: without `/etc/letsencrypt/live/<domain>/fullchain.pem` it writes a temporary HTTP-only config (ACME challenge + 503); after `certbot`, rerunning it installs the full HTTPS config. When installing, it `sed`-rewrites the domain and the `unix:/run/php/php*-fpm.sock` path to the detected socket, backs up the old config, and restores it if `nginx -t` fails.
- `wp-install.sh` — idempotent WP-CLI install (DB + user, core in `vi` locale, `wp-config.php` with `FS_METHOD direct` and `DISALLOW_FILE_EDIT`, permalink `/%postname%/`, plugins RankMath / LiteSpeed Cache / Redis Cache). All settings are overridable via env vars; refuses to run if `DB_PASS`/`ADMIN_PASS` are unset (`__CHANGE_ME*`) or shorter than 12 chars:
  ```bash
  sudo DB_PASS='...' ADMIN_PASS='...' bash scripts/wp-install.sh
  ```
- `maintenance.sh` — subcommands `clean-locks | kill-zombies [--force] | fix-permissions | all [--force]`. `killall -9` only runs with `--force` and only targets php-fpm/nginx.

Domain, web root and `www-data` are hardcoded at the top of `setup.sh` and `maintenance.sh` (env-overridable only in `wp-install.sh`); change them consistently across all three plus the Nginx config.

There are no automated checks. To sanity-check edits locally:
```bash
bash -n scripts/*.sh          # syntax check
shellcheck scripts/*.sh       # if installed
nginx -t -c <conf>            # only meaningful on a server with the certs/snippets present
```

## Conventions that span files

- **Nginx location order matters**: the deny blocks (`wp-config.php`, dotfiles, PHP in uploads) must stay *before* the `\.php$` block. A `location` that declares its own `add_header` stops inheriting the server-level security headers.
- **Cache busting**: Nginx caches hub CSS/JS/images 30 days but HTML is never cached (`map $sent_http_content_type`). When editing `style.css` or `main.js`, bump `?v=YYYYMMDD` on both references in `index.html`.
- **Adding a partner** touches four places: a new `<article class="partner frame">` in `index.html` (pastel colours via `style="--brand:…;--brand-ink:#0F1B2D;--brand-deep:…"`, add `partner__plate--dark` for white-text logos), a logo in the hero's `.hero__logos` list, the `OFFICIAL` array in `js/main.js` (drives the "Kiểm tra link" checker), and the `application/ld+json` ItemList.
- **Referral links**: replace `<span class="btn btn--soon" …>` with `<a class="btn btn--secondary" href="…" target="_blank" rel="noopener sponsored" data-partner="…">Link giới thiệu</a>`.
- **Design rules**: one typeface (Be Vietnam Pro, 500/700/800), pastel colour fields with navy `#0F1B2D` text (light theme only, by choice), square corners, no borders/shadows/gradients, no eyebrow labels or 01/02 numbering, headlines at most two lines, ~6 font sizes via the `--t-*` tokens.
- **Full-screen frames**: every `.frame` (hero, each partner, checker, FAQ, footer) is exactly `100svh - var(--bar-h)` tall with `scroll-snap-type: y mandatory` on desktop (≥900px wide and ≥680px tall), and `main.js` pages one frame per wheel gesture there. Smaller screens fall back to `proximity` and natural heights. Content added to a frame must still fit one 1366×768 screen. The `.bar` toolbar is `position: sticky`. Reveal animations only apply under `.js` and `prefers-reduced-motion: no-preference`, so content stays visible without JS.
- `main.js` is progressive enhancement only (page must work without JS): copy buttons, reveal motion, wheel paging between frames, current-section nav highlight, and the client-side link checker (hostname match against `OFFICIAL`, plus lookalike/punycode warnings). Click tracking fires a `partner_click` event to `gtag`/`dataLayer` for any `a[data-partner]` (with optional `data-placement`) — keep those attributes on outbound partner links.
- **News tab** (`affiliate_hub/news/`): static pages, no build step. `news/index.html` is a single-column timeline (newest first; text left, 3:2 thumbnail right; `time[data-relative]` with a full ISO datetime is rewritten by `main.js` to "34 phút trước" for posts under 7 days old); each article lives in `news/<slug>/index.html` with its images beside it, built from `templates/news-article.html` (outside `affiliate_hub/`, so it is not deployed). Card thumbnail and article hero share `view-transition-name: thumb-<slug>` for the cross-document zoom (`@view-transition` in `style.css`). News pages carry `html.page-news` to turn off scroll-snap. Add each article to `sitemap.xml`; README has the step-by-step.
- Don't point a root cron at anything under `/var/www/…` (writable by `www-data`); use the installed `/usr/local/sbin/atlas-maintenance`.
- `.gitattributes` forces LF line endings — shell scripts with CRLF break on the server.

`rollback-intruction.md` documents tagging `v0.1.0` and rolling back (git tag + rsync, or tarball/mysqldump restore).
