/**
 * Universal navigation component for Ask Territory.
 * Include with: <script src="/nav.js"></script>
 * Place a <div id="nav-root"></div> where the header should appear.
 * The current page link is highlighted automatically based on location.pathname.
 */
(function () {
  const LINKS = [
    { href: '/',       label: 'Ask Territory',  icon: '🏛' },
    { href: '/forms',  label: 'Form Finder',    icon: '📋' },
    { href: '/howto',  label: 'How-To Hub',     icon: '📖' },
    { href: '/tour',   label: 'Tour Guide',     icon: '🏖' },
    { href: '/guide',  label: 'Guide',          icon: '🤖' },
  ];

  const PAGE_TITLES = {
    '/':      { title: 'Ask Territory',   sub: '' },
    '/forms': { title: 'Form',            sub: 'Finder' },
    '/howto': { title: 'How-To',          sub: ' Hub' },
    '/tour':  { title: 'NT Tour',         sub: ' Guide' },
    '/guide': { title: 'Guide',           sub: ' Assistant' },
    '/admin': { title: 'Admin',           sub: ' Dashboard' },
  };

  const path = location.pathname.replace(/\.html$/, '').replace(/\/$/, '') || '/';
  const pageInfo = PAGE_TITLES[path] || { title: 'Ask Territory', sub: '' };

  const css = `
    #ask-nav {
      background: #1a1d27;
      border-bottom: 1px solid #2a2d3a;
      padding: 0 24px;
      display: flex;
      align-items: center;
      gap: 0;
      position: sticky;
      top: 0;
      z-index: 50;
      min-height: 52px;
    }
    #ask-nav .an-logo {
      font-size: 15px;
      font-weight: 800;
      color: #e8a020;
      white-space: nowrap;
      padding: 14px 20px 14px 0;
      border-right: 1px solid #2a2d3a;
      margin-right: 4px;
      text-decoration: none;
      letter-spacing: -0.3px;
    }
    #ask-nav .an-logo span { color: #8892a0; font-weight: 500; font-size: 13px; }
    #ask-nav .an-links {
      display: flex;
      gap: 0;
      overflow-x: auto;
      scrollbar-width: none;
      flex: 1;
    }
    #ask-nav .an-links::-webkit-scrollbar { display: none; }
    #ask-nav .an-link {
      display: flex;
      align-items: center;
      gap: 5px;
      color: #8892a0;
      text-decoration: none;
      font-size: 13px;
      font-weight: 500;
      padding: 0 14px;
      height: 52px;
      border-bottom: 2px solid transparent;
      white-space: nowrap;
      transition: color .12s, border-color .12s;
    }
    #ask-nav .an-link:hover { color: #e2e8f0; }
    #ask-nav .an-link.active {
      color: #e8a020;
      border-bottom-color: #e8a020;
    }
    @media (max-width: 480px) {
      #ask-nav .an-logo { padding: 14px 12px 14px 0; font-size: 15px; }
      #ask-nav .an-link { padding: 0 10px; font-size: 12px; }
      #ask-nav .an-icon { display: none; }
    }
  `;

  // Inject CSS once
  if (!document.getElementById('ask-nav-css')) {
    const style = document.createElement('style');
    style.id = 'ask-nav-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function render() {
    const linksHtml = LINKS.map(l => {
      const isActive = (l.href === '/' ? path === '/' : path.startsWith(l.href));
      return `<a class="an-link${isActive ? ' active' : ''}" href="${l.href}">
        <span class="an-icon">${l.icon}</span>${l.label}
      </a>`;
    }).join('');

    return `
      <nav id="ask-nav">
        <a class="an-logo" href="/">AskTerritory<span>.com</span></a>
        <div class="an-links">${linksHtml}</div>
      </nav>`;
  }

  // Insert nav — into #nav-root if present, else prepend to body
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
