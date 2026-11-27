import type { ReactNode } from "react";

function Phone({ label, children }: { label: string; children: ReactNode }) {
  return (
    <svg viewBox="0 0 160 210" className="mx-auto h-36 w-auto" role="img" aria-label={label}>
      <rect x="10" y="6" width="140" height="198" rx="22" fill="#0d0d0f" stroke="rgba(255,255,255,0.45)" strokeWidth="2" />
      <rect x="60" y="14" width="40" height="6" rx="3" fill="rgba(255,255,255,0.35)" />
      {children}
    </svg>
  );
}

export function DownloadArt() {
  return (
    <Phone label="A phone with a download button">
      <rect x="32" y="78" width="96" height="28" rx="14" fill="#ffffff" />
      <text x="80" y="97" textAnchor="middle" fontSize="11" fill="#111111" fontFamily="sans-serif">Download</text>
      <path d="M80 48 v22 M72 62 l8 8 8-8" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
    </Phone>
  );
}

export function AllowSourceArt() {
  return (
    <Phone label="A settings switch turned on for installs from this source">
      <text x="28" y="70" fontSize="11" fill="#f4f4f5" fontFamily="sans-serif">Allow from</text>
      <text x="28" y="86" fontSize="11" fill="#f4f4f5" fontFamily="sans-serif">this source</text>
      <rect x="28" y="108" width="104" height="36" rx="18" fill="#ffffff" />
      <circle cx="110" cy="126" r="12" fill="#111111" />
    </Phone>
  );
}

export function InstallArt() {
  return (
    <Phone label="An install button on the phone">
      <rect x="36" y="88" width="88" height="28" rx="14" fill="#ffffff" />
      <text x="80" y="107" textAnchor="middle" fontSize="12" fill="#111111" fontFamily="sans-serif">Install</text>
    </Phone>
  );
}

export function ShareArt() {
  return (
    <Phone label="The Safari share button, a square with an arrow">
      <rect x="58" y="78" width="44" height="36" rx="4" fill="none" stroke="#ffffff" strokeWidth="3" />
      <path d="M80 108 V70 M70 80 l10-12 10 12" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </Phone>
  );
}

export function HomeScreenArt() {
  return (
    <Phone label="An Add to Home Screen row">
      <rect x="28" y="70" width="104" height="36" rx="10" fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.4)" />
      <rect x="38" y="80" width="16" height="16" rx="4" fill="#ffffff" />
      <text x="62" y="93" fontSize="10" fill="#f4f4f5" fontFamily="sans-serif">Add to Home</text>
    </Phone>
  );
}

export function FullScreenArt() {
  return (
    <Phone label="The app filling the phone screen with no browser bar">
      <rect x="24" y="36" width="112" height="140" rx="12" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.35)" />
      <text x="80" y="110" textAnchor="middle" fontSize="12" fill="#f4f4f5" fontFamily="sans-serif">LEVIII</text>
    </Phone>
  );
}

export function SignInArt() {
  return (
    <Phone label="A sign-in screen">
      <rect x="32" y="64" width="96" height="18" rx="6" fill="rgba(255,255,255,0.16)" />
      <rect x="32" y="90" width="96" height="18" rx="6" fill="rgba(255,255,255,0.16)" />
      <rect x="32" y="122" width="96" height="24" rx="12" fill="#ffffff" />
      <text x="80" y="138" textAnchor="middle" fontSize="11" fill="#111111" fontFamily="sans-serif">Sign in</text>
    </Phone>
  );
}

export function StepsArt() {
  return (
    <Phone label="Three setup steps on the home screen">
      <rect x="32" y="58" width="96" height="16" rx="8" fill="rgba(255,255,255,0.2)" />
      <rect x="32" y="84" width="96" height="16" rx="8" fill="rgba(255,255,255,0.2)" />
      <rect x="32" y="110" width="96" height="16" rx="8" fill="rgba(255,255,255,0.2)" />
    </Phone>
  );
}

export function SoonArt() {
  return (
    <svg viewBox="0 0 220 140" className="mx-auto h-32 w-auto" role="img" aria-label="A laptop with no installer yet">
      <rect x="28" y="18" width="164" height="96" rx="8" fill="#0d0d0f" stroke="rgba(255,255,255,0.45)" strokeWidth="2" />
      <path d="M16 118 h188 l-14 12 H30 Z" fill="rgba(255,255,255,0.2)" />
      <text x="110" y="72" textAnchor="middle" fontSize="14" fill="#f4f4f5" fontFamily="sans-serif">Coming soon</text>
    </svg>
  );
}
