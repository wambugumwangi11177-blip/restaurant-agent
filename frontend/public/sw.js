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
