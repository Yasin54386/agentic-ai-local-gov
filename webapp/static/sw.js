// Service Worker — Ask Territory PWA
// Strategy:
//   - Navigations (HTML pages): network-first → always get fresh code when online,
//     fall back to cache only when offline. Prevents stale-page-stuck-in-cache.
//   - API calls: network-first, cache successful responses for offline fallback.
//   - Other static assets (manifest, nav.js, fonts): stale-while-revalidate →
//     fast from cache, but refreshed in the background within one reload.
// Bump CACHE when the strategy changes so old caches are purged on activate.

const CACHE  = 'ask-territory-v2';
const STATIC = ['/', '/forms', '/howto', '/tour', '/manifest.json', '/nav.js'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(STATIC))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // HTML navigations: network-first so new code always wins when online.
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request).then(c => c || caches.match('/')))
    );
    return;
  }

  // API calls: network-first, cache on success for offline fallback.
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
          }
          return res;
        })
        .catch(() => caches.match(e.request)
          .then(cached => cached || new Response(
            JSON.stringify({error: 'offline', offline: true}),
            {headers: {'Content-Type': 'application/json'}}
          ))
        )
    );
    return;
  }

  // Other static assets: stale-while-revalidate.
  e.respondWith(
    caches.match(e.request).then(cached => {
      const network = fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
