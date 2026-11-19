// LEVIII Service Worker — offline caching + PWA install support
//
// CACHE_NAME is versioned and MUST be bumped whenever the caching rules below
// change: `activate` deletes every cache whose key differs, so the bump is what
// evicts the previous version's entries.
const CACHE_NAME = 'leviii-v4';

const PRECACHE_URLS = [];

self.addEventListener('install', (event) => {
    event.waitUntil(
        PRECACHE_URLS.length
            ? caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
            : Promise.resolve()
    );
    self.skipWaiting();
});

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

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith('/api')) return;

    const isStaticAsset =
        url.pathname.startsWith('/_next/static/') ||
        url.pathname.startsWith('/icon-') ||
        url.pathname === '/manifest.json' ||
        url.pathname === '/store-manifest.json';

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response.status === 200 && isStaticAsset) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'PURGE_CACHES') {
        event.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))));
    }
});

self.addEventListener('push', (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch {
        data = { title: 'LEVIII', body: event.data ? event.data.text() : '' };
    }
    event.waitUntil(
        self.registration.showNotification(data.title || 'LEVIII', {
            body: data.body || '',
            icon: '/icon-192.png',
            badge: '/icon-192.png',
            data: { url: data.url || '/eleven' },
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const raw = event.notification.data && event.notification.data.url ? event.notification.data.url : '/eleven';
    const url = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/eleven';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const c of clientList) {
                if (c.url.includes(url) && 'focus' in c) return c.focus();
            }
            return self.clients.openWindow(url);
        })
    );
});