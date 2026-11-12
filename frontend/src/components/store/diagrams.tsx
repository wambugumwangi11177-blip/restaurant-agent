/** Inline diagrams for the storekeeper. They explain a step; they are not buttons. */

export function AccountDiagram() {
  return (
    <svg viewBox="0 0 320 120" role="img" aria-label="Temporary password becomes your own password and a 4-digit PIN" className="w-full">
      <rect x="8" y="18" width="86" height="84" rx="16" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.2)" />
      <text x="51" y="52" textAnchor="middle" fill="#f4f4f5" fontSize="12">Given</text>
      <text x="51" y="72" textAnchor="middle" fill="#a1a1aa" fontSize="11">password</text>
      <path d="M104 60 H132" stroke="#f4f4f5" strokeWidth="1.5" />
      <path d="M126 54 L136 60 L126 66" fill="none" stroke="#f4f4f5" strokeWidth="1.5" />
      <rect x="142" y="18" width="86" height="84" rx="16" fill="rgba(255,255,255,0.14)" stroke="rgba(255,255,255,0.35)" />
      <text x="185" y="52" textAnchor="middle" fill="#f4f4f5" fontSize="12">Your</text>
      <text x="185" y="72" textAnchor="middle" fill="#a1a1aa" fontSize="11">password</text>
      <path d="M238 60 H266" stroke="#f4f4f5" strokeWidth="1.5" />
      <path d="M260 54 L270 60 L260 66" fill="none" stroke="#f4f4f5" strokeWidth="1.5" />
      <rect x="276" y="28" width="36" height="64" rx="10" fill="#f4f4f5" />
      <text x="294" y="66" textAnchor="middle" fill="#111" fontSize="13" fontWeight="700">••••</text>
    </svg>
  );
}

export function RecipeDiagram() {
  return (
    <svg viewBox="0 0 320 132" role="img" aria-label="A dish breaks into an ingredient with quantity, unit, and yield" className="w-full">
      <rect x="8" y="36" width="78" height="60" rx="16" fill="rgba(255,255,255,0.14)" stroke="rgba(255,255,255,0.3)" />
      <text x="47" y="70" textAnchor="middle" fill="#f4f4f5" fontSize="13">Dish</text>
      <path d="M92 66 H118" stroke="#f4f4f5" strokeWidth="1.5" />
      <path d="M112 60 L122 66 L112 72" fill="none" stroke="#f4f4f5" strokeWidth="1.5" />
      <rect x="128" y="16" width="184" height="100" rx="16" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.2)" />
      <text x="220" y="40" textAnchor="middle" fill="#f4f4f5" fontSize="13">Ingredient</text>
      <text x="220" y="64" textAnchor="middle" fill="#a1a1aa" fontSize="12">quantity · unit</text>
      <text x="220" y="88" textAnchor="middle" fill="#a1a1aa" fontSize="12">yield after prep</text>
    </svg>
  );
}

export function CustodyDiagram() {
  return (
    <svg viewBox="0 0 320 148" role="img" aria-label="Supplier delivery is photographed twice, then quantities are keyed, then the photos stay private" className="w-full">
      <g fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.4">
        <rect x="8" y="16" width="68" height="52" rx="12" />
        <rect x="88" y="16" width="68" height="52" rx="12" />
        <rect x="168" y="16" width="68" height="52" rx="12" />
        <rect x="248" y="16" width="64" height="52" rx="12" />
      </g>
      <text x="42" y="46" textAnchor="middle" fill="#f4f4f5" fontSize="11">Invoice</text>
      <text x="122" y="46" textAnchor="middle" fill="#f4f4f5" fontSize="11">Goods</text>
      <text x="202" y="40" textAnchor="middle" fill="#f4f4f5" fontSize="11">You key</text>
      <text x="202" y="56" textAnchor="middle" fill="#a1a1aa" fontSize="10">quantities</text>
      <text x="280" y="46" textAnchor="middle" fill="#f4f4f5" fontSize="11">Private</text>
      <path d="M42 78 V98 H280 V78" fill="none" stroke="rgba(255,255,255,0.25)" />
      <text x="160" y="124" textAnchor="middle" fill="#a1a1aa" fontSize="12">Photos stay as evidence. Prices stay with the owner.</text>
    </svg>
  );
}

export function OfflineMark() {
  return (
    <svg viewBox="0 0 120 80" role="img" aria-label="A cloud with a break in the connection" className="mx-auto h-16 w-24">
      <path d="M28 52h56a16 16 0 0 0 0-32 22 22 0 0 0-42-4A14 14 0 0 0 28 52z" fill="none" stroke="#f4f4f5" strokeWidth="2" />
      <path d="M46 58 H74" stroke="#f4f4f5" strokeWidth="2" strokeDasharray="4 4" />
    </svg>
  );
}
