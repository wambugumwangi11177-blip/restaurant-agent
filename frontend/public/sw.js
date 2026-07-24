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

// Fetch — network first, fall back to cache
self.addEventListener('fetch', (event) => {
    // Skip non-GET and API requests
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.pathname.startsWith('/api')) return;

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Clone and cache successful responses
                if (response.status === 200) {
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
// is open, otherwise open a new one.
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/dashboard';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const c of clientList) {
                if (c.url.includes(url) && 'focus' in c) return c.focus();
            }
            return self.clients.openWindow(url);
        })
    );
});
