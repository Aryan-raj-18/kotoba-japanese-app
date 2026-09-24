/* =====================================================================
   Kotoba — theme switching
   ---------------------------------------------------------------------
   The actual palettes live in style.css, keyed off <html data-theme>.
   This file only decides *which* key is set, remembers the choice, and
   wires up the settings menu in the header.

   A tiny inline copy of the "apply saved theme" step runs in base.html's
   <head>, before the stylesheet paints, so switching to a dark theme
   doesn't flash a screen of white paper on every navigation.
   ================================================================== */

(function () {
  'use strict';

  var KEY = 'kotoba:theme';
  var DARK = { sumi: true, yozakura: true };

  var THEMES = [
    { id: 'auto',     name: 'Match system', jp: '自動' },
    { id: 'washi',    name: 'Washi',        jp: '和紙 · paper' },
    { id: 'sakura',   name: 'Sakura',       jp: '桜 · blossom' },
    { id: 'matcha',   name: 'Matcha',       jp: '抹茶 · tea' },
    { id: 'sumi',     name: 'Sumi',         jp: '墨 · ink (dark)' },
    { id: 'yozakura', name: 'Yozakura',     jp: '夜桜 · night (dark)' },
  ];

  // Matches the --paper value of each theme, for the Android status bar.
  var BAR_COLOR = {
    washi: '#EFE7D6',
    sakura: '#FAF0F2',
    matcha: '#EFF1E3',
    sumi: '#13161A',
    yozakura: '#161119',
  };

  function read() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function save(v) {
    try { localStorage.setItem(KEY, v); } catch (e) { /* private mode */ }
  }

  function systemIsDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  /** "auto" is resolved to a real theme so every rule has one source. */
  function resolve(id) {
    if (id === 'auto' || !id) return systemIsDark() ? 'sumi' : 'washi';
    return id;
  }

  function apply(id) {
    var resolved = resolve(id);
    var root = document.documentElement;
    root.setAttribute('data-theme', resolved);
    root.setAttribute('data-theme-choice', id || 'auto');

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', BAR_COLOR[resolved] || '#EFE7D6');

    document.querySelectorAll('.theme-opt').forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(btn.dataset.theme === (id || 'auto')));
    });
  }

  // Track the OS setting while "Match system" is selected.
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function () {
      if ((read() || 'auto') === 'auto') apply('auto');
    };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  function buildThemeOptions(container) {
    THEMES.forEach(function (t) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'theme-opt';
      btn.dataset.theme = t.id;
      btn.setAttribute('aria-pressed', 'false');
      btn.innerHTML =
        '<span class="theme-swatch" aria-hidden="true"></span>' +
        '<span><span class="theme-opt-name"></span><span class="theme-opt-jp"></span></span>';
      btn.querySelector('.theme-opt-name').textContent = t.name;
      btn.querySelector('.theme-opt-jp').textContent = t.jp;
      btn.addEventListener('click', function () {
        save(t.id);
        apply(t.id);
        if (window.Sfx) Sfx.tap();
      });
      container.appendChild(btn);
    });
  }

  function wireSwitch(el, isOn, setter) {
    if (!el) return;
    el.setAttribute('aria-checked', String(isOn()));
    el.addEventListener('click', function () {
      var next = el.getAttribute('aria-checked') !== 'true';
      setter(next);
      el.setAttribute('aria-checked', String(next));
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    apply(read() || 'auto');

    var optionsEl = document.getElementById('theme-options');
    if (optionsEl) {
      buildThemeOptions(optionsEl);
      apply(read() || 'auto'); // re-run so the new buttons get their pressed state
    }

    if (window.Sfx) {
      wireSwitch(document.getElementById('sound-switch'), Sfx.isSoundOn, Sfx.setSound);
      wireSwitch(document.getElementById('haptics-switch'), Sfx.isHapticsOn, Sfx.setHaptics);
    }

    // ---- open / close the panel ----
    var btn = document.getElementById('settings-btn');
    var panel = document.getElementById('settings-panel');
    if (!btn || !panel) return;

    function close() {
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    }
    function open() {
      panel.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (panel.hidden) { open(); if (window.Sfx) Sfx.tap(); } else { close(); }
    });
    panel.addEventListener('click', function (e) { e.stopPropagation(); });
    document.addEventListener('click', function () { if (!panel.hidden) close(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) { close(); btn.focus(); }
    });
  });

  window.KotobaTheme = { apply: apply, resolve: resolve, themes: THEMES };
})();
