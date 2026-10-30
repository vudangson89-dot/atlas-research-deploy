/* =============================================================================
   ATLAS RESEARCH — Affiliate Hub script
   File đích: /var/www/atlasresearch.blog/affiliate_hub/js/main.js
   Trang vẫn hoạt động đầy đủ khi tắt JavaScript; script chỉ bổ sung tiện ích.
   ============================================================================= */
(function () {
  'use strict';

  // Có JS -> bật các trạng thái ẩn ban đầu cho chuyển động (không JS: nội dung hiện đủ)
  var root = document.documentElement;
  root.classList.remove('no-js');
  root.classList.add('js');

  // ---- Năm hiện tại ở footer ----
  var yearEl = document.querySelector('[data-year]');
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  // ---- Nút "Sao chép" tên miền chính thức ----
  // Clipboard API có thể bị chặn (trình duyệt nhúng của Zalo/Facebook, iframe...)
  // nên luôn có phương án dự phòng execCommand.
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy') ? resolve() : reject(new Error('copy failed'));
      } catch (err) {
        reject(err);
      }
      document.body.removeChild(ta);
    });
  }

  function flash(btn, message, ok) {
    var label = btn.querySelector('[data-label]');
    if (!label) return;
    if (!btn.dataset.original) btn.dataset.original = label.textContent;
    label.textContent = message;
    btn.classList.toggle('is-done', ok);
    clearTimeout(btn._timer);
    btn._timer = setTimeout(function () {
      label.textContent = btn.dataset.original;
      btn.classList.remove('is-done');
    }, 1800);
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-copy]'), function (btn) {
    btn.hidden = false;
    btn.addEventListener('click', function () {
      copyText(btn.getAttribute('data-copy')).then(
        function () { flash(btn, 'Đã sao chép', true); },
        function () { flash(btn, 'Không thể sao chép', false); }
      );
    });
  });

  // ---- Đo lượt click sang sàn đối tác (khi site đã gắn Google Analytics / GTM) ----
  document.addEventListener('click', function (e) {
    var link = e.target.closest ? e.target.closest('a[data-partner]') : null;
    if (!link) return;
    var detail = {
      partner: link.getAttribute('data-partner'),
      placement: link.getAttribute('data-placement') || ''
    };
    if (typeof window.gtag === 'function') {
      window.gtag('event', 'partner_click', detail);
    } else if (Array.isArray(window.dataLayer)) {
      window.dataLayer.push({ event: 'partner_click', partner: detail.partner, placement: detail.placement });
    }
  });

  // ---- Chuyển động: tiêu đề trượt lên khi tải, từng khối hiện dần khi cuộn tới ----
  var masked = document.querySelector('.masked');
  if (masked) requestAnimationFrame(function () { masked.classList.add('is-in'); });

  var reveals = document.querySelectorAll('[data-reveal]');
  // Các phần tử cùng khối hiện lệch nhau 80ms
  Array.prototype.forEach.call(reveals, function (el) {
    var siblings = el.parentElement ? el.parentElement.querySelectorAll(':scope > [data-reveal]') : [];
    var i = Array.prototype.indexOf.call(siblings, el);
    if (i > 0) el.style.setProperty('--delay', (i * 80) + 'ms');
  });
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -10% 0px' });
    Array.prototype.forEach.call(reveals, function (el) { io.observe(el); });
  } else {
    Array.prototype.forEach.call(reveals, function (el) { el.classList.add('is-in'); });
  }

  // ---- Kiểm tra link: so tên miền với danh sách chính thức (chạy hoàn toàn trên máy) ----
  var OFFICIAL = [
    { name: 'Moonbase', domain: 'moonbase.vn', url: 'https://moonbase.vn/', key: 'moonbase' },
    { name: 'SCEX', domain: 'scex.com.vn', url: 'https://scex.com.vn/', key: 'scex' },
    { name: 'TCEX', domain: 'tcex.com.vn', url: 'https://www.tcex.com.vn/', key: 'tcex' },
    { name: 'CAEX', domain: 'caex.com.vn', url: 'https://www.caex.com.vn/', key: 'caex' }
  ];

  function hostnameOf(input) {
    var text = input.trim();
    if (!text) return '';
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) text = 'https://' + text;
    try {
      return new URL(text).hostname.toLowerCase().replace(/\.$/, '');
    } catch (err) {
      return '';
    }
  }

  // Khoảng cách chỉnh sửa giữa hai chuỗi, để bắt tên gõ sai cố ý (moonbsae, tcexx…)
  function distance(a, b) {
    var prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      for (j = 1; j <= b.length; j++) {
        cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      prev = cur;
    }
    return prev[b.length];
  }

  function check(host) {
    var i, p;
    for (i = 0; i < OFFICIAL.length; i++) {
      p = OFFICIAL[i];
      if (host === p.domain || host.slice(-(p.domain.length + 1)) === '.' + p.domain) {
        return { kind: 'ok', partner: p };
      }
    }
    var labels = host.split('.');
    for (i = 0; i < OFFICIAL.length; i++) {
      p = OFFICIAL[i];
      if (host.indexOf(p.key) !== -1) return { kind: 'warn', partner: p };
      for (var k = 0; k < labels.length; k++) {
        if (labels[k].length >= 3 && distance(labels[k], p.key) <= (p.key.length > 5 ? 2 : 1)) {
          return { kind: 'warn', partner: p };
        }
      }
    }
    if (host.indexOf('xn--') !== -1) return { kind: 'warn', partner: null };
    return { kind: 'unknown' };
  }

  var form = document.querySelector('[data-checker]');
  if (form) {
    var input = form.querySelector('input');
    var out = form.querySelector('[data-result]');

    function show(kind, html) {
      out.className = 'checker__result is-' + kind;
      out.innerHTML = html;
      out.hidden = false;
    }

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var host = hostnameOf(input.value);
      if (!host) {
        show('unknown', '<strong>Chưa đọc được đường link</strong>Hãy dán lại, ví dụ: moonbase.vn hoặc https://scex.com.vn/login');
        return;
      }
      var r = check(host);
      var shown = escapeHtml(host);
      if (r.kind === 'ok') {
        show('ok', '<strong>Đúng tên miền chính thức của ' + r.partner.name + '</strong>' + shown +
          ' thuộc ' + r.partner.domain + '. <a href="' + r.partner.url + '" target="_blank" rel="noopener sponsored" data-partner="' +
          r.partner.key + '" data-placement="checker">Mở ' + r.partner.domain + '</a>');
      } else if (r.kind === 'warn') {
        show('warn', '<strong>Cảnh báo: có thể là trang giả mạo</strong>' + shown + ' không phải tên miền chính thức' +
          (r.partner ? ' của ' + r.partner.name + ' (' + r.partner.domain + ')' : '') +
          '. Đừng đăng nhập hay nhập mã OTP ở trang này.');
      } else {
        show('unknown', '<strong>Không thuộc bốn sàn trong danh sách</strong>' + shown +
          ' không khớp với moonbase.vn, scex.com.vn, tcex.com.vn hay caex.com.vn.');
      }
    });
  }

  // ---- Thanh công cụ: gạch chân mục đang xem ----
  var navLinks = document.querySelectorAll('.bar__nav a[href^="#"]');
  if (navLinks.length && 'IntersectionObserver' in window) {
    var byId = {};
    Array.prototype.forEach.call(navLinks, function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var watched = ['doi-tac', 'kiem-tra', 'an-toan'];
    var sections = [];
    watched.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) sections.push(el);
    });
    var navIo = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = byId[entry.target.id];
        if (link) link.classList.toggle('is-current', entry.isIntersecting);
      });
    }, { rootMargin: '-45% 0px -45% 0px' });
    sections.forEach(function (el) { navIo.observe(el); });
  }

  // ---- Lăn chuột nhảy đúng một khung hình (máy tính, màn hình đủ cao) ----
  // CSS scroll-snap lo phần lớn; đoạn này giúp mỗi lần lăn chuột/vuốt touchpad
  // luôn sang đúng khung kế tiếp, kể cả trên trình duyệt xử lý snap khác nhau.
  var pagedMq = window.matchMedia('(min-width: 900px) and (min-height: 680px)');
  var calmMq = window.matchMedia('(prefers-reduced-motion: reduce)');
  var frames = Array.prototype.slice.call(document.querySelectorAll('.frame'));
  var bar = document.querySelector('.bar');
  var locked = false, idleTimer = null, minTimer = null, minDone = true;

  function currentFrame() {
    var offset = bar ? bar.offsetHeight : 0;
    var y = window.scrollY + offset, best = 0, bestDist = Infinity;
    frames.forEach(function (f, i) {
      var d = Math.abs(f.offsetTop - y);
      if (d < bestDist) { bestDist = d; best = i; }
    });
    return best;
  }

  function unlockWhenIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function () { if (minDone) locked = false; else idleTimer = null; }, 180);
  }

  if (frames.length) {
    window.addEventListener('wheel', function (e) {
      if (!pagedMq.matches || e.ctrlKey || Math.abs(e.deltaY) < Math.abs(e.deltaX)) return;
      e.preventDefault();
      if (locked) { unlockWhenIdle(); return; }   // quán tính touchpad: chờ dứt hẳn
      if (Math.abs(e.deltaY) < 4) return;
      var i = currentFrame() + (e.deltaY > 0 ? 1 : -1);
      if (i < 0 || i >= frames.length) return;
      locked = true; minDone = false;
      clearTimeout(minTimer);
      minTimer = setTimeout(function () { minDone = true; if (!idleTimer) locked = false; }, 650);
      idleTimer = null;
      frames[i].scrollIntoView({ behavior: calmMq.matches ? 'auto' : 'smooth', block: 'start' });
    }, { passive: false });
  }

  // ---- Tin tức: hiển thị thời gian đăng dạng "34 phút trước" (không JS: giữ ngày tháng) ----
  Array.prototype.forEach.call(document.querySelectorAll('time[data-relative]'), function (el) {
    var t = Date.parse(el.getAttribute('datetime'));
    if (isNaN(t)) return;
    var mins = Math.floor((Date.now() - t) / 60000);
    if (mins < 0) return;
    var text;
    if (mins < 1) text = 'Vừa xong';
    else if (mins < 60) text = mins + ' phút trước';
    else if (mins < 24 * 60) text = Math.floor(mins / 60) + ' giờ trước';
    else if (mins < 7 * 24 * 60) text = Math.floor(mins / 1440) + ' ngày trước';
    else return;   // quá 7 ngày: giữ nguyên ngày tháng
    el.title = el.textContent;
    el.textContent = text;
  });
})();
