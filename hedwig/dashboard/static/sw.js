// Hedwig service worker (Phase 7 S7).
// - Caches the app shell for offline / fast nav.
// - Handles push events from /run/critical when delivered_signals fires
//   server-side via Web Push (S8 hookup is server-side).

const SHELL_CACHE = 'hedwig-shell-v3-2';
const SHELL_FILES = [
  '/',
  '/chat',
  '/feed',
  '/brief',
  '/static/style.css',
  '/static/v3.css',
  '/static/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL_FILES).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== SHELL_CACHE).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Network-first for dynamic data; cache-first for static shell.
  if (url.pathname.startsWith('/static/') || SHELL_FILES.includes(url.pathname)) {
    event.respondWith(
      caches.match(event.request).then(hit => hit || fetch(event.request))
    );
  } else if (event.request.method === 'GET' &&
             (url.pathname === '/' || url.pathname.startsWith('/chat') ||
              url.pathname.startsWith('/feed') || url.pathname.startsWith('/brief'))) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  }
});

// In-app push (S8 — for now triggered manually from the page;
// server can later send a Push subscription payload.)
self.addEventListener('push', (event) => {
  let data = {title: 'Hedwig', body: 'New critical signal'};
  if (event.data) {
    try { data = event.data.json(); } catch (_) {}
  }
  event.waitUntil(self.registration.showNotification(
    data.title || 'Hedwig',
    {body: data.body || '', icon: '/assets/hedwig-icon.svg', tag: 'critical'},
  ));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/feed?stream=critical_only'));
});
