/* Bump this version whenever any cached public asset changes. */
const CACHE = 'tutorplatform-public-v4';
const OFFLINE = '/pwa/offline.html';
const PRECACHE = [OFFLINE, '/pwa/mobile.css', '/pwa/pwa.js', '/pwa/icon-180.png', '/pwa/icon-192.png', '/pwa/icon-512.png'];
const STATIC_FILES = ['vendor/bootstrap.min.css', 'auth.css', 'auth.js', 'dashboard_theme.css', 'student_dashboard.css', 'admin_dashboard.css', 'profile.css', 'messages.css', 'messaging.js', 'dashboard.js', 'modules.js', 'academic_admin.js', 'csv_upload.js', 'lms_catalog.js', 'socket.io.min.js', 'role-switcher.js'];
const PUBLIC_PATHS = new Set([...PRECACHE, ...['/dashboard/static/', '/users/static/', '/registration/static/'].flatMap(prefix => STATIC_FILES.map(file => prefix + file))]);

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PRECACHE)));
  // Updates wait for explicit acceptance; never interrupt an active form.
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('tutorplatform-public-') && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data?.type === 'ACTIVATE_UPDATE') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE)));
    return;
  }
  // Exact allowlist: no HTML, API data, arbitrary files, or query variants.
  if (url.search || !PUBLIC_PATHS.has(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok && !response.redirected && response.type === 'basic') {
      await cache.put(request, response.clone());
    }
    return response;
  })());
});
