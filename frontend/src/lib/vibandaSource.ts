export type VibandaSourceConnection = {
  state?: string;
  reconciled?: boolean;
};

/** Live owner metrics are allowed only after delivery and a clean reconcile. */
export function isVerifiedVibandaSource(connection?: VibandaSourceConnection | null): boolean {
  return connection?.state === "receiving" && connection.reconciled === true;
}
