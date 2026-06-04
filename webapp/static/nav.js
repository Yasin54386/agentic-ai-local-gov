/**
 * Universal navigation strip for AskTerritory.com.
 * Renders identically on every page — all dashboard tabs + all section pages.
 * Include with: <script src="/nav.js"></script>
 * Place a <div id="nav-root"></div> where the nav should appear.
 * On the home page (/) the tabs switch panels via JS; on sub-pages they
 * link back to /?p=<section> which index.html reads on load.
 */
(function () {
  // Dashboard panel tabs (link back to index with ?p= on sub-pages)
  const TABS = [
    { p: 'home',      label: 'Overview'    },
    { p: 'ask',       label: 'Ask AI'      },
    { p: 'suburb',    label: 'My Suburb'   },
    { p: 'canopy',    label: 'Canopy'      },
    { p: 'equity',    label: 'Ward Spend'  },
    { p: 'motion',    label: 'City Motion' },
    { p: 'money',     label: 'The Money'   },
    { p: 'decisions', label: 'Decisions'   },
    { p: 'grants',    label: 'Grants'      },
    { p: 'weather',   label: 'Weather'     },
    { p: 'data',      label: 'Data'        },
  ];

  // Section pages
  const PAGES = [
    { href: '/forms', label: 'Form Finder' },
    { href: '/howto', label: 'How-To Hub'  },
    { href: '/tour',  label: 'Tour Guide'  },
    { href: '/guide', label: 'Guide'       },
  ];

  const path = location.pathname.replace(/\.html$/, '') || '/';
  const isHome = (path === '/' || path === '/index');

  const css = `
    #ask-nav {
      background: var(--surface, #1a1d27);
      border-bottom: 1px solid var(--border, #2a2d3a);
      display: flex;
      align-items: stretch;
      overflow-x: auto;
      scrollbar-width: none;
      -webkit-overflow-scrolling: touch;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    #ask-nav::-webkit-scrollbar { display: none; }
    #ask-nav .an-logo {
      font-family: 'Segoe UI', system-ui, sans-serif;
      font-size: 15px;
      font-weight: 800;
      color: #e8a020;
      white-space: nowrap;
      padding: 0 18px;
      display: flex;
      align-items: center;
      border-right: 1px solid var(--border, #2a2d3a);
      text-decoration: none;
      flex-shrink: 0;
    }
    #ask-nav .an-logo span { color: #8892a0; font-weight: 400; font-size: 13px; }
    #ask-nav .an-divider {
      width: 1px;
      background: var(--border, #2a2d3a);
      margin: 8px 2px;
      flex-shrink: 0;
    }
    #ask-nav .an-btn {
      font-family: 'Barlow Condensed', 'Segoe UI', system-ui, sans-serif;
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .1em;
      padding: 0 16px;
      height: 48px;
      display: flex;
      align-items: center;
      border: none;
      border-top: 3px solid transparent;
      border-bottom: 3px solid transparent;
      background: none;
      color: var(--ink3, #8892a0);
      cursor: pointer;
      white-space: nowrap;
      text-decoration: none;
      transition: color .12s, border-color .12s, background .12s;
      flex-shrink: 0;
    }
    #ask-nav .an-btn:hover {
      color: var(--ink, #e2e8f0);
      background: rgba(255,255,255,.04);
    }
    #ask-nav .an-btn.active {
      color: var(--terra, #e8a020);
      border-bottom-color: var(--terra, #e8a020);
    }
  `;

  if (!document.getElementById('ask-nav-css')) {
    const style = document.createElement('style');
    style.id = 'ask-nav-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function render() {
    // Tab buttons — on sub-pages these are <a> links; on home they are <button>
    const tabsHtml = TABS.map(t => {
      if (isHome) {
        return `<button class="an-btn" data-p="${t.p}">${t.label}</button>`;
      }
      return `<a class="an-btn" href="/?p=${t.p}">${t.label}</a>`;
    }).join('');

    // Section page links — active if current path matches
    const pagesHtml = PAGES.map(pg => {
      const active = path.startsWith(pg.href) ? ' active' : '';
      return `<a class="an-btn${active}" href="${pg.href}">${pg.label}</a>`;
    }).join('');

    return `
      <nav id="ask-nav">
        <a class="an-logo" href="/">AskTerritory<span>.com</span></a>
        ${tabsHtml}
        <div class="an-divider"></div>
        ${pagesHtml}
      </nav>`;
  }

  function mount() {
    const root = document.getElementById('nav-root');
    if (root) {
      root.outerHTML = render();
    } else {
      document.body.insertAdjacentHTML('afterbegin', render());
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
