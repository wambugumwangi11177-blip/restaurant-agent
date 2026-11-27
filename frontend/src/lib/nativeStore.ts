/** True in the LEVIII Store Capacitor shell (WebView stamps LEVIIIStore/x.y.z). */
export function isLeviiiStoreClient(): boolean {
  if (typeof window === "undefined") return false;
  const cap = (window as Window & { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  if (cap?.isNativePlatform?.()) return true;
  return /LEVIIIStore\/\d+\.\d+\.\d+/.test(navigator.userAgent);
}