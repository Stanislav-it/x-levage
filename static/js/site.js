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
  const scrollNext = document.getElementById('scrollNext');
  const soundToggle = document.getElementById('soundToggle');
  const soundLabel = document.getElementById('soundLabel');

  if (scrollNext) {
    scrollNext.addEventListener('click', () => {
      const el = document.getElementById('start');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  if (video) {
    // iOS/Safari requires muted + playsinline set as properties too.
    video.muted = true;
    video.defaultMuted = true;
    video.setAttribute('muted', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');
    // Ensure src is set only after muted/playsinline are applied (helps iOS autoplay).
    // Use a silent asset for autoplay reliability; swap to the audio asset when the user enables sound.
    const silentSrc = video.getAttribute('data-src');
    const audioSrc = video.getAttribute('data-audio-src') || '';

    function setSrcKeepTime(nextSrc, nextMuted) {
      if (!nextSrc) return;
      const current = video.getAttribute('src') || '';
      if (current === nextSrc) {
        video.muted = nextMuted;
        video.defaultMuted = nextMuted;
        return;
      }
      const t = (typeof video.currentTime === 'number' && isFinite(video.currentTime)) ? video.currentTime : 0;
      video.muted = nextMuted;
      video.defaultMuted = nextMuted;
      video.setAttribute('src', nextSrc);
      try { video.load(); } catch (_) {}
      // After metadata is available, restore approximate time.
      const restore = () => {
        try { video.currentTime = Math.min(t, Math.max(0, (video.duration || t))); } catch (_) {}
      };
      video.addEventListener('loadedmetadata', restore, { once: true });
    }

    if (silentSrc && !video.getAttribute('src')) {
      setSrcKeepTime(silentSrc, true);
    }


    // Best-effort: ensure the hero video actually starts (iOS/FB in-app can be finicky).
    const tryPlay = () => {
      try {
        if (video.readyState === 0) {
          try { video.load(); } catch (_) {}
        }
        const p = video.play();
        if (p && typeof p.catch === 'function') p.catch(() => {});
      } catch (_) {}
    };

    // Attempt multiple times across the initial load window.
    tryPlay();
    setTimeout(tryPlay, 200);
    setTimeout(tryPlay, 800);
    setTimeout(tryPlay, 1500);
    video.addEventListener('loadedmetadata', tryPlay, { once: true });
    video.addEventListener('loadeddata', tryPlay, { once: true });
    video.addEventListener('canplay', tryPlay, { once: true });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) tryPlay();
    });

    // If autoplay is blocked, start playback on the very first user interaction
    // (so user doesn't have to hit the native play triangle).
    const startOnFirstGesture = () => {
      tryPlay();
      window.removeEventListener('touchstart', startOnFirstGesture, true);
      window.removeEventListener('click', startOnFirstGesture, true);
      window.removeEventListener('scroll', startOnFirstGesture, true);
    };
    window.addEventListener('touchstart', startOnFirstGesture, { passive: true, capture: true, once: true });
    window.addEventListener('click', startOnFirstGesture, { capture: true, once: true });
    window.addEventListener('scroll', startOnFirstGesture, { passive: true, capture: true, once: true });

    // Do not attach click-to-pause (touch users can pause accidentally).


    // Optional: user-controlled sound toggle (does not affect autoplay: video starts muted).
    if (soundToggle) {
      const renderSoundState = () => {
        if (!soundLabel) return;
        soundLabel.textContent = video.muted ? 'Włącz dźwięk' : 'Wycisz';
      };
      renderSoundState();

      soundToggle.addEventListener('click', async () => {
        // User gesture: enable/disable sound. For iOS reliability, swap assets:
        // - muted autoplay uses silentSrc
        // - unmuted uses audioSrc (if available)
        const wantSound = video.muted;
        try {
          if (wantSound) {
            // Switch to audio asset if provided, then unmute.
            if (audioSrc) setSrcKeepTime(audioSrc, false);
            video.muted = false;
            video.defaultMuted = false;
            video.volume = 1.0;
          } else {
            // Mute (and optionally return to silent asset)
            video.muted = true;
            video.defaultMuted = true;
            if (silentSrc) setSrcKeepTime(silentSrc, true);
          }
          await video.play();
        } catch (_) {
          // If something blocks unmuted playback, fall back to muted silent playback.
          video.muted = true;
          video.defaultMuted = true;
          if (silentSrc) setSrcKeepTime(silentSrc, true);
          try { await video.play(); } catch (_) {}
        } finally {
          renderSoundState();
        }
      });
    }
  }

  // ---------------- Effects gallery: show first N, then load more ----------------
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
