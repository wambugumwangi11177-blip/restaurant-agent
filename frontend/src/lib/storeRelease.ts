export type StoreRelease = {
  name: string;
  version: string;
  versionCode: number;
  android: { available: boolean; filename: string; url: string };
  windows: { available: boolean; url?: string };
};

export function parseVersion(value: string | null | undefined): [number, number, number] | null {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec((value ?? "").trim());
  if (!match) return null;
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

export function isNewerVersion(latest: string, current: string): boolean {
  const next = parseVersion(latest);
  const have = parseVersion(current);
  if (!next || !have) return false;
  for (let index = 0; index < 3; index += 1) {
    if (next[index] !== have[index]) return next[index] > have[index];
  }
  return false;
}

export function versionFromUserAgent(userAgent: string): string | null {
  const match = /LEVIIIStore\/(\d+\.\d+\.\d+)/.exec(userAgent);
  return match ? match[1] : null;
}

export function shouldOfferStoreUpdate(input: {
  userAgent: string;
  native?: boolean;
  current: string | null;
  latest: string;
  androidUrl: string;
  androidAvailable: boolean;
}): boolean {
  const inApk = Boolean(input.native) || /LEVIIIStore\/\d+\.\d+\.\d+/.test(input.userAgent);
  if (!inApk || !input.androidAvailable || !input.androidUrl.startsWith("https://")) return false;
  if (!input.current) return false;
  return isNewerVersion(input.latest, input.current);
}
