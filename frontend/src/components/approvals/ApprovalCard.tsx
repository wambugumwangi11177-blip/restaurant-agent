"use client";

export type ApprovalFeedItem = {
  kind: string;
  id: number;
  approval_card_title?: string;
  approval_card_subtitle?: string;
  approval_detail_bullets?: string[];
  approval_viewer_is_actor?: boolean;
  approval_waiting_on?: string | null;
  status?: string;
  photo_path?: string | null;
};

export default function ApprovalCard({ item }: { item: ApprovalFeedItem }) {
  if (!item.approval_card_title) return null;
  const primary = item.approval_viewer_is_actor;
  const bullets = item.approval_detail_bullets?.length
    ? item.approval_detail_bullets
    : item.approval_card_subtitle
      ? [item.approval_card_subtitle]
      : [];
  return (
    <article
      className={`owner-oat-highlight rounded-2xl p-4 ${primary ? "ring-1 ring-[var(--accent)]/35" : ""}`}
      data-kind={item.kind}
      data-id={item.id}
    >
      <p className={`text-sm font-medium ${primary ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`}>
        {item.approval_card_title}
      </p>
      {item.photo_path && (
        <img
          src={item.photo_path}
          alt=""
          className="mt-2 h-16 w-16 rounded-lg object-cover ring-1 ring-white/10"
        />
      )}
      <ul className="mt-2 space-y-1 text-[0.9375rem] leading-6 text-[var(--text)]">
        {bullets.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {!primary && item.approval_waiting_on && (
        <p className="mt-2 text-xs text-zinc-400">You will be told when it is decided.</p>
      )}
    </article>
  );
}