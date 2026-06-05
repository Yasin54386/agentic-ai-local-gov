/**
 * Shared site chrome for AskTerritory.com — included on every public page.
 *
 *  1. A language switcher placed in the top bar, next to the theme toggle.
 *     It is a custom dropdown that drives a HIDDEN Google Translate widget,
 *     so translation lives in one consistent place (not a per-page plugin)
 *     and Google's own (ugly) UI is suppressed.
 *  2. A consistent footer: author credit + LinkedIn, and a clear notice that
 *     this is an independent project, not an official government service.
 *
 * Relies only on the shared design-system CSS variables (--ink, --terra, …)
 * that every page already defines.
 */
(function () {
  var LANGS = [
    { c: 'en',    n: 'English' },
    { c: 'zh-CN', n: '中文（简体）' },
    { c: 'zh-TW', n: '中文（繁體）' },
    { c: 'el',    n: 'Ελληνικά' },
    { c: 'id',    n: 'Bahasa Indonesia' },
    { c: 'tl',    n: 'Filipino' },
    { c: 'vi',    n: 'Tiếng Việt' },
    { c: 'ar',    n: 'العربية' },
    { c: 'ne',    n: 'नेपाली' },
    { c: 'hi',    n: 'हिन्दी' },
    { c: 'pa',    n: 'ਪੰਜਾਬੀ' },
    { c: 'th',    n: 'ไทย' },
    { c: 'km',    n: 'ខ្មែរ' },
    { c: 'ko',    n: '한국어' },
    { c: 'ja',    n: '日本語' },
    { c: 'pt',    n: 'Português' },
    { c: 'es',    n: 'Español' },
    { c: 'fr',    n: 'Français' },
    { c: 'de',    n: 'Deutsch' },
    { c: 'sw',    n: 'Kiswahili' }
  ];

  var CSS = '' +
    /* language switcher — mirrors the existing .theme-btn look */
    '.sc-lang{position:relative}' +
    '.sc-lang-btn{display:inline-flex;align-items:center;gap:7px;font-family:"Barlow Condensed","Segoe UI",system-ui,sans-serif;' +
      'font-weight:700;font-size:12px;letter-spacing:.08em;text-transform:uppercase;line-height:1;' +
      'background:none;border:1.5px solid var(--ink,#1a1208);color:var(--ink,#1a1208);padding:6px 11px;cursor:pointer;white-space:nowrap}' +
    '.sc-lang-btn:hover{background:var(--ink,#1a1208);color:var(--cream,#f5f0e8)}' +
    '.sc-lang-globe{font-size:13px;line-height:1}.sc-lang-caret{font-size:9px;opacity:.7}' +
    '.sc-lang-menu{position:absolute;top:calc(100% + 7px);right:0;min-width:200px;max-height:62vh;overflow-y:auto;' +
      'background:var(--cream,#f5f0e8);border:1.5px solid var(--ink,#1a1208);box-shadow:5px 5px 0 var(--rule,rgba(26,18,8,.15));z-index:500;display:none}' +
    '.sc-lang-menu.open{display:block}' +
    '.sc-lang-item{display:block;width:100%;text-align:left;font-family:"Barlow","Segoe UI",system-ui,sans-serif;font-size:14px;' +
      'color:var(--ink2,#3a2e1e);background:none;border:none;border-bottom:1px solid var(--rule2,rgba(26,18,8,.08));padding:9px 15px;cursor:pointer}' +
    '.sc-lang-item:last-child{border-bottom:none}' +
    '.sc-lang-item:hover{background:var(--terra,#c8441a);color:#fff}' +
    '.sc-lang-item.active{color:var(--terra,#c8441a);font-weight:600}.sc-lang-item.active:hover{color:#fff}' +
    '@media(max-width:560px){.sc-lang-label{display:none}.sc-lang-btn{padding:6px 9px}}' +
    /* suppress Google Translate's injected chrome — we drive it ourselves */
    '.goog-te-banner-frame,.goog-te-gadget,.skiptranslate{display:none!important}' +
    '#google_translate_element{display:none!important}' +
    'body{top:0!important}' +
    '#goog-gt-tt,.goog-te-balloon-frame{display:none!important}' +
    '.goog-text-highlight{background:none!important;box-shadow:none!important;color:inherit!important}' +
    /* footer */
    '.site-footer{border-top:3px solid var(--ink,#1a1208);background:var(--cream2,#ede8dc);margin-top:48px}' +
    '.site-footer .footer-inner{max-width:1300px;margin:0 auto;padding:36px 40px;display:grid;grid-template-columns:60fr 40fr;gap:40px}' +
    '.site-footer .footer-logo{font-family:"Playfair Display",Georgia,serif;font-style:italic;font-weight:900;font-size:26px;color:var(--ink,#1a1208);margin-bottom:12px}' +
    '.site-footer .footer-logo span{color:var(--terra,#c8441a);font-style:normal}' +
    '.site-footer .footer-note{font-size:13px;line-height:1.6;color:var(--ink3,#6b5c44);font-weight:300;max-width:62ch}' +
    '.site-footer .footer-note strong{color:var(--ink2,#3a2e1e);font-weight:600}' +
    '.site-footer .footer-meta{text-align:right}' +
    '.site-footer .footer-credit{font-family:"Barlow Condensed","Segoe UI",system-ui,sans-serif;font-size:13px;letter-spacing:.05em;color:var(--ink3,#6b5c44);text-transform:uppercase;line-height:1.5}' +
    '.site-footer .footer-credit a{display:inline-block;margin-top:4px;font-weight:700;font-size:17px;color:var(--terra,#c8441a);text-decoration:none;letter-spacing:.01em}' +
    '.site-footer .footer-credit a:hover{text-decoration:underline}' +
    '.site-footer .footer-copy{font-family:"Barlow Condensed","Segoe UI",system-ui,sans-serif;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3,#6b5c44);margin-top:16px}' +
    '.site-footer .footer-fine{font-size:11px;color:var(--ink3,#6b5c44);opacity:.85;margin-top:10px;font-weight:300;line-height:1.5}' +
    '@media(max-width:900px){.site-footer .footer-inner{grid-template-columns:1fr;padding:26px 16px;gap:22px}.site-footer .footer-meta{text-align:left}}';

  function injectCSS() {
    if (document.getElementById('site-chrome-css')) return;
    var s = document.createElement('style');
    s.id = 'site-chrome-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ---- Google Translate (hidden) ------------------------------------- */
  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement(
      { pageLanguage: 'en', autoDisplay: false, includedLanguages: LANGS.map(function (l) { return l.c; }).join(',') },
      'google_translate_element'
    );
  };

  function loadTranslate() {
    if (!document.getElementById('google_translate_element')) {
      var d = document.createElement('div');
      d.id = 'google_translate_element';
      document.body.appendChild(d);
    }
    if (!document.getElementById('site-chrome-gtjs')) {
      var sc = document.createElement('script');
      sc.id = 'site-chrome-gtjs';
      sc.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
      document.body.appendChild(sc);
    }
  }

  /* ---- language switcher UI ------------------------------------------ */
  function currentLang() {
    var m = document.cookie.match(/googtrans=\/[^/]*\/([^;]+)/);
    return m ? decodeURIComponent(m[1]) : 'en';
  }

  function mountLang() {
    var right = document.querySelector('.masthead-right');
    if (!right || document.getElementById('sc-langWrap')) return;

    var wrap = document.createElement('div');
    wrap.className = 'sc-lang';
    wrap.id = 'sc-langWrap';
    wrap.innerHTML =
      '<button class="sc-lang-btn" id="sc-langBtn" aria-haspopup="true" aria-expanded="false" title="Translate this page">' +
        '<span class="sc-lang-globe">🌐</span><span class="sc-lang-label" id="sc-langLabel">English</span><span class="sc-lang-caret">▾</span>' +
      '</button>' +
      '<div class="sc-lang-menu" id="sc-langMenu" role="menu"></div>';

    var themeBtn = document.getElementById('themeBtn');
    if (themeBtn && themeBtn.parentNode === right) right.insertBefore(wrap, themeBtn);
    else right.appendChild(wrap);

    var btn = wrap.querySelector('#sc-langBtn');
    var menu = wrap.querySelector('#sc-langMenu');
    var label = wrap.querySelector('#sc-langLabel');

    menu.innerHTML = LANGS.map(function (l) {
      return '<button class="sc-lang-item" role="menuitem" data-c="' + l.c + '">' + l.n + '</button>';
    }).join('');

    function paint() {
      var cur = currentLang();
      var f = LANGS.filter(function (l) { return l.c === cur; })[0];
      label.textContent = f ? f.n : 'English';
      [].forEach.call(menu.children, function (it) {
        it.classList.toggle('active', it.getAttribute('data-c') === cur);
      });
    }

    function waitCombo(cb, t) {
      t = t || 0;
      var combo = document.querySelector('.goog-te-combo');
      if (combo) return cb(combo);
      if (t > 40) return;
      setTimeout(function () { waitCombo(cb, t + 1); }, 150);
    }

    function setLang(code) {
      if (code === 'en') { // back to source language: clear cookie and reload
        var exp = '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
        document.cookie = 'googtrans' + exp;
        document.cookie = 'googtrans' + exp + ';domain=.' + location.hostname;
        location.reload();
        return;
      }
      waitCombo(function (combo) {
        combo.value = code;
        combo.dispatchEvent(new Event('change'));
        setTimeout(paint, 500);
      });
    }

    [].forEach.call(menu.querySelectorAll('.sc-lang-item'), function (it) {
      it.addEventListener('click', function () {
        menu.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
        setLang(it.getAttribute('data-c'));
      });
    });

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = menu.classList.toggle('open');
      btn.setAttribute('aria-expanded', open);
    });
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) {
        menu.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });

    paint();
    setTimeout(paint, 1200); // reflect any language restored from a prior visit
  }

  /* ---- footer -------------------------------------------------------- */
  function mountFooter() {
    if (document.querySelector('.site-footer')) return;
    var f = document.createElement('footer');
    f.className = 'site-footer';
    f.innerHTML =
      '<div class="footer-inner">' +
        '<div class="footer-brand">' +
          '<div class="footer-logo">AskTerritory<span>.com</span></div>' +
          '<p class="footer-note">An independent, non-commercial project that makes Northern Territory &amp; City of Darwin ' +
            '<strong>public open data and services</strong> easy to ask about, in plain language. It is ' +
            '<strong>not affiliated with, endorsed by, or an official service of any government agency.</strong> ' +
            'Information may be incomplete or out of date — always confirm anything important with the relevant authority.</p>' +
        '</div>' +
        '<div class="footer-meta">' +
          '<p class="footer-credit">Designed, developed &amp; maintained by ' +
            '<a href="https://www.linkedin.com/in/mohammad-yasin-arafat-083425174/" target="_blank" rel="noopener noreferrer">Mohammad Yasin Arafat &#8599;</a></p>' +
          '<p class="footer-copy">&copy; ' + new Date().getFullYear() + ' Mohammad Yasin Arafat &middot; All rights reserved.</p>' +
          '<p class="footer-fine">Page translations are provided by Google Translate — machine translation may be imperfect, and translated text is processed by Google.</p>' +
        '</div>' +
      '</div>';
    document.body.appendChild(f);
  }

  function init() {
    injectCSS();
    mountLang();
    mountFooter();
    loadTranslate();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
