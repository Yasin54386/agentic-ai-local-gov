/**
 * Universal navigation strip for AskTerritory.com.
 * Place a <div id="nav-root"></div> inside the .masthead header.
 * On home (/) tabs switch panels via JS; on sub-pages they link to /?p=<section>.
 * On mobile (<768px) collapses to a hamburger menu.
 */
(function () {
  const TABS = [
    { p: 'home',      label: 'Overview'    },
    { p: 'ask',       label: 'Ask AI'      },
    { p: 'suburb',    label: 'My Suburb'   },
    { p: 'canopy',    label: 'Canopy'      },
    { p: 'motion',    label: 'City Motion' },
    { p: 'decisions', label: 'Decisions'   },
    { p: 'weather',   label: 'Weather'     },
    { p: 'data',      label: 'Data'        },
  ];

  const PAGES = [
    { href: '/forms', label: 'Form Finder' },
    { href: '/howto', label: 'How-To Hub'  },
    { href: '/tour',  label: 'Tour Guide'  },
    { href: '/guide', label: 'Guide'       },
  ];

  const path = location.pathname.replace(/\.html$/, '') || '/';
  const isHome = (path === '/' || path === '/index');

  const css = `
    #ask-nav-wrap { position: relative; }

    /* ── hamburger button (mobile only) ── */
    #ask-nav-toggle {
      display: none;
      align-items: center; justify-content: center;
      width: 44px; height: 44px;
      background: none; border: none; cursor: pointer;
      color: var(--ink3, #6b5c44);
      font-size: 22px; line-height: 1;
    }
    #ask-nav-toggle:hover { color: var(--terra, #c8441a); }

    /* ── desktop strip ── */
    #ask-nav {
      background: var(--cream, #f5f0e8);
      border-top: 1px solid var(--rule, rgba(26,18,8,.15));
      display: flex; align-items: stretch;
      overflow-x: auto; scrollbar-width: none; -webkit-overflow-scrolling: touch;
    }
    #ask-nav::-webkit-scrollbar { display: none; }
    #ask-nav .an-divider {
      width: 1px; background: var(--rule, rgba(26,18,8,.15));
      margin: 6px 2px; flex-shrink: 0;
    }
    #ask-nav .an-btn {
      font-family: 'Barlow Condensed', 'Segoe UI', system-ui, sans-serif;
      font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: .1em;
      padding: 10px 18px; display: flex; align-items: center;
      border: none; border-top: 3px solid transparent;
      background: none; color: var(--ink3, #6b5c44);
      cursor: pointer; white-space: nowrap; text-decoration: none;
      transition: color .12s, border-color .12s, background .12s; flex-shrink: 0;
    }
    #ask-nav .an-btn:hover { color: var(--ink, #1a1208); background: var(--cream2, #ede8dc); }
    #ask-nav .an-btn.active { color: var(--terra, #c8441a); border-top-color: var(--terra, #c8441a); }

    /* ── mobile dropdown ── */
    @media (max-width: 767px) {
      #ask-nav-toggle { display: flex; }
      #ask-nav {
        display: none;
        flex-direction: column;
        position: absolute; top: 100%; left: 0; right: 0;
        z-index: 200;
        border-top: none;
        border-bottom: 2px solid var(--rule, rgba(26,18,8,.15));
        box-shadow: 0 8px 24px rgba(26,18,8,.12);
      }
      #ask-nav.open { display: flex; }
      #ask-nav .an-divider {
        width: auto; height: 1px;
        margin: 2px 16px; flex-shrink: 0;
      }
      #ask-nav .an-btn {
        border-top: none;
        border-left: 3px solid transparent;
        padding: 13px 20px;
        font-size: 13px;
      }
      #ask-nav .an-btn.active {
        border-top: none;
        border-left-color: var(--terra, #c8441a);
        background: var(--cream2, #ede8dc);
      }
    }
  `;

  if (!document.getElementById('ask-nav-css')) {
    const style = document.createElement('style');
    style.id = 'ask-nav-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function render() {
    const tabsHtml = TABS.map(t => {
      if (isHome) return `<button class="an-btn" data-p="${t.p}">${t.label}</button>`;
      return `<a class="an-btn" href="/?p=${t.p}">${t.label}</a>`;
    }).join('');

    const pagesHtml = PAGES.map(pg => {
      const active = path.startsWith(pg.href) ? ' active' : '';
      return `<a class="an-btn${active}" href="${pg.href}">${pg.label}</a>`;
    }).join('');

    return `
      <div id="ask-nav-wrap">
        <button id="ask-nav-toggle" aria-label="Open menu" aria-expanded="false">&#9776;</button>
        <nav id="ask-nav">${tabsHtml}<div class="an-divider"></div>${pagesHtml}</nav>
      </div>`;
  }

  function mount() {
    const root = document.getElementById('nav-root');
    if (root) root.outerHTML = render();
    else document.body.insertAdjacentHTML('afterbegin', render());

    // hamburger toggle
    const toggle = document.getElementById('ask-nav-toggle');
    const nav = document.getElementById('ask-nav');
    if (toggle && nav) {
      toggle.addEventListener('click', () => {
        const open = nav.classList.toggle('open');
        toggle.setAttribute('aria-expanded', open);
        toggle.innerHTML = open ? '&#10005;' : '&#9776;';
      });
      // close on any nav item click
      nav.addEventListener('click', e => {
        if (e.target.closest('.an-btn')) {
          nav.classList.remove('open');
          toggle.setAttribute('aria-expanded', false);
          toggle.innerHTML = '&#9776;';
        }
      });
      // close on outside click
      document.addEventListener('click', e => {
        if (!e.target.closest('#ask-nav-wrap')) {
          nav.classList.remove('open');
          toggle.setAttribute('aria-expanded', false);
          toggle.innerHTML = '&#9776;';
        }
      });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
