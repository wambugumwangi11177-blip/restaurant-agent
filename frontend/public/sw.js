// Chakula Service Worker — offline caching + PWA install support
const CACHE_NAME = 'chakula-v1';
const PRECACHE_URLS = [
    '/dashboard',
    '/dashboard/pos',
    '/dashboard/kitchen',
    '/dashboard/orders',
];

// Install — cache shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(PRECACHE_URLS);
        })
    );
    self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

// Fetch — network first, fall back to cache.
// Runtime caching is restricted to static assets (icons, build output,
// manifest). Arbitrary same-origin documents are no longer runtime-cached:
// that stored authenticated pages in CacheStorage forever, and on a shared
// device the next user could read the previous user's pages offline.
self.addEventListener('fetch', (event) => {
    // Skip non-GET and API requests
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith('/api')) return;

    const isStaticAsset =
        url.pathname.startsWith('/_next/static/') ||
        url.pathname.startsWith('/icon-') ||
        url.pathname === '/manifest.json';

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response.status === 200 && isStaticAsset) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => {
                // Offline — serve from cache
                return caches.match(event.request);
            })
    );
});

// Allow the page to purge all caches (used on logout — a shared POS/tablet
// must not keep the previous user's cached pages or offline queue).
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'PURGE_CACHES') {
        event.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))));
    }
});

// Push — staff notifications (stock alerts, support tickets, etc). Twilio is
// unfunded, so this is the channel that actually reaches staff in the
// background; see backend/ai/notify.py for the send side. Payload is plain
// JSON ({title, body, url}), not the Push API's binary default.
self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch {
        data = { title: 'Chakula', body: event.data ? event.data.text() : '' };
    }
    event.waitUntil(
        self.registration.showNotification(data.title || 'Chakula', {
            body: data.body || '',
            icon: '/icon-192.png',
            badge: '/icon-192.png',
            data: { url: data.url || '/dashboard' },
        })
    );
});

// Notification click — focus an existing dashboard tab on that route if one
// is open, otherwise open a new one. The payload URL must be a same-origin
// relative path: a misbehaving/compromised push source must not be able to
// send users to an arbitrary site.
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const raw = event.notification.data && event.notification.data.url ? event.notification.data.url : '/dashboard';
    const url = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/dashboard';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const c of clientList) {
                if (c.url.includes(url) && 'focus' in c) return c.focus();
            }
            return self.clients.openWindow(url);
        })
    );
});
