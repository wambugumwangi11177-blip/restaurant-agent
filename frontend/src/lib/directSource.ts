export type SourceConnection = {
  source?: string;
  state?: string;
  records?: number | null;
  last_received_at?: string | null;
  reconciled?: boolean;
};

/** Demo Restaurant's data is recorded here directly (backend state "direct"):
 * there is no MacSoft delivery or API push to wait for before showing it. */
export function isDirectSource(connection?: SourceConnection | null): boolean {
  return connection?.state === "direct";
}
