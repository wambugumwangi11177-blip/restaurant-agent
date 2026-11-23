"use client";

export type ApprovalFeedItem = {
  kind: string;
  id: number;
  approval_card_title?: string;
  approval_card_subtitle?: string;
  approval_viewer_is_actor?: boolean;
  approval_waiting_on?: string | null;
  status?: string;
};

export default function ApprovalCard({ item }: { item: ApprovalFeedItem }) {
  if (!item.approval_card_title) return null;
  const primary = item.approval_viewer_is_actor;
  return (
    <article
      className={`owner-oat-highlight rounded-2xl p-4 ${primary ? "ring-1 ring-[var(--accent)]/35" : ""}`}
      data-kind={item.kind}
      data-id={item.id}
    >
      <p className={`text-sm font-medium ${primary ? "text-[var(--accent)]" : "text-[var(--text-muted)]"}`}>
        {item.approval_card_title}
      </p>
      {item.approval_card_subtitle && (
        <p className="mt-1 text-[0.9375rem] leading-6 text-[var(--text)]">{item.approval_card_subtitle}</p>
      )}
      {!primary && item.approval_waiting_on && (
        <p className="mt-2 text-xs text-zinc-400">You will be told when it is decided.</p>
      )}
    </article>
  );
}