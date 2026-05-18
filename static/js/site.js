(function () {
  // ---------------- Analytics helpers (GTM / GA4 / Google Ads) ----------------
  const analyticsConfig = window.xlvAnalyticsConfig || {};

  function sanitizeAnalyticsParams(params) {
    const blocked = {
      name: true,
      email: true,
      phone: true,
      message: true,
      full_name: true,
      user_email: true,
      user_phone: true
    };
    const clean = {};
    Object.keys(params || {}).forEach((key) => {
      if (blocked[key]) return;
      const value = params[key];
      if (value === undefined || value === null || value === '') return;
      if (typeof value === 'string') clean[key] = value.slice(0, 180);
      else if (typeof value === 'number' || typeof value === 'boolean') clean[key] = value;
      else clean[key] = String(value).slice(0, 180);
    });
    return clean;
  }

  function adsSendToForEvent(eventName, params) {
    const adsId = analyticsConfig.googleAdsConversionId || '';
    if (!adsId) return '';

    let label = '';
    if (eventName === 'presentation_request' || (params && params.lead_type === 'presentation')) {
      label = analyticsConfig.googleAdsPresentationConversionLabel || analyticsConfig.googleAdsLeadConversionLabel || '';
    } else if (eventName === 'generate_lead' || eventName === 'contact_form_submit_success') {
      label = analyticsConfig.googleAdsLeadConversionLabel || '';
    }
    return label ? `${adsId}/${label}` : '';
  }

  function trackEvent(eventName, params) {
    if (!eventName) return;
    const cleanParams = sanitizeAnalyticsParams(params || {});
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push(Object.assign({ event: eventName }, cleanParams));

    // Direct GA4 fallback is used when GA4 was loaded without GTM.
    if (typeof window.gtag === 'function' && analyticsConfig.ga4MeasurementId && !analyticsConfig.gtmId) {
      window.gtag('event', eventName, cleanParams);

      const sendTo = adsSendToForEvent(eventName, cleanParams);
      if (sendTo) {
        window.gtag('event', 'conversion', Object.assign({ send_to: sendTo }, cleanParams));
      }
    }
  }

  window.xlvTrack = trackEvent;

  (analyticsConfig.queuedEvents || []).forEach((queued) => {
    if (!queued || !queued.event) return;
    trackEvent(queued.event, queued.params || {});
  });

  document.addEventListener('DOMContentLoaded', () => {
    trackEvent('page_ready', {
      page_path: window.location.pathname,
      page_title: document.title
    });
  });

  // Google Consent Mode v2: default is denied in the template, user choice updates it here.
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.getElementById('cookieConsent');
    const acceptBtn = document.getElementById('cookieAccept');
    const rejectBtn = document.getElementById('cookieReject');
    const storageKey = 'xlv_cookie_consent';

    function applyConsent(value) {
      const granted = value === 'granted';
      if (typeof window.gtag === 'function') {
        window.gtag('consent', 'update', {
          ad_storage: granted ? 'granted' : 'denied',
          analytics_storage: granted ? 'granted' : 'denied',
          ad_user_data: granted ? 'granted' : 'denied',
          ad_personalization: granted ? 'granted' : 'denied',
          functionality_storage: 'granted',
          security_storage: 'granted'
        });
      }
      trackEvent('cookie_consent_update', { consent_status: granted ? 'granted' : 'denied' });
    }

    let stored = '';
    try { stored = window.localStorage.getItem(storageKey) || ''; } catch (_) {}

    if (stored === 'granted' || stored === 'denied') {
      applyConsent(stored);
      return;
    }

    if (banner) banner.classList.remove('hidden');

    if (acceptBtn) {
      acceptBtn.addEventListener('click', () => {
        try { window.localStorage.setItem(storageKey, 'granted'); } catch (_) {}
        applyConsent('granted');
        if (banner) banner.classList.add('hidden');
      });
    }

    if (rejectBtn) {
      rejectBtn.addEventListener('click', () => {
        try { window.localStorage.setItem(storageKey, 'denied'); } catch (_) {}
        applyConsent('denied');
        if (banner) banner.classList.add('hidden');
      });
    }
  });

  // Public forms: track attempts in the browser; successful submissions are tracked server-side after redirect.
  document.querySelectorAll('form').forEach((form) => {
    const action = form.getAttribute('action') || window.location.pathname;
    if (action.indexOf('/admin') === 0 || action.indexOf('/admin') > -1) return;

    let formName = form.getAttribute('data-analytics-form') || '';
    if (!formName) {
      if (action.indexOf('umow-prezentacje') > -1) formName = 'presentation_request';
      else if (action.indexOf('lead') > -1) formName = 'contact';
      else formName = 'public_form';
    }

    let started = false;
    form.addEventListener('focusin', () => {
      if (started) return;
      started = true;
      trackEvent('form_start', { form_name: formName, page_path: window.location.pathname });
    });

    form.addEventListener('submit', () => {
      trackEvent('form_submit_attempt', { form_name: formName, page_path: window.location.pathname });
    });
  });

  // Generic click tracking for marked links/buttons plus common contact actions.
  document.addEventListener('click', function (e) {
    const target = e.target && e.target.closest ? e.target.closest('a,button,[data-analytics-event]') : null;
    if (!target) return;

    const explicit = target.getAttribute('data-analytics-event') || '';
    if (explicit) {
      trackEvent(explicit, {
        event_label: target.getAttribute('data-analytics-label') || (target.textContent || '').trim(),
        link_url: target.getAttribute('href') || '',
        page_path: window.location.pathname
      });
      return;
    }

    const href = target.getAttribute('href') || '';
    if (href.indexOf('tel:') === 0) {
      trackEvent('phone_click', { event_label: 'phone', page_path: window.location.pathname });
    } else if (href.indexOf('mailto:') === 0) {
      trackEvent('email_click', { event_label: 'email', page_path: window.location.pathname });
    } else if (href && /^https?:\/\//i.test(href)) {
      try {
        const url = new URL(href, window.location.href);
        if (url.hostname !== window.location.hostname) {
          trackEvent('outbound_click', { link_domain: url.hostname, link_url: url.href, page_path: window.location.pathname });
        }
      } catch (_) {}
    }
  });

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
    trackEvent('mobile_menu_open', { page_path: window.location.pathname });
  }

  function closeMenu() {
    if (!root || !btn) return;
    root.classList.remove('open');
    root.setAttribute('aria-hidden', 'true');
    btn.setAttribute('aria-expanded', 'false');
    lockScroll(false);
    trackEvent('mobile_menu_close', { page_path: window.location.pathname });
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
      trackEvent('cta_click', { event_label: 'scroll_next', page_path: window.location.pathname });
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
          trackEvent('video_sound_toggle', { muted: video.muted, page_path: window.location.pathname });
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
        trackEvent('gallery_load_more', { gallery: 'effects', shown_count: shownCount(), page_path: window.location.pathname });
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
