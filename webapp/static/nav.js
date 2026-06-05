/**
 * Universal navigation strip for AskTerritory.com.
 * Place a <div id="nav-root"></div> inside the .masthead header.
 * On home (/) tabs switch panels via JS; on sub-pages they link to /?p=<section>.
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

    return `<nav id="ask-nav">${tabsHtml}<div class="an-divider"></div>${pagesHtml}</nav>`;
  }

  function mount() {
    const root = document.getElementById('nav-root');
    if (root) root.outerHTML = render();
    else document.body.insertAdjacentHTML('afterbegin', render());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
