(function () {
  // ---------------- Mobile menu ----------------
  const btn = document.getElementById('mobileMenuBtn');
  const root = document.getElementById('mobileMenuRoot');
  const drawer = document.getElementById('mobileMenu');
  const backdrop = document.getElementById('mobileMenuBackdrop');
  const closeBtn = document.getElementById('mobileMenuClose');

  function lockScroll(lock) {
    document.documentElement.style.overflow = lock ? 'hidden' : '';
    document.body.style.overflow = lock ? 'hidden' : '';
  }

  function openMenu() {
    if (!root || !btn) return;
    root.classList.add('open');
    root.setAttribute('aria-hidden', 'false');
    btn.setAttribute('aria-expanded', 'true');
    lockScroll(true);
  }

  function closeMenu() {
    if (!root || !btn) return;
    root.classList.remove('open');
    root.setAttribute('aria-hidden', 'true');
    btn.setAttribute('aria-expanded', 'false');
    lockScroll(false);
  }

  if (btn && root) {
    btn.addEventListener('click', openMenu);
    if (backdrop) backdrop.addEventListener('click', closeMenu);
    if (closeBtn) closeBtn.addEventListener('click', closeMenu);

    // Close after tapping any link inside the drawer
    if (drawer) {
      drawer.addEventListener('click', function (e) {
        var a = e.target && e.target.closest ? e.target.closest('a') : null;
        if (!a) return;
        closeMenu();
      });
    }

    // ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeMenu();
    });
  }

// ---------------- Video hero ----------------
  const video = document.getElementById('heroVideo');
  const soundToggle = document.getElementById('soundToggle');
  const scrollNext = document.getElementById('scrollNext');

  if (scrollNext) {
    scrollNext.addEventListener('click', () => {
      const el = document.getElementById('start');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  if (video) {
    // iOS/FB in-app browsers can be strict: ensure muted + inline playback, then try autoplay.
    video.muted = true;
    video.setAttribute('muted', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');

    const tryPlay = () => {
      try {
        const p = video.play();
        if (p && typeof p.catch === 'function') p.catch(() => {});
      } catch (_) {}
    };

    // Best-effort autoplay
    tryPlay();
    video.addEventListener('loadeddata', tryPlay, { once: true });
    video.addEventListener('canplay', tryPlay, { once: true });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) tryPlay();
    });

    // Fallback: start on first user interaction (fixes iPhone / in-app autoplay blocks)
    const armGesture = () => {
      const handler = () => {
        tryPlay();
        window.removeEventListener('touchstart', handler, true);
        window.removeEventListener('click', handler, true);
        window.removeEventListener('scroll', handler, true);
      };
      window.addEventListener('touchstart', handler, true);
      window.addEventListener('click', handler, true);
      window.addEventListener('scroll', handler, true);
    };
    armGesture();

    // Optional sound toggle if present (kept for compatibility)
    if (soundToggle) {
      const updateLabel = () => {
        soundToggle.textContent = video.muted ? 'Włącz dźwięk' : 'Wycisz';
      };
      updateLabel();
      soundToggle.addEventListener('click', async () => {
        try {
          video.muted = !video.muted;
          if (!video.muted) video.volume = 1.0;
          await video.play();
        } catch (_) {
          video.muted = true;
        } finally {
          updateLabel();
        }
      });
    }
  }

  // ---------------- Effects gallery: show first N, then load more ----------------
: show first N, then load more ----------------
  document.querySelectorAll('[data-effects-gallery]').forEach((gallery) => {
    const items = Array.from(gallery.querySelectorAll('[data-effects-item]'));
    const moreBtn = gallery.querySelector('[data-effects-more]');
    const shownEl = gallery.querySelector('[data-effects-shown]');
    const totalEl = gallery.querySelector('[data-effects-total]');
    const initial = parseInt(gallery.getAttribute('data-initial') || '8', 10);
    const step = parseInt(gallery.getAttribute('data-step') || '8', 10);

    if (!items.length) return;

    const total = items.length;
    if (totalEl) totalEl.textContent = String(total);

    function shownCount() {
      return items.filter((el) => !el.classList.contains('hidden')).length;
    }

    function updateUI() {
      const shown = shownCount();
      if (shownEl) shownEl.textContent = String(shown);

      if (!moreBtn) return;
      const remaining = Math.max(0, total - shown);
      if (remaining <= 0) {
        moreBtn.classList.add('hidden');
        return;
      }

      const next = Math.min(step, remaining);
      // Label: show how many will be revealed and how many total remain.
      moreBtn.textContent = `Pokaż kolejne ${next} (pozostało ${remaining})`;
    }

    // Ensure the first `initial` are visible, others hidden (server already hides, but keep safe)
    items.forEach((el, idx) => {
      if (idx < initial) el.classList.remove('hidden');
      else el.classList.add('hidden');
    });

    updateUI();

    if (moreBtn) {
      moreBtn.addEventListener('click', () => {
        const shown = shownCount();
        const toShow = items.slice(shown, shown + step);
        toShow.forEach((el) => el.classList.remove('hidden'));
        updateUI();
      });
    }
  });

  // ---------------- Admin notifications: smart reply (mailto + Gmail fallback) ----------------
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('[data-reply-link]') : null;
    if (!a) return;

    var mailto = a.getAttribute('href') || '';
    var gmail = a.getAttribute('data-gmail') || '';
    if (!mailto || mailto.indexOf('mailto:') !== 0) return;

    // Attempt to open the native mail client; if nothing happens (common on mobile/webviews),
    // fall back to Gmail web compose which reliably pre-fills the recipient.
    e.preventDefault();

    var didBlur = false;
    function onBlur() {
      didBlur = true;
      window.removeEventListener('blur', onBlur);
    }

    window.addEventListener('blur', onBlur);
    window.location.href = mailto;

    setTimeout(function () {
      window.removeEventListener('blur', onBlur);
      if (!didBlur && gmail) {
        window.open(gmail, '_blank', 'noopener');
      }
    }, 900);
  });

  // ---------------- Admin notifications: expand/collapse message row ----------------
  document.addEventListener('click', function (e) {
    var toggle = e.target && e.target.closest ? e.target.closest('.lead-toggle') : null;
    if (!toggle) return;

    e.preventDefault();
    var targetId = toggle.getAttribute('data-target') || '';
    if (!targetId) return;

    var row = document.getElementById(targetId);
    if (!row) return;

    var isHidden = row.classList.contains('hidden');
    if (isHidden) {
      row.classList.remove('hidden');
      toggle.textContent = 'Ukryj';
      toggle.setAttribute('aria-expanded', 'true');
    } else {
      row.classList.add('hidden');
      toggle.textContent = 'Podgląd';
      toggle.setAttribute('aria-expanded', 'false');
    }
  });

})();
