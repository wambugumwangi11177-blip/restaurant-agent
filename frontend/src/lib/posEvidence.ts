export type PosSourceStatus = {
  durable_inbox_enabled: boolean;
  source_bound: boolean;
  receipts: number;
  by_status: Partial<Record<"pending" | "failed" | "unrecognized" | "parsed", number>>;
  last_receipt_at: string | null;
  last_successful_parse_at: string | null;
  backlog: number;
  completeness: "not_checked";
  sales_live: null;
  why: string;
  legacy_receipts: string;
};

export type PosReceipt = {
  id: string;
  received_at: string;
  status: "pending" | "failed" | "unrecognized" | "parsed";
  parser_version: string | null;
  attempts: number;
  last_attempt_at: string | null;
  parsed_at: string | null;
  error_code: string | null;
  payload_sha256: string;
};

export type PosReplay = {
  receipt_id: string;
  parse_status: PosReceipt["status"];
  orders_inserted: number;
  orders_updated: number;
  already_parsed?: boolean;
};
