import api from "@/lib/api";
import type { PosSourceStatus } from "@/lib/posEvidence";

/** True when the QuickSell POS webhook has delivered at least one receipt. */
export async function posHasLiveData(): Promise<boolean> {
  try {
    const response = await api.get<PosSourceStatus>("/api/v1/pos/quicksell/status", { timeout: 12000 });
    const data = response.data;
    return Boolean(data.source_bound && data.receipts > 0);
  } catch {
    return false;
  }
}