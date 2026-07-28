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
    // Skip non-GET requests and anything not same-origin. This SW exists to
    // offline-cache the frontend's OWN shell routes (PRECACHE_URLS above) —
    // it must never touch backend API calls. The previous guard only checked
    // for a `/api` path prefix, but this frontend's actual backend calls are
    // unprefixed (/orders/, /ai/..., /menu/ — only AuthContext's login/register
    // use /api/v1/...), so that check silently missed almost every real API
    // request. The practical effect: when the backend went down, this
    // fetch-then-catch-then-serve-from-cache handler served a stale, previously
    // cached 200 response for e.g. /orders/ as if it were live data — masking
    // a real backend outage as a normal (if empty) page load, with no error
    // anywhere for the user to see. Checking origin instead of a path prefix
    // is what actually scopes this to the frontend's own routes.
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin) return;

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
