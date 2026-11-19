export type InstallDevice = "android" | "windows" | "iphone" | "ipad" | "mac";

export const INSTALL_DEVICES: { id: InstallDevice; label: string }[] = [
  { id: "android", label: "Android" },
  { id: "windows", label: "Windows" },
  { id: "iphone", label: "iPhone" },
  { id: "ipad", label: "iPad" },
  { id: "mac", label: "Mac" },
];

export type DeviceHints = {
  userAgent: string;
  platform?: string;
  maxTouchPoints?: number;
  clientHintPlatform?: string;
  clientHintMobile?: boolean;
};

function looksLikeIpad(userAgent: string, hint: string, touch: number): boolean {
  if (/iPad/.test(userAgent)) return true;
  const mac = /Macintosh|Mac OS X/.test(userAgent) || hint === "macos" || hint === "mac";
  return mac && touch > 1;
}

export function detectInstallDevice(input: DeviceHints): InstallDevice | "unknown" {
  const ua = input.userAgent || "";
  const hint = (input.clientHintPlatform || "").toLowerCase();
  const touch = input.maxTouchPoints ?? 0;
  const ipad = looksLikeIpad(ua, hint, touch);

  if (hint === "android" || /Android/i.test(ua)) return "android";
  if (hint === "ios" || /iPhone|iPad/.test(ua)) return ipad ? "ipad" : "iphone";
  if (ipad) return "ipad";
  if (hint === "windows" || /Windows/i.test(ua)) return "windows";
  if (hint === "macos" || hint === "mac" || /Macintosh|Mac OS X/.test(ua)) return "mac";
  return "unknown";
}

type UserAgentData = {
  platform?: string;
  mobile?: boolean;
  getHighEntropyValues?: (hints: string[]) => Promise<{ platform?: string; mobile?: boolean }>;
};

export async function resolveInstallDevice(): Promise<InstallDevice | "unknown"> {
  const nav = navigator as Navigator & { userAgentData?: UserAgentData };
  const data = nav.userAgentData;
  let clientHintPlatform = data?.platform;
  let clientHintMobile = data?.mobile;
  if (data?.getHighEntropyValues) {
    try {
      const high = await data.getHighEntropyValues(["platform"]);
      clientHintPlatform = high.platform || clientHintPlatform;
      if (typeof high.mobile === "boolean") clientHintMobile = high.mobile;
    } catch {
      // The low-entropy platform is enough when the high-entropy call is blocked.
    }
  }
  return detectInstallDevice({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    maxTouchPoints: navigator.maxTouchPoints,
    clientHintPlatform,
    clientHintMobile,
  });
}
