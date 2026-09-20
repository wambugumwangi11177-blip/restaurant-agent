// Service-worker registration.
//
// This lived as an inline <script dangerouslySetInnerHTML> in app/layout.tsx,
// which is why script-src needed 'unsafe-inline'. Moved to a real file so it
// is covered by plain script-src 'self' and the CSP can drop 'unsafe-inline'
// entirely — see src/proxy.ts for the policy this feeds into.
//
// Failures are swallowed on purpose: no service worker means no offline mode,
// which is a degraded PWA, not a broken app. A registration error must never
// stop the page rendering.
(function () {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js').catch(function () {});
  });
})();
