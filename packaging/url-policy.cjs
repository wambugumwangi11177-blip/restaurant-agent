function appUrl(value) {
  const url = new URL(value || '');
  if (url.protocol !== 'https:' || url.username || url.password || url.port || url.search || url.hash || url.pathname !== '/') {
    throw new Error('LEVIII_APP_URL must be an HTTPS origin without credentials, path, port, query or fragment.');
  }
  if (url.hostname === 'localhost' || url.hostname.endsWith('.localhost') || /^[\d.]+$/.test(url.hostname) || url.hostname.startsWith('[')) {
    throw new Error('Use the public production hostname, not a local address.');
  }
  return url.origin;
}
function sameOrigin(candidate, origin) {
  try { const url = new URL(candidate); return url.protocol === 'https:' && url.origin === origin && !url.username && !url.password; }
  catch { return false; }
}
module.exports = { appUrl, sameOrigin };
